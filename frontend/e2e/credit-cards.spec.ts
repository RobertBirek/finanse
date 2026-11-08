import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures } from "./fixtures";
import type { CreditCard } from "../src/api/creditCards";

const accountId = "10000000-0000-0000-0000-000000000021";
const secondId = "10000000-0000-0000-0000-000000000022";
const sourceId = "20000000-0000-0000-0000-000000000021";
async function cardFixtures(page: Page) {
  const api = await fixtures(page);
  const mutations: unknown[] = [];
  const card: CreditCard = {
    account_id: accountId,
    limit_pln: 3360000,
    apr: "14.5000",
    cycle_close_day: 17,
    due_day: 12,
    grace_days: 57,
    version: 1,
    debt_pln: 102796,
    available_pln: 3257204,
    pending_debits_pln: 0,
    overpayment_pln: 0,
    overlimit_pln: 0,
    plans: [],
    charges: [],
    allocations: [],
    statements: [
      {
        id: "statement",
        period_start: "2026-09-18",
        period_end: "2026-10-17",
        due_date: "2026-11-12",
        debt_pln: 102796,
        minimum_pln: 3000,
        remaining_pln: 102796,
        minimum_remaining_pln: 3000,
        reconciliation_difference_pln: 0,
        source_reference: "Bank PDF",
      },
    ],
  };
  const cards = new Map([
    [accountId, card],
    [
      secondId,
      {
        ...card,
        account_id: secondId,
        limit_pln: 1200000,
        available_pln: 1200000,
        debt_pln: 0,
        statements: [],
        plans: [],
      },
    ],
  ]);
  const terms = (value: CreditCard) => ({
    limit_pln: value.limit_pln,
    apr: value.apr,
    cycle_close_day: value.cycle_close_day,
    due_day: value.due_day,
    grace_days: value.grace_days,
    version: value.version,
  });
  const accounts = [
    {
      id: accountId,
      name: "VELOBANK - karta",
      type: "credit_card",
      currency: "PLN",
      is_active: true,
      is_budget_account: true,
      balance_pln: -102796,
      opened_at: "2026-01-01",
      closed_at: null,
      credit_card: terms(card),
    },
    {
      id: secondId,
      name: "Druga karta",
      type: "credit_card",
      currency: "PLN",
      is_active: true,
      is_budget_account: true,
      balance_pln: 0,
      opened_at: "2026-01-01",
      closed_at: null,
      credit_card: terms(cards.get(secondId)!),
    },
  ];
  await page.route("**/api/finance/accounts", async (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: accounts });
    const body = route.request().postDataJSON();
    mutations.push({ path: "/api/finance/accounts", body });
    const id = "10000000-0000-0000-0000-000000000023";
    const { expected_version, ...settings } = body.credit_card;
    if (expected_version !== 0)
      return route.fulfill({
        status: 409,
        json: { detail: "Stale card version" },
      });
    const created = {
      ...accounts[0],
      ...body,
      id,
      balance_pln: 0,
      credit_card: { ...settings, version: 1 },
    };
    accounts.push(created);
    cards.set(id, {
      ...card,
      ...settings,
      account_id: id,
      debt_pln: 0,
      available_pln: settings.limit_pln,
      version: 1,
      statements: [],
      plans: [],
      charges: [],
      allocations: [],
    });
    return route.fulfill({ status: 201, json: created });
  });
  await page.route("**/api/finance/accounts/*", async (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[4];
    const account = accounts.find((item) => item.id === id);
    if (!account)
      return route.fulfill({
        status: 404,
        json: { detail: "Account not found" },
      });
    if (route.request().method() === "GET")
      return route.fulfill({ json: account });
    const body = route.request().postDataJSON();
    mutations.push({ path: `/api/finance/accounts/${id}`, body });
    if (body.credit_card) {
      const { expected_version, ...settings } = body.credit_card;
      if (expected_version !== account.credit_card.version)
        return route.fulfill({
          status: 409,
          json: { detail: "Stale card version" },
        });
      account.credit_card = {
        ...settings,
        version: account.credit_card.version + 1,
      };
      const detail = cards.get(id)!;
      Object.assign(detail, settings, {
        version: account.credit_card.version,
        available_pln: Math.max(
          0,
          settings.limit_pln - detail.debt_pln - detail.pending_debits_pln,
        ),
      });
    }
    Object.assign(account, { ...body, credit_card: account.credit_card });
    return route.fulfill({ json: account });
  });
  await page.route("**/api/finance/credit-cards", (route) =>
    route.fulfill({
      json: accounts.map((account) => {
        const value = cards.get(account.id)!;
        return {
          account_id: account.id,
          name: account.name,
          is_active: account.is_active,
          color: null,
          configured: true,
          limit_pln: value.limit_pln,
          debt_pln: value.debt_pln,
          available_pln: value.available_pln,
          pending_debits_pln: value.pending_debits_pln,
          overpayment_pln: value.overpayment_pln,
          overlimit_pln: value.overlimit_pln,
        };
      }),
    }),
  );
  await page.route("**/api/finance/accounts/*/credit-card**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const selected = cards.get(path.split("/")[4]);
    if (!selected)
      return route.fulfill({ status: 404, json: { detail: "Card not found" } });
    if (request.method() === "GET") {
      if (path.endsWith("/candidates")) {
        await route.fulfill({
          json: {
            total: 1,
            items: [
              {
                id: sourceId,
                date: "2026-10-01",
                description: "Zakup testowy",
                amount_pln: 100000,
              },
            ],
          },
        });
        return;
      }
      await route.fulfill({ json: selected });
      return;
    }
    const body = request.postDataJSON();
    mutations.push({ path, body });
    if (path.endsWith("/plans")) {
      const plan = {
        id: "plan",
        name: body.name,
        source_transaction_id: body.source_transaction_id,
        principal_pln: body.principal_pln,
        apr: body.apr,
        fees_pln: body.fees_pln,
        version: 1,
        schedule_kind: "estimated" as const,
        remaining_principal_pln: body.principal_pln,
        status: "active" as const,
        installments: [
          {
            number: 1,
            due_date: body.first_due,
            principal_pln: body.principal_pln,
            interest_pln: 687,
            fees_pln: 0,
          },
        ],
      };
      selected.plans.push(plan);
      await route.fulfill({ status: 201, json: plan });
      return;
    }
    await route.fulfill({
      status: 422,
      json: { detail: "Unexpected mutation" },
    });
  });
  return { ...api, mutations };
}

