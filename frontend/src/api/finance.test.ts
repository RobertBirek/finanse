import { QueryClient } from "@tanstack/react-query";
import { describe, expect, expectTypeOf, it } from "vitest";
import {
  budgetProgress,
  buildCategoryTree,
  buildTransactionPostings,
  canConfirmSuggestion,
  cashflowStatusLabel,
  parsePlnToGrosze,
  splitAccounts,
  useCategorySummary,
  useFinancialSummary,
  type Account,
  type CategorySummary,
  type FinancialPeriod,
  type PostingInput,
} from "./finance";

const account = (id: string, is_budget_account: boolean): Account => ({
  id,
  name: id,
  type: "checking",
  currency: "PLN",
  is_active: true,
  is_budget_account,
  balance_pln: 0,
  opened_at: "2026-01-01",
  closed_at: null,
});

describe("splitAccounts", () => {
  it("keeps informational accounts out of the budget account list", () => {
    const result = splitAccounts([
      account("Konto główne", true),
      account("Pożyczka", false),
    ]);

    expect(result.budget.map(({ name }) => name)).toEqual(["Konto główne"]);
    expect(result.informational.map(({ name }) => name)).toEqual(["Pożyczka"]);
  });
});

describe("buildCategoryTree", () => {
  it("attaches expenditure categories to their group with their totals", () => {
    const summary: CategorySummary = {
      month: 8,
      year: 2026,
      groups: [
        {
          category_id: "transport",
          name: "Transport",
          parent_id: null,
          total_pln: 5000,
        },
      ],
      categories: [
        {
          category_id: "fuel",
          name: "Paliwo",
          parent_id: "transport",
          total_pln: 5000,
        },
      ],
    };

    expect(buildCategoryTree(summary)).toEqual([
      {
        category_id: "transport",
        name: "Transport",
        parent_id: null,
        total_pln: 5000,
        children: [
          {
            category_id: "fuel",
            name: "Paliwo",
            parent_id: "transport",
            total_pln: 5000,
          },
        ],
      },
    ]);
  });
});

describe("budgetProgress", () => {
  it("reports one-decimal percentage of a partially spent budget", () => {
    expect(budgetProgress(4000, 2500)).toEqual({ percent: 62.5, over: false });
  });

  it("caps a fully spent budget at 100 percent without overspending", () => {
    expect(budgetProgress(4000, 4000)).toEqual({ percent: 100, over: false });
  });

  it("clamps overspending at 100 percent and flags it as over", () => {
    expect(budgetProgress(4000, 4500)).toEqual({ percent: 100, over: true });
  });
});

describe("cashflowStatusLabel", () => {
  it("makes uncertain overdue forecasts explicit without suggesting a ledger action", () => {
    expect(cashflowStatusLabel("overdue_uncertain")).toBe(
      "Po terminie - kwota niepewna",
    );
  });
});

describe("parsePlnToGrosze", () => {
  it("parses a spaced Polish decimal amount into grosze", () => {
    expect(parsePlnToGrosze("1 234,50")).toBe(123450);
  });

  it("rejects zero and an amount with more than two fractional digits", () => {
    expect(parsePlnToGrosze("0")).toBeNull();
    expect(parsePlnToGrosze("12,345")).toBeNull();
  });
});

describe("canConfirmSuggestion", () => {
  it("allows a positive suggestion due today", () => {
    expect(
      canConfirmSuggestion(
        { status: "due", amount_pln: 12500, due_date: "2026-08-14" },
        "2026-08-14",
      ),
    ).toBe(true);
  });

  it("rejects a future due suggestion", () => {
    expect(
      canConfirmSuggestion(
        { status: "due", amount_pln: 12500, due_date: "2026-08-15" },
        "2026-08-14",
      ),
    ).toBe(false);
  });

  it("rejects an uncertain overdue suggestion", () => {
    expect(
      canConfirmSuggestion(
        {
          status: "overdue_uncertain",
          amount_pln: 12500,
          due_date: "2026-08-13",
        },
        "2026-08-14",
      ),
    ).toBe(false);
  });
});

describe("cashflow invalidation scope", () => {
  it("invalidates per-account transactions via the accounts prefix", async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["finance", "accounts"], []);
    queryClient.setQueryData(
      ["finance", "accounts", "acc-1", "transactions"],
      [],
    );
    queryClient.setQueryData(["finance", "transactions"], []);

    await queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });

    expect(
      queryClient.getQueryState(["finance", "accounts"])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState([
        "finance",
        "accounts",
        "acc-1",
        "transactions",
      ])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(["finance", "transactions"])?.isInvalidated,
    ).toBe(false);
  });
});

const plnPosting = (overrides: Partial<PostingInput>): PostingInput => ({
  account_id: null,
  category_id: null,
  source_amount: 2500,
  source_currency: "PLN",
  base_amount_pln: 2500,
  fx_rate: 1,
  fx_rate_source: "manual",
  direction: "debit",
  ...overrides,
});

describe("buildTransactionPostings", () => {
  it("builds an income with the account credited and category debited", () => {
    expect(
      buildTransactionPostings({
        type: "income",
        accountId: "acc-1",
        categoryId: "cat-income",
        amountPlng: 2500,
      }),
    ).toEqual([
      plnPosting({ account_id: "acc-1", direction: "credit" }),
      plnPosting({ category_id: "cat-income", direction: "debit" }),
    ]);
  });

  it("builds an expense with the account debited and category credited", () => {
    expect(
      buildTransactionPostings({
        type: "expense",
        accountId: "acc-1",
        categoryId: "cat-expense",
        amountPlng: 2500,
      }),
    ).toEqual([
      plnPosting({ account_id: "acc-1", direction: "debit" }),
      plnPosting({ category_id: "cat-expense", direction: "credit" }),
    ]);
  });

  it("builds a transfer with the source debited and destination credited", () => {
    expect(
      buildTransactionPostings({
        type: "transfer",
        fromAccountId: "acc-from",
        toAccountId: "acc-to",
        amountPlng: 2500,
      }),
    ).toEqual([
      plnPosting({ account_id: "acc-from", direction: "debit" }),
      plnPosting({ account_id: "acc-to", direction: "credit" }),
    ]);
  });

  it("balances postings to zero with debits positive and credits negative", () => {
    const transactions = [
      buildTransactionPostings({
        type: "income",
        accountId: "acc-1",
        categoryId: "cat-income",
        amountPlng: 2500,
      }),
      buildTransactionPostings({
        type: "expense",
        accountId: "acc-1",
        categoryId: "cat-expense",
        amountPlng: 2500,
      }),
      buildTransactionPostings({
        type: "transfer",
        fromAccountId: "acc-from",
        toAccountId: "acc-to",
        amountPlng: 2500,
      }),
    ];

    for (const postings of transactions) {
      const signed = postings.reduce(
        (sum, posting) =>
          sum +
          (posting.direction === "debit"
            ? posting.source_amount
            : -posting.source_amount),
        0,
      );
      expect(signed).toBe(0);
    }
  });
});

describe("financial period hook contracts", () => {
  it("accepts the same optional period object for both summaries", () => {
    expectTypeOf<Parameters<typeof useFinancialSummary>>().toEqualTypeOf<
      [period?: FinancialPeriod]
    >();
    expectTypeOf<Parameters<typeof useCategorySummary>>().toEqualTypeOf<
      [period?: FinancialPeriod]
    >();
  });
});
