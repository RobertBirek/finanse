import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { localTodayIso } from "../../lib/date";
import { TransactionForm } from "./TransactionForm";
import { categorySelectFixture } from "../../test/categoryFixtures";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useCreateTransaction: vi.fn(),
  useCreateExchange: vi.fn(),
  useCreateExpenseRefund: vi.fn(),
}));

vi.mock("../../api/finance", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/finance")>();
  return { ...original, ...hooks };
});

const accounts = [
  {
    id: "a1",
    name: "Rachunek a1",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 100000,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "a2",
    name: "Rachunek a2",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 50000,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "eur",
    name: "Konto EUR",
    type: "checking",
    currency: "EUR",
    is_active: true,
    is_budget_account: true,
    balance_pln: 200000,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "usd",
    name: "Konto USD (nieaktywne)",
    type: "checking",
    currency: "PLN",
    is_active: false,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

const categories = [
  { id: "c1", name: "Czynsz", parent_id: null, type: "expense" as const },
  { id: "c2", name: "Wynagrodzenie", parent_id: null, type: "income" as const },
  {
    id: "c-inactive",
    name: "Stara kategoria",
    parent_id: null,
    type: "expense" as const,
    is_active: false,
  },
];

describe("TransactionForm", () => {
  it("keeps archived ancestors in labels even though they are not selectable", () => {
    hooks.useCategories.mockReturnValue({
      data: categorySelectFixture,
      isLoading: false,
      isError: false,
    });
    render(<TransactionForm />);
    expect(
      within(screen.getByLabelText("Kategoria"))
        .getAllByRole("option")
        .slice(1)
        .map((option) => option.textContent),
    ).toEqual(["Auto - Zamek", "Dom - Gaz", "Dom - Woda"]);
  });
  it("keeps Friday purchase and Monday booking separate without a conflicting legacy date", () => {
    render(<TransactionForm />);
    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "c1" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "100" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "Zakup" },
    });
    fireEvent.change(screen.getByLabelText("Data zakupu"), {
      target: { value: "2026-01-30" },
    });
    fireEvent.click(screen.getByLabelText("Księgowanie w dniu zakupu"));
    fireEvent.change(screen.getByLabelText("Data księgowania"), {
      target: { value: "2026-02-02" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));
    expect(mutate.mock.calls[0][0]).toMatchObject({
      purchase_date: "2026-01-30",
      booking_date: "2026-02-02",
    });
    expect(mutate.mock.calls[0][0]).not.toHaveProperty("transaction_date");
  });
  let mutate: ReturnType<typeof vi.fn>;
  let exchangeMutate: ReturnType<typeof vi.fn>;
  let refundMutate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mutate = vi.fn();
    exchangeMutate = vi.fn();
    refundMutate = vi.fn();
    hooks.useCreateExpenseRefund.mockReturnValue({
      mutate: refundMutate,
      isPending: false,
      error: null,
    });
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
    hooks.useCreateTransaction.mockReturnValue({
      mutate,
      isPending: false,
      error: null,
    });
    hooks.useCreateExchange.mockReturnValue({
      mutate: exchangeMutate,
      isPending: false,
      error: null,
    });
  });

  it("defaults to expense and adjusts fields when switching type", () => {
    render(<TransactionForm />);

    const typeSelect = screen.getByLabelText("Typ");
    expect(typeSelect).toHaveValue("expense");

    const categorySelect = screen.getByLabelText("Kategoria");
    expect(
      within(categorySelect).getByRole("option", { name: "Czynsz" }),
    ).toBeInTheDocument();
    expect(
      within(categorySelect).queryByRole("option", { name: "Stara kategoria" }),
    ).not.toBeInTheDocument();
    expect(
      within(categorySelect).queryByRole("option", { name: "Wynagrodzenie" }),
    ).not.toBeInTheDocument();

    fireEvent.change(typeSelect, { target: { value: "income" } });
    const incomeCategory = screen.getByLabelText("Kategoria");
    expect(
      within(incomeCategory).getByRole("option", { name: "Wynagrodzenie" }),
    ).toBeInTheDocument();
    expect(
      within(incomeCategory).queryByRole("option", { name: "Czynsz" }),
    ).not.toBeInTheDocument();

    fireEvent.change(typeSelect, { target: { value: "transfer" } });
    expect(screen.queryByLabelText("Kategoria")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Z konta")).toBeInTheDocument();
    expect(screen.getByLabelText("Na konto")).toBeInTheDocument();
  });

  it("records a positive refund in the expense category without sending postings or pretending it is income", () => {
    render(<TransactionForm />);
    expect(
      screen.getByRole("option", { name: "Zwrot wydatku" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "expense_refund" },
    });
    const category = screen.getByLabelText("Kategoria");
    expect(
      within(category).getByRole("option", { name: "Czynsz" }),
    ).toBeInTheDocument();
    expect(
      within(category).queryByRole("option", { name: "Wynagrodzenie" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Data zakupu")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "a1" },
    });
    fireEvent.change(category, { target: { value: "c1" } });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "150,25" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: " Zwrot części zakupów " },
    });
    fireEvent.change(screen.getByLabelText("Data operacji"), {
      target: { value: "2026-11-12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));
    expect(refundMutate.mock.calls[0][0]).toEqual({
      account_id: "a1",
      category_id: "c1",
      amount_minor: 15025,
      transaction_date: "2026-11-12",
      description: "Zwrot części zakupów",
    });
    expect(mutate).not.toHaveBeenCalled();
    expect(exchangeMutate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "income" },
    });
    expect(screen.getByLabelText("Kategoria")).toHaveValue("");
  });

  it.each(["0", "-1", "1.234"])(
    "rejects invalid refund amount %s before sending it",
    (amount) => {
      render(<TransactionForm />);
      fireEvent.change(screen.getByLabelText("Typ"), {
        target: { value: "expense_refund" },
      });
      fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
        target: { value: amount },
      });
      fireEvent.click(
        screen.getByRole("button", { name: "Zapisz transakcję" }),
      );
      expect(refundMutate).not.toHaveBeenCalled();
      expect(screen.getByText("Podaj kwotę większą od 0.")).toBeInTheDocument();
    },
  );

  it("shows refund errors and disables submission while refund is being recorded", () => {
    hooks.useCreateExpenseRefund.mockReturnValue({
      mutate: refundMutate,
      isPending: true,
      error: { response: { data: { detail: "Kategoria jest nieaktywna" } } },
    });
    render(<TransactionForm />);
    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "expense_refund" },
    });
    expect(screen.getByText("Kategoria jest nieaktywna")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Zapis/ })).toBeDisabled();
  });

  it("requires the refund date before sending the command", () => {
    render(<TransactionForm />);
    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "expense_refund" },
    });
    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "c1" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "Zwrot" },
    });
    fireEvent.change(screen.getByLabelText("Data operacji"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));
    expect(refundMutate).not.toHaveBeenCalled();
    expect(screen.getByText("Podaj datę zwrotu.")).toBeInTheDocument();
  });

  it("shows only active PLN accounts in the account selector", () => {
    render(<TransactionForm />);

    const accountSelect = screen.getByLabelText("Konto");
    expect(
      within(accountSelect).getByRole("option", { name: "Rachunek a1" }),
    ).toBeInTheDocument();
    expect(
      within(accountSelect).getByRole("option", { name: "Rachunek a2" }),
    ).toBeInTheDocument();
    expect(
      within(accountSelect).queryByRole("option", { name: "Konto EUR" }),
    ).not.toBeInTheDocument();
    expect(
      within(accountSelect).queryByRole("option", {
        name: "Konto USD (nieaktywne)",
      }),
    ).not.toBeInTheDocument();
  });

  it("submits an expense with correct postings", () => {
    render(<TransactionForm />);

    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "c1" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "25" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    const payload = mutate.mock.calls[0][0] as {
      type: string;
      description: string;
      purchase_date: string;
      booking_date: string;
      postings: Array<{
        account_id: string | null;
        category_id: string | null;
        direction: string;
        base_amount_pln: number;
      }>;
    };

    expect(payload.type).toBe("expense");
    expect(payload.description).toBe("test");
    expect(payload.purchase_date).toBe(localTodayIso());
    expect(payload.booking_date).toBe(localTodayIso());
    expect(payload).not.toHaveProperty("transaction_date");
    expect(payload).not.toHaveProperty("date");

    const debit = payload.postings.find((p) => p.direction === "debit");
    expect(debit?.account_id).toBe("a1");
    expect(debit?.base_amount_pln).toBe(2500);

    const credit = payload.postings.find((p) => p.direction === "credit");
    expect(credit?.category_id).toBe("c1");
    expect(credit?.base_amount_pln).toBe(2500);
  });

  it("shows a validation message and does not submit when amount is empty", () => {
    render(<TransactionForm />);

    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "c1" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Podaj kwotę większą od 0.",
    );
    expect(mutate).not.toHaveBeenCalled();
  });

  it("shows two account selects and optional rate without category for exchange", () => {
    render(<TransactionForm />);

    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "exchange" },
    });

    expect(screen.queryByLabelText("Kategoria")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Z konta")).toBeInTheDocument();
    expect(screen.getByLabelText("Na konto")).toBeInTheDocument();
    expect(screen.getByLabelText("Kurs (opcjonalnie)")).toBeInTheDocument();

    const fromSelect = screen.getByLabelText("Z konta");
    expect(
      within(fromSelect).getByRole("option", { name: "Konto EUR" }),
    ).toBeInTheDocument();
    expect(
      within(fromSelect).queryByRole("option", {
        name: "Konto USD (nieaktywne)",
      }),
    ).not.toBeInTheDocument();
  });

  it("submits an exchange without manual rate", () => {
    render(<TransactionForm />);

    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "exchange" },
    });
    fireEvent.change(screen.getByLabelText("Z konta"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Na konto"), {
      target: { value: "eur" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "43" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "wymiana" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));

    expect(exchangeMutate).toHaveBeenCalledTimes(1);
    expect(exchangeMutate.mock.calls[0][0]).toEqual({
      from_account_id: "a1",
      to_account_id: "eur",
      from_amount: 4300,
      transaction_date: localTodayIso(),
      description: "wymiana",
    });
  });

  it("submits an exchange with manual rate as float", () => {
    render(<TransactionForm />);

    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "exchange" },
    });
    fireEvent.change(screen.getByLabelText("Z konta"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Na konto"), {
      target: { value: "eur" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "43" },
    });
    fireEvent.change(screen.getByLabelText("Kurs (opcjonalnie)"), {
      target: { value: "4.3" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "wymiana" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));

    expect(exchangeMutate).toHaveBeenCalledTimes(1);
    expect(exchangeMutate.mock.calls[0][0]).toEqual(
      expect.objectContaining({ fx_rate: 4.3 }),
    );
  });

  it("shows a message and does not submit when both accounts are PLN", () => {
    render(<TransactionForm />);

    fireEvent.change(screen.getByLabelText("Typ"), {
      target: { value: "exchange" },
    });
    fireEvent.change(screen.getByLabelText("Z konta"), {
      target: { value: "a1" },
    });
    fireEvent.change(screen.getByLabelText("Na konto"), {
      target: { value: "a2" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "43" },
    });
    fireEvent.change(screen.getByLabelText("Opis"), {
      target: { value: "wymiana" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz transakcję" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Przewalutowanie wymaga jednego konta w PLN i drugiego w obcej walucie.",
    );
    expect(exchangeMutate).not.toHaveBeenCalled();
  });
});
