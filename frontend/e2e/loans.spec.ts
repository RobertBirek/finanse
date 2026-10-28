import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { loanFixtures, loanId, installmentId } from "./loan-fixtures";

for (const theme of ["light", "dark"]) {
  test(`loan partial/full coverage and unlink preserve ledger in ${theme}`, async ({
    page,
  }) => {
    const api = await loanFixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.goto("/settings/finances/loans");
    await expect(
      page.getByRole("heading", { name: "Kredyty i pożyczki" }),
    ).toBeVisible();
    await expect(page.getByText("Niepokryta", { exact: true })).toBeVisible();
    await expect(page.getByText(/Saldo księgowe nie jest/)).toBeVisible();
    await page
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    const candidate = (description: string) =>
      page.getByRole("listitem").filter({ hasText: description });
    await candidate("Pierwsza część raty")
      .getByRole("button", { name: "Wybierz" })
      .click();
    await expect(
      page.getByText("Częściowo pokryta", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Edytuj ratę", exact: true }),
    ).toHaveCount(0);
    await candidate("Druga część raty")
      .getByRole("button", { name: "Wybierz" })
      .click();
    await expect(page.getByText("Pokryta", { exact: true })).toBeVisible();
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
    await expect(
      page.getByText("Częściowo pokryta", { exact: true }),
    ).toBeVisible();
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
  await page.goto("/settings/finances/loans");
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
  await expect(page.getByText("Niepokryta", { exact: true })).toBeVisible();
  expect(api.loanMutations).toHaveLength(1);
  api.assertLoanClean();
});

test("loan list failure is not an empty agreement list", async ({ page }) => {
  const api = await loanFixtures(page, { listError: true });
  await page.goto("/settings/finances/loans");
  await expect(page.getByRole("alert")).toContainText(
    "Nie udało się pobrać umów lub kont.",
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
  await page.goto("/settings/finances/loans");
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
  await expect(
    page.getByText("Częściowo pokryta", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Poprzednie", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText(/Pierwsza część raty/)).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Odepnij", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Nie udało się odpiąć płatności.",
  );
  await expect(
    page.getByText("Częściowo pokryta", { exact: true }),
  ).toBeVisible();
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
  await expect(page.getByText("Niepokryta", { exact: true })).toBeVisible();
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
