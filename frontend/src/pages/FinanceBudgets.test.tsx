import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FinanceBudgets } from "./FinanceBudgets";

const hooks = vi.hoisted(() => ({
  useBudgetStatus: vi.fn(),
  useBudgets: vi.fn(),
  useCreateBudget: vi.fn(),
  useUpdateBudget: vi.fn(),
  useDeleteBudget: vi.fn(),
  useCategories: vi.fn(),
  useCategorySummary: vi.fn(),
}));

vi.mock("../api/finance", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/finance")>();
  return { ...original, ...hooks };
});

vi.mock("../components/finance/CategorySpendTree", () => ({
  CategorySpendTree: ({ title }: { title: string }) => <h2>{title}</h2>,
}));

const categories = [
  { id: "c-food", name: "Jedzenie", parent_id: null, type: "expense" },
  { id: "c-rent", name: "Czynsz", parent_id: null, type: "expense" },
  { id: "c-salary", name: "Wynagrodzenie", parent_id: null, type: "income" },
];

const budgets = [{ id: "b1", category_id: "c-food", amount_pln: 100000 }];

function statusItems(items: unknown[]) {
  return {
    data: {
      month: new Date().getMonth() + 1,
      year: new Date().getFullYear(),
      items,
    },
    isLoading: false,
    isError: false,
  };
}

describe("FinanceBudgets", () => {
  const createMutate = vi.fn();
  const updateMutate = vi.fn();
  const deleteMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    hooks.useBudgetStatus.mockReturnValue(
      statusItems([
        {
          category_id: "c-food",
          name: "Jedzenie",
          parent_id: null,
          budget_amount_pln: 100000,
          spent_pln: 80000,
          remaining_pln: 20000,
        },
      ]),
    );
    hooks.useBudgets.mockReturnValue({
      data: budgets,
      isLoading: false,
      isError: false,
    });
    hooks.useCreateBudget.mockReturnValue({
      mutate: createMutate,
      isPending: false,
      error: null,
    });
    hooks.useUpdateBudget.mockReturnValue({
      mutate: updateMutate,
      isPending: false,
      error: null,
    });
    hooks.useDeleteBudget.mockReturnValue({
      mutate: deleteMutate,
      isPending: false,
      error: null,
    });
    hooks.useCategories.mockReturnValue({
      data: categories,
      isLoading: false,
      isError: false,
    });
    hooks.useCategorySummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });
  });

  it("renders the budget row with name, limit, spent and remaining", () => {
    render(<FinanceBudgets />);

    expect(screen.getByRole("heading", { name: "Budżet" })).toBeInTheDocument();
    expect(screen.getByText("Jedzenie")).toBeInTheDocument();
    expect(screen.getByText(/1.*000,00 PLN/)).toBeInTheDocument();
    expect(screen.getByText(/800,00 PLN/)).toBeInTheDocument();
    expect(screen.getByText(/200,00 PLN/)).toBeInTheDocument();
  });

  it("shows the over state with a red bar and an exceeded message", () => {
    hooks.useBudgetStatus.mockReturnValue(
      statusItems([
        {
          category_id: "c-food",
          name: "Jedzenie",
          parent_id: null,
          budget_amount_pln: 100000,
          spent_pln: 150000,
          remaining_pln: -50000,
        },
      ]),
    );

    render(<FinanceBudgets />);

    expect(screen.getByText(/Przekroczono o 500,00 PLN/)).toBeInTheDocument();
    expect(screen.getByTestId("budget-progress-c-food")).toHaveClass(
      "bg-red-500",
    );
  });

  it("filters the add form to unbudgeted expense categories", () => {
    render(<FinanceBudgets />);

    const categorySelect = screen.getByLabelText("Kategoria");
    expect(
      within(categorySelect).getByRole("option", { name: "Czynsz" }),
    ).toBeInTheDocument();
    expect(
      within(categorySelect).queryByRole("option", { name: "Jedzenie" }),
    ).not.toBeInTheDocument();
    expect(
      within(categorySelect).queryByRole("option", { name: "Wynagrodzenie" }),
    ).not.toBeInTheDocument();
  });

  it("submits a new budget with category_id and amount in grosze", () => {
    render(<FinanceBudgets />);

    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "c-rent" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj budżet" }));

    expect(createMutate).toHaveBeenCalledWith(
      { category_id: "c-rent", amount_pln: 50000 },
      expect.anything(),
    );
  });

  it("deletes a budget after confirmation", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<FinanceBudgets />);

    fireEvent.click(
      screen.getByRole("button", { name: "Usuń budżet Jedzenie" }),
    );

    expect(confirmSpy).toHaveBeenCalledWith(
      expect.stringContaining("Jedzenie"),
    );
    expect(deleteMutate).toHaveBeenCalledWith("b1");
  });

  it("renders the unbudgeted expenses section", () => {
    render(<FinanceBudgets />);

    expect(
      screen.getByRole("heading", { name: "Wydatki bez budżetu" }),
    ).toBeInTheDocument();
  });

  it("updates a budget limit inline", () => {
    render(<FinanceBudgets />);

    fireEvent.click(
      screen.getByRole("button", { name: "Edytuj limit Jedzenie" }),
    );
    fireEvent.change(screen.getByLabelText("Limit (PLN)"), {
      target: { value: "1200" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(updateMutate).toHaveBeenCalledWith(
      { id: "b1", amount_pln: 120000 },
      expect.anything(),
    );
  });
});
