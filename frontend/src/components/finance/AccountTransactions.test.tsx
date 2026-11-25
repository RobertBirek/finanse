import {
  fireEvent,
  render as renderView,
  screen,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountTransactions, TransactionList } from "./AccountTransactions";

it("exposes one unified edit action under More and keeps unavailable actions visible", () => {
  useUpdateTransaction.mockReturnValue({ mutate: vi.fn() });
  useDeleteTransaction.mockReturnValue({ mutate: vi.fn() });
  const edit = vi.fn();
  render(
    <TransactionList
      transactions={[incomeTransaction]}
      loading={false}
      error={false}
      onEdit={edit}
      onDetails={vi.fn()}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Szczegóły: Wynagrodzenie" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Więcej: Wynagrodzenie" }),
  );
  const actions = within(
    screen.getByRole("group", { name: "Więcej: Wynagrodzenie" }),
  );
  const openingBalance = actions.getByRole("button", {
    name: "Bilans otwarcia konta",
  });
  expect(openingBalance).toHaveAttribute("aria-disabled", "true");
  expect(openingBalance).toHaveAttribute("aria-description");
  fireEvent.click(actions.getByRole("button", { name: "Edytuj transakcję" }));
  expect(edit).toHaveBeenCalledWith("tx-income");
});

