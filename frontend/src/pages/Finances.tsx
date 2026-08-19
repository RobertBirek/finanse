import { Link } from "react-router-dom";
import {
  splitAccounts,
  useAccounts,
  useCashflowForecast,
  useFinancialSummary,
} from "../api/finance";
import { CashflowMetric, SummaryCard } from "../components/finance/SummaryCard";
import { formatPLN } from "../lib/format";

export function Finances() {
  const accounts = useAccounts();
  const summary = useFinancialSummary();
  const cashflow = useCashflowForecast();
  const accountGroups = splitAccounts(
    (accounts.data ?? []).filter((account) => account.is_active !== false),
  );

  return (
    <div className="max-w-6xl">
      <h1 className="mb-6 text-2xl font-bold text-white">Finanse</h1>

      {summary.isLoading ? (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
        </div>
      ) : summary.isError ? (
        <p className="card mb-6 text-sm text-red-400">
          Nie udało się pobrać podsumowania finansowego.
        </p>
      ) : summary.data ? (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <SummaryCard
            label="Przychody"
            amount={summary.data.income_total_pln}
            tone="income"
          />
          <SummaryCard
            label="Wydatki"
            amount={summary.data.expense_total_pln}
            tone="expense"
          />
          <SummaryCard
            label="Bilans"
            amount={summary.data.net_total_pln}
            tone="net"
          />
        </div>
      ) : (
        <p className="card mb-6 text-sm text-gray-500">
          Brak podsumowania finansowego dla bieżącego miesiąca.
        </p>
      )}

      <section className="mb-6">
        <h2 className="mb-4 text-lg font-semibold text-white">Konta</h2>
        {accounts.isLoading ? (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
          </div>
        ) : accounts.isError ? (
          <p className="card text-sm text-red-400">
            Nie udało się pobrać kont.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <AccountCard
              title="Konta budżetowe"
              accounts={accountGroups.budget}
            />
            <AccountCard
              title="Konta informacyjne"
              description="wyłączone z analiz"
              accounts={accountGroups.informational}
            />
          </div>
        )}
      </section>

      {cashflow.isLoading ? (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
        </div>
      ) : cashflow.isError ? (
        <p className="card text-sm text-red-400">
          Nie udało się pobrać prognozy płynności.
        </p>
      ) : cashflow.data ? (
        <section className="card border border-advisor-500/30 bg-gradient-to-br from-advisor-500/10 via-gray-900 to-gray-900">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-advisor-300">
                Płynność
              </p>
              <h2 className="text-lg font-semibold text-white">
                Prognoza do wypłaty
              </h2>
            </div>
            <Link to="/finances/cashflow" className="btn-secondary self-start">
              Przejdź do płynności
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <CashflowMetric
              label="Przed wypłatą"
              amount={cashflow.data.projected_balance_before_next_payday_pln}
            />
            <CashflowMetric
              label="Najniższe saldo"
              amount={cashflow.data.lowest_balance_pln}
            />
            <CashflowMetric
              label="Bezpiecznie dziennie"
              amount={cashflow.data.safe_daily_limit_pln}
              neutral
            />
          </div>
        </section>
      ) : (
        <p className="card text-sm text-gray-500">Brak prognozy płynności.</p>
      )}
    </div>
  );
}

function AccountCard({
  title,
  description,
  accounts,
}: {
  title: string;
  description?: string;
  accounts: Array<{
    id: string;
    name: string;
    balance_pln: number;
  }>;
}) {
  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-white">{title}</h3>
        {description ? (
          <span className="text-xs text-gray-500">{description}</span>
        ) : null}
      </div>
      {accounts.length === 0 ? (
        <p className="py-2 text-sm text-gray-500">Brak kont.</p>
      ) : (
        <div className="space-y-2">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="flex items-center justify-between gap-4 text-sm"
            >
              <span className="truncate text-gray-200">{account.name}</span>
              <span
                className={`shrink-0 font-mono ${account.balance_pln >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatPLN(account.balance_pln)} PLN
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
