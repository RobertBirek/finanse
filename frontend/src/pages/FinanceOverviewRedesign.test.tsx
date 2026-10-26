import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Finances } from "./Finances";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useFinancialSummary: vi.fn(),
  useCashflowForecast: vi.fn(),
  useTransactions: vi.fn(),
  useBudgetStatus: vi.fn(),
}));
vi.mock("../api/finance", async (original) => ({
  ...(await original<object>()),
  ...hooks,
}));

beforeEach(() => {
  const ready = { isLoading: false, isError: false, refetch: vi.fn() };
  hooks.useAccounts.mockReturnValue({
    ...ready,
    data: [
      {
        id: "a",
        name: "Eurokonto",
        bank_name: "Bank EUR",
        currency: "EUR",
        balance_pln: 44000,
        balance_source: 10000,
        is_active: true,
        is_budget_account: true,
      },
      {
        id: "b",
        name: "Oszczędności",
        currency: "PLN",
        balance_pln: 100000,
        balance_source: 100000,
        is_active: true,
        is_budget_account: false,
      },
      {
        id: "c",
        name: "Zamknięte",
        currency: "PLN",
        balance_pln: 900000,
        is_active: false,
        is_budget_account: true,
      },
    ],
  });
  hooks.useFinancialSummary.mockReturnValue({
    ...ready,
    data: {
      balance_all_pln: 144000,
      balance_budget_pln: 44000,
      income_total_pln: 200000,
      expense_total_pln: 50000,
      net_total_pln: 150000,
    },
  });
  hooks.useCashflowForecast.mockReturnValue({
    ...ready,
    data: {
      next_payday: "2026-11-10",
      opening_balance_pln: 44000,
      projected_balance_before_next_payday_pln: 35000,
      safe_daily_limit_pln: 2000,
      lowest_balance_pln: 35000,
      days: [],
    },
  });
  hooks.useTransactions.mockReturnValue({ ...ready, data: [] });
  hooks.useBudgetStatus.mockReturnValue({
    ...ready,
    data: {
      total_budget_pln: 100000,
      total_spent_pln: 50000,
      remaining_pln: 50000,
      items: [],
    },
  });
});

describe("Approved finance overview", () => {
  it("shows owned active book-value balance and lets user select budget accounts", () => {
    render(
      <MemoryRouter>
        <Finances />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("Łączne saldo kont")).toHaveTextContent(
      "1440,00",
    );
    fireEvent.click(screen.getByRole("button", { name: "Budżetowe" }));
    expect(screen.getByLabelText("Łączne saldo kont")).toHaveTextContent(
      "440,00",
    );
    expect(screen.queryByText("Zamknięte")).not.toBeInTheDocument();
    expect(screen.getByText("100,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Bank EUR · Eurokonto")).toBeInTheDocument();
    expect(screen.getAllByText(/księgowa/i).length).toBeGreaterThan(0);
  });
  it("offers transaction actions but never account creation on the daily overview", () => {
    render(
      <MemoryRouter>
        <Finances />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Wydatek" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Przychód" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Transfer" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Dodaj konto" }),
    ).not.toBeInTheDocument();
  });
});
