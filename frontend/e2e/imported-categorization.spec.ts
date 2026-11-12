import { expect, test } from "@playwright/test";
import { account, fixtures, transaction } from "./fixtures";

test("reviewed imported expense category changes without editing payment, while loan stays protected", async ({
  page,
}, info) => {
  const base = await fixtures(page);
  const categories = [
    {
      id: "food",
      name: "Zakupy",
      parent_id: null,
      type: "expense",
      is_active: true,
    },
    {
      id: "home",
      name: "Dom",
      parent_id: null,
      type: "expense",
      is_active: true,
    },
    {
      id: "repairs",
      name: "Naprawy",
      parent_id: "home",
      type: "expense",
      is_active: true,
    },
  ];
  const bank = { ...account, currency: "PLN" };
  const payment = {
    ...transaction.postings[0],
    source_currency: "PLN",
    source_amount: 10000,
    base_amount_pln: 10000,
    fx_rate: 1,
    direction: "debit",
  };
  let parts = [{ category_id: "food", amount_minor: 10000 }],
    version = 0;
  const current = () => ({
    ...transaction,
    source: "actual",
    description: "[actual:old] Historyczny zakup",
    postings: [
      payment,
      ...parts.map((p) => ({
        ...payment,
        id: "category",
        account_id: null,
        category_id: p.category_id,
        source_amount: p.amount_minor,
        base_amount_pln: p.amount_minor,
        direction: "credit",
      })),
    ],
  });
  const loan = {
    ...current(),
    id: "loan",
    source: "loan_payment",
    description: "Płatność pożyczki",
  };
  const context = () => ({
    transaction_id: transaction.id,
    eligibility: { allowed: true },
    amount_minor: 10000,
    currency: "PLN",
    parts,
    version,
    source: version ? "manual" : null,
    context_snapshot: "a".repeat(64),
    max_parts: 50,
  });
  const writes: {
    path: string;
    body: Record<string, unknown>;
    key?: string;
  }[] = [];
  await page.route("**/api/finance/**", async (route) => {
    const path = new URL(route.request().url()).pathname,
      method = route.request().method();
    if (method === "GET") {
      if (path.endsWith("/transactions/loan/categorization"))
        return route.fulfill({
          json: {
            ...context(),
            transaction_id: "loan",
            eligibility: {
              allowed: false,
              reason_code: "protected_loan",
              message: "Płatność pożyczki jest chroniona.",
            },
            parts: [],
          },
        });
      if (path.endsWith("/categorization"))
        return route.fulfill({ json: context() });
      if (path === "/api/finance/categories")
        return route.fulfill({ json: categories });
      if (path === "/api/finance/accounts")
        return route.fulfill({ json: [bank] });
      if (path === "/api/finance/transactions/search")
        return route.fulfill({
          json: { items: [current(), loan], total: 2, limit: 25, offset: 0 },
        });
      if (path === "/api/finance/category-summary")
        return route.fulfill({
          json: {
            month: 2,
            year: 2026,
            groups: [],
            tree: [],
            categories: parts.map((p) => ({
              ...categories.find((c) => c.id === p.category_id),
              category_id: p.category_id,
              total_pln: p.amount_minor,
            })),
          },
        });
      return route.fallback();
    }
    const body = route.request().postDataJSON();
    writes.push({
      path,
      body,
      key: route.request().headers()["idempotency-key"],
    });
    if (path.endsWith("/categorization/preview"))
      return route.fulfill({
        json: {
          expected_version: version,
          preview_snapshot: "b".repeat(64),
          before_parts: parts,
          after_parts: body.parts,
          target_paths: { food: "Zakupy", repairs: "Dom / Naprawy" },
        },
      });
    if (path.endsWith("/categorization/apply")) {
      parts = body.parts;
      version++;
      return route.fulfill({ json: context() });
    }
    return route.fallback();
  });
  await page.goto("/finances/transactions");
  await page
    .getByRole("button", { name: "Zmień kategorie", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog", { name: "Kategorie wydatku" });
  await dialog
    .getByLabel("Kategoria 1", { exact: true })
    .selectOption("repairs");
  await expect(dialog.getByLabel("Kwota PLN 1", { exact: true })).toHaveValue(
    "100.00",
  );
  expect(writes).toEqual([]);
  await dialog.getByRole("button", { name: "Sprawdź podział" }).click();
  await expect(dialog.getByText("Dom / Naprawy").first()).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("imported-category-preview.png"),
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Zatwierdź podział" }).click();
  await expect(dialog).toHaveCount(0);
  expect(writes[1].key).toBeTruthy();
  expect(writes[1].body).toEqual({
    expected_version: 0,
    expected_preview_snapshot: "b".repeat(64),
    parts: [{ category_id: "repairs", amount_minor: 10000 }],
    confirmed: true,
  });
  expect(payment.id).toBe("p1");
  await page
    .getByRole("button", { name: "Zmień kategorie", exact: true })
    .nth(1)
    .click();
  await expect(
    dialog.getByText("Płatność pożyczki jest chroniona."),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Sprawdź podział" }),
  ).toHaveCount(0);
  await dialog.getByRole("button", { name: "Zamknij", exact: true }).click();
  await page.goto("/finances/reports?month=2&year=2026");
  await expect(
    page.getByText("100,00 PLN", { exact: true }).first(),
  ).toBeVisible();
  expect(writes).toHaveLength(2);
  base.assertClean();
});
