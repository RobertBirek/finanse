import { expect, test, type Page } from "@playwright/test";
import { account, fixtures } from "./fixtures";

const zero = {
  amount_minor: 0,
  date: "2026-01-01",
  fx_rate: null,
  version: 1,
  can_edit: true,
  blocked_reason: null,
};

async function openingFixtures(page: Page, conflict = false) {
  const base = await fixtures(page);
  let accounts = [
    {
      ...account,
      id: "empty-bo",
      name: "Puste konto",
      currency: "PLN",
      balance_source: 0,
      balance_pln: 0,
      opening_balance: { ...zero },
    },
    {
      ...account,
      id: "history-bo",
      name: "Konto z historią",
      currency: "PLN",
      balance_source: 54321,
      opening_balance: {
        ...zero,
        can_edit: false,
        blocked_reason: "Konto ma inne transakcje.",
      },
    },
  ];
  const writes: {
    method: string;
    path: string;
    body: Record<string, unknown>;
    key?: string;
  }[] = [];
  await page.route("**/api/finance/accounts**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (request.method() === "GET") {
      if (path === "/api/finance/accounts")
        return route.fulfill({ json: accounts });
      const found = accounts.find(
        (a) => path === `/api/finance/accounts/${a.id}`,
      );
      if (found) return route.fulfill({ json: found });
      return route.fallback();
    }
    const body = request.postDataJSON();
    writes.push({
      method: request.method(),
      path,
      body,
      key: request.headers()["idempotency-key"],
    });
    if (request.method() === "POST" && path === "/api/finance/accounts") {
      const opening = body.opening_balance ?? {
        amount_minor: 0,
        date: "2026-11-16",
      };
      const created = {
        ...account,
        ...body,
        id: `created-${writes.length}`,
        balance_source: opening.amount_minor,
        balance_pln: opening.amount_minor,
        ...(body.credit_card
          ? { credit_card: { ...body.credit_card, version: 1 } }
          : {}),
        opening_balance: { ...zero, ...opening, fx_rate: null },
      };
      accounts = [...accounts, created];
      return route.fulfill({ status: 201, json: created });
    }
    const target = accounts.find(
      (a) => path === `/api/finance/accounts/${a.id}/opening-balance`,
    );
    if (request.method() === "PUT" && target) {
      if (conflict && writes.length === 1) {
        target.opening_balance = { ...target.opening_balance, version: 2 };
        return route.fulfill({
          status: 409,
          json: { detail: "Wersja BO zmieniła się." },
        });
      }
      expect(body.expected_version).toBe(target.opening_balance.version);
      target.opening_balance = {
        ...target.opening_balance,
        amount_minor: body.amount_minor,
        date: body.date,
        version: target.opening_balance.version + 1,
      };
      target.balance_pln = target.balance_source = body.amount_minor;
      return route.fulfill({ json: target.opening_balance });
    }
    return route.fallback();
  });
  return { base, writes };
}

test("creates positive, negative card and zero BO in one account request", async ({
  page,
}, info) => {
  const state = await openingFixtures(page);
  await page.goto("/settings/finances/accounts");
  const form = page.getByRole("form", { name: "Nowe konto" });
  for (const [name, amount, expected, card] of [
    ["Dodatni start", "123,45", 12345, false],
    ["Ujemna karta", "-250,00", -25000, true],
    ["Zerowy start", "", 0, false],
  ] as const) {
    await form.getByLabel("Nazwa", { exact: true }).fill(name);
    await form
      .getByLabel("Typ", { exact: true })
      .selectOption(card ? "credit_card" : "checking");
    await form.getByLabel("Kwota BO (PLN)", { exact: true }).fill(amount);
    await form.getByLabel("Data BO", { exact: true }).fill("2026-11-16");
    if (card) {
      for (const [label, value] of [
        ["Limit PLN", "1000"],
        ["Oprocentowanie roczne %", "14,5"],
        ["Dzień zamknięcia cyklu", "17"],
        ["Domyślny dzień spłaty", "12"],
        ["Maksymalny okres bezodsetkowy (dni)", "57"],
      ])
        await form.getByLabel(label, { exact: true }).fill(value);
      await page.screenshot({
        path: info.outputPath("negative-card-bo.png"),
        fullPage: true,
      });
    }
    await form
      .getByRole("button", { name: "Dodaj konto", exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: `Edytuj BO konta ${name}`,
        exact: true,
      }),
    ).toBeVisible();
    const last = state.writes.at(-1)!;
    expect(last.method).toBe("POST");
    expect(last.path).toBe("/api/finance/accounts");
    expect(
      (last.body.opening_balance as { amount_minor: number } | undefined)
        ?.amount_minor ?? 0,
    ).toBe(expected);
  }
  expect(state.writes).toHaveLength(3);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
  state.base.assertClean();
});

test("edits only empty-account BO and requires a fresh confirmation after conflict", async ({
  page,
}, info) => {
  const state = await openingFixtures(page, true);
  await page.goto("/settings/finances/accounts");
  await expect(
    page.getByRole("button", { name: "Edytuj BO konta Konto z historią" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Konto ma inne transakcje.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edytuj BO konta Puste konto", exact: true })
    .click();
  const form = page.getByRole("form", {
    name: "Bilans otwarcia konta Puste konto",
    exact: true,
  });
  await form.getByLabel("Kwota BO (PLN)", { exact: true }).fill("-20,00");
  await form.getByRole("button", { name: "Zapisz BO", exact: true }).click();
  await expect(form.getByRole("alert")).toHaveText("Wersja BO zmieniła się.");
  await expect(
    form.getByRole("button", { name: "Zapisz BO", exact: true }),
  ).toBeDisabled();
  await form.getByRole("button", { name: "Odśwież BO", exact: true }).click();
  await form
    .getByLabel("Potwierdzam zmianę bilansu otwarcia", { exact: true })
    .check();
  await form.getByLabel("Kwota BO (PLN)", { exact: true }).fill("-20,00");
  await page.screenshot({
    path: info.outputPath("opening-editor.png"),
    fullPage: true,
  });
  await form.getByRole("button", { name: "Zapisz BO", exact: true }).click();
  await expect(form).toHaveCount(0);
  expect(state.writes).toHaveLength(2);
  expect(state.writes[0].key).not.toBe(state.writes[1].key);
  expect(state.writes[1].body).toEqual({
    amount_minor: -2000,
    date: "2026-01-01",
    expected_version: 2,
  });
  expect(
    state.writes.every(
      (w) => w.method === "PUT" && w.path.endsWith("/opening-balance"),
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  state.base.assertClean();
});