function render(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderView(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const { useAccountTransactions, useUpdateTransaction, useDeleteTransaction } =
  vi.hoisted(() => ({
    useAccountTransactions: vi.fn(),
    useUpdateTransaction: vi.fn(),
    useDeleteTransaction: vi.fn(),
  }));

vi.mock("../../api/finance", () => ({
  splitAccounts: (accounts: Array<{ is_budget_account: boolean }>) => ({
    budget: accounts.filter((account) => account.is_budget_account),
    informational: accounts.filter((account) => !account.is_budget_account),
  }),
  useAccountTransactions,
  useUpdateTransaction,
  useDeleteTransaction,
}));

const accounts = [
  {
    id: "budget-account",
    name: "Rachunek główny",
    type: "bank",
    currency: "PLN",
    is_active: true,
    is_budget_account: true,
    balance_pln: 123456,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "info-account",
    name: "Karta firmowa",
    type: "card",
    currency: "PLN",
    is_active: true,
    is_budget_account: false,
    balance_pln: 45678,
    opened_at: "2026-01-01",
    closed_at: null,
  },
  {
    id: "inactive-account",
    name: "Stare konto",
    type: "bank",
    currency: "PLN",
    is_active: false,
    is_budget_account: true,
    balance_pln: 0,
    opened_at: "2026-01-01",
    closed_at: null,
  },
];

const incomeTransaction = {
  id: "tx-income",
  transaction_date: "2026-08-14",
  description: "Wynagrodzenie",
  type: "income" as const,
  is_pending: false,
  project_id: null,
  source: "manual",
  postings: [
    {
      id: "p-income",
      transaction_id: "tx-income",
      account_id: "budget-account",
      category_id: null,
      source_amount: 500000,
      source_currency: "PLN",
      base_amount_pln: 500000,
      fx_rate: 1,
      is_budget_impact: true,
      direction: "credit" as const,
    },
  ],
};

const expenseTransaction = {
  id: "tx-expense",
  transaction_date: "2026-08-14",
  description: "Czynsz",
  type: "expense" as const,
  is_pending: false,
  project_id: null,
  source: "manual",
  postings: [
    {
      id: "p-expense",
      transaction_id: "tx-expense",
      account_id: "budget-account",
      category_id: null,
      source_amount: 12300,
      source_currency: "PLN",
      base_amount_pln: 12300,
      fx_rate: 1,
      is_budget_impact: true,
      direction: "debit" as const,
    },
  ],
};

describe("AccountTransactions", () => {
  let updateMutate: ReturnType<typeof vi.fn>;
  let deleteMutate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate = vi.fn();
    deleteMutate = vi.fn();
    useAccountTransactions.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    useUpdateTransaction.mockReturnValue({
      mutate: updateMutate,
      isPending: false,
      error: null,
      variables: undefined,
    });
    useDeleteTransaction.mockReturnValue({
      mutate: deleteMutate,
      isPending: false,
      error: null,
      variables: undefined,
    });
  });

  it("separates informational accounts and loads transactions after selection", () => {
    render(<AccountTransactions accounts={accounts} />);

    expect(screen.getByText("Konta budżetowe")).toBeInTheDocument();
    expect(screen.getByText("Konta informacyjne")).toBeInTheDocument();
    expect(screen.getByText("wyłączone z analiz")).toBeInTheDocument();
    expect(screen.queryByText("Stare konto")).not.toBeInTheDocument();
    expect(screen.getByText(/1.*234,56 PLN/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(useAccountTransactions).toHaveBeenLastCalledWith("budget-account");
    expect(
      screen.getByText("Brak transakcji dla tego konta."),
    ).toBeInTheDocument();
  });

  it("renders income as a green plus and expense as a red minus", () => {
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction, expenseTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(screen.getByText("+5000,00 PLN")).toHaveClass("text-green-400");
    expect(screen.getByText("−123,00 PLN")).toHaveClass("text-red-400");
  });

  it("shows batch-projected history locks and only verified provenance links", () => {
    useAccountTransactions.mockReturnValue({
      data: [
        {
          ...expenseTransaction,
          id: "tx-protected",
          source: "bank_import",
          ledger_editable: false,
          ledger_lock_reason: "Dowód importu chroni tożsamość księgową.",
          import_batch_id: "batch-1",
          financial_document_ids: ["bill-1"],
        },
      ],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Powód blokady edycji" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Więcej:/ }));
    const lock = screen.getByRole("button", { name: "Powód blokady edycji" });
    expect(lock).toHaveAttribute(
      "aria-description",
      "Dowód importu chroni tożsamość księgową.",
    );
    fireEvent.click(lock);
    expect(
      screen.getByText("Dowód importu chroni tożsamość księgową."),
    ).toHaveAttribute("data-open", "true");
    expect(
      screen.getByRole("button", { name: "Import bankowy" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Powiązana z fakturą" }),
    ).toBeInTheDocument();
  });

  it("does not invent history links when the batch projection has no targets", () => {
    useAccountTransactions.mockReturnValue({
      data: [
        {
          ...expenseTransaction,
          id: "tx-locked-no-link",
          ledger_editable: false,
          ledger_lock_reason:
            "Płatność pożyczki jest powiązana z harmonogramem.",
          import_batch_id: null,
          financial_document_ids: [],
        },
      ],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    fireEvent.click(screen.getByRole("button", { name: /^Więcej:/ }));
    expect(
      screen.getByRole("button", { name: "Powód blokady edycji" }),
    ).toHaveAttribute(
      "aria-description",
      "Płatność pożyczki jest powiązana z harmonogramem.",
    );
    expect(
      screen.queryByRole("button", { name: "Import bankowy" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Powiązana z fakturą" }),
    ).not.toBeInTheDocument();
  });

  it("puts date editing and deletion behind the transaction's disclosure", () => {
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    expect(
      screen.getByRole("button", { name: "Opis i oznaczenia" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Usuń transakcję" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Więcej: Wynagrodzenie" }),
    );
    expect(
      screen.getByRole("button", { name: "Edytuj datę" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Usuń transakcję" }),
    ).toBeInTheDocument();
  });

  it("labels BO explicitly and links to the account instead of ordinary ledger mutations", () => {
    useAccountTransactions.mockReturnValue({
      data: [
        {
          ...incomeTransaction,
          type: "opening_balance",
          source: "opening_balance",
          description: "Start",
        },
      ],
      isLoading: false,
      isError: false,
    });
    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));
    expect(screen.getByText(/Bilans otwarcia/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "BO konta" })).toHaveAttribute(
      "href",
      "/settings/finances/accounts?edit=budget-account",
    );
    for (const name of [
      "Opis i oznaczenia",
      "Więcej: Start",
      "Usuń transakcję",
    ])
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  });

  it("keeps legacy date editing separate and never overwrites a source description", () => {
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    fireEvent.click(
      screen.getByRole("button", { name: "Więcej: Wynagrodzenie" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Edytuj datę" }));

    expect(screen.queryByLabelText("Opis")).not.toBeInTheDocument();
    const dateInput = screen.getByLabelText("Data");
    expect(dateInput).toHaveValue("2026-08-14");

    fireEvent.change(dateInput, { target: { value: "2026-08-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(updateMutate).toHaveBeenCalledWith({
      id: "tx-income",
      transaction_date: "2026-08-20",
    });
  });

  it("deletes a transaction after confirmation and skips it without", () => {
    useAccountTransactions.mockReturnValue({
      data: [incomeTransaction],
      isLoading: false,
      isError: false,
    });

    render(<AccountTransactions accounts={accounts} />);
    fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));

    const openConfirm = () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Więcej: Wynagrodzenie" }),
      );
      fireEvent.click(screen.getByRole("button", { name: "Usuń transakcję" }));
      return within(screen.getByRole("dialog", { name: "Usuń transakcję" }));
    };
    const confirmation = openConfirm();
    expect(deleteMutate).not.toHaveBeenCalled();
    fireEvent.click(
      confirmation.getByRole("button", { name: "Usuń transakcję" }),
    );
    expect(deleteMutate).toHaveBeenCalledWith(
      "tx-income",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    fireEvent.click(confirmation.getByRole("button", { name: "Anuluj" }));

    fireEvent.click(openConfirm().getByRole("button", { name: "Anuluj" }));
    expect(deleteMutate).toHaveBeenCalledTimes(1);
  });
});

describe("foreign currency presentation", () => {
  it.each(["EUR", "USD"])(
    "keeps %s source amount separate from the PLN equivalent in view and edit modes",
    (currency) => {
      useAccountTransactions.mockReturnValue({
        data: [
          {
            ...expenseTransaction,
            postings: [
              {
                ...expenseTransaction.postings[0],
                source_currency: currency,
                source_amount: 12345,
                base_amount_pln: 54321,
              },
            ],
          },
        ],
        isLoading: false,
        isError: false,
      });
      useUpdateTransaction.mockReturnValue({ mutate: vi.fn() });
      useDeleteTransaction.mockReturnValue({ mutate: vi.fn() });
      render(<AccountTransactions accounts={accounts} />);
      fireEvent.click(screen.getByRole("button", { name: /Rachunek główny/ }));
      expect(screen.getByText(`−123,45 ${currency}`)).toBeInTheDocument();
      expect(screen.getByText("Równowartość: 543,21 PLN")).toBeInTheDocument();
      expect(screen.queryByText("−123,45 PLN")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /^Więcej:/ }));
      fireEvent.click(screen.getByRole("button", { name: "Edytuj datę" }));
      expect(screen.getByText(`−123,45 ${currency}`)).toBeInTheDocument();
    },
  );
});
