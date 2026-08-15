import { useCashflowForecast } from "../api/finance";
import { CashflowMetric } from "../components/finance/SummaryCard";

export function FinanceCashflow() {
  const cashflow = useCashflowForecast();

  return (
    <div className="max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold text-white">Płynność</h1>
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
          <div className="mb-6 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-advisor-300">
                Cykl wypłaty
              </p>
              <h2 className="text-lg font-semibold text-white">
                Płynność do{" "}
                {new Date(cashflow.data.next_payday).toLocaleDateString(
                  "pl-PL",
                )}
              </h2>
            </div>
            <p className="text-xs text-gray-400">Prognoza, bez księgowania</p>
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
