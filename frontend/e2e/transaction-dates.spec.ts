import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures, account } from "./fixtures";

async function dateFixture(page: Page) {
  const base = await fixtures(page);
  const writes: { path: string; data: Record<string, unknown> }[] = [];
  let current: Record<string, unknown> | null = null;
  const bank = {
    ...account,
    name: "Synthetic bank",
    currency: "PLN",
    balance_pln: 0,
  };
  const category = {
    id: "food",
    name: "Spożywka",
    parent_id: null,
    type: "expense",
    is_active: true,
  };
  await page.route("**/api/finance/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname,
      method = route.request().method();
    if (method === "POST" && path === "/api/finance/transactions") {
      const data = route.request().postDataJSON();
      writes.push({ path, data });
      current = {
        ...data,
        id: "synthetic-date-txn",
        source: "manual",
        transaction_date: data.booking_date,
        updated_at: "2026-11-03T12:00:00Z",
        is_pending: false,
        project_id: null,
        date_metadata: {
          purchase_date: data.purchase_date,
          booking_date: data.booking_date,
          purchase_date_source: "manual",
          booking_date_source: "manual",
          version: 1,
        },
      };
      return route.fulfill({ status: 201, json: current });
    }
    if (
      method === "PATCH" &&
      path === "/api/finance/transactions/synthetic-date-txn/dates"
    ) {
      writes.push({ path, data: route.request().postDataJSON() });
      return route.fulfill({
        status: 409,
        json: {
          code: "date_version_conflict",
          detail:
            "Dane transakcji zmieniły się. Odśwież je i ponownie sprawdź daty.",
        },
      });
    }
    if (method !== "GET") return route.fallback();
    if (path === "/api/finance/accounts")
      return route.fulfill({ json: [bank] });
    if (path === "/api/finance/categories")
      return route.fulfill({ json: [category] });
    if (path === "/api/finance/transactions/search")
      return route.fulfill({
        json: {
          items: current ? [current] : [],
          total: current ? 1 : 0,
          offset: 0,
          limit: 25,
        },
      });
    if (path === "/api/finance/transactions")
      return route.fulfill({ json: current ? [current] : [] });
    if (path === "/api/finance/summary") {
      const jan = url.searchParams.get("month") === "1";
      return route.fulfill({
        json: {
          accounts: [],
          balance_all_pln: current ? -10000 : 0,
          balance_budget_pln: current ? -10000 : 0,
          income_total_pln: 0,
          expense_total_pln: current && jan ? 10000 : 0,
          net_total_pln: current && jan ? -10000 : 0,
          month: jan ? 1 : 2,
          year: 2026,
        },
      });
    }
    if (path === "/api/finance/transactions/synthetic-date-txn")
      return route.fulfill({ json: current });
    return route.fallback();
  });
  return { base, writes };
}

test("purchase and booking dates are explicit, reports explain month basis and conflicts retain review", async ({
  page,
}, testInfo) => {
  const api = await dateFixture(page);
  await page.goto("/finances/transactions?create=expense");
  const create = page.getByRole("dialog", {
    name: "Dodaj transakcję",
    exact: true,
  });
  await create.getByLabel("Konto", { exact: true }).selectOption(account.id);
  await create.getByLabel("Kategoria", { exact: true }).selectOption("food");
  await create.getByLabel("Kwota (PLN)").fill("100");
  await create.getByLabel("Opis", { exact: true }).fill("Synthetic purchase");
  await create.getByLabel("Data zakupu", { exact: true }).fill("2026-01-30");
  await create.getByLabel("Księgowanie w dniu zakupu").uncheck();
  await create
    .getByLabel("Data księgowania", { exact: true })
    .fill("2026-02-02");
  await create.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(create).toHaveCount(0);
  await expect(page.getByText("Zakup: 30.01.2026")).toBeVisible();
  await expect(page.getByText("Księgowanie: 2.02.2026")).toBeVisible();
  expect(api.writes[0].data).toMatchObject({
    purchase_date: "2026-01-30",
    booking_date: "2026-02-02",
  });
  expect(api.writes[0].data).not.toHaveProperty("transaction_date");
  await page.getByRole("button", { name: "Koryguj daty" }).click();
  const correction = page.getByRole("dialog", {
    name: "Daty zakupu i księgowania",
    exact: true,
  });
  await correction
    .getByLabel("Data zakupu", { exact: true })
    .fill("2026-01-29");
  await correction.getByRole("button", { name: "Zapisz daty" }).click();
  await expect(correction.getByRole("alert")).toContainText("Odśwież");
  await expect(
    correction.getByLabel("Data zakupu", { exact: true }),
  ).toHaveValue("2026-01-29");
  await expect(
    correction.getByRole("button", { name: "Zapisz daty" }),
  ).toBeDisabled();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await correction.getByRole("button", { name: "Zamknij i odśwież" }).click();
  await page.goto("/finances/reports?month=1&year=2026");
  await expect(
    page.getByText(/Wydatki i budżety według daty zakupu/),
  ).toBeVisible();
  await expect(page.getByText("100,00 PLN", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("purchase-month.png"),
    fullPage: true,
  });
  expect(api.writes).toHaveLength(2);
  api.base.assertClean();
});