for (const theme of ["light", "dark"]) {
  test(`multiple card overview and account editing in ${theme}`, async ({
    page,
  }, testInfo) => {
    const api = await cardFixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    const detailReads: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.endsWith("/credit-card"))
        detailReads.push(request.url());
    });
    await page.goto("/settings/finances/cards");
    const first = page.getByRole("article", { name: "VELOBANK - karta" });
    const second = page.getByRole("article", { name: "Druga karta" });
    await expect(first).toContainText(/32\s?572,04/);
    await expect(second).toContainText(/12\s?000,00/);
    await expect(page.getByRole("form")).toHaveCount(0);
    expect(detailReads).toEqual([]);
    await page.waitForLoadState("networkidle");
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`cards-overview-${theme}.png`),
      fullPage: true,
    });
    await second.getByRole("link", { name: "Edytuj konto" }).click();
    await expect(page.getByLabel("Limit PLN")).toHaveValue("12000");
    await page.getByLabel("Limit PLN").fill("12500,50");
    await page.waitForLoadState("networkidle");
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`card-account-edit-${theme}.png`),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Zapisz konto Druga karta" })
      .click();
    await expect(page.getByLabel("Limit PLN")).toHaveCount(0);
    expect(api.mutations).toHaveLength(1);
    expect(api.mutations[0]).toMatchObject({
      path: `/api/finance/accounts/${secondId}`,
      body: { credit_card: { limit_pln: 1250050, expected_version: 1 } },
    });
    await page.goBack();
    await expect(
      page.getByRole("article", { name: "Druga karta" }),
    ).toContainText(/12\s?500,50/);
    await first.getByRole("link", { name: "Wyciągi i raty" }).click();
    await expect(page).toHaveURL(new RegExp(`/cards/${accountId}$`));
    await expect(
      page.getByRole("region", { name: "Wykorzystanie limitu" }),
    ).toContainText(/32\s?572,04/);
    await expect(
      page.getByRole("form", { name: "Ustawienia karty" }),
    ).toHaveCount(0);
    api.assertClean();
  });
  test(`card limits, statement dates and accessibility in ${theme}`, async ({
    page,
  }, testInfo) => {
    const api = await cardFixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.goto(`/settings/finances/cards?account=${accountId}`);
    await expect(
      page.getByRole("region", { name: "Wykorzystanie limitu" }),
    ).toContainText(/32\s?572,04/);
    await expect(page.getByText("2026-11-12", { exact: true })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`credit-card-${theme}.png`),
      fullPage: true,
    });
    expect(api.mutations).toEqual([]);
    api.assertClean();
  });
}

