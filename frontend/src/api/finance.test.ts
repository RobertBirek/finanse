import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse } from "axios";
import { createElement, type ReactNode } from "react";
import { describe, expect, expectTypeOf, it, vi } from "vitest";
import api from "../lib/api";
import {
  budgetProgress,
  buildCategoryTree,
  buildTransactionPostings,
  canConfirmSuggestion,
  cashflowStatusLabel,
  invalidateFinanceLedger,
  parsePlnToGrosze,
  splitAccounts,
  useCategorySummary,
  useCreateExchange,
  useDeleteAccount,
  useDeleteCategory,
  useDeleteTransaction,
  useFinancialSummary,
  useUpdateAccount,
  useUpdateCategory,
  useUpdateTransaction,
  type Account,
  type Category,
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

function queryClientWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("invalidateFinanceLedger", () => {
  it("invalidates the transaction ledger queries", () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["finance", "transactions"], []);
    queryClient.setQueryData(["finance", "accounts"], []);
    queryClient.setQueryData(["finance", "summary"], []);
    queryClient.setQueryData(["finance", "category-summary"], []);

    invalidateFinanceLedger(queryClient);

    expect(
      queryClient.getQueryState(["finance", "transactions"])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(["finance", "accounts"])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(["finance", "summary"])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(["finance", "category-summary"])?.isInvalidated,
    ).toBe(true);
  });
});

describe("transaction mutation hooks", () => {
  it("exports the update and delete hooks as functions", () => {
    expect(useUpdateTransaction).toBeTypeOf("function");
    expect(useDeleteTransaction).toBeTypeOf("function");
  });

  it("updates a transaction with its editable fields at its URL", async () => {
    const patchSpy = vi.spyOn(api, "patch").mockResolvedValue({
      data: { id: "tx-123" },
    } as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useUpdateTransaction(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({
      id: "tx-123",
      transaction_date: "2026-08-16",
      description: "Zakupy",
    });

    expect(patchSpy).toHaveBeenCalledWith("/finance/transactions/tx-123", {
      transaction_date: "2026-08-16",
      description: "Zakupy",
    });
    patchSpy.mockRestore();
  });

  it("deletes a transaction via its id in the URL", async () => {
    const deleteSpy = vi
      .spyOn(api, "delete")
      .mockResolvedValue({} as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useDeleteTransaction(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync("tx-123");

    expect(deleteSpy).toHaveBeenCalledWith("/finance/transactions/tx-123");
    deleteSpy.mockRestore();
  });
});

describe("account mutation hooks", () => {
  it("updates an account with its editable fields at its URL", async () => {
    const patchSpy = vi
      .spyOn(api, "patch")
      .mockResolvedValue({ data: { id: "acc-1" } } as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useUpdateAccount(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({
      id: "acc-1",
      is_active: false,
      is_budget_account: true,
    });

    expect(patchSpy).toHaveBeenCalledWith("/finance/accounts/acc-1", {
      is_active: false,
      is_budget_account: true,
    });
    patchSpy.mockRestore();
  });

  it("passes a closed_at date through when closing an account", async () => {
    const patchSpy = vi
      .spyOn(api, "patch")
      .mockResolvedValue({ data: { id: "acc-1" } } as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useUpdateAccount(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({ id: "acc-1", closed_at: "2026-08-17" });

    expect(patchSpy).toHaveBeenCalledWith("/finance/accounts/acc-1", {
      closed_at: "2026-08-17",
    });
    patchSpy.mockRestore();
  });

  it("deletes an account via its id in the URL", async () => {
    const deleteSpy = vi
      .spyOn(api, "delete")
      .mockResolvedValue({} as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useDeleteAccount(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync("acc-1");

    expect(deleteSpy).toHaveBeenCalledWith("/finance/accounts/acc-1");
    deleteSpy.mockRestore();
  });

  it("invalidates the accounts list after a mutation", async () => {
    const patchSpy = vi
      .spyOn(api, "patch")
      .mockResolvedValue({ data: { id: "acc-1" } } as unknown as AxiosResponse);
    const queryClient = new QueryClient();
    queryClient.setQueryData(["finance", "accounts"], []);

    const { result } = renderHook(() => useUpdateAccount(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({ id: "acc-1", is_active: false });

    expect(
      queryClient.getQueryState(["finance", "accounts"])?.isInvalidated,
    ).toBe(true);
    patchSpy.mockRestore();
  });
});

describe("category mutation hooks", () => {
  it("updates a category with its editable fields at its URL", async () => {
    const patchSpy = vi
      .spyOn(api, "patch")
      .mockResolvedValue({ data: { id: "cat-1" } } as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useUpdateCategory(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({ id: "cat-1", is_active: false });

    expect(patchSpy).toHaveBeenCalledWith("/finance/categories/cat-1", {
      is_active: false,
    });
    patchSpy.mockRestore();
  });

  it("deletes a category via its id in the URL", async () => {
    const deleteSpy = vi
      .spyOn(api, "delete")
      .mockResolvedValue({} as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useDeleteCategory(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync("cat-1");

    expect(deleteSpy).toHaveBeenCalledWith("/finance/categories/cat-1");
    deleteSpy.mockRestore();
  });

  it("invalidates the category queries after a mutation", async () => {
    const patchSpy = vi
      .spyOn(api, "patch")
      .mockResolvedValue({ data: { id: "cat-1" } } as unknown as AxiosResponse);
    const queryClient = new QueryClient();
    queryClient.setQueryData(["finance", "categories"], []);
    queryClient.setQueryData(["finance", "category-summary"], []);
    queryClient.setQueryData(["finance", "summary"], []);

    const { result } = renderHook(() => useUpdateCategory(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({ id: "cat-1", is_active: false });

    expect(
      queryClient.getQueryState(["finance", "categories"])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(["finance", "category-summary"])?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(["finance", "summary"])?.isInvalidated,
    ).toBe(true);
    patchSpy.mockRestore();
  });
});

describe("Category type", () => {
  it("exposes is_active on the category response", () => {
    expectTypeOf<Category["is_active"]>().toEqualTypeOf<boolean>();
  });
});

describe("exchange transaction hook", () => {
  it("posts an exchange to its URL with the input payload", async () => {
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({
      data: { id: "tx-456" },
    } as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useCreateExchange(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({
      from_account_id: "acc-from",
      to_account_id: "acc-to",
      from_amount: 2500,
      transaction_date: "2026-08-16",
      description: "Przewalutowanie",
    });

    expect(postSpy).toHaveBeenCalledWith("/finance/transactions/exchange", {
      from_account_id: "acc-from",
      to_account_id: "acc-to",
      from_amount: 2500,
      transaction_date: "2026-08-16",
      description: "Przewalutowanie",
    });
    postSpy.mockRestore();
  });

  it("omits the fx_rate key when it is not provided", async () => {
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({
      data: { id: "tx-456" },
    } as unknown as AxiosResponse);
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useCreateExchange(), {
      wrapper: queryClientWrapper(queryClient),
    });

    await result.current.mutateAsync({
      from_account_id: "acc-from",
      to_account_id: "acc-to",
      from_amount: 2500,
      fx_rate: null,
      description: "Przewalutowanie",
    });

    expect(postSpy).toHaveBeenCalledWith("/finance/transactions/exchange", {
      from_account_id: "acc-from",
      to_account_id: "acc-to",
      from_amount: 2500,
      description: "Przewalutowanie",
    });
    postSpy.mockRestore();
  });
});
