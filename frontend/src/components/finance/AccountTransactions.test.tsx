import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountTransactions } from "./AccountTransactions";

const { useAccountTransactions, useUpdateTransaction, useDeleteTransaction } =
  vi.hoisted(() => ({
    useAccountTransactions: vi.fn(),
    useUpdateTransaction: vi.fn(),
    useDeleteTransaction: vi.fn(),
  }));

vi.mock("../../api/finance", () => ({
  splitAccounts: (accounts: Array<{ is_budget_account: boolean }>) => ({
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  }),
  useAccountTransactions,
  useUpdateTransaction,
  useDeleteTransaction,
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

const incomeTransaction = {
  id: "tx-income",
  transaction_date: "2026-08-14",
  description: "Wynagrodzenie",
  type: "income" as const,
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
      direction: "credit" as const,
    },
  ],
};

const expenseTransaction = {
  id: "tx-expense",
  transaction_date: "2026-08-14",
  description: "Czynsz",
  type: "expense" as const,
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
      direction: "debit" as const,
    },
  ],
};

describe("AccountTransactions", () => {
  let updateMutate: ReturnType<typeof vi.fn>;
  let deleteMutate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate = vi.fn();
    deleteMutate = vi.fn();
    useAccountTransactions.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    useUpdateTransaction.mockReturnValue({
      mutate: updateMutate,
      isPending: false,
      error: null,
      variables: undefined,
    });
    useDeleteTransaction.mockReturnValue({
      mutate: deleteMutate,
      isPending: false,
      error: null,
      variables: undefined,
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
      data: [incomeTransaction, expenseTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(screen.getByText("+5000,00 PLN")).toHaveClass("text-green-400");
    expect(screen.getByText("−123,00 PLN")).toHaveClass("text-red-400");
  });

  it("renders edit and delete buttons for each transaction row", () => {
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(screen.getByRole("button", { name: "Edytuj" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Usuń" })).toBeInTheDocument();
  });

  it("edits a transaction inline and saves the new description and date", () => {
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));

    const descriptionInput = screen.getByLabelText("Opis");
    expect(descriptionInput).toHaveValue("Wynagrodzenie");
    const dateInput = screen.getByLabelText("Data");
    expect(dateInput).toHaveValue("2026-08-14");

    fireEvent.change(descriptionInput, { target: { value: "Premia roczna" } });
    fireEvent.change(dateInput, { target: { value: "2026-08-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(updateMutate).toHaveBeenCalledWith({
      id: "tx-income",
      transaction_date: "2026-08-20",
      description: "Premia roczna",
    });
  });

  it("deletes a transaction after confirmation and skips it without", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    fireEvent.click(screen.getByRole("button", { name: "Usuń" }));
    expect(confirm).toHaveBeenCalledWith('Usunąć transakcję "Wynagrodzenie"?');
    expect(deleteMutate).toHaveBeenCalledWith("tx-income");

    confirm.mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Usuń" }));
    expect(deleteMutate).toHaveBeenCalledTimes(1);
  });
});
