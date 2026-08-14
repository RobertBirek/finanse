import { useState } from "react";
import { useCategorySummary, type FinancialPeriod } from "../api/finance";
import { CategorySpendTree } from "../components/finance/CategorySpendTree";
import { MonthPicker } from "../components/finance/MonthPicker";

function currentPeriod(): FinancialPeriod {
  const today = new Date();
  return { month: today.getMonth() + 1, year: today.getFullYear() };
}

export function FinanceBudgets() {
  const [period, setPeriod] = useState(currentPeriod);
  const categorySummary = useCategorySummary(period);

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-white">Budżet</h1>
        <MonthPicker period={period} onChange={setPeriod} />
      </div>
      <CategorySpendTree
        title="Wydatki według kategorii"
        summary={categorySummary.data}
        loading={categorySummary.isLoading}
        error={categorySummary.isError}
      />
    </div>
  );
}
