import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useAccounts,
  useBudgetStatus,
  useCashflowForecast,
  useFinancialSummary,
  useTransactions,
  type Account,
  type FinancialPeriod,
} from "../api/finance";
import { formatPLN } from "../lib/format";
import { formatCalendarDate } from "../lib/date";
import { TRANSACTION_TYPES } from "../lib/transactionSearch";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { MonthPicker } from "../components/finance/MonthPicker";
import { QueryFeedback } from "../components/QueryFeedback";

export function Finances() {
  const [period, setPeriod] = useState<FinancialPeriod>(() => ({
    month: new Date().getMonth() + 1,
    year: new Date().getFullYear(),
  }));
  const [scope, setScope] = useState<"all" | "budget">("all");
  const navigate = useNavigate();
  const accounts = useAccounts();
  const summary = useFinancialSummary(period);
  const cashflow = useCashflowForecast();
  const latest = useTransactions({ limit: 5 });
  const budgets = useBudgetStatus(period);
  const active = (accounts.data ?? []).filter((a) => a.is_active !== false);
  const balance =
    scope === "all"
      ? summary.data?.balance_all_pln
      : summary.data?.balance_budget_pln;
  return (
    <div className="finance-overview max-w-6xl">
      <header className="finance-page-heading">
        <div>
          <h1>Twoje finanse</h1>
          <p>Saldo, codzienne wydatki i spokojny plan na kolejne dni.</p>
        </div>
        <MonthPicker period={period} onChange={setPeriod} />
      </header>
      <FinanceTabs />
      <div className="finance-primary-grid">
        <section className="card balance-surface">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="finance-caption">
              {scope === "all" ? "Łączne saldo kont" : "Saldo kont budżetowych"}
            </p>
            <div className="finance-segment" aria-label="Zakres salda">
              {(
                [
                  ["all", "Wszystkie"],
                  ["budget", "Budżetowe"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={scope === id}
                  onClick={() => setScope(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <QueryFeedback
            loading={summary.isLoading}
            error={summary.isError}
            errorMessage="Nie udało się pobrać podsumowania finansowego."
            onRetry={summary.refetch}
          >
            <p className="finance-balance" aria-label="Łączne saldo kont">
              {balance === undefined ? "—" : formatPLN(balance)}{" "}
              <span>PLN</span>
            </p>
            <p className="finance-caption">
              Bieżąca wartość księgowa · nie wynik wybranego miesiąca
            </p>
            <div className="finance-quick-actions">
              {(
                [
                  ["expense", "Wydatek", "+"],
                  ["income", "Przychód", "↓"],
                  ["transfer", "Transfer", "⇄"],
                ] as const
              ).map(([type, label, glyph]) => (
                <button
                  key={type}
                  className={
                    type === "expense" ? "btn-primary" : "btn-secondary"
                  }
                  type="button"
                  onClick={() =>
                    navigate(`/finances/transactions?create=${type}`)
                  }
                >
                  <span aria-hidden="true">{glyph}</span> {label}
                </button>
              ))}
            </div>
            <div className="finance-period-totals">
              <div>
                <small>Przychody · konta budżetowe</small>
                <strong>
                  {summary.data
                    ? formatPLN(summary.data.income_total_pln)
                    : "—"}{" "}
                  PLN
                </strong>
              </div>
              <div>
                <small>Wydatki · konta budżetowe</small>
                <strong>
                  {summary.data
                    ? formatPLN(summary.data.expense_total_pln)
                    : "—"}{" "}
                  PLN
                </strong>
              </div>
            </div>
          </QueryFeedback>
        </section>
        <section
          className="card finance-runway"
          aria-label="Prognoza do wypłaty"
        >
          <QueryFeedback
            loading={cashflow.isLoading}
            error={cashflow.isError}
            errorMessage="Nie udało się pobrać prognozy płynności."
            onRetry={cashflow.refetch}
          >
            <p className="finance-caption">
              Prognoza do wypłaty
              {cashflow.data?.next_payday
                ? ` · ${formatCalendarDate(cashflow.data.next_payday)}`
                : ""}
            </p>
            <h2 className="finance-forecast-amount">
              {cashflow.data
                ? formatPLN(
                    cashflow.data.projected_balance_before_next_payday_pln,
                  )
                : "—"}{" "}
              PLN
            </h2>
            <p className="finance-caption">
              Saldo kont budżetowych po uwzględnieniu planowanych operacji.
            </p>
            {cashflow.data?.days?.length ? (
              <ForecastLine days={cashflow.data.days} />
            ) : (
              <p className="py-5 text-sm">Brak dziennego przebiegu prognozy.</p>
            )}
            <div className="finance-runway-footer">
              <div>
                <small>Orientacyjnie dziennie</small>
                <strong>
                  {cashflow.data
                    ? formatPLN(cashflow.data.safe_daily_limit_pln)
                    : "—"}{" "}
                  PLN
                </strong>
              </div>
              <Link to="/finances/cashflow">Przejdź do płynności →</Link>
            </div>
          </QueryFeedback>
        </section>
      </div>
      <section className="my-6" aria-label="Twoje konta">
        <QueryFeedback
          loading={accounts.isLoading}
          error={accounts.isError}
          errorMessage="Nie udało się pobrać kont."
          onRetry={accounts.refetch}
        >
          <div className="finance-account-strip">
            {active.map((a) => (
              <Link
                key={a.id}
                to={`/finances/transactions?account_id=${encodeURIComponent(a.id)}`}
                className="finance-account-chip"
              >
                <span className="finance-bank-mark" aria-hidden="true">
                  {(a.bank_name || a.name).slice(0, 1).toUpperCase()}
                </span>
                <span>
                  <small>
                    {a.bank_name ? `${a.bank_name} · ${a.name}` : a.name}
                  </small>
                  <strong>{sourceBalance(a)}</strong>
                  {a.currency !== "PLN" ? (
                    <small>
                      Wartość księgowa: {formatPLN(a.balance_pln)} PLN
                    </small>
                  ) : null}
                </span>
              </Link>
            ))}
          </div>
          {active.length === 0 ? (
            <p className="text-sm text-gray-500">
              Brak aktywnych kont. Dodaj konto w ustawieniach.
            </p>
          ) : null}
        </QueryFeedback>
      </section>
      <div className="finance-primary-grid">
        <section className="card">
          <div className="finance-section-heading">
            <div>
              <h2>Ostatnie transakcje</h2>
              <p>Twoja codzienność w jednym miejscu</p>
            </div>
            <Link to="/finances/transactions">Cała historia →</Link>
          </div>
          <QueryFeedback
            loading={latest.isLoading}
            error={latest.isError}
            errorMessage="Nie udało się pobrać ostatnich transakcji."
            onRetry={latest.refetch}
          >
            {latest.data?.length ? (
              <ul className="finance-recent-list">
                {latest.data.map((t) => {
                  const leg = t.postings.find((p) => p.account_id !== null);
                  return (
                    <li key={t.id}>
                      <Link
                        to={`/finances/transactions?detail=${encodeURIComponent(t.id)}`}
                      >
                        <span
                          className="finance-transaction-mark"
                          aria-hidden="true"
                        >
                          {t.type === "transfer" || t.type === "exchange"
                            ? "⇄"
                            : t.description.slice(0, 1).toUpperCase()}
                        </span>
                        <span className="min-w-0 flex-1">
                          <strong>{t.description}</strong>
                          <small>
                            {formatCalendarDate(t.transaction_date)} ·{" "}
                            {TRANSACTION_TYPES[t.type]}
                          </small>
                        </span>
                        <span className="finance-transaction-amount">
                          {leg
                            ? `${leg.direction === "credit" ? "+" : "−"}${formatPLN(leg.source_amount)} ${leg.source_currency}`
                            : "Kwota niedostępna"}
                          {t.type === "transfer" ? (
                            <small>Transfer własny</small>
                          ) : null}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-gray-500">
                Brak ostatnich transakcji.
              </p>
            )}
          </QueryFeedback>
        </section>
        <section className="card">
          <div className="finance-section-heading">
            <div>
              <h2>Budżet miesiąca</h2>
              <p>Limity i podlimity, bez podwójnego liczenia</p>
            </div>
            <Link to="/finances/budgets">Szczegóły →</Link>
          </div>
          <QueryFeedback
            loading={budgets.isLoading}
            error={budgets.isError}
            errorMessage="Nie udało się pobrać budżetu."
            onRetry={budgets.refetch}
          >
            {budgets.data?.items.slice(0, 3).map((b) => (
              <Link
                key={b.category_id}
                className="finance-budget-preview"
                to={`/finances/transactions?category_id=${encodeURIComponent(b.category_id)}&include_descendants=true&budget_accounts_only=true&date_from=${period.year}-${String(period.month).padStart(2, "0")}-01&date_to=${period.year}-${String(period.month).padStart(2, "0")}-${new Date(period.year!, period.month!, 0).getDate()}`}
              >
                <span>{b.name}</span>
                <strong>{formatPLN(b.spent_pln)} PLN</strong>
                <progress
                  aria-label={`Wykorzystanie budżetu ${b.name}`}
                  value={Math.max(0, b.spent_pln)}
                  max={Math.max(1, b.budget_amount_pln)}
                />
                <small>z {formatPLN(b.budget_amount_pln)} PLN</small>
              </Link>
            ))}
            {!budgets.data?.items.length ? (
              <p className="text-sm text-gray-500">
                Brak zdefiniowanych limitów.
              </p>
            ) : null}
            <div className="finance-budget-remaining">
              <small>Pozostało w całym budżecie</small>
              <strong>
                {budgets.data?.remaining_pln === undefined
                  ? "—"
                  : `${formatPLN(budgets.data.remaining_pln)} PLN`}
              </strong>
              <Link to="/settings/finances/budgets">Ustawienia limitów →</Link>
            </div>
          </QueryFeedback>
        </section>
      </div>
      <div className="finance-footer">
        <span>Konta budżetowe · konta informacyjne</span>
        <Link to="/settings/finances/accounts">Ustawienia kont</Link>
      </div>
    </div>
  );
}

function sourceBalance(a: Account): string {
  if (a.balance_source !== undefined)
    return `${formatPLN(a.balance_source)} ${a.currency}`;
  return `${formatPLN(a.balance_pln)} PLN${a.currency === "PLN" ? "" : " · wartość księgowa"}`;
}

function ForecastLine({
  days,
}: {
  days: Array<{ date: string; projected_balance_pln: number }>;
}) {
  const values = days.map((d) => d.projected_balance_pln);
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const points = days
    .map(
      (d, i) =>
        `${days.length === 1 ? 50 : (i / (days.length - 1)) * 100},${90 - ((d.projected_balance_pln - min) / range) * 75}`,
    )
    .join(" ");
  return (
    <figure className="finance-forecast-chart">
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        role="img"
        aria-label="Prognozowany przebieg salda"
      >
        <polyline
          points={points}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <figcaption>
        <span>{formatCalendarDate(days[0].date)}</span>
        <span>{formatCalendarDate(days[days.length - 1].date)}</span>
      </figcaption>
    </figure>
  );
}
