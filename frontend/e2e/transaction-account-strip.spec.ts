import { expect, test } from "@playwright/test";
import { account, fixtures } from "./fixtures";

test("account tile toggles account filter and keeps the other filters", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/transactions?q=kawa&page=2");
  const tiles = page.getByRole("region", { name: "Twoje konta" });
  const tile = tiles.getByRole("button", { name: new RegExp(account.name) });
  await expect(tile).toHaveAttribute("aria-pressed", "false");
  await tile.click();
  await expect(tile).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveURL(new RegExp(`account_id=${account.id}`));
  await expect(page).toHaveURL(/q=kawa/);
  await expect(page).not.toHaveURL(/page=2/);
  await tile.click();
  await expect(tile).toHaveAttribute("aria-pressed", "false");
  await expect(page).not.toHaveURL(/account_id=/);
  api.assertClean();
});
