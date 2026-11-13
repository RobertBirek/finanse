import { expect, test } from "@playwright/test";
import { account, fixtures, transaction } from "./fixtures";

test("two gifts share a person history without creating financial writes", async ({
  page,
}, info) => {
  const base = await fixtures(page);
  const donor = {
    id: "30000000-0000-0000-0000-000000000001",
    name: "Osoba A",
    is_active: true,
    version: 1,
    reference_account_id: null,
  };
  const bank = {
    ...account,
    name: "Bank",
    currency: "PLN",
    balance_pln: 30000,
  };
  const gifts = [10000, 20000].map((amount, index) => ({
    ...transaction,
    id: `20000000-0000-0000-0000-00000000000${index + 1}`,
    description: `Darowizna ${index + 1}`,
    type: "income",
    source: "actual",
    postings: [
      {
        ...transaction.postings[0],
        id: `bank-${index}`,
        direction: "credit",
        source_currency: "PLN",
        source_amount: amount,
        base_amount_pln: amount,
        fx_rate: 1,
      },
      {
        ...transaction.postings[0],
        id: `cat-${index}`,
        account_id: null,
        category_id: "gift-category",
        direction: "debit",
        source_currency: "PLN",
        source_amount: amount,
        base_amount_pln: amount,
        fx_rate: 1,
      },
    ],
  }));
  const assigned = new Set<string>();
  const writes: {
    method: string;
    path: string;
    body: Record<string, unknown>;
  }[] = [];
  await page.route("**/api/finance/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path.endsWith("/person-link")) {
      const id = path.split("/").at(-2)!;
      if (request.method() !== "GET") {
        const body = request.postDataJSON();
        writes.push({ method: request.method(), path, body });
        expect(request.headers()["idempotency-key"]).toBeTruthy();
        expect(body.expected_transaction_snapshot).toHaveLength(64);
        if (request.method() === "PUT") {
          expect(body.person_id).toBe(donor.id);
          assigned.add(id);
        } else assigned.delete(id);
      }
      return route.fulfill({
        json: {
          transaction_id: id,
          snapshot: (assigned.has(id) ? "b" : "a").repeat(64),
          person: assigned.has(id) ? donor : null,
          eligible: true,
          reason: null,
        },
      });
    }
    if (request.method() !== "GET") return route.fallback();
    if (path === "/api/finance/people")
      return route.fulfill({
        json: { items: [donor], total: 1, offset: 0, limit: 50 },
      });
    if (path === `/api/finance/people/${donor.id}`)
      return route.fulfill({ json: donor });
    const linked = gifts.filter((g) => assigned.has(g.id));
    if (path.endsWith(`/people/${donor.id}/summary`)) {
      const amount = linked.reduce(
        (sum, g) => sum + g.postings[0].base_amount_pln,
        0,
      );
      return route.fulfill({
        json: {
          person_id: donor.id,
          gift_count: linked.length,
          received_gifts_pln: amount,
          received_by_currency: { PLN: amount },
        },
      });
    }
    if (path.endsWith(`/people/${donor.id}/gifts`))
      return route.fulfill({
        json: { items: linked, total: linked.length, offset: 0, limit: 50 },
      });
    if (path === "/api/finance/transactions/search")
      return route.fulfill({
        json: { items: gifts, total: 2, offset: 0, limit: 25 },
      });
    if (path === "/api/finance/accounts")
      return route.fulfill({ json: [bank] });
    const gift = gifts.find(
      (g) => path === `/api/finance/transactions/${g.id}`,
    );
    if (gift) return route.fulfill({ json: gift });
    return route.fallback();
  });
  for (const gift of gifts) {
    await page.goto(`/finances/transactions?detail=${gift.id}`);
    await page
      .getByRole("button", { name: "Darczyńca i powiązanie", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "Darczyńca", exact: true });
    await dialog
      .getByRole("combobox", { name: "Darczyńca" })
      .selectOption(donor.id);
    await dialog.getByRole("button", { name: "Przypisz darczyńcę" }).click();
    await expect(dialog).toHaveCount(0);
  }
  await page.goto(`/finances/people/${donor.id}`);
  await expect(page.getByText("300,00 PLN", { exact: true })).toBeVisible();
  await expect(page.getByText("Darowizna 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Darowizna 2", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("person-gift-history.png"),
    fullPage: true,
  });
  await page.goto(`/finances/transactions?detail=${gifts[0].id}`);
  await page
    .getByRole("button", { name: "Darczyńca i powiązanie", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Darczyńca", exact: true });
  await dialog.getByRole("button", { name: "Odepnij darczyńcę" }).click();
  await expect(dialog).toHaveCount(0);
  await page.goto(`/finances/people/${donor.id}`);
  await expect(
    page
      .locator("section")
      .filter({
        has: page.getByRole("heading", {
          name: "Otrzymane darowizny",
          exact: true,
        }),
      })
      .getByText("200,00 PLN", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(3);
  for (const write of writes)
    expect(Object.keys(write.body).sort()).toEqual(
      write.method === "PUT"
        ? ["expected_transaction_snapshot", "person_id"]
        : ["expected_transaction_snapshot"],
    );
  base.assertClean();
});
