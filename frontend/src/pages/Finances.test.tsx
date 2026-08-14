import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Finances } from "./Finances";

const {
  useAccounts,
  useAccountTransactions,
  useCashflowForecast,
  useCategorySummary,
  useFinancialSummary,
  useScheduledFinanceItems,
} = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useAccountTransactions: vi.fn(),
  useCashflowForecast: vi.fn(),
  useCategorySummary: vi.fn(),
  useFinancialSummary: vi.fn(),
  useScheduledFinanceItems: vi.fn(),
}));

vi.mock("../api/finance", () => ({
  buildCategoryTree: () => [],
  splitAccounts: (accounts: Array<{ is_budget_account: boolean }>) => ({
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  }),
  useAccounts,
  useAccountTransactions,
  useCashflowForecast,
  useCategorySummary,
  useFinancialSummary,
  useScheduledFinanceItems,
}));

describe("Finances", () => {
  it("keeps the dashboard compact and links to the cashflow route", () => {
    useAccounts.mockReturnValue({
      data: [
        {
          id: "budget",
          name: "Konto główne",
          is_budget_account: true,
          balance_pln: 500000,
          type: "bank",
          currency: "PLN",
        },
        {
          id: "info",
          name: "Karta firmowa",
          is_budget_account: false,
          balance_pln: 12345,
          type: "card",
          currency: "PLN",
        },
      ],
      isLoading: false,
      isError: false,
    });
    useFinancialSummary.mockReturnValue({
      data: {
        income_total_pln: 100000,
        expense_total_pln: 40000,
        net_total_pln: 60000,
      },
      isLoading: false,
      isError: false,
    });
    useCashflowForecast.mockReturnValue({
      data: {
        projected_balance_before_next_payday_pln: 450000,
        lowest_balance_pln: 300000,
        safe_daily_limit_pln: 10000,
        suggestions: [],
      },
      isLoading: false,
      isError: false,
    });
    useCategorySummary.mockReturnValue({ data: undefined });
    useScheduledFinanceItems.mockReturnValue({
      data: [{ id: "rent", name: "Czynsz" }],
    });
    useAccountTransactions.mockReturnValue({ data: [] });

    render(
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Finances />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: "Przejdź do płynności" }),
    ).toHaveAttribute("href", "/finances/cashflow");
    expect(screen.getByText("Konta budżetowe")).toBeInTheDocument();
    expect(screen.getByText("Konta informacyjne")).toBeInTheDocument();
    expect(
      screen.queryByText("Planowane wpływy i wydatki"),
    ).not.toBeInTheDocument();
  });
});
