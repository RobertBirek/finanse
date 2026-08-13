import { useState } from "react";
import {
  useAccounts,
  useFinancialSummary,
  useAccountTransactions,
} from "../api/finance";
import type { Transaction } from "../api/finance";

const formatPLN = (amount: number) => {
  return new Intl.NumberFormat("pl-PL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount / 100);
};

export function Finances() {
  const { data: accounts } = useAccounts();
  const { data: summary } = useFinancialSummary();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: acctTxns, isLoading: txLoading } =
    useAccountTransactions(selectedId);

  const selected = accounts?.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-bold text-white mb-6">Finanse</h1>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Przychody</p>
            <p className="text-lg font-bold text-green-400">
              {formatPLN(summary.income_total_pln)} PLN
            </p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Wydatki</p>
            <p className="text-lg font-bold text-red-400">
              {formatPLN(summary.expense_total_pln)} PLN
            </p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Bilans</p>
            <p
              className={`text-lg font-bold ${summary.net_total_pln >= 0 ? "text-green-400" : "text-red-400"}`}
            >
              {formatPLN(summary.net_total_pln)} PLN
            </p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Okres</p>
            <p className="text-lg font-bold text-gray-200">
              {summary.month}.{summary.year}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">Konta</h2>
            {accounts?.length === 0 ? (
              <p className="text-gray-500 text-sm py-4 text-center">
                Brak kont
              </p>
            ) : (
              <div className="space-y-1">
                {accounts?.map((a) => (
                  <button
                    key={a.id}
                    onClick={() =>
                      setSelectedId(selectedId === a.id ? null : a.id)
                    }
                    className={`w-full flex items-center justify-between p-3 rounded-lg text-left transition-colors ${
                      selectedId === a.id
                        ? "bg-advisor-500/20 border border-advisor-500/30"
                        : "bg-gray-800/50 hover:bg-gray-800 border border-transparent"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white truncate">
                        {a.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {a.type} · {a.currency}
                      </p>
                    </div>
                    <p
                      className={`text-sm font-mono font-medium flex-shrink-0 ml-2 ${(a.balance_pln ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                    >
                      {formatPLN(a.balance_pln ?? 0)}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    {selected.name}
                  </h2>
                  <p className="text-sm text-gray-500">
                    {selected.type} · {selected.currency}
                  </p>
                </div>
                <p
                  className={`text-xl font-bold ${(selected.balance_pln ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  {formatPLN(selected.balance_pln ?? 0)} PLN
                </p>
              </div>

              <h3 className="text-sm font-medium text-gray-400 mb-3">
                Transakcje
              </h3>
              {txLoading ? (
                <div className="flex justify-center py-8">
                  <div className="w-6 h-6 border-2 border-advisor-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : acctTxns?.length === 0 ? (
                <p className="text-gray-500 text-sm py-4 text-center">
                  Brak transakcji dla tego konta
                </p>
              ) : (
                <div className="space-y-1">
                  {acctTxns?.map((tx: Transaction) => {
                    const myPosting = tx.postings?.find(
                      (p) => p.account_id === selected.id,
                    );
                    const amount = myPosting?.source_amount ?? 0;
                    const isIncome = myPosting?.direction === "debit";
                    return (
                      <div
                        key={tx.id}
                        className="flex items-center justify-between p-2.5 rounded bg-gray-800/30 hover:bg-gray-800/50 transition-colors"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-gray-200 truncate">
                            {tx.description}
                          </p>
                          <p className="text-xs text-gray-500">
                            {new Date(tx.transaction_date).toLocaleDateString(
                              "pl-PL",
                            )}{" "}
                            · {tx.type}
                          </p>
                        </div>
                        <p
                          className={`text-sm font-mono font-medium flex-shrink-0 ml-3 ${isIncome ? "text-green-400" : "text-red-400"}`}
                        >
                          {isIncome ? "+" : "\u2212"}
                          {formatPLN(amount)}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="card flex items-center justify-center min-h-[200px]">
              <p className="text-gray-500 text-sm">
                Wybierz konto z listy, aby zobaczyć szczegóły
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
