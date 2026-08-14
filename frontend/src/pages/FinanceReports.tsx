import { useState } from "react";
import {
  useCategorySummary,
  useFinancialSummary,
  type FinancialPeriod,
} from "../api/finance";
import { CategorySpendTree } from "../components/finance/CategorySpendTree";
import { MonthPicker } from "../components/finance/MonthPicker";

function currentPeriod(): FinancialPeriod {
  const today = new Date();
  return { month: today.getMonth() + 1, year: today.getFullYear() };
}

export function FinanceReports() {
  const [period, setPeriod] = useState(currentPeriod);
  const summary = useFinancialSummary(period);
  const categorySummary = useCategorySummary(period);

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-white">Raporty</h1>
        <MonthPicker period={period} onChange={setPeriod} />
      </div>

      {summary.isLoading ? (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
        </div>
      ) : summary.isError ? (
        <p className="card text-sm text-red-400">
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
          Brak danych finansowych dla wybranego miesiąca.
        </p>
      )}

      <CategorySpendTree
        title="Wydatki według kategorii"
        summary={categorySummary.data}
        loading={categorySummary.isLoading}
        error={categorySummary.isError}
      />
    </div>
  );
}

function SummaryCard({
  label,
  amount,
  tone,
}: {
  label: string;
  amount: number;
  tone: "income" | "expense" | "net";
}) {
  const color =
    tone === "income" || (tone === "net" && amount >= 0)
      ? "text-green-400"
      : "text-red-400";

  return (
    <div className="card">
      <p className="mb-1 text-xs text-gray-400">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{formatPLN(amount)} PLN</p>
    </div>
  );
}

function formatPLN(amount: number) {
  return new Intl.NumberFormat("pl-PL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount / 100);
}
