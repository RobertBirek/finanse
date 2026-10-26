import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Finances } from "./Finances";

const {
  useAccounts,
  useCashflowForecast,
  useFinancialSummary,
  useTransactions,
  useBudgetStatus,
} = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCashflowForecast: vi.fn(),
  useFinancialSummary: vi.fn(),
  useTransactions: vi.fn(),
  useBudgetStatus: vi.fn(() => ({
    data: { items: [] },
    isLoading: false,
    isError: false,
  })),
}));

vi.mock("../api/finance", () => ({
  splitAccounts: (accounts: Array<{ is_budget_account: boolean }>) => ({
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  }),
  useAccounts,
  useCashflowForecast,
  useFinancialSummary,
  useTransactions,
  useBudgetStatus,
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
        {
          id: "inactive",
          name: "Stare konto",
          is_active: false,
          is_budget_account: true,
          balance_pln: 99999,
          type: "bank",
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
        days: [
          { date: "2026-10-20", projected_balance_pln: 500000 },
          { date: "2026-10-25", projected_balance_pln: 450000 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    useTransactions.mockReturnValue({
      data: [
        {
          id: "tx latest",
          description: "Zakup kawy",
          transaction_date: "2026-10-25",
          type: "expense",
          postings: [],
        },
        {
          id: "transfer",
          description: "Zasilenie konta",
          transaction_date: "2026-10-24",
          type: "transfer",
          postings: [],
        },
      ],
      isLoading: false,
      isError: false,
    });

    render(
      <MemoryRouter>
        <Finances />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: /Przejdź do płynności/ }),
    ).toHaveAttribute("href", "/finances/cashflow");
    expect(screen.getByText(/Konta budżetowe/)).toBeInTheDocument();
    expect(screen.queryByText("Stare konto")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Planowane wpływy i wydatki"),
    ).not.toBeInTheDocument();
    expect(useTransactions).toHaveBeenCalledWith({ limit: 5 });
    expect(screen.getByText("Zakup kawy")).toBeInTheDocument();
    expect(screen.getByText(/Transfer własny/)).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Prognozowany przebieg salda" }),
    ).toBeInTheDocument();
    expect(screen.getByText("20.10.2026")).toBeInTheDocument();
    expect(screen.getAllByText(/25.10.2026/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Zakup kawy/ })).toHaveAttribute(
      "href",
      "/finances/transactions?detail=tx%20latest",
    );
    expect(
      screen.getByRole("link", { name: "Ustawienia kont" }),
    ).toHaveAttribute("href", "/settings/finances/accounts");
  });

  it("retries latest transaction data instead of rendering an invented empty history", () => {
    const refetch = vi.fn();
    useAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });
    useFinancialSummary.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });
    useCashflowForecast.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });
    useTransactions.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch,
    });

    render(
      <MemoryRouter>
        <Finances />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByText("Brak ostatnich transakcji."),
    ).not.toBeInTheDocument();
  });
});
