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
