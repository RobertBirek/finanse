import { useState } from "react";
import {
  splitAccounts,
  useAccountTransactions,
  type Account,
  type Transaction,
} from "../../api/finance";
import { formatPLN } from "../../lib/format";

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
        const isIncome = posting?.direction === "debit";
        const amount = posting?.source_amount ?? 0;

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
          </div>
        );
      })}
    </div>
  );
}
