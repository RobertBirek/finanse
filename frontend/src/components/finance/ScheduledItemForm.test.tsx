import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScheduledItemForm } from "./ScheduledItemForm";
import { categorySelectFixture } from "../../test/categoryFixtures";

const hooks = vi.hoisted(() => ({
  useCreateScheduledFinanceItem: vi.fn(),
  useUpdateScheduledFinanceItem: vi.fn(),
}));

vi.mock("../../api/finance", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/finance")>();
  return { ...original, ...hooks };
});

const accounts = [
  {
    id: "pln-budget",
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
    id: "eur-budget",
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
    id: "usd-inactive",
    name: "Konto USD",
    type: "checking",
    currency: "USD",
    is_active: false,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

const categories: Array<{
  id: string;
  name: string;
  parent_id: string | null;
  type: "income" | "expense" | "transfer";
  is_active: boolean;
}> = [
  {
    id: "c-expense",
    name: "Czynsz",
    parent_id: null,
    type: "expense",
    is_active: true,
  },
  {
    id: "c-inactive",
    name: "Stara kategoria",
    parent_id: null,
    type: "expense",
    is_active: false,
  },
];

describe("ScheduledItemForm", () => {
  it("keeps full archived-parent paths after filtering scheduled expense choices", () => {
    render(
      <ScheduledItemForm
        mode="create"
        accounts={accounts}
        categories={categorySelectFixture}
      />,
    );
    expect(
      within(screen.getByLabelText("Kategoria"))
        .getAllByRole("option")
        .slice(1)
        .map((option) => option.textContent),
    ).toEqual(["Auto - Zamek", "Dom - Gaz", "Dom - Woda"]);
  });
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

  it("shows only active PLN budget accounts in the account selector", () => {
    render(
      <ScheduledItemForm
        mode="create"
        accounts={accounts}
        categories={categories}
      />,
    );

    const accountSelect = screen.getByLabelText("Konto");
    expect(
      within(accountSelect).getByRole("option", { name: "Rachunek główny" }),
    ).toBeInTheDocument();
    expect(
      within(accountSelect).queryByRole("option", { name: "Konto EUR" }),
    ).not.toBeInTheDocument();
    expect(
      within(accountSelect).queryByRole("option", { name: "Konto USD" }),
    ).not.toBeInTheDocument();
  });

  it("locks the currency field to PLN", () => {
    render(
      <ScheduledItemForm
        mode="create"
        accounts={accounts}
        categories={categories}
      />,
    );

    expect(screen.getByLabelText("Waluta")).toHaveValue("PLN");
  });

  it("collects an annual anchor month and safe due day", () => {
    const mutate = vi.fn();
    hooks.useCreateScheduledFinanceItem.mockReturnValue({
      mutate,
      isPending: false,
      error: null,
    });
    render(
      <ScheduledItemForm
        mode="create"
        accounts={accounts}
        categories={categories}
      />,
    );

    fireEvent.change(screen.getByLabelText("Nazwa"), {
      target: { value: "Amazon" },
    });
    fireEvent.change(screen.getByLabelText("Konto"), {
      target: { value: "pln-budget" },
    });
    fireEvent.change(screen.getByLabelText("Kategoria"), {
      target: { value: "c-expense" },
    });
    fireEvent.change(screen.getByLabelText("Częstotliwość"), {
      target: { value: "annual" },
    });
    fireEvent.change(screen.getByLabelText("Miesiąc"), {
      target: { value: "11" },
    });
    fireEvent.change(screen.getByLabelText("Dzień (1-28)"), {
      target: { value: "28" },
    });
    fireEvent.change(screen.getByLabelText("Kwota (PLN)"), {
      target: { value: "69" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj pozycję" }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        cadence: "annual",
        due_month: 11,
        due_day: 28,
        fixed_amount_pln: 6900,
      }),
      expect.any(Object),
    );
  });

  it("hides inactive categories while keeping the type filter", () => {
    render(
      <ScheduledItemForm
        mode="create"
        accounts={accounts}
        categories={categories}
      />,
    );

    const categorySelect = screen.getByLabelText("Kategoria");
    expect(
      within(categorySelect).getByRole("option", { name: "Czynsz" }),
    ).toBeInTheDocument();
    expect(
      within(categorySelect).queryByRole("option", { name: "Stara kategoria" }),
    ).not.toBeInTheDocument();
  });
});
