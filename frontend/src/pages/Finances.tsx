import { useState } from "react";
import {
  buildCategoryTree,
  cashflowStatusLabel,
  splitAccounts,
  useAccounts,
  useAccountTransactions,
  useCashflowForecast,
  useCategorySummary,
  useFinancialSummary,
  useScheduledFinanceItems,
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
  const { data: categorySummary } = useCategorySummary();
  const { data: cashflow } = useCashflowForecast();
  const { data: scheduledItems } = useScheduledFinanceItems();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: acctTxns, isLoading: txLoading } =
    useAccountTransactions(selectedId);

  const selected = accounts?.find((a) => a.id === selectedId) ?? null;
  const accountGroups = splitAccounts(accounts ?? []);
  const categoryGroups = categorySummary
    ? buildCategoryTree(categorySummary)
    : [];

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

      {cashflow && (
        <section className="card mb-8 border border-advisor-500/30 bg-gradient-to-br from-advisor-500/10 via-gray-900 to-gray-900">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between mb-5">
            <div>
              <p className="text-xs font-medium tracking-wide text-advisor-300 uppercase">
                Cykl wypłaty
              </p>
              <h2 className="text-lg font-semibold text-white">
                Płynność do{" "}
                {new Date(cashflow.next_payday).toLocaleDateString("pl-PL")}
              </h2>
            </div>
            <p className="text-xs text-gray-400">Prognoza, bez księgowania</p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs text-gray-400">Przed wypłatą</p>
              <p
                className={`mt-1 text-xl font-bold ${cashflow.projected_balance_before_next_payday_pln >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatPLN(cashflow.projected_balance_before_next_payday_pln)}{" "}
                PLN
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Najniższe saldo</p>
              <p
                className={`mt-1 text-xl font-bold ${cashflow.lowest_balance_pln >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatPLN(cashflow.lowest_balance_pln)} PLN
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Bezpiecznie dziennie</p>
              <p className="mt-1 text-xl font-bold text-white">
                {formatPLN(cashflow.safe_daily_limit_pln)} PLN
              </p>
            </div>
          </div>
        </section>
      )}

      {scheduledItems && (
        <section className="card mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">
              Planowane wpływy i wydatki
            </h2>
            <span className="text-xs text-gray-500">miesięcznie</span>
          </div>
          {scheduledItems.length === 0 ? (
            <p className="text-sm text-gray-500">Brak zaplanowanych pozycji</p>
          ) : (
            <div className="divide-y divide-gray-800">
              {scheduledItems.map((item) => {
                const suggestion = cashflow?.suggestions.find(
                  (entry) => entry.scheduled_item_id === item.id,
                );
                const amount = suggestion?.amount_pln ?? item.fixed_amount_pln;
                return (
                  <div
                    key={item.id}
                    className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-200 truncate">
                        {item.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {item.type === "income" ? "Wpływ" : "Wydatek"}{" "}
                        {item.due_day}. dnia
                        {suggestion &&
                          ` · ${cashflowStatusLabel(suggestion.status)}`}
                      </p>
                    </div>
                    <p
                      className={`shrink-0 font-mono text-sm ${item.type === "income" ? "text-green-400" : "text-red-400"}`}
                    >
                      {amount === null
                        ? "Brak kwoty"
                        : `${formatPLN(amount)} PLN`}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {categorySummary && (
        <section className="card mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">
            Wydatki według kategorii
          </h2>
          {categoryGroups.length === 0 ? (
            <p className="text-gray-500 text-sm">
              Brak wydatków skategoryzowanych w tym miesiącu
            </p>
          ) : (
            <div className="space-y-3">
              {categoryGroups.map((group) => (
                <div key={group.category_id}>
                  <div className="flex items-center justify-between text-sm font-medium text-gray-200">
                    <span>{group.name}</span>
                    <span className="font-mono">
                      {formatPLN(group.total_pln)} PLN
                    </span>
                  </div>
                  {group.children.length > 0 && (
                    <div className="mt-1 space-y-1 border-l border-gray-700 pl-3">
                      {group.children.map((category) => (
                        <div
                          key={category.category_id}
                          className="flex items-center justify-between text-sm text-gray-400"
                        >
                          <span>{category.name}</span>
                          <span className="font-mono">
                            {formatPLN(category.total_pln)} PLN
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="card">
            {accounts?.length === 0 ? (
              <p className="text-gray-500 text-sm py-4 text-center">
                Brak kont
              </p>
            ) : (
              <div className="space-y-6">
                {[
                  {
                    title: "Konta budżetowe",
                    accounts: accountGroups.budget,
                    label: null,
                  },
                  ...(accountGroups.informational.length > 0
                    ? [
                        {
                          title: "Pozabudżetowe / informacyjne",
                          accounts: accountGroups.informational,
                          label: "poza analizami",
                        },
                      ]
                    : []),
                ].map((section) => (
                  <section key={section.title}>
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-lg font-semibold text-white">
                        {section.title}
                      </h2>
                      {section.label && (
                        <span className="text-xs text-gray-500">
                          {section.label}
                        </span>
                      )}
                    </div>
                    {section.accounts.length === 0 ? (
                      <p className="text-gray-500 text-sm py-2">
                        Brak kont budżetowych
                      </p>
                    ) : (
                      <div className="space-y-1">
                        {section.accounts.map((a) => (
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
                  </section>
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
