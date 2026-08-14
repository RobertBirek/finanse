import { describe, expect, expectTypeOf, it } from "vitest";
import {
  buildCategoryTree,
  canConfirmSuggestion,
  cashflowStatusLabel,
  parsePlnToGrosze,
  splitAccounts,
  useCategorySummary,
  useFinancialSummary,
  type Account,
  type CategorySummary,
  type FinancialPeriod,
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
