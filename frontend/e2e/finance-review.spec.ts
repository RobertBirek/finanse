import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { account, fixtures, transaction } from "./fixtures";

test("selected month survives reload, drilldown Back and finance tabs", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route("**/api/finance/category-summary?*", (route) => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: {
        month: Number(query.get("month")),
        year: Number(query.get("year")),
        groups: [],
        categories: [],
        tree: [
          {
            category_id: "home",
            name: "Dom",
            parent_id: null,
            is_active: true,
            direct_total_pln: 10000,
            total_pln: 10000,
            children: [],
          },
        ],
      },
    });
  });
  await page.goto("/finances/reports?month=9&year=2026");
  const picker = page.getByRole("group", { name: "Miesiąc raportowania" });
  const visibleMonth = (month: string) =>
    picker.getByText(month, { exact: true });
  await expect(visibleMonth("wrzesień 2026")).toBeVisible();
  await picker.getByRole("button", { name: "Poprzedni miesiąc" }).click();
  await expect(visibleMonth("sierpień 2026")).toBeVisible();
  await page.reload();
  await expect(visibleMonth("sierpień 2026")).toBeVisible();
  await page.getByRole("link", { name: "Dom", exact: true }).click();
  await expect(page).toHaveURL(/date_from=2026-08-01/);
  await expect
    .poll(() => api.searches.at(-1)?.get("date_basis"))
    .toBe("purchase");
  await expect(page.getByText(/według daty zakupu/i)).toBeVisible();
  await page.goBack();
  await expect(visibleMonth("sierpień 2026")).toBeVisible();
  for (const label of ["Budżet", "Przegląd", "Raporty"]) {
    const tabs = page.getByRole("navigation", { name: "Widoki finansów" });
    const link = tabs.getByRole("link", { name: label, exact: true });
    const more = tabs.getByRole("button", { name: "Więcej" });
    if (label === "Raporty" && (await more.isVisible())) {
      await more.click();
    }
    await link.click();
    await expect(visibleMonth("sierpień 2026")).toBeVisible();
  }
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("overview actions remain available while the monthly summary fails", async ({
  page,
}) => {
  const api = await fixtures(page, { todayError: true });
  await page.goto("/finances?month=9&year=2026");
  await expect(page.getByText("Nie udało się pobrać salda.")).toBeVisible();
  await page.getByRole("button", { name: "Wydatek", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Dodaj transakcję" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/month=9&year=2026&create=expense/);
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("overview prioritizes exceeded limits and explains the forecast and account movements", async ({
  page,
}) => {
  const api = await fixtures(page);
  const budget = (name: string, spent: number, limit: number) => ({
    category_id: name,
    name,
    spent_pln: spent,
    budget_amount_pln: limit,
    remaining_pln: limit - spent,
  });
  await page.route("**/api/finance/budget-status?*", (route) =>
    route.fulfill({
      json: {
        items: [
          budget("Auta", 300, 1000),
          budget("Dom", 1100, 1000),
          budget("Prąd", 2000, 1000),
          budget("Ubrania", 800, 1000),
        ],
        remaining_pln: -200,
      },
    }),
  );
  await page.route("**/api/finance/cashflow/forecast", (route) =>
    route.fulfill({
      json: {
        next_payday: "2026-11-28",
        projected_balance_before_next_payday_pln: 76000,
        safe_daily_limit_pln: 0,
        lowest_balance_before_payday: {
          date: "2026-11-21",
          projected_balance_pln: -5000,
        },
        days: [
          { date: "2026-11-20", projected_balance_pln: 100000 },
          { date: "2026-11-21", projected_balance_pln: -5000 },
          { date: "2026-11-27", projected_balance_pln: 76000 },
          { date: "2026-11-29", projected_balance_pln: 120000 },
        ],
      },
    }),
  );
  const pln = {
    ...transaction.postings[0],
    account_id: "konto-pln",
    source_currency: "PLN",
    source_amount: 11000,
  };
  const eur = { ...transaction.postings[0], source_amount: 2500 };
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({
      json: [
        account,
        { ...account, id: pln.account_id, name: "Konto PLN", currency: "PLN" },
      ],
    }),
  );
  await page.route("**/api/finance/transactions?limit=5", (route) =>
    route.fulfill({
      json: [
        {
          ...transaction,
          description: "Wymiana na EUR",
          type: "exchange",
          postings: [
            { ...eur, direction: "credit" },
            { ...pln, direction: "debit" },
          ],
        },
        {
          ...transaction,
          id: "transfer",
          description: "Wymiana na PLN",
          type: "exchange",
          postings: [
            { ...pln, direction: "credit" },
            { ...eur, direction: "debit" },
          ],
        },
      ],
    }),
  );
  await page.goto("/finances?month=11&year=2026");
  await expect(
    page.locator(".finance-budget-preview > span:first-child"),
  ).toHaveText(["Prąd", "Dom", "Ubrania"]);
  await expect(page.getByText("Przekroczono o 10,00 PLN")).toBeVisible();
  const chart = page.locator(".finance-forecast-chart");
  await expect(chart.getByText("27.11.2026")).toBeVisible();
  await expect(chart.getByText("29.11.2026")).toHaveCount(0);
  await expect(
    page.getByText("Najniższe saldo do wypłaty", { exact: false }),
  ).toContainText("-50,00 PLN · 21.11.2026");
  await expect(
    page.getByRole("link", { name: /Wymiana na EUR/ }),
  ).toContainText("Konto PLN → Eurokonto");
  await expect(
    page.getByRole("link", { name: /Wymiana na EUR/ }),
  ).toContainText("−110,00 PLN → +25,00 EUR");
  await expect(
    page.getByRole("link", { name: /Wymiana na PLN/ }),
  ).toContainText("−25,00 EUR → +110,00 PLN");
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("mobile finance navigation works with the keyboard and keeps long balances inside the card", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.setViewportSize({ width: 320, height: 850 });
  await page.route("**/api/finance/summary?*", (route) =>
    route.fulfill({
      json: {
        balance_all_pln: 999999999999999,
        balance_budget_pln: 123,
        income_total_pln: 999999999999999,
        expense_total_pln: 1,
      },
    }),
  );
  await page.goto("/finances?month=9&year=2026");
  const balance = page.getByLabel("Saldo aktywnych kont");
  await expect(balance).toBeVisible();
  expect(
    await balance.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  const tabs = page.getByRole("navigation", { name: "Widoki finansów" });
  const more = tabs.getByRole("button", { name: "Więcej" });
  const people = tabs.getByRole("link", { name: "Osoby" });
  await expect(people).toBeHidden();
  await more.focus();
  await page.keyboard.press("Enter");
  await expect(more).toHaveAttribute("aria-expanded", "true");
  await expect(people).toBeVisible();
  await people.focus();
  await page.keyboard.press("Escape");
  await expect(more).toBeFocused();
  await expect(people).toBeHidden();
  await page.getByRole("button", { name: "Budżetowe" }).click();
  await expect(page.getByLabel("Saldo kont budżetowych")).toContainText(
    "1,23 PLN",
  );
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

for (const theme of ["light", "dark"]) {
  test(`archived account contrast in ${theme} theme`, async ({ page }) => {
    const api = await fixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.route("**/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          { ...account, balance_source: 12345 },
          {
            ...account,
            id: "archived",
            name: "Archiwalne konto",
            is_active: false,
            balance_source: 0,
            iban: "DE89370400440532013000",
          },
        ],
      }),
    );
    await page.goto("/settings/finances/accounts");
    await expect(
      page.getByText("Archiwalne konto", { exact: true }),
    ).toBeVisible();
    await page.waitForLoadState("networkidle");
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
    expect(api.mutations).toEqual([]);
    api.assertClean();
  });
}

for (const mode of ["success", "denied", "unavailable"] as const) {
  test(`IBAN clipboard ${mode} gives accessible feedback without errors`, async ({
    page,
  }) => {
    const api = await fixtures(page);
    await page.addInitScript((value) => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value:
          value === "unavailable"
            ? undefined
            : {
                writeText: () =>
                  value === "denied"
                    ? Promise.reject(
                        new DOMException("Denied", "NotAllowedError"),
                      )
                    : Promise.resolve(),
              },
      });
    }, mode);
    await page.route("**/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          { ...account, balance_source: 12345, iban: "DE89370400440532013000" },
        ],
      }),
    );
    await page.goto("/settings/finances/accounts");
    await page.getByRole("button", { name: "Kopiuj", exact: true }).click();
    await expect(page.getByRole("status")).toContainText(
      mode === "success" ? /skopiowan/i : /ręczni/i,
    );
    if (mode !== "success") {
      const manual = page.getByRole("textbox", {
        name: "Numer rachunku do ręcznego skopiowania",
      });
      await expect(manual).toHaveValue("DE89370400440532013000");
      await manual.focus();
      expect(
        await manual.evaluate(
          (element: HTMLInputElement) =>
            element.selectionEnd! - element.selectionStart!,
        ),
      ).toBe(22);
    }
    expect(api.mutations).toEqual([]);
    api.assertClean();
  });
}
