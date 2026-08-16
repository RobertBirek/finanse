import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FinanceCashflow } from "./FinanceCashflow";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useCashflowSettings: vi.fn(),
  useScheduledFinanceItems: vi.fn(),
  useCashflowForecast: vi.fn(),
  useUpdateCashflowSettings: vi.fn(),
  useCreateScheduledFinanceItem: vi.fn(),
  useUpdateScheduledFinanceItem: vi.fn(),
  useDeleteScheduledFinanceItem: vi.fn(),
  useConfirmScheduledFinanceItem: vi.fn(),
}));

vi.mock("../api/finance", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/finance")>();
  return { ...original, ...hooks };
});

const accounts = [
  {
    id: "a-budget",
    name: "Rachunek główny",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 100000,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "a-info",
    name: "Karta firmowa",
    type: "card",
    currency: "PLN",
    is_active: true,
    is_budget_account: false,
    balance_pln: 5000,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

const categories = [
  { id: "c-income", name: "Wynagrodzenie", parent_id: null, type: "income" },
  { id: "c-expense", name: "Czynsz", parent_id: null, type: "expense" },
];

const settings = {
  payday_day: 10,
  payday_account_id: "a-budget",
  forecast_horizon_days: 30,
  overdue_grace_days: 3,
};

const items = [
  {
    id: "item-1",
    name: "Czynsz",
    type: "expense",
    account_id: "a-budget",
    category_id: "c-expense",
    currency: "PLN",
    cadence: "monthly",
    due_day: 5,
    amount_method: "fixed",
    fixed_amount_pln: 250000,
    is_active: true,
  },
];

const forecast = {
  last_payday: "2026-07-10",
  next_payday: "2026-08-10",
  opening_balance_pln: 100000,
  projected_balance_before_next_payday_pln: 250000,
  safe_daily_limit_pln: 25000,
  lowest_balance_pln: 50000,
  days: [{ date: "2026-08-01", projected_balance_pln: 100000 }],
  suggestions: [],
  budgets: {
    total_budget_pln: 200000,
    total_spent_pln: 50000,
    remaining_pln: 150000,
  },
};

describe("FinanceCashflow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hooks.useAccounts.mockReturnValue({
      data: accounts,
      isLoading: false,
      isError: false,
    });
    hooks.useCategories.mockReturnValue({
      data: categories,
      isLoading: false,
      isError: false,
    });
    hooks.useCashflowSettings.mockReturnValue({
      data: settings,
      isLoading: false,
      isError: false,
    });
    hooks.useScheduledFinanceItems.mockReturnValue({
      data: items,
      isLoading: false,
      isError: false,
    });
    hooks.useCashflowForecast.mockReturnValue({
      data: forecast,
      isLoading: false,
      isError: false,
    });
    hooks.useUpdateCashflowSettings.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useCreateScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useUpdateScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useDeleteScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
    hooks.useConfirmScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    });
  });

  it("pokazuje tylko konta budżetowe jako konto wypłaty", () => {
    render(<FinanceCashflow />);

    expect(
      screen.getByRole("heading", { name: "Płynność" }),
    ).toBeInTheDocument();

    const paydayAccount = screen.getByLabelText("Konto wypłaty");
    expect(
      within(paydayAccount).getByRole("option", { name: "Rachunek główny" }),
    ).toBeInTheDocument();
    expect(
      within(paydayAccount).queryByRole("option", { name: "Karta firmowa" }),
    ).not.toBeInTheDocument();
  });

  it("chowa pole kwoty dla metody last_actual", () => {
    render(<FinanceCashflow />);

    expect(screen.getByLabelText("Kwota (PLN)")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Metoda kwoty"), {
      target: { value: "last_actual" },
    });

    expect(screen.queryByLabelText("Kwota (PLN)")).not.toBeInTheDocument();
  });

  it("wyłącza przycisk potwierdzenia dla niekwalifikującej się sugestii", () => {
    hooks.useCashflowForecast.mockReturnValue({
      data: {
        ...forecast,
        suggestions: [
          {
            scheduled_item_id: "item-1",
            name: "Czynsz",
            type: "expense",
            due_date: "2099-01-01",
            amount_pln: 250000,
            status: "due",
            included_in_forecast: true,
            actual_transaction_id: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
    });

    render(<FinanceCashflow />);

    expect(screen.getByRole("button", { name: "Potwierdź" })).toBeDisabled();
  });

  it("otwiera dialog dla pozycji due-today i wywołuje confirm z id", () => {
    const confirmMutate = vi.fn();
    hooks.useConfirmScheduledFinanceItem.mockReturnValue({
      mutate: confirmMutate,
      isPending: false,
      error: null,
    });
    hooks.useCashflowForecast.mockReturnValue({
      data: {
        ...forecast,
        suggestions: [
          {
            scheduled_item_id: "item-1",
            name: "Czynsz",
            type: "expense",
            due_date: "2000-01-01",
            amount_pln: 250000,
            status: "due",
            included_in_forecast: true,
            actual_transaction_id: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
    });

    render(<FinanceCashflow />);

    fireEvent.click(screen.getByRole("button", { name: "Potwierdź" }));

    const confirmButton = screen.getByRole("button", {
      name: "Potwierdź i zapisz transakcję",
    });
    expect(confirmButton).toBeInTheDocument();

    fireEvent.click(confirmButton);

    expect(confirmMutate).toHaveBeenCalledTimes(1);
    expect(confirmMutate.mock.calls[0][0]).toBe("item-1");
  });

  it("wypełnia pola formularza przy przejściu z trybu tworzenia do edycji", () => {
    render(<FinanceCashflow />);

    expect(screen.getByLabelText("Nazwa")).toHaveValue("");

    fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));

    expect(screen.getByLabelText("Nazwa")).toHaveValue("Czynsz");
    expect(
      (screen.getByLabelText("Dzień (1-28)") as HTMLInputElement).value,
    ).toBe("5");
    expect(screen.getByLabelText("Typ")).toHaveValue("expense");
    expect(screen.getByLabelText("Typ")).toBeDisabled();
    expect(screen.getByLabelText("Kwota (PLN)")).toHaveValue("2500.00");
    expect(
      screen.getByRole("button", { name: "Zapisz zmiany" }),
    ).toBeInTheDocument();
  });

  it("dialog jest dostępny i przywraca focus do wyzwalacza", () => {
    hooks.useCashflowForecast.mockReturnValue({
      data: {
        ...forecast,
        suggestions: [
          {
            scheduled_item_id: "item-1",
            name: "Czynsz",
            type: "expense",
            due_date: "2000-01-01",
            amount_pln: 250000,
            status: "due",
            included_in_forecast: true,
            actual_transaction_id: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
    });

    render(<FinanceCashflow />);

    const trigger = screen.getByRole("button", { name: "Potwierdź" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "confirm-item-title");
    expect(
      screen.getByRole("heading", { name: "Potwierdź pozycję" }),
    ).toHaveAttribute("id", "confirm-item-title");
    expect(dialog).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("wyłącza dezaktywację i usunięcie w trakcie mutacji", () => {
    hooks.useUpdateScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      error: null,
      variables: { id: "item-1" },
    });
    hooks.useDeleteScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: true,
      error: null,
      variables: "item-1",
    });

    render(<FinanceCashflow />);

    expect(screen.getByRole("button", { name: "Dezaktywuj" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Usuń" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edytuj" })).toBeEnabled();
  });

  it("pokazuje błąd mutacji inline przy pozycji", () => {
    hooks.useDeleteScheduledFinanceItem.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: {
        response: { data: { detail: "Nie udało się usunąć pozycji." } },
      },
      variables: "item-1",
    });

    render(<FinanceCashflow />);

    expect(
      screen.getByText("Nie udało się usunąć pozycji."),
    ).toBeInTheDocument();
  });

  it("nie zamienia pustych pól liczbowych na 0", () => {
    render(<FinanceCashflow />);

    const paydayDay = screen.getByLabelText(
      "Dzień wypłaty",
    ) as HTMLInputElement;
    const dueDay = screen.getByLabelText("Dzień (1-28)") as HTMLInputElement;

    fireEvent.change(paydayDay, { target: { value: "" } });
    fireEvent.change(dueDay, { target: { value: "" } });

    expect(paydayDay.value).toBe("");
    expect(dueDay.value).toBe("");
  });
});
