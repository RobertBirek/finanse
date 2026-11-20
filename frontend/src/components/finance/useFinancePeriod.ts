import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import type { FinancialPeriod } from "../../api/finance";

export const MIN_FINANCIAL_YEAR = 2000;
export const MAX_FINANCIAL_YEAR = 2100;

export type ValidFinancialPeriod = Required<FinancialPeriod>;

function currentPeriod(): ValidFinancialPeriod {
  const today = new Date();
  return { month: today.getMonth() + 1, year: today.getFullYear() };
}

export function isValidFinancialPeriod(
  period: FinancialPeriod,
): period is ValidFinancialPeriod {
  const { month, year } = period;
  return (
    Number.isInteger(month) &&
    month !== undefined &&
    month >= 1 &&
    month <= 12 &&
    Number.isInteger(year) &&
    year !== undefined &&
    year >= MIN_FINANCIAL_YEAR &&
    year <= MAX_FINANCIAL_YEAR
  );
}

export function periodFromSearch(
  search: URLSearchParams,
): ValidFinancialPeriod {
  const period = {
    month: Number(search.get("month")),
    year: Number(search.get("year")),
  };
  return isValidFinancialPeriod(period) ? period : currentPeriod();
}

export function financePeriodSearch(period: FinancialPeriod): string {
  if (!isValidFinancialPeriod(period)) return "";
  const search = new URLSearchParams();
  search.set("month", String(period.month));
  search.set("year", String(period.year));
  return `?${search.toString()}`;
}

export function retainFinancePeriod(search: URLSearchParams): URLSearchParams {
  const period = new URLSearchParams();
  for (const field of ["month", "year"]) {
    const value = search.get(field);
    if (value) period.set(field, value);
  }
  return period;
}

export function categoryTransactionsHref(
  period: ValidFinancialPeriod,
  categoryId: string,
): string {
  const month = String(period.month).padStart(2, "0");
  const lastDay = new Date(period.year, period.month, 0).getDate();
  const search = new URLSearchParams(financePeriodSearch(period));
  search.set("category_id", categoryId);
  search.set("include_descendants", "true");
  search.set("budget_accounts_only", "true");
  search.set("date_basis", "purchase");
  search.set("date_from", `${period.year}-${month}-01`);
  search.set("date_to", `${period.year}-${month}-${lastDay}`);
  return `/finances/transactions?${search}`;
}

export function useFinancePeriod(): [
  ValidFinancialPeriod,
  (period: FinancialPeriod) => void,
] {
  const [search, setSearch] = useSearchParams();
  const period = periodFromSearch(search);
  const setPeriod = useCallback(
    (nextPeriod: FinancialPeriod) => {
      if (!isValidFinancialPeriod(nextPeriod)) return;
      const nextSearch = new URLSearchParams(search);
      nextSearch.set("month", String(nextPeriod.month));
      nextSearch.set("year", String(nextPeriod.year));
      setSearch(nextSearch);
    },
    [search, setSearch],
  );

  return [period, setPeriod];
}
