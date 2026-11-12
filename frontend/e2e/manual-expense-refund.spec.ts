import { expect, test } from "@playwright/test";
import { account, fixtures, transaction } from "./fixtures";
import { categorySelectFixture } from "../src/test/categoryFixtures";

test("manual partial refund posts a small command and keeps expense categories", async ({
  page,
}) => {
  const base = await fixtures(page);
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({ json: [{ ...account, currency: "PLN" }] }),
  );
  await page.route("**/api/finance/categories", (route) =>
    route.fulfill({ json: categorySelectFixture }),
  );
  const writes: unknown[] = [];
  await page.route(
    "**/api/finance/transactions/expense-refund",
    async (route) => {
      expect(route.request().method()).toBe("POST");
      const payload = route.request().postDataJSON();
      writes.push(payload);
      await route.fulfill({
        status: 201,
        json: {
          ...transaction,
          id: "refund",
          type: "expense",
          description: payload.description,
          transaction_date: payload.transaction_date,
          postings: [
            {
              ...transaction.postings[0],
              account_id: account.id,
              category_id: null,
              direction: "credit",
              source_currency: "PLN",
              source_amount: 15025,
              base_amount_pln: 15025,
            },
            {
              ...transaction.postings[0],
              account_id: null,
              category_id: "gas",
              direction: "debit",
              source_currency: "PLN",
              source_amount: 15025,
              base_amount_pln: 15025,
            },
          ],
        },
      });
    },
  );
  await page.goto("/finances/transactions?create=expense");
  const dialog = page.getByRole("dialog", { name: "Dodaj transakcję" });
  await dialog
    .getByLabel("Typ", { exact: true })
    .selectOption("expense_refund");
  await expect(dialog.getByText(/Nie jest przychodem/)).toBeVisible();
  await expect(
    dialog.getByLabel("Kategoria", { exact: true }).locator("option"),
  ).toHaveText([
    "Wybierz kategorię",
    "Auto - Zamek",
    "Dom - Gaz",
    "Dom - Woda",
  ]);
  await dialog.getByLabel("Konto", { exact: true }).selectOption(account.id);
  await dialog.getByLabel("Kategoria", { exact: true }).selectOption("gas");
  await dialog.getByLabel("Kwota (PLN)", { exact: true }).fill("150.25");
  await dialog.getByLabel("Data operacji").fill("2026-11-12");
  await dialog.getByLabel("Opis", { exact: true }).fill("Zwrot części zakupu");
  await page.screenshot({
    path: test.info().outputPath("manual-refund.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await dialog.getByRole("button", { name: "Zapisz transakcję" }).click();
  await expect(dialog).not.toBeVisible();
  expect(writes).toEqual([
    {
      account_id: account.id,
      category_id: "gas",
      amount_minor: 15025,
      transaction_date: "2026-11-12",
      description: "Zwrot części zakupu",
    },
  ]);
  expect(base.mutations).toEqual([]);
  base.assertClean();
});
