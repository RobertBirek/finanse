import { expect, test } from "@playwright/test";
import { account, fixtures } from "./fixtures";

test("compares booked balance without navigating away until the history link is chosen", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route(
    `**/api/finance/accounts/${account.id}/balance-reconciliation`,
    async (route) => {
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toEqual({
        day: "2026-11-23",
        statement_minor: "98",
      });
      await route.fulfill({
        json: {
          day: "2026-11-23",
          currency: account.currency,
          ledger_minor: "100",
          statement_minor: "98",
          difference_minor: "-2",
        },
      });
    },
  );
  await page.goto("/finances/transactions");
  await page.getByRole("button", { name: "Uzgodnij saldo" }).click();
  const dialog = page.getByRole("dialog", { name: "Uzgodnij saldo" });
  await dialog.getByRole("combobox").selectOption(account.id);
  await dialog.getByLabel("Data końcowa wyciągu").fill("2026-11-23");
  await dialog.getByLabel(/Saldo końcowe z wyciągu/).fill("0,98");
  await dialog.getByRole("button", { name: "Porównaj salda" }).click();
  await expect(dialog.getByText(/Różnica .*−0,02/)).toBeVisible();
  await dialog.getByRole("link", { name: "Przejdź do historii konta" }).click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/account_id=.*date_to=2026-11-23/);
  api.assertClean();
});
