import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConditionalRecurringObligations } from "./ConditionalRecurringObligations";

const hooks = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("../../api/finance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/finance")>()),
  useCreateConditionalRecurringObligation: () => ({
    mutate: hooks.create,
    isPending: false,
    error: null,
  }),
  useUpdateConditionalRecurringObligation: () => ({
    mutate: hooks.update,
    isPending: false,
    error: null,
  }),
  useDeleteConditionalRecurringObligation: () => ({
    mutate: hooks.remove,
    isPending: false,
    error: null,
  }),
}));

const accounts = [
  {
    id: "usd",
    name: "USD",
    type: "checking",
    currency: "USD",
    is_active: true,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "pln",
    name: "PLN",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

describe("ConditionalRecurringObligations", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits an explicitly unknown fallback amount without inventing a value", () => {
    render(
      <ConditionalRecurringObligations
        accounts={accounts}
        items={[]}
        loading={false}
      />,
    );

    fireEvent.change(screen.getByLabelText("Nazwa zobowiązania"), {
      target: { value: "Subscription" },
    });
    fireEvent.change(screen.getByLabelText("Klucz warunku"), {
      target: { value: "subscription_eligible" },
    });
    const accountsSelects = screen.getAllByLabelText("Konto");
    fireEvent.change(accountsSelects[0], { target: { value: "usd" } });
    fireEvent.change(accountsSelects[1], { target: { value: "pln" } });
    fireEvent.change(screen.getAllByLabelText("Kwota")[0], {
      target: { value: "20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Dodaj zobowiązanie" }));

    expect(hooks.create).toHaveBeenCalledWith(
      expect.objectContaining({
        primary_amount_minor: 2000,
        fallback_amount_minor: null,
        fallback_currency: "PLN",
      }),
      expect.anything(),
    );
  });

  it("lets the user explicitly resolve the condition without asserting payment", () => {
    render(
      <ConditionalRecurringObligations
        accounts={accounts}
        loading={false}
        items={[
          {
            id: "obligation",
            name: "Subscription",
            condition_key: "subscription_eligible",
            condition_state: "unknown",
            cadence: "monthly",
            due_month: null,
            due_day: 15,
            primary_account_id: "usd",
            primary_amount_minor: 2000,
            primary_currency: "USD",
            fallback_account_id: "pln",
            fallback_amount_minor: null,
            fallback_currency: "PLN",
            is_active: true,
          },
        ]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Stan warunku"), {
      target: { value: "not_satisfied" },
    });

    expect(hooks.update).toHaveBeenCalledWith({
      id: "obligation",
      condition_state: "not_satisfied",
    });
  });
});
