import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures } from "./fixtures";
import type { CreditCard } from "../src/api/creditCards";

const accountId = "10000000-0000-0000-0000-000000000021";
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
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({
      json: [
        {
          id: accountId,
          name: "VELOBANK - karta",
          type: "credit",
          currency: "PLN",
          is_active: true,
          is_budget_account: true,
          balance_pln: -102796,
        },
      ],
    }),
  );
  await page.route(
    `**/api/finance/accounts/${accountId}/credit-card**`,
    async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
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
        await route.fulfill({ json: card });
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
        card.plans.push(plan);
        await route.fulfill({ status: 201, json: plan });
        return;
      }
      await route.fulfill({
        status: 422,
        json: { detail: "Unexpected mutation" },
      });
    },
  );
  return { ...api, mutations };
}

for (const theme of ["light", "dark"]) {
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
