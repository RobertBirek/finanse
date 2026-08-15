import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScheduledItemForm } from "./ScheduledItemForm";

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
}> = [{ id: "c-expense", name: "Czynsz", parent_id: null, type: "expense" }];

describe("ScheduledItemForm", () => {
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
});
