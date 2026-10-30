import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
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

function LocationDisplay() {
  const location = useLocation();
  return (
    <p data-testid="location">{`${location.pathname}${location.search}`}</p>
  );
}

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
        has_excluded_obligations: true,
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
    useBudgetStatus.mockReturnValue({
      data: {
        items: [
          {
            category_id: "c-food",
            name: "Jedzenie",
            spent_pln: 40000,
            budget_amount_pln: 100000,
          },
        ],
      },
      isLoading: false,
      isError: false,
    } as never);

    render(
      <MemoryRouter initialEntries={["/finances?month=2&year=2026"]}>
        <Finances />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: /Przejdź do płynności/ }),
    ).toHaveAttribute("href", "/finances/cashflow?month=2&year=2026");
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
    expect(
      screen.getByText("Przychody · konta budżetowe").parentElement,
    ).toHaveTextContent(/PLN/);
    expect(
      screen.getByText("Limit dzienny niepewny").parentElement,
    ).not.toHaveTextContent(/—\s*PLN/);
    expect(screen.getAllByText(/25.10.2026/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Zakup kawy/ })).toHaveAttribute(
      "href",
      "/finances/transactions?month=2&year=2026&detail=tx%20latest",
    );
    expect(screen.getByRole("link", { name: /Konto główne/ })).toHaveAttribute(
      "href",
      "/finances/transactions?month=2&year=2026&account_id=budget",
    );
    expect(
      screen.getByRole("link", { name: "Cała historia →" }),
    ).toHaveAttribute("href", "/finances/transactions?month=2&year=2026");
    expect(screen.getByRole("link", { name: "Szczegóły →" })).toHaveAttribute(
      "href",
      "/finances/budgets?month=2&year=2026",
    );
    expect(screen.getByRole("link", { name: /Jedzenie/ })).toHaveAttribute(
      "href",
      "/finances/transactions?month=2&year=2026&category_id=c-food&include_descendants=true&budget_accounts_only=true&date_from=2026-02-01&date_to=2026-02-28",
    );
    expect(
      screen.getByRole("link", { name: "Ustawienia kont" }),
    ).toHaveAttribute("href", "/settings/finances/accounts");
  });

  it("keeps the selected period when a quick action opens a transaction form", () => {
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
      data: [],
      isLoading: false,
      isError: false,
    });
    useBudgetStatus.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
    });

    render(
      <MemoryRouter initialEntries={["/finances?month=2&year=2026"]}>
        <Finances />
        <LocationDisplay />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Wydatek/ }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/finances/transactions?month=2&year=2026&create=expense",
    );
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
