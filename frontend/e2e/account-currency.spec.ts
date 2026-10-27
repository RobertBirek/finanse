import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { account, fixtures } from "./fixtures";

test("currency settings edit empty accounts and preserve locked history", async ({
  page,
}) => {
  const api = await fixtures(page);
  let empty = {
    ...account,
    name: "Revolut nowy",
    balance_source: 0,
    balance_pln: 0,
    can_change_currency: true,
  };
  const locked = {
    ...account,
    id: "locked",
    name: "Revolut USD",
    currency: "USD",
    balance_source: 0,
    balance_pln: 0,
    can_change_currency: false,
  };
  const patches: unknown[] = [];
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({ json: [empty, locked] }),
  );
  await page.route(`**/api/finance/accounts/${account.id}`, async (route) => {
    expect(route.request().method()).toBe("PATCH");
    const payload = route.request().postDataJSON();
    patches.push(payload);
    empty = { ...empty, ...payload };
    await route.fulfill({ json: empty });
  });
  await page.goto("/settings/finances/accounts");
  await page.getByRole("button", { name: "Edytuj konto Revolut nowy" }).click();
  const editable = page.locator('select[id^="account-edit-currency-"]');
  await expect(editable).toBeEnabled();
  await expect(editable).toHaveValue("EUR");
  await editable.selectOption("USD");
  await page.getByRole("button", { name: "Zapisz konto Revolut nowy" }).click();
  await expect(
    page.getByRole("button", { name: "Edytuj konto Revolut nowy" }),
  ).toBeVisible();
  expect(patches).toEqual([expect.objectContaining({ currency: "USD" })]);
  await page.getByRole("button", { name: "Edytuj konto Revolut USD" }).click();
  const historical = page.locator('select[id^="account-edit-currency-"]');
  await expect(historical).toBeDisabled();
  await expect(historical).toHaveValue("USD");
  await expect(page.getByText(/Walutę można zmienić tylko/i)).toBeVisible();
  await expect(page.locator("#account-edit-name")).toBeEnabled();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  expect(api.mutations).toEqual([]); // Real API is unreachable; only our fixture PATCH was handled.
  api.assertClean();
});

test("currency conflict retains the draft and explains the history lock", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({ json: [{ ...account, can_change_currency: true }] }),
  );
  await page.route(`**/api/finance/accounts/${account.id}`, (route) =>
    route.fulfill({
      status: 409,
      json: {
        detail:
          "Account currency is locked by history, schedules or import links",
      },
    }),
  );
  await page.goto("/settings/finances/accounts");
  await page.getByRole("button", { name: "Edytuj konto Eurokonto" }).click();
  await page
    .locator('select[id^="account-edit-currency-"]')
    .selectOption("USD");
  await page.getByRole("button", { name: "Zapisz konto Eurokonto" }).click();
  await expect(page.getByText(/Waluta konta jest zablokowana/i)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Anuluj edycję konta Eurokonto" }),
  ).toBeVisible();
  await expect(
    page.locator('select[id^="account-edit-currency-"]'),
  ).toHaveValue("USD");
  api.assertClean();
});
