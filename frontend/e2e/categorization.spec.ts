import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures, account, transaction } from "./fixtures";

async function categoryFixture(page: Page) {
  const base = await fixtures(page);
  const bank = { ...account, currency: "PLN" };
  const categories = [
    {
      id: "food",
      name: "Spożywka",
      type: "expense",
      parent_id: null,
      is_active: true,
    },
    {
      id: "home",
      name: "Chemia",
      type: "expense",
      parent_id: null,
      is_active: true,
    },
  ];
  let parts = [{ category_id: "food", amount_minor: 10000 }],
    version = 0;
  const writes: {
    path: string;
    body: Record<string, unknown>;
    key: string | undefined;
  }[] = [];
  const accountPosting = {
    ...transaction.postings[0],
    category_id: null,
    source_currency: "PLN",
    source_amount: 10000,
    base_amount_pln: 10000,
    fx_rate: 1,
    is_budget_impact: true,
  };
  const current = () => ({
    ...transaction,
    updated_at: "2026-11-03T12:00:00Z",
    postings: [
      accountPosting,
      ...parts.map((p, index) => ({
        ...accountPosting,
        id: `cat-${index}`,
        account_id: null,
        category_id: p.category_id,
        direction: "credit",
        source_amount: p.amount_minor,
        base_amount_pln: p.amount_minor,
      })),
    ],
  });
  const context = () => ({
    transaction_id: transaction.id,
    eligibility: { allowed: true, reason_code: null, message: null },
    amount_minor: 10000,
    currency: "PLN",
    parts,
    version,
    source: version ? "manual" : null,
    context_snapshot: "a".repeat(64),
    max_parts: 50,
  });
  await page.route("**/api/finance/**", async (route) => {
    const path = new URL(route.request().url()).pathname,
      method = route.request().method();
    if (method === "GET") {
      if (path.endsWith("/categorization"))
        return route.fulfill({ json: context() });
      if (path === "/api/finance/accounts")
        return route.fulfill({ json: [bank] });
      if (path === "/api/finance/categories")
        return route.fulfill({ json: categories });
      if (path === "/api/finance/category-summary")
        return route.fulfill({
          json: {
            month: 2,
            year: 2026,
            groups: [],
            categories: parts.map((p) => ({
              category_id: p.category_id,
              name: categories.find((c) => c.id === p.category_id)!.name,
              parent_id: null,
              total_pln: p.amount_minor,
            })),
            tree: [],
          },
        });
      if (path === "/api/finance/budget-status")
        return route.fulfill({
          json: {
            month: 2,
            year: 2026,
            total_budget_pln: 20000,
            total_spent_pln: 10000,
            remaining_pln: 10000,
            items: categories.map((c) => ({
              category_id: c.id,
              name: c.name,
              parent_id: null,
              budget_amount_pln: 10000,
              spent_pln:
                parts.find((p) => p.category_id === c.id)?.amount_minor ?? 0,
              remaining_pln:
                10000 -
                (parts.find((p) => p.category_id === c.id)?.amount_minor ?? 0),
            })),
          },
        });
      if (path === "/api/finance/transactions/search")
        return route.fulfill({
          json: { items: [current()], total: 1, limit: 25, offset: 0 },
        });
      if (path === "/api/finance/transactions")
        return route.fulfill({ json: [current()] });
      if (path === `/api/finance/transactions/${transaction.id}`)
        return route.fulfill({ json: current() });
      return route.fallback();
    }
    if (path.endsWith("/categorization/preview")) {
      const body = route.request().postDataJSON();
      writes.push({ path, body, key: undefined });
      return route.fulfill({
        json: {
          expected_version: version,
          preview_snapshot: "b".repeat(64),
          before_parts: parts,
          after_parts: body.parts,
          target_paths: { food: "Spożywka", home: "Chemia" },
        },
      });
    }
    if (path.endsWith("/categorization/apply")) {
      const body = route.request().postDataJSON();
      writes.push({
        path,
        body,
        key: route.request().headers()["idempotency-key"],
      });
      parts = body.parts;
      version++;
      return route.fulfill({ json: context() });
    }
    return route.fallback();
  });
  return { base, writes, accountPosting };
}

test("category preview and approval retain one payment and let the owner merge it back", async ({
  page,
}, testInfo) => {
  const api = await categoryFixture(page);
  await page.goto("/finances/transactions");
  await page
    .getByRole("button", { name: "Zmień kategorie", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Kategorie wydatku",
    exact: true,
  });
  await dialog.getByLabel("Kwota PLN 1", { exact: true }).fill("99.99");
  await expect(
    dialog.getByRole("button", { name: "Sprawdź podział" }),
  ).toBeDisabled();
  await dialog.getByLabel("Kwota PLN 1", { exact: true }).fill("80");
  await dialog.getByRole("button", { name: "Dodaj kategorię" }).click();
  await dialog.getByLabel("Kategoria 2", { exact: true }).selectOption("home");
  await dialog.getByLabel("Kwota PLN 2", { exact: true }).fill("20");
  expect(api.writes).toHaveLength(0);
  await dialog.getByRole("button", { name: "Sprawdź podział" }).click();
  await expect(
    dialog.getByRole("heading", { name: "Przed zmianą" }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("heading", { name: "Po zmianie" }),
  ).toBeVisible();
  expect(api.writes).toHaveLength(1);
  await expect(
    dialog.getByRole("button", { name: "Zatwierdź podział" }),
  ).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("approved-split-preview.png"),
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Zatwierdź podział" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Zmień kategorie", exact: true }),
  ).toHaveCount(1);
  expect(api.writes[1].body).toMatchObject({
    confirmed: true,
    parts: [
      { category_id: "food", amount_minor: 8000 },
      { category_id: "home", amount_minor: 2000 },
    ],
  });
  expect(api.writes[1].key).toBeTruthy();
  await page.goto("/finances/reports?month=2&year=2026");
  await expect(
    page.getByText("80,00 PLN", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("20,00 PLN", { exact: true }).first(),
  ).toBeVisible();
  await page.goto("/finances/budgets?month=2&year=2026");
  await expect(
    page.getByText("80,00 PLN", { exact: true }).first(),
  ).toBeVisible();
  await page.goto("/finances/transactions");
  await page
    .getByRole("button", { name: "Zmień kategorie", exact: true })
    .click();
  await expect(
    dialog.getByText(/Ręcznie zatwierdzony podział, wersja 1/),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Usuń część 2" }).click();
  await dialog.getByLabel("Kwota PLN 1", { exact: true }).fill("100");
  await dialog.getByRole("button", { name: "Sprawdź podział" }).click();
  await dialog.getByRole("button", { name: "Zatwierdź podział" }).click();
  await expect(dialog).toHaveCount(0);
  expect(api.writes).toHaveLength(4);
  expect(api.accountPosting.id).toBe("p1");
  api.base.assertClean();
});
