import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { loanFixtures, loanId, installmentId } from "./loan-fixtures";

function installmentStatus(page: Page, status: string) {
  return page
    .getByRole("article")
    .filter({ hasText: "Rata 1" })
    .getByText(status, { exact: true });
}

function tomorrow(): string {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

test("operational overview shows an upcoming active installment and retains the loan deep link", async ({
  page,
}) => {
  const api = await loanFixtures(page, { dueDate: tomorrow() });
  await page.goto(`/finances/loans?loan=${loanId}`);
  const overview = page.getByRole("region", { name: "Nadchodzące raty" });
  await expect(overview.getByText(/Kredyt testowy Q7.*rata 1/)).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Ustawienia kredytów i pożyczek" }),
  ).toHaveAttribute("href", `/settings/finances/loans?loan=${loanId}`);
  await page
    .getByRole("link", { name: "Ustawienia kredytów i pożyczek" })
    .click();
  await expect(
    page.getByRole("link", { name: "Przejdź do kredytów i pożyczek" }),
  ).toHaveAttribute("href", `/finances/loans?loan=${loanId}`);
  expect(api.loanMutations).toEqual([]);
  api.assertLoanClean();
});

test("operational overview reports a partial active-schedule error without an empty-state claim", async ({
  page,
}) => {
  const api = await loanFixtures(page, { detailError: true });
  await page.goto("/finances/loans");
  const overview = page.getByRole("region", { name: "Nadchodzące raty" });
  await expect(overview.getByRole("alert")).toContainText(
    "Widoczne pozycje mogą być niepełne",
  );
  await expect(
    overview.getByText(/Brak niepokrytych rat z terminem/),
  ).toHaveCount(0);
  expect(api.loanMutations).toEqual([]);
  api.assertLoanClean();
});

test("shows a card plan recognized from a saved statement", async ({
  page,
}) => {
  const api = await loanFixtures(page);
  await page.route("**/api/finance/loans/card-statement-plans", (route) =>
    route.fulfill({
      json: [
        {
          batch_id: "batch-card",
          source_id: "source-card",
          period_end: "2026-03-17",
          breakdown: {
            installment_original_principal_pln: 1200000,
            future_installment_principal_pln: 1125781,
            komfort_installment: {
              principal_pln: 74219,
              interest_pln: 2754,
              total_pln: 76973,
              included_in_minimum: true,
            },
          },
        },
      ],
    }),
  );
  await page.goto("/finances/loans");
  await page
    .getByRole("button", { name: /Plan „Komfort” z wyciągu Velo/ })
    .click();
  const plan = page
    .getByRole("article")
    .filter({ hasText: "Plan „Komfort” z wyciągu Velo" });
  await expect(plan).toContainText(/12\s000,00 PLN/);
  await expect(plan).toContainText(/11\s257,81 PLN/);
  await expect(plan).toContainText("769,73 PLN");
  await expect(plan).toContainText("27,54 PLN");
  await expect(
    plan.getByRole("link", { name: "Otwórz wyciąg" }),
  ).toHaveAttribute("href", "/finances/imports/batch-card");
  expect(api.loanMutations).toEqual([]);
  api.assertLoanClean();
});

test("finance navigation opens the loan overview with schedule totals", async ({
  page,
}) => {
  const api = await loanFixtures(page);
  await page.goto("/finances");
  const menu = page.getByRole("button", { name: "Otwórz menu aplikacji" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: "Kredyty i pożyczki" }).click();
  await expect(page).toHaveURL(/\/finances\/loans/);
  await expect(
    page.getByRole("heading", { name: "Kredyty i pożyczki" }),
  ).toBeVisible();
  await expect(page.getByText("Kapitał w harmonogramie")).toBeVisible();
  const tile = page
    .getByRole("region", { name: "Wybór zobowiązania" })
    .getByRole("button")
    .first();
  await tile.click();
  await expect(page).toHaveURL(new RegExp(`loan=${loanId}`));
  await page.reload();
  await expect(tile).toHaveAttribute("aria-pressed", "true");
  await page.goBack();
  await expect(page.getByText("Kapitał w harmonogramie")).toBeVisible();
  const values = page
    .locator("dl")
    .filter({ hasText: "Kapitał w harmonogramie" });
  await expect(values).toContainText("900,00 PLN");
  await expect(values).toContainText("90,00 PLN");
  await expect(values).toContainText("10,00 PLN");
  await expect(values).toContainText("Powiązane spłaty");
  await expect(
    page.getByText("Rata 1", { exact: false }).first(),
  ).toBeVisible();
  expect(api.loanMutations).toEqual([]);
  api.assertLoanClean();
});

