import { useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useAccounts,
  useCategories,
  useBudgetStatus,
  useCashflowForecast,
  useFinancialSummary,
  useTransactions,
  type Account,
  type CashflowDay,
  type CashflowForecast,
  type Transaction,
  type BudgetStatusItem,
} from "../api/finance";
import { formatPLN, formatPostingAmount } from "../lib/format";
import { categoryColorMap, entityColor } from "../lib/financeColors";
import { formatCalendarDate } from "../lib/date";
import {
  forecastExclusionLabel,
  hasPaydayExclusions,
} from "../lib/cashflowForecast";
import { TRANSACTION_TYPES } from "../lib/transactionSearch";
import { MonthPicker } from "../components/finance/MonthPicker";
import { AccountStrip } from "../components/finance/AccountStrip";
import { QueryFeedback } from "../components/QueryFeedback";
import { PageHeader } from "../components/PageHeader";
import {
  ExpenseDateBasis,
  TransactionDateLabel,
} from "../components/finance/TransactionDateLabel";
import {
  categoryTransactionsHref,
  financePeriodSearch,
  useFinancePeriod,
} from "../components/finance/useFinancePeriod";

export function Finances() {
  const [period, setPeriod] = useFinancePeriod();
  const [scope, setScope] = useState<"all" | "budget">("all");
  const navigate = useNavigate();
  const periodSearch = financePeriodSearch(period);
  const accounts = useAccounts();
  const categories = useCategories();
  const colors = categoryColorMap(categories.data ?? []);
  const summary = useFinancialSummary(period);
  const cashflow = useCashflowForecast();
  const latest = useTransactions({ limit: 5 });
  const budgets = useBudgetStatus(period);
  const accountsById = new Map(
    accounts.data?.map((account) => [account.id, account]),
  );
  const balance =
    scope === "all"
      ? summary.data?.balance_all_pln
      : summary.data?.balance_budget_pln;
  const balanceLabel =
    scope === "all" ? "Saldo aktywnych kont" : "Saldo kont budżetowych";
  const budgetPreview = (budgets.data?.items ?? [])
    .slice()
    .sort(compareBudgetPriority)
    .slice(0, 3);

  return (
    <div className="finance-overview page-workspace">
      <PageHeader title="Twoje finanse" />
      <div className="finance-primary-grid">
        <section className="card balance-surface" aria-label="Saldo bieżące">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h2 className="finance-caption">{balanceLabel}</h2>
            <div
              className="finance-segment"
              role="group"
              aria-label="Zakres salda"
            >
              <button
                type="button"
                aria-pressed={scope === "all"}
                onClick={() => setScope("all")}
              >
                Wszystkie
              </button>
              <button
                type="button"
                aria-pressed={scope === "budget"}
                onClick={() => setScope("budget")}
              >
                Budżetowe
              </button>
            </div>
          </div>
          <QueryFeedback
            loading={summary.isLoading}
            error={summary.isError}
            errorMessage="Nie udało się pobrać salda."
            onRetry={summary.refetch}
          >
            <output className="finance-balance" aria-label={balanceLabel}>
              {balance === undefined ? "—" : formatPLN(balance)}{" "}
              <span>PLN</span>
            </output>
            <p className="finance-caption">Bieżąca wartość księgowa</p>
          </QueryFeedback>
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
                className={type === "expense" ? "btn-primary" : "btn-secondary"}
                type="button"
                onClick={() =>
                  navigate(
                    `/finances/transactions${periodSearch}&create=${type}`,
                  )
                }
              >
                <span aria-hidden="true">{glyph}</span> {label}
              </button>
            ))}
          </div>
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
            {cashflow.data ? (
              <ForecastPreview
                forecast={cashflow.data}
                periodSearch={periodSearch}
              />
            ) : null}
          </QueryFeedback>
        </section>
      </div>
      <AccountStrip mode="links" periodSearch={periodSearch} />
      <section className="my-6" aria-labelledby="finance-month-heading">
        <div className="finance-section-heading flex-wrap">
          <h2 id="finance-month-heading">Podsumowanie miesiąca</h2>
          <MonthPicker period={period} onChange={setPeriod} />
        </div>
        <div className="finance-primary-grid">
          <section className="card">
            <h3 className="font-semibold">Konta budżetowe</h3>
            <QueryFeedback
              loading={summary.isLoading || summary.isPlaceholderData}
              error={summary.isError}
              errorMessage="Nie udało się pobrać podsumowania finansowego."
              onRetry={summary.refetch}
            >
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
            <ExpenseDateBasis />
          </section>
          <section className="card">
            <div className="finance-section-heading">
              <h3 className="font-semibold">Budżet miesiąca</h3>
              <Link to={`/finances/budgets${periodSearch}`}>
                Szczegóły budżetu →
              </Link>
            </div>
            <QueryFeedback
              loading={budgets.isLoading}
              error={budgets.isError}
              errorMessage="Nie udało się pobrać budżetu."
              onRetry={budgets.refetch}
            >
              {budgetPreview.map((budget) => (
                <Link
                  key={budget.category_id}
                  className="finance-budget-preview"
                  to={categoryTransactionsHref(period, budget.category_id)}
                >
                  <span>{budget.name}</span>
                  <strong>{formatPLN(budget.spent_pln)} PLN</strong>
                  <progress
                    aria-label={`Wykorzystanie budżetu ${budget.name}`}
                    value={Math.max(0, budget.spent_pln)}
                    max={Math.max(1, budget.budget_amount_pln)}
                    style={
                      {
                        "--finance-color":
                          colors.get(budget.category_id) ??
                          entityColor(budget.category_id),
                      } as CSSProperties
                    }
                  />
                  <small>z {formatPLN(budget.budget_amount_pln)} PLN</small>
                  {budget.remaining_pln < 0 ? (
                    <span className="finance-budget-overrun">
                      Przekroczono o {formatPLN(-budget.remaining_pln)} PLN
                    </span>
                  ) : null}
                </Link>
              ))}
              {budgetPreview.length ? (
                <div className="finance-budget-remaining">
                  <small>Pozostało w całym budżecie</small>
                  <strong>
                    {budgets.data?.remaining_pln === undefined
                      ? "—"
                      : `${formatPLN(budgets.data.remaining_pln)} PLN`}
                  </strong>
                  <Link to="/settings/finances/budgets">
                    Ustawienia limitów →
                  </Link>
                </div>
              ) : (
                <div className="space-y-2 text-sm">
                  <p className="text-gray-500">Brak zdefiniowanych limitów.</p>
                  <Link
                    className="inline-block underline"
                    to={`/settings/finances/budgets${periodSearch}#new-budget`}
                  >
                    Ustaw limity
                  </Link>
                </div>
              )}
            </QueryFeedback>
          </section>
        </div>
      </section>
      <section className="card">
        <div className="finance-section-heading">
          <h2>Ostatnie transakcje</h2>
          <Link to={`/finances/transactions${periodSearch}`}>
            Cała historia →
          </Link>
        </div>
        <QueryFeedback
          loading={latest.isLoading}
          error={latest.isError}
          errorMessage="Nie udało się pobrać ostatnich transakcji."
          onRetry={latest.refetch}
        >
          {latest.data?.length ? (
            <ul className="finance-recent-list">
              {latest.data.map((transaction) => (
                <RecentTransaction
                  key={transaction.id}
                  transaction={transaction}
                  accounts={accountsById}
                  colors={colors}
                  periodSearch={periodSearch}
                />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">Brak ostatnich transakcji.</p>
          )}
        </QueryFeedback>
      </section>
      <div className="finance-footer">
        <Link to="/settings/finances/accounts">Ustawienia kont</Link>
      </div>
    </div>
  );
}

function compareBudgetPriority(
  a: BudgetStatusItem,
  b: BudgetStatusItem,
): number {
  const overA = Math.max(0, -a.remaining_pln);
  const overB = Math.max(0, -b.remaining_pln);
  if (overA || overB) return overB - overA;
  return b.spent_pln / b.budget_amount_pln - a.spent_pln / a.budget_amount_pln;
}

function RecentTransaction({
  transaction,
  accounts,
  colors,
  periodSearch,
}: {
  transaction: Transaction;
  accounts: Map<string, Account>;
  colors: Map<string, string>;
  periodSearch: string;
}) {
  const { id, postings, type } = transaction;
  const description =
    transaction.effective_description || transaction.description;
  const movesFunds = type === "transfer" || type === "exchange";
  const accountLegs = postings.filter((posting) => posting.account_id);
  const debit = accountLegs.find((posting) => posting.direction === "debit");
  const credit = accountLegs.find((posting) => posting.direction === "credit");
  const leg = movesFunds ? (debit ?? credit) : accountLegs[0];
  const account = leg?.account_id ? accounts.get(leg.account_id) : undefined;
  const category = postings.find((posting) => posting.category_id);
  const color =
    colors.get(category?.category_id ?? "") ??
    entityColor(account?.id ?? id, account?.color);
  const accountName = (accountId: string | null) =>
    (accountId && accounts.get(accountId)?.name) || "Konto";

  return (
    <li>
      <Link
        to={`/finances/transactions${periodSearch}&detail=${encodeURIComponent(id)}`}
      >
        <span
          className="finance-transaction-mark"
          aria-hidden="true"
          style={{ borderInlineStart: `4px solid ${color}` }}
        >
          {movesFunds ? "⇄" : description.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <strong>{description}</strong>
          <small>
            <TransactionDateLabel transaction={transaction} />
            {type === "opening_balance"
              ? "Bilans otwarcia"
              : type === "transfer"
                ? "Transfer własny"
                : TRANSACTION_TYPES[type]}
          </small>
          {movesFunds && debit && credit ? (
            <small>
              {accountName(debit.account_id)} → {accountName(credit.account_id)}
            </small>
          ) : null}
        </span>
        <span className="finance-transaction-amount">
          {movesFunds && debit && credit
            ? `${formatPostingAmount(debit)} → ${formatPostingAmount(credit)}`
            : formatPostingAmount(leg)}
          {leg && !movesFunds && leg.source_currency !== "PLN" ? (
            <small>Równowartość: {formatPLN(leg.base_amount_pln)} PLN</small>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

function ForecastPreview({
  forecast,
  periodSearch,
}: {
  forecast: CashflowForecast;
  periodSearch: string;
}) {
  const omissions = hasPaydayExclusions(forecast);
  const projected = forecast.projected_balance_before_next_payday_pln;
  const days = (forecast.days ?? []).filter(
    (day) => day.date < forecast.next_payday,
  );
  const lowest = forecast.lowest_balance_before_payday;
  return (
    <>
      <h2 className="finance-caption">
        Prognoza do wypłaty · {formatCalendarDate(forecast.next_payday)}
      </h2>
      <p className="finance-forecast-amount">
        {projected === null ? "Niedostępne" : `${formatPLN(projected)} PLN`}
      </p>
      <p className="finance-caption">
        {projected === null
          ? "Horyzont nie obejmuje całego okresu do wypłaty."
          : omissions
            ? "Szacunkowe saldo kont budżetowych przed wypłatą."
            : "Saldo kont budżetowych przed wypłatą."}
      </p>
      {days.length ? (
        <ForecastLine days={days} />
      ) : (
        <p className="py-5 text-sm">Brak dziennego przebiegu prognozy.</p>
      )}
      {lowest ? (
        <p className="finance-caption">
          {projected === null
            ? "Najniższe saldo w dostępnym okresie"
            : "Najniższe saldo do wypłaty"}{" "}
          <strong>{formatPLN(lowest.projected_balance_pln)} PLN</strong> ·{" "}
          {formatCalendarDate(lowest.date)}
        </p>
      ) : null}
      <div className="finance-runway-footer">
        <div>
          <small>
            {omissions ? "Limit dzienny niepewny" : "Limit dzienny"}
          </small>
          <strong>
            {forecast.safe_daily_limit_pln == null || omissions
              ? "—"
              : `${formatPLN(forecast.safe_daily_limit_pln)} PLN`}
          </strong>
          {omissions ? (
            <>
              <small>Prognoza nie obejmuje wszystkich zobowiązań.</small>
              {forecast.excluded_obligation_reasons?.length ? (
                <small>
                  {forecast.excluded_obligation_reasons
                    .map(forecastExclusionLabel)
                    .join(", ")}
                </small>
              ) : null}
            </>
          ) : null}
        </div>
        <Link to={`/finances/cashflow${periodSearch}`}>
          Przejdź do płynności →
        </Link>
      </div>
    </>
  );
}

function ForecastLine({ days }: { days: CashflowDay[] }) {
  const values = days.map((day) => day.projected_balance_pln);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
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
        {min < 0 && max >= 0 ? (
          <line
            x1="0"
            x2="100"
            y1={90 - ((0 - min) / range) * 75}
            y2={90 - ((0 - min) / range) * 75}
            stroke="currentColor"
            strokeDasharray="4 3"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
        {days.length === 1 ? (
          <circle cx="50" cy="90" r="2" fill="currentColor" />
        ) : null}
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
        {days.length > 1 ? (
          <span>{formatCalendarDate(days[days.length - 1].date)}</span>
        ) : null}
      </figcaption>
    </figure>
  );
}
