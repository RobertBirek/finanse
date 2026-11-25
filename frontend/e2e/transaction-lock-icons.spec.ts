import { expect, test } from "@playwright/test";
import { fixtures, transaction } from "./fixtures";

test("lock and source icons appear under More and reveal the reason", async ({
  page,
}) => {
  const api = await fixtures(page);
  const current = {
    ...transaction,
    ledger_editable: false,
    ledger_lock_reason: "Import bankowy",
    import_batch_id: "batch-1",
    financial_document_ids: ["bill-1"],
  };
  await page.route("**/api/finance/transactions/search*", (route) =>
    route.fulfill({
      json: { items: [current], total: 1, limit: 25, offset: 0 },
    }),
  );
  await page.goto("/finances/transactions");
  const more = page.getByRole("button", { name: /^Więcej: / });
  await expect(
    page.getByRole("button", { name: "Powód blokady edycji" }),
  ).toBeHidden();
  await more.click();
  const lock = page.getByRole("button", { name: "Powód blokady edycji" });
  await expect(lock).toHaveAttribute("aria-description", "Import bankowy");
  await lock.click();
  await expect(
    page.locator(".ui-tooltip[data-open='true']", {
      hasText: "Import bankowy",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Import bankowy" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Powiązana z fakturą" }),
  ).toBeVisible();
  api.assertClean();
});
