import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountTransactions } from "./AccountTransactions";

const { useAccountTransactions } = vi.hoisted(() => ({
  useAccountTransactions: vi.fn(),
}));

vi.mock("../../api/finance", () => ({
  splitAccounts: (accounts: Array<{ is_budget_account: boolean }>) => ({
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  }),
  useAccountTransactions,
}));

const accounts = [
  {
    id: "budget-account",
    name: "Rachunek główny",
    type: "bank",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 123456,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "info-account",
    name: "Karta firmowa",
    type: "card",
    currency: "PLN",
    is_active: true,
    is_budget_account: false,
    balance_pln: 45678,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

describe("AccountTransactions", () => {
  beforeEach(() => {
    useAccountTransactions.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
  });

  it("separates informational accounts and loads transactions after selection", () => {
    render(<AccountTransactions accounts={accounts} />);

    expect(screen.getByText("Konta budżetowe")).toBeInTheDocument();
    expect(screen.getByText("Konta informacyjne")).toBeInTheDocument();
    expect(screen.getByText("wyłączone z analiz")).toBeInTheDocument();
    expect(screen.getByText(/1.*234,56 PLN/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(useAccountTransactions).toHaveBeenLastCalledWith("budget-account");
    expect(
      screen.getByText("Brak transakcji dla tego konta."),
    ).toBeInTheDocument();
  });

  it("renders income as a green plus and expense as a red minus", () => {
    useAccountTransactions.mockReturnValue({
      data: [
        {
          id: "tx-income",
          transaction_date: "2026-08-14",
          description: "Wynagrodzenie",
          type: "income",
          is_pending: false,
          project_id: null,
          source: "manual",
          postings: [
            {
              id: "p-income",
              transaction_id: "tx-income",
              account_id: "budget-account",
              category_id: null,
              source_amount: 500000,
              source_currency: "PLN",
              base_amount_pln: 500000,
              fx_rate: 1,
              is_budget_impact: true,
              direction: "credit",
            },
          ],
        },
        {
          id: "tx-expense",
          transaction_date: "2026-08-14",
          description: "Czynsz",
          type: "expense",
          is_pending: false,
          project_id: null,
          source: "manual",
          postings: [
            {
              id: "p-expense",
              transaction_id: "tx-expense",
              account_id: "budget-account",
              category_id: null,
              source_amount: 12300,
              source_currency: "PLN",
              base_amount_pln: 12300,
              fx_rate: 1,
              is_budget_impact: true,
              direction: "debit",
            },
          ],
        },
      ],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(screen.getByText("+5000,00 PLN")).toHaveClass("text-green-400");
    expect(screen.getByText("−123,00 PLN")).toHaveClass("text-red-400");
  });
});
