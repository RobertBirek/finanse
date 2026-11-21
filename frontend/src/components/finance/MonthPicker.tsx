import type { FinancialPeriod } from "../../api/finance";
import { IconButton } from "../IconButton";
import { MAX_FINANCIAL_YEAR, MIN_FINANCIAL_YEAR } from "./useFinancePeriod";

type MonthPickerProps = {
  period: FinancialPeriod;
  onChange: (period: FinancialPeriod) => void;
};

export function MonthPicker({ period, onChange }: MonthPickerProps) {
  const today = new Date();
  const month = period.month ?? today.getMonth() + 1;
  const year = period.year ?? today.getFullYear();
  const currentMonth = today.getMonth() + 1;
  const currentYear = today.getFullYear();
  const isAtOrAfterCurrentMonth =
    year > currentYear || (year === currentYear && month >= currentMonth);
  const isAtEarliestMonth = year === MIN_FINANCIAL_YEAR && month === 1;
  const isAtLatestMonth = year === MAX_FINANCIAL_YEAR && month === 12;
  const label = new Intl.DateTimeFormat("pl-PL", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, month - 1, 1));

  function previousMonth() {
    onChange(
      month === 1 ? { month: 12, year: year - 1 } : { month: month - 1, year },
    );
  }

  function nextMonth() {
    onChange(
      month === 12 ? { month: 1, year: year + 1 } : { month: month + 1, year },
    );
  }

  return (
    <div
      role="group"
      aria-label="Miesiąc raportowania"
      className="flex min-w-0 items-center gap-1.5"
    >
      <IconButton
        icon="previous"
        label="Poprzedni miesiąc"
        onClick={previousMonth}
        disabled={isAtEarliestMonth}
      />
      <p className="min-w-0 text-center text-sm font-medium capitalize text-gray-200 sm:min-w-32">
        {label}
      </p>
      <IconButton
        icon="next"
        label="Następny miesiąc"
        onClick={nextMonth}
        disabled={isAtOrAfterCurrentMonth || isAtLatestMonth}
      />
    </div>
  );
}
