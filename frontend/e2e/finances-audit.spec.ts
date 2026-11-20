import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures, transaction } from "./fixtures";
import { batchFixture } from "../src/test/bankImportFixtures";
import { scheduleBatch, scheduleLoan } from "../src/test/loanScheduleFixtures";

const empty = { items: [], offset: 0, limit: 25, total: 0 };
const person = {
  id: "person",
  name: "Osoba testowa",
  is_active: true,
  notes: null,
  version: 1,
};
const gift = {
  ...transaction,
  type: "income",
  postings: [{ ...transaction.postings[0], direction: "credit" }],
};

async function auditFixtures(page: Page) {
  const base = await fixtures(page);
  const responses: Record<string, object> = {
    "/api/finance/bills": empty,
    "/api/finance/people": { ...empty, items: [person], total: 60 },
    "/api/finance/people/person": person,
    "/api/finance/people/person/summary": {
      gift_count: 1,
      received_gifts_pln: 54321,
      received_by_currency: { EUR: 12345 },
    },
    "/api/finance/people/person/gifts": { ...empty, items: [gift], total: 1 },
    "/api/finance/imports/statement": batchFixture({
      id: "statement",
      sources: [],
      groups: [],
    }),
    "/api/finance/imports/statement/rows": empty,
    "/api/finance/imports/empty-schedule": {
      ...scheduleBatch(),
      id: "empty-schedule",
      sources: [],
    },
    "/api/finance/imports/empty-schedule/rows": empty,
    "/api/finance/imports/batch-a": scheduleBatch(),
    "/api/finance/imports/batch-a/rows": empty,
    "/api/finance/loans": [scheduleLoan],
  };
  await page.route("**/api/finance/**", (route) => {
    const response = responses[new URL(route.request().url()).pathname];
    return response ? route.fulfill({ json: response }) : route.fallback();
  });
  return base;
}

test("reports keep mismatched monthly values hidden, and ledger shows the matched amount", async ({
  page,
}) => {
  const api = await fixtures(page);
  let releaseAugust!: () => void;
  const august = new Promise<void>((resolve) => {
    releaseAugust = resolve;
  });
  await page.route("**/api/finance/summary?*", async (route) => {
    const month = Number(
      new URL(route.request().url()).searchParams.get("month"),
    );
    if (month === 8) await august;
    await route.fulfill({
      json: {
        accounts: [],
        balance_all_pln: 0,
        balance_budget_pln: 0,
        income_total_pln: month === 8 ? 30000 : 120000,
        expense_total_pln: 0,
        net_total_pln: 0,
        month,
        year: 2026,
      },
    });
  });
  await page.route("**/api/finance/transactions/search?*", (route) =>
    route.fulfill({
      json: {
        ...empty,
        total: 1,
        items: [{ ...transaction, matched_category_amount_pln: 2000 }],
      },
    }),
  );
  try {
    await page.goto("/finances/reports?month=9&year=2026");
    await expect(page.getByText(/1\s*200,00 PLN/)).toBeVisible();
    await page.getByRole("button", { name: "Poprzedni miesiąc" }).click();
    await expect(page.getByText(/1\s*200,00 PLN/)).toHaveCount(0);
    releaseAugust();
    await expect(page.getByText("300,00 PLN")).toBeVisible();
    await page.goto("/finances/transactions?category_id=dom");
    await expect(page.getByText("W tej kategorii 20,00 PLN")).toBeVisible();
    api.assertClean();
  } finally {
    releaseAugust();
  }
});