for (const theme of ["light", "dark"]) {
  test(`loan partial/full coverage and unlink preserve ledger in ${theme}`, async ({
    page,
  }) => {
    const api = await loanFixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.goto(`/finances/loans?loan=${loanId}`);
    await expect(
      page.getByRole("heading", { name: "Kredyty i pożyczki" }),
    ).toBeVisible();
    await expect(installmentStatus(page, "Niepokryta")).toBeVisible();
    await expect(page.getByText(/Saldo księgowe nie jest/)).toBeVisible();
    await page
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    const candidate = (description: string) =>
      page.getByRole("listitem").filter({ hasText: description });
    await candidate("Pierwsza część raty")
      .getByRole("button", { name: "Wybierz" })
      .click();
    await expect(installmentStatus(page, "Częściowo pokryta")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Edytuj ratę", exact: true }),
    ).toHaveCount(0);
    await candidate("Druga część raty")
      .getByRole("button", { name: "Wybierz" })
      .click();
    await expect(installmentStatus(page, "Pokryta")).toBeVisible();
    await expect(page.getByText(/Brak kwalifikujących się/)).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Odepnij", exact: true }),
    ).toHaveCount(2);
    await page.waitForLoadState("networkidle");
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Odepnij", exact: true })
      .first()
      .click();
    await expect(installmentStatus(page, "Częściowo pokryta")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Odepnij", exact: true }),
    ).toHaveCount(1);
    expect(api.loanMutations).toEqual([
      {
        method: "POST",
        path: `/api/finance/loans/${loanId}/installments/${installmentId}/payments`,
        body: { transaction_id: "74000000-0000-0000-0000-000000000001" },
      },
      {
        method: "POST",
        path: `/api/finance/loans/${loanId}/installments/${installmentId}/payments`,
        body: { transaction_id: "74000000-0000-0000-0000-000000000002" },
      },
      {
        method: "DELETE",
        path: `/api/finance/loans/${loanId}/payments/75000000-0000-0000-0000-000000000001`,
        body: null,
      },
    ]);
    api.assertLoanClean();
  });
}

test("loan conflict retains manual transfer selection without ledger writes", async ({
  page,
}) => {
  const api = await loanFixtures(page, { conflict: true });
  await page.goto(`/finances/loans?loan=${loanId}`);
  await page
    .getByRole("button", { name: "Powiąż płatność", exact: true })
    .click();
  const input = page.getByRole("textbox", { name: "ID istniejącego przelewu" });
  await input.fill("74000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "Powiąż ID", exact: true }).click();
  await expect(
    page.getByText("Płatność jest już powiązana.", { exact: true }),
  ).toBeVisible();
  await expect(input).toHaveValue("74000000-0000-0000-0000-000000000001");
  await expect(installmentStatus(page, "Niepokryta")).toBeVisible();
  expect(api.loanMutations).toHaveLength(1);
  api.assertLoanClean();
});

test("loan list failure is not an empty agreement list", async ({ page }) => {
  const api = await loanFixtures(page, { listError: true });
  await page.goto("/settings/finances/loans");
  await expect(page.getByRole("alert")).toContainText(
    "Nie udało się pobrać umów.",
  );
  await expect(page.getByText(/Brak umów/)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Spróbuj ponownie" }),
  ).toBeVisible();
  expect(api.loanMutations).toEqual([]);
  api.assertLoanClean();
});

test("candidate link blocks repeated selection and resets the page; unlink conflict is visible", async ({
  page,
}) => {
  const api = await loanFixtures(page, {
    paginated: true,
    pauseLink: true,
    unlinkConflict: true,
  });
  await page.goto(`/finances/loans?loan=${loanId}`);
  await page
    .getByRole("button", { name: "Powiąż płatność", exact: true })
    .click();
  await page.getByRole("button", { name: "Następne", exact: true }).click();
  await expect(page.getByText(/Dodatkowa płatność 21/)).toBeVisible();
  const select = page.getByRole("button", { name: "Wybierz", exact: true });
  await expect(select).toHaveCount(1);
  await select.click();
  await expect(select).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Powiąż ID", exact: true }),
  ).toBeDisabled();
  api.releaseLink();
  await expect(installmentStatus(page, "Częściowo pokryta")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Poprzednie", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText(/Pierwsza część raty/)).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Odepnij", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Nie udało się odpiąć płatności.",
  );
  await expect(installmentStatus(page, "Częściowo pokryta")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Odepnij", exact: true }),
  ).toBeVisible();
  expect(api.loanMutations).toHaveLength(2);
  api.assertLoanClean();
});

