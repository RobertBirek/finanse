import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { localTodayIso } from "../../lib/date";
import { TransactionForm } from "./TransactionForm";

const hooks = vi.hoisted(() => ({
  useAccounts: vi.fn(),
  useCategories: vi.fn(),
  useCreateTransaction: vi.fn(),
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
];

describe("TransactionForm", () => {
  let mutate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mutate = vi.fn();
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
    fireEvent.click(screen.getByRole("button", { name: "Dodaj transakcję" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    const payload = mutate.mock.calls[0][0] as {
      type: string;
      description: string;
      date: string;
      postings: Array<{
        account_id: string | null;
        category_id: string | null;
        direction: string;
        base_amount_pln: number;
      }>;
    };

    expect(payload.type).toBe("expense");
    expect(payload.description).toBe("test");
    expect(payload.date).toBe(localTodayIso());

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
    fireEvent.click(screen.getByRole("button", { name: "Dodaj transakcję" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Podaj kwotę większą od 0.",
    );
    expect(mutate).not.toHaveBeenCalled();
  });
});
