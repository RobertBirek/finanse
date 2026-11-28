import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Account, Category } from "../../../api/finance";
import { ImportGroupEditor } from "./ImportGroupEditor";
import { RecurringExpenseProposal } from "./RecurringExpenseProposal";
import { rowFixture } from "../../../test/bankImportFixtures";

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

const accounts: Account[] = [
  {
    id: "account-pln",
    name: "Konto PLN",
    type: "checking",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];
const categories: Category[] = [
  {
    id: "category-expense",
    name: "Subskrypcje",
    parent_id: null,
    type: "expense",
    is_active: true,
  },
];

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
      evidence: [],
    },
    error: null,
    isPending: false,
    mutate: vi.fn(),
  });
});

it("submits an explicit schedule without submitting the surrounding import decision", () => {
  const onSave = vi.fn();
  const row = rowFixture({
    bank_fields: {
      ...rowFixture().bank_fields!,
      bank_reference: "bank-ref",
    },
  });

  function Harness() {
    const [candidate, setCandidate] = useState<{
      rowId: string;
      accountId: string;
    } | null>(null);
    return (
      <>
        <ImportGroupEditor
          batchId="batch-a"
          rows={[row]}
          accounts={accounts}
          categories={categories}
          sources={[]}
          pending={false}
          onSave={onSave}
          onRecurringCandidateChange={setCandidate}
        />
        {candidate ? (
          <RecurringExpenseProposal
            batchId="batch-a"
            rowId={candidate.rowId}
            accountId={candidate.accountId}
            accounts={accounts}
            categories={categories}
          />
        ) : null}
      </>
    );
  }

  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Harness />
    </QueryClientProvider>,
  );

  fireEvent.change(screen.getByLabelText("Rachunek źródłowy"), {
    target: { value: "account-pln" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Sprawdź sugestię cykliczności" }),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "Przygotuj edytowalny formularz harmonogramu",
    }),
  );
  fireEvent.change(
    screen.getByLabelText("Kategoria", { selector: "#item-category" }),
    {
      target: { value: "category-expense" },
    },
  );
  fireEvent.change(screen.getByLabelText("Dzień (1-28)"), {
    target: { value: "3" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj pozycję" }));

  expect(hooks.useCreateScheduledFinanceItem().mutate).toHaveBeenCalled();
  expect(onSave).not.toHaveBeenCalled();
});
