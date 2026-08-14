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
});
