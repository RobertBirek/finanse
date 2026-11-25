import { type Page } from "@playwright/test";

export async function openTransactionEditor(page: Page, index = 0) {
  await page
    .getByRole("button", { name: /^Więcej: / })
    .nth(index)
    .click();
  await page
    .getByRole("button", { name: "Edytuj transakcję", exact: true })
    .click();
  return page.getByRole("dialog", { name: "Edytuj transakcję", exact: true });
}

export async function openTransactionSplit(page: Page, index = 0) {
  const editor = await openTransactionEditor(page, index);
  await editor
    .getByRole("button", { name: "Edytuj podział kategorii", exact: true })
    .click();
  return page.getByRole("dialog", { name: "Kategorie wydatku", exact: true });
}

export function protectedEditorFixture(transaction: object) {
  return {
    transaction: { updated_at: "2026-11-24T12:00:00Z", ...transaction },
    ledger_editable: false,
    ledger_lock_reason: "Zapis księgowy jest chroniony.",
  };
}
