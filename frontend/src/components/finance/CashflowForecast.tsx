import type { CashflowForecast as CashflowForecastData } from "../../api/finance";
import { formatPLN } from "../../lib/format";
import { CashflowMetric } from "./SummaryCard";

type CashflowForecastProps = {
  forecast?: CashflowForecastData;
  loading: boolean;
  error: boolean;
};

export function CashflowForecast({
  forecast,
  loading,
  error,
}: CashflowForecastProps) {
  if (loading) {
    return (
      <div className="mb-6 flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="card mb-6 text-sm text-red-400">
        Nie udało się pobrać prognozy płynności.
      </p>
    );
  }

  if (!forecast) {
    return (
      <p className="card mb-6 text-sm text-gray-500">
        Brak prognozy płynności.
      </p>
    );
  }

  return (
    <section className="card mb-6 border border-advisor-500/30 bg-gradient-to-br from-advisor-500/10 via-gray-900 to-gray-900">
      <div className="mb-6 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-advisor-300">
            Płynność
          </p>
          <h2 className="text-lg font-semibold text-white">
            Prognoza do wypłaty
          </h2>
        </div>
        <p className="text-xs text-gray-400">Prognoza, bez księgowania</p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <CashflowMetric
          label="Przed wypłatą"
          amount={forecast.projected_balance_before_next_payday_pln}
        />
        <CashflowMetric
          label="Najniższe saldo"
          amount={forecast.lowest_balance_pln}
        />
        <CashflowMetric
          label="Bezpiecznie dziennie"
          amount={forecast.safe_daily_limit_pln}
          neutral
        />
        <div>
          <p className="text-xs text-gray-400">Następna wypłata</p>
          <p className="mt-1 text-xl font-bold text-white">
            {new Date(forecast.next_payday).toLocaleDateString("pl-PL")}
          </p>
        </div>
      </div>
      <div className="mt-6 border-t border-gray-800 pt-4">
        <h3 className="mb-3 text-sm font-medium text-gray-400">
          Salda dzienne
        </h3>
        <ul className="space-y-1">
          {forecast.days.map((day) => (
            <li
              key={day.date}
              className="flex items-center justify-between text-sm"
            >
              <span className="text-gray-300">
                {new Date(day.date).toLocaleDateString("pl-PL")}
              </span>
              <span
                className={`font-mono ${day.projected_balance_pln >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatPLN(day.projected_balance_pln)} PLN
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