test("documents use the selected lifecycle and keep filters on reload", async ({
  page,
}) => {
  const api = await fixtures(page);
  const queries: URLSearchParams[] = [];
  await page.route("**/api/finance/bills?*", (route) => {
    queries.push(new URL(route.request().url()).searchParams);
    return route.fulfill({ json: empty });
  });
  await page.goto("/finances/documents");
  await expect.poll(() => queries[0]?.get("lifecycle")).toBe("active");
  await page
    .getByRole("combobox", { name: "Stan dokumentu" })
    .selectOption("archived");
  const search = page.getByRole("textbox", { name: "Szukaj dokumentu" });
  await search.evaluate((input: HTMLInputElement) => {
    const setValue = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    for (const value of ["FV", "FV 12"]) {
      setValue?.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  await expect.poll(() => queries.at(-1)?.get("query")).toBe("FV 12");
  expect(queries.some((query) => query.get("query") === "FV")).toBe(false);
  await page.reload();
  await expect(search).toHaveValue("FV 12");
  await expect(
    page.getByRole("combobox", { name: "Stan dokumentu" }),
  ).toHaveValue("archived");
  api.assertClean();
});

test("import history pages by type and a source-less schedule can resume upload", async ({
  page,
}) => {
  const api = await auditFixtures(page);
  await page.route("**/api/finance/imports/history?*", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset"));
    if (params.get("kind") === "statement")
      return route.fulfill({ json: { ...empty, total: 51, offset } });
    return route.fulfill({
      json: {
        ...empty,
        offset,
        total: 26,
        items: [
          {
            id: "empty-schedule",
            source_names: offset
              ? ["Ostatni harmonogram"]
              : ["Pierwszy harmonogram"],
            archived_at: null,
            commit_state: "not_committed",
            unresolved_count: 0,
          },
        ],
      },
    });
  });
  await page.goto("/finances/imports");
  await page
    .getByRole("combobox", { name: "Rodzaj importu" })
    .selectOption("loan_schedule");
  await page.getByRole("button", { name: "Następna strona" }).click();
  await page.getByRole("link", { name: "Ostatni harmonogram" }).click();
  await expect(
    page.getByRole("heading", { name: "Weryfikacja harmonogramu" }),
  ).toBeVisible();
  await expect(page.getByLabel("Pliki harmonogramów")).toBeVisible();
  await page.getByRole("link", { name: "Wszystkie importy" }).click();
  await expect(
    page.getByRole("link", { name: "Ostatni harmonogram" }),
  ).toBeVisible();
  api.assertClean();
});

test("people return preserves archive, page and the source amount of a gift", async ({
  page,
}) => {
  const api = await auditFixtures(page);
  await page.goto("/finances/people?archived=1&page=2");
  await page.getByRole("link", { name: person.name }).click();
  await expect(
    page.getByRole("link", { name: gift.description }),
  ).toHaveAttribute("href", `/finances/transactions?detail=${gift.id}`);
  await expect(page.getByText("123,45 EUR", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Wszystkie osoby" }).click();
  const params = new URL(page.url()).searchParams;
  expect(params.get("archived")).toBe("1");
  expect(params.get("page")).toBe("2");
  api.assertClean();
});

for (const theme of ["light", "dark"]) {
  test(`all finance routes support keyboard focus and pass the Axe rules in ${theme}`, async ({
    page,
  }) => {
    test.setTimeout(150000);
    const api = await auditFixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    for (const path of [
      "/finances",
      "/finances/accounts",
      "/finances/transactions",
      "/finances/cashflow",
      "/finances/budgets",
      "/finances/reports",
      "/finances/people",
      "/finances/people/person",
      "/finances/documents",
      "/finances/imports",
      "/finances/imports/statement",
      "/finances/proposals",
      "/finances/imports?kind=loan_schedule",
      "/finances/imports/batch-a",
      "/finances/imports/empty-schedule",
    ]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const main = page.locator("#main-content");
      await expect(
        main.getByRole("heading", { level: 1 }).first(),
      ).toBeVisible();
      expect(
        await main.evaluate(
          (element) => element.scrollWidth <= element.clientWidth + 1,
        ),
        path,
      ).toBe(true);
      await page.keyboard.press("Tab");
      expect(
        await page.evaluate(() => document.activeElement !== document.body),
        path,
      ).toBe(true);
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(
        scan.violations.map((violation) => ({
          id: violation.id,
          nodes: violation.nodes.map((node) => node.target),
        })),
        path,
      ).toEqual([]);
    }
    api.assertClean();
  });
}