test("installment form sends exact components and resets after metadata-only creation", async ({
  page,
}) => {
  const api = await loanFixtures(page, { emptySchedule: true });
  await page.goto("/settings/finances/loans");
  await expect(page.getByText(/Brak rat. To nie oznacza/)).toBeVisible();
  await page.getByText("Dodaj ratę ręcznie", { exact: true }).click();
  const form = page.getByRole("form", { name: "Nowa rata" });
  const submit = form.getByRole("button", { name: "Dodaj ratę", exact: true });
  await form.getByLabel("Numer", { exact: true }).fill("1");
  await form.getByLabel("Termin", { exact: true }).fill("2026-10-15");
  await form.getByLabel("Kapitał (PLN)", { exact: true }).fill("900,001");
  await expect(submit).toBeDisabled();
  await form.getByLabel("Kapitał (PLN)", { exact: true }).fill("900,00");
  await form.getByLabel("Odsetki (PLN)", { exact: true }).fill("90,00");
  await form.getByLabel("Opłaty (PLN)", { exact: true }).fill("10,00");
  await expect(
    form.getByText("Suma planu: 1000.00 PLN", { exact: true }),
  ).toBeVisible();
  await submit.click();
  await expect(installmentStatus(page, "Niepokryta")).toBeVisible();
  await expect(form.getByLabel("Numer", { exact: true })).toHaveValue("");
  await expect(submit).toBeDisabled();
  expect(api.loanMutations).toEqual([
    {
      method: "POST",
      path: `/api/finance/loans/${loanId}/installments`,
      body: {
        number: 1,
        due_date: "2026-10-15",
        principal_pln: 90000,
        interest_pln: 9000,
        fees_pln: 1000,
      },
    },
  ]);
  api.assertLoanClean();
});

test("switches between a card plan and Allegro Pay when agreements cannot load", async ({
  page,
}) => {
  await loanFixtures(page, { listError: true });
  await page.route("**/api/finance/credit-cards", (route) =>
    route.fulfill({
      json: [{ account_id: "card-a", name: "Karta testowa", configured: true }],
    }),
  );
  await page.route("**/api/finance/accounts/card-a/credit-card", (route) =>
    route.fulfill({
      json: {
        plans: [
          {
            id: "plan-a",
            name: "Plan karty A",
            status: "active",
            apr: "0",
            version: 1,
            principal_pln: 20000,
            remaining_principal_pln: 15000,
            schedule_kind: "bank",
            installments: [],
          },
        ],
        allocations: [
          { id: "allocation-a", plan_id: "plan-a", amount_pln: 5000 },
          { id: "allocation-b", plan_id: "plan-b", amount_pln: 6000 },
        ],
      },
    }),
  );
  await page.route("**/api/finance/allegro-pay", (route) =>
    route.fulfill({
      json: [
        {
          id: "allegro-a",
          account_name: "Allegro testowe",
          ledger_balance_pln: 0,
          limit_pln: null,
          available_pln: null,
          scheduled_remaining_pln: 0,
          scheduled_costs_pln: 0,
          purchases: [],
        },
      ],
    }),
  );
  await page.goto("/finances/loans?month=2");
  const strip = page.getByRole("region", { name: "Wybór zobowiązania" });
  await expect(strip.getByRole("alert")).toContainText("umów");
  await strip.getByRole("button", { name: /Plan karty A/ }).click();
  await expect(page.getByText("Spłata planu: 50,00 PLN")).toBeVisible();
  await expect(page.getByText("Spłata planu: 60,00 PLN")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Uzgodnij harmonogram z bankiem" }),
  ).toHaveCount(0);
  await strip.getByRole("button", { name: /Allegro testowe/ }).click();
  await expect(page).toHaveURL(/month=2&allegro=allegro-a/);
  await expect(
    page.getByRole("form", { name: "Zakupy i spłaty" }),
  ).toBeVisible();
  await expect(page.getByRole("form", { name: "Dodaj zakup" })).toHaveCount(0);
  await expect(page.getByText("Spłata planu: 50,00 PLN")).toHaveCount(0);
});