test("creates another card through the account form with one atomic request", async ({
  page,
}) => {
  const api = await cardFixtures(page);
  await page.goto("/settings/finances/accounts");
  const form = page.getByRole("form", { name: "Nowe konto" });
  await form.getByLabel("Nazwa", { exact: true }).fill("Nowa karta");
  await form.getByLabel("Typ", { exact: true }).selectOption("credit_card");
  await expect(form.getByLabel("Waluta")).toHaveValue("PLN");
  await expect(form.getByLabel("Waluta")).toBeDisabled();
  for (const [label, value] of [
    ["Limit PLN", "8000"],
    ["Oprocentowanie roczne %", "11,25"],
    ["Dzień zamknięcia cyklu", "17"],
    ["Domyślny dzień spłaty", "12"],
    ["Maksymalny okres bezodsetkowy (dni)", "57"],
  ])
    await form.getByLabel(label).fill(value);
  await form.getByRole("button", { name: "Dodaj konto" }).click();
  await expect(page.getByText("Nowa karta", { exact: true })).toBeVisible();
  expect(api.mutations).toHaveLength(1);
  expect(api.mutations[0]).toMatchObject({
    path: "/api/finance/accounts",
    body: {
      type: "credit_card",
      credit_card: { limit_pln: 800000, apr: "11.25", expected_version: 0 },
    },
  });
  await page
    .getByRole("link", { name: "Karty kredytowe", exact: true })
    .click();
  await expect(page.getByRole("article", { name: "Nowa karta" })).toContainText(
    /8\s?000,00/,
  );
  await expect(page.getByRole("article")).toHaveCount(3);
  api.assertClean();
});

test("new plan uses its own APR without posting a new transaction", async ({
  page,
}) => {
  const api = await cardFixtures(page);
  await page.goto(`/settings/finances/cards?account=${accountId}`);
  const form = page.getByRole("form", { name: "Nowy plan ratalny" });
  await form.getByLabel("Nazwa planu").fill("Nowy Komfort");
  await form.getByLabel("Transakcja źródłowa").selectOption(sourceId);
  await form.getByLabel("Kapitał PLN").fill("1000,00");
  await form.getByLabel("Oprocentowanie planu %").fill("8,25");
  await form.getByLabel("Liczba rat").fill("10");
  await form.getByLabel("Pierwsza rata").fill("2026-12-12");
  await form.getByRole("button").click();
  await expect(
    page.getByRole("heading", { name: "Nowy Komfort", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Wykorzystanie limitu" }),
  ).toContainText(/1\s?027,96/);
  expect(api.mutations).toHaveLength(1);
  expect(api.mutations[0]).toMatchObject({
    path: `/api/finance/accounts/${accountId}/credit-card/plans`,
    body: {
      source_transaction_id: sourceId,
      principal_pln: 100000,
      apr: "8.25",
      fees_pln: 0,
      count: 10,
    },
  });
  api.assertClean();
});
