import { expect, test } from "@playwright/test";
import { account, fixtures, transaction } from "./fixtures";
import { openTransactionEditor } from "./transaction-editor-helpers";

test("changes a manual expense amount and dates in one request", async ({
  page,
}) => {
  const api = await fixtures(page);
  const category = {
    id: "groceries",
    name: "Spożywka",
    type: "expense",
    is_active: true,
  };
  const payment = {
    ...transaction.postings[0],
    source_currency: "PLN",
    source_amount: 10000,
    base_amount_pln: 10000,
    fx_rate: 1,
  };
  const current = {
    ...transaction,
    updated_at: "2026-11-24T12:00:00Z",
    date_metadata: {
      purchase_date: "2026-10-19",
      booking_date: "2026-10-20",
      purchase_date_source: "manual",
      booking_date_source: "manual",
      version: 1,
    },
    postings: [
      payment,
      {
        ...payment,
        id: "p2",
        account_id: null,
        category_id: category.id,
        direction: "credit",
      },
    ],
  };
  const writes: unknown[] = [];
  await page.route("**/api/finance/categories", (route) =>
    route.fulfill({ json: [category] }),
  );
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({ json: [{ ...account, currency: "PLN" }] }),
  );
  await page.route("**/api/finance/transactions/search*", (route) =>
    route.fulfill({
      json: { items: [current], total: 1, limit: 25, offset: 0 },
    }),
  );
  await page.route(
    `**/api/finance/transactions/${transaction.id}/editor`,
    (route) => {
      const response = {
        transaction: current,
        ledger_editable: true,
        ledger_lock_reason: null,
      };
      if (route.request().method() === "PUT")
        writes.push(route.request().postDataJSON());
      return route.fulfill({ json: response });
    },
  );
  await page.goto("/finances/transactions");
  const editor = await openTransactionEditor(page);
  await expect(editor.getByLabel("Konto", { exact: true })).toHaveValue(
    account.id,
  );
  await expect(
    editor.getByLabel("Data księgowania", { exact: true }),
  ).toHaveValue("2026-10-20");
  await editor
    .getByLabel("Data księgowania", { exact: true })
    .fill("2026-10-21");
  await editor.getByLabel("Kwota (PLN)", { exact: true }).fill("125,50");
  expect(writes).toHaveLength(0);
  await editor
    .getByRole("button", { name: "Zapisz zmiany", exact: true })
    .click();
  await expect(editor).toBeHidden();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({
    expected_updated_at: current.updated_at,
    expected_date_version: 1,
    ledger: {
      kind: "transaction",
      data: {
        booking_date: "2026-10-21",
        purchase_date: "2026-10-19",
        postings: [
          expect.objectContaining({
            source_amount: 12550,
            account_id: account.id,
          }),
          expect.objectContaining({
            source_amount: 12550,
            category_id: category.id,
          }),
        ],
      },
    },
  });
  api.assertClean();
});
