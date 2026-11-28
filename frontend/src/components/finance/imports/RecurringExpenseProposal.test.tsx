import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecurringExpenseProposal } from "./RecurringExpenseProposal";

const hooks = vi.hoisted(() => ({
  useRecurringExpenseProposal: vi.fn(),
  useCreateScheduledFinanceItem: vi.fn(),
  useUpdateScheduledFinanceItem: vi.fn(),
}));

vi.mock("../../../api/bankImports", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../../../api/bankImports")>();
  return {
    ...original,
    useRecurringExpenseProposal: hooks.useRecurringExpenseProposal,
  };
});

vi.mock("../../../api/finance", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../../../api/finance")>();
  return {
    ...original,
    useCreateScheduledFinanceItem: hooks.useCreateScheduledFinanceItem,
    useUpdateScheduledFinanceItem: hooks.useUpdateScheduledFinanceItem,
  };
});

const accounts = [
  {
    id: "account-pln",
    name: "Rachunek PLN",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];
const categories = [
  {
    id: "category-expense",
    name: "Subskrypcje",
    parent_id: null,
    type: "expense" as const,
    is_active: true,
  },
];

describe("RecurringExpenseProposal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
  });

  it("fetches evidence only after an explicit request and requires a separate schedule submission", async () => {
    const mutate = vi.fn();
    hooks.useRecurringExpenseProposal.mockReturnValue({
      data: undefined,
      error: null,
      isPending: false,
      mutate,
    });
    const { rerender } = render(
      <RecurringExpenseProposal
        batchId="batch-a"
        rowId="row-a"
        accountId="account-pln"
        accounts={accounts}
        categories={categories}
      />,
    );

    expect(mutate).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Sprawdź sugestię cykliczności" }),
    );
    expect(mutate).toHaveBeenCalledWith({
      batchId: "batch-a",
      rowId: "row-a",
      accountId: "account-pln",
    });

    hooks.useRecurringExpenseProposal.mockReturnValue({
      data: {
        status: "proposed",
        reason: null,
        proposal: {
          target: "new_schedule",
          merchant: "netflix.com",
          frequency: "monthly",
          amount_kind: "stable",
          amount_minor: -4900,
          currency: "PLN",
          formal_deadline: null,
        },
        evidence: [
          {
            strong_identity: "velo:ref-1",
            economic_identity: "velo:ref-1",
            source: "bank_import",
            occurred_on: "2026-01-03",
            amount_minor: -4900,
            currency: "PLN",
          },
          {
            strong_identity: "velo:ref-2",
            economic_identity: "velo:ref-2",
            source: "bank_import",
            occurred_on: "2026-02-03",
            amount_minor: -4900,
            currency: "PLN",
          },
          {
            strong_identity: "velo:ref-3",
            economic_identity: "velo:ref-3",
            source: "bank_import",
            occurred_on: "2026-03-03",
            amount_minor: -4900,
            currency: "PLN",
          },
        ],
      },
      error: null,
      isPending: false,
      mutate,
    });
    rerender(
      <RecurringExpenseProposal
        batchId="batch-a"
        rowId="row-a"
        accountId="account-pln"
        accounts={accounts}
        categories={categories}
      />,
    );

    expect(screen.getByText("3 potwierdzone obserwacje")).toBeVisible();
    expect(screen.getByText(/Nie wyznaczono terminu/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Dodaj pozycję" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Przygotuj edytowalny formularz harmonogramu",
      }),
    );
    expect(screen.getByLabelText("Nazwa")).toHaveValue("netflix.com");
    expect(screen.getByLabelText("Dzień (1-28)")).toHaveValue(null);

    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "category-expense" },
    });
    fireEvent.change(screen.getByLabelText("Dzień (1-28)"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj pozycję" }));

    await waitFor(() =>
      expect(hooks.useCreateScheduledFinanceItem().mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "netflix.com",
          account_id: "account-pln",
          category_id: "category-expense",
          cadence: "monthly",
          due_day: 3,
          fixed_amount_pln: 4900,
        }),
        expect.any(Object),
      ),
    );
  });

  it("keeps an actionable retry after a failed evidence read", () => {
    const mutate = vi.fn();
    hooks.useRecurringExpenseProposal.mockReturnValue({
      data: undefined,
      error: new Error("Synthetic read failure"),
      isPending: false,
      mutate,
    });
    render(
      <RecurringExpenseProposal
        batchId="batch-a"
        rowId="row-a"
        accountId="account-pln"
        accounts={accounts}
        categories={categories}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Sprawdź sugestię cykliczności" }),
    );
    expect(
      screen.getByRole("button", { name: "Ponów sprawdzenie sugestii" }),
    ).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: "Ponów sprawdzenie sugestii" }),
    );
    expect(mutate).toHaveBeenCalledTimes(2);
  });
});
