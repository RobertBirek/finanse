import type { AxiosError } from "axios";
import { useEffect, useState } from "react";
import {
  splitAccounts,
  useAccountTransactions,
  useDeleteTransaction,
  useUpdateTransaction,
  type Account,
  type Transaction,
} from "../../api/finance";
import { formatPLN } from "../../lib/format";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

type AccountTransactionsProps = {
  accounts: Account[];
};

export function AccountTransactions({ accounts }: AccountTransactionsProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const groups = splitAccounts(accounts);
  const selected =
    accounts.find((account) => account.id === selectedId) ?? null;
  const transactions = useAccountTransactions(selectedId);

  if (accounts.length === 0) {
    return (
      <p className="card py-8 text-center text-sm text-gray-500">Brak kont.</p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="card lg:col-span-1">
        <AccountGroup
          title="Konta budżetowe"
          accounts={groups.budget}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        {groups.informational.length > 0 ? (
          <div className="mt-6 border-t border-gray-800 pt-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-white">
                Konta informacyjne
              </h2>
              <span className="text-xs text-gray-500">wyłączone z analiz</span>
            </div>
            <AccountList
              accounts={groups.informational}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
        ) : null}
      </div>

      <div className="lg:col-span-2">
        {selected ? (
          <section className="card">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  {selected.name}
                </h2>
                <p className="text-sm text-gray-500">
                  {selected.type} · {selected.currency}
                </p>
              </div>
              <p
                className={`shrink-0 text-xl font-bold ${selected.balance_pln >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatPLN(selected.balance_pln)} PLN
              </p>
            </div>
            <h3 className="mb-3 text-sm font-medium text-gray-400">
              Transakcje
            </h3>
            <TransactionList
              accountId={selected.id}
              transactions={transactions.data}
              loading={transactions.isLoading}
              error={transactions.isError}
            />
          </section>
        ) : (
          <div className="card flex min-h-[200px] items-center justify-center">
            <p className="text-sm text-gray-500">
              Wybierz konto, aby zobaczyć transakcje.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function AccountGroup({
  title,
  accounts,
  selectedId,
  onSelect,
}: {
  title: string;
  accounts: Account[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-white">{title}</h2>
      {accounts.length === 0 ? (
        <p className="py-2 text-sm text-gray-500">Brak kont budżetowych.</p>
      ) : (
        <AccountList
          accounts={accounts}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      )}
    </section>
  );
}

function AccountList({
  accounts,
  selectedId,
  onSelect,
}: {
  accounts: Account[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  return (
    <div className="space-y-1">
      {accounts.map((account) => (
        <button
          key={account.id}
          type="button"
          onClick={() =>
            onSelect(selectedId === account.id ? null : account.id)
          }
          className={`flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors ${
            selectedId === account.id
              ? "border-advisor-500/30 bg-advisor-500/20"
              : "border-transparent bg-gray-800/50 hover:bg-gray-800"
          }`}
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">
              {account.name}
            </p>
            <p className="text-xs text-gray-500">
              {account.type} · {account.currency}
            </p>
          </div>
          <p
            className={`ml-2 shrink-0 font-mono text-sm font-medium ${account.balance_pln >= 0 ? "text-green-400" : "text-red-400"}`}
          >
            {formatPLN(account.balance_pln)} PLN
          </p>
        </button>
      ))}
    </div>
  );
}

function TransactionList({
  accountId,
  transactions,
  loading,
  error,
}: {
  accountId: string;
  transactions: Transaction[] | undefined;
  loading: boolean;
  error: boolean;
}) {
  const updateMutation = useUpdateTransaction();
  const deleteMutation = useDeleteTransaction();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDescription, setEditDescription] = useState("");
  const [editDate, setEditDate] = useState("");

  const updateError = apiErrorDetail(updateMutation.error);
  const deleteError = apiErrorDetail(deleteMutation.error);

  useEffect(() => {
    if (
      updateMutation.isSuccess &&
      updateMutation.variables?.id === editingId
    ) {
      setEditingId(null);
    }
  }, [updateMutation.isSuccess, updateMutation.variables, editingId]);

  function startEdit(transaction: Transaction) {
    setEditingId(transaction.id);
    setEditDescription(transaction.description);
    setEditDate(transaction.transaction_date);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  function saveEdit(transaction: Transaction) {
    updateMutation.mutate({
      id: transaction.id,
      transaction_date: editDate,
      description: editDescription,
    });
  }

  function removeTransaction(transaction: Transaction) {
    if (window.confirm(`Usunąć transakcję "${transaction.description}"?`)) {
      deleteMutation.mutate(transaction.id);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="py-4 text-sm text-red-400">
        Nie udało się pobrać transakcji.
      </p>
    );
  }

  if (!transactions || transactions.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-500">
        Brak transakcji dla tego konta.
      </p>
    );
  }

  return (
    <div className="space-y-1">
      {transactions.map((transaction) => {
        const posting = transaction.postings.find(
          (item) => item.account_id === accountId,
        );
        const isIncome = posting?.direction === "credit";
        const amount = posting?.source_amount ?? 0;
        const isEditing = editingId === transaction.id;
        const isUpdating =
          updateMutation.isPending &&
          updateMutation.variables?.id === transaction.id;
        const isDeleting =
          deleteMutation.isPending &&
          deleteMutation.variables === transaction.id;
        const rowUpdateError =
          updateMutation.variables?.id === transaction.id ? updateError : null;
        const rowDeleteError =
          deleteMutation.variables === transaction.id ? deleteError : null;

        if (isEditing) {
          return (
            <div
              key={transaction.id}
              className="rounded bg-gray-800/30 p-2.5 transition-colors hover:bg-gray-800/50"
            >
              <div className="mb-2 flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-gray-200">
                    {transaction.description}
                  </p>
                  <p className="text-xs text-gray-500">
                    {new Date(transaction.transaction_date).toLocaleDateString(
                      "pl-PL",
                    )}{" "}
                    · {transaction.type}
                  </p>
                </div>
                <p
                  className={`shrink-0 font-mono text-sm font-medium ${isIncome ? "text-green-400" : "text-red-400"}`}
                >
                  {isIncome ? "+" : "−"}
                  {formatPLN(amount)} PLN
                </p>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor={`transaction-description-${transaction.id}`}
                    className="mb-1 block text-xs text-gray-400"
                  >
                    Opis
                  </label>
                  <input
                    id={`transaction-description-${transaction.id}`}
                    type="text"
                    value={editDescription}
                    onChange={(event) => setEditDescription(event.target.value)}
                    className="w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-white"
                  />
                </div>
                <div>
                  <label
                    htmlFor={`transaction-date-${transaction.id}`}
                    className="mb-1 block text-xs text-gray-400"
                  >
                    Data
                  </label>
                  <input
                    id={`transaction-date-${transaction.id}`}
                    type="date"
                    value={editDate}
                    onChange={(event) => setEditDate(event.target.value)}
                    className="w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-white"
                  />
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => saveEdit(transaction)}
                  disabled={isUpdating}
                  className="btn-primary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Zapisz
                </button>
                <button
                  type="button"
                  onClick={cancelEdit}
                  disabled={isUpdating}
                  className="btn-secondary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Anuluj
                </button>
              </div>
              {rowUpdateError ? (
                <p className="mt-2 text-xs text-red-400">{rowUpdateError}</p>
              ) : null}
            </div>
          );
        }

        return (
          <div
            key={transaction.id}
            className="flex items-center justify-between gap-4 rounded bg-gray-800/30 p-2.5 transition-colors hover:bg-gray-800/50"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-gray-200">
                {transaction.description}
              </p>
              <p className="text-xs text-gray-500">
                {new Date(transaction.transaction_date).toLocaleDateString(
                  "pl-PL",
                )}{" "}
                · {transaction.type}
              </p>
            </div>
            <p
              className={`shrink-0 font-mono text-sm font-medium ${isIncome ? "text-green-400" : "text-red-400"}`}
            >
              {isIncome ? "+" : "−"}
              {formatPLN(amount)} PLN
            </p>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => startEdit(transaction)}
                disabled={isDeleting}
                className="btn-secondary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                Edytuj
              </button>
              <button
                type="button"
                onClick={() => removeTransaction(transaction)}
                disabled={isDeleting}
                className="btn-danger px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                Usuń
              </button>
            </div>
            {rowDeleteError ? (
              <p className="w-full text-xs text-red-400">{rowDeleteError}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
