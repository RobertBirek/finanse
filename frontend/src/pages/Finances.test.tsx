import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Finances } from "./Finances";

const { useAccounts, useCashflowForecast, useFinancialSummary } = vi.hoisted(
  () => ({
    useAccounts: vi.fn(),
    useCashflowForecast: vi.fn(),
    useFinancialSummary: vi.fn(),
  }),
);

vi.mock("../api/finance", () => ({
  splitAccounts: (accounts: Array<{ is_budget_account: boolean }>) => ({
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  }),
  useAccounts,
  useCashflowForecast,
  useFinancialSummary,
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
      },
      isLoading: false,
      isError: false,
    });

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
    expect(screen.queryByText("Stare konto")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Planowane wpływy i wydatki"),
    ).not.toBeInTheDocument();
  });
});
