import type { FinancialPeriod } from "../../api/finance";

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
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={previousMonth}
        className="btn-secondary px-3"
        aria-label="Poprzedni miesiąc"
      >
        &larr;
      </button>
      <p className="min-w-32 text-center text-sm font-medium capitalize text-gray-200">
        {label}
      </p>
      <button
        type="button"
        onClick={nextMonth}
        disabled={isAtOrAfterCurrentMonth}
        className="btn-secondary px-3 disabled:cursor-not-allowed disabled:opacity-50"
        aria-label="Następny miesiąc"
      >
        &rarr;
      </button>
    </div>
  );
}
