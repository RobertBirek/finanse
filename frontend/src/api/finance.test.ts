import { describe, expect, it } from "vitest";
import {
  buildCategoryTree,
  cashflowStatusLabel,
  splitAccounts,
  type Account,
  type CategorySummary,
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
