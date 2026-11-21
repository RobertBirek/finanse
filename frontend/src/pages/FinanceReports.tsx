import {
  useCategories,
  useCategorySummary,
  useFinancialSummary,
} from "../api/finance";
import { CategorySpendTree } from "../components/finance/CategorySpendTree";
import { MonthPicker } from "../components/finance/MonthPicker";
import { SummaryCard } from "../components/finance/SummaryCard";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { PageHeader } from "../components/PageHeader";
import { useFinancePeriod } from "../components/finance/useFinancePeriod";
import { ExpenseDateBasis } from "../components/finance/TransactionDateLabel";

export function FinanceReports() {
  const [period, setPeriod] = useFinancePeriod();
  const summary = useFinancialSummary(period);
  const categorySummary = useCategorySummary(period);
  const categories = useCategories();

  return (
    <div className="page-workspace">
      <PageHeader
        title="Raporty"
        actions={<MonthPicker period={period} onChange={setPeriod} />}
      />
      <FinanceTabs />
      <ExpenseDateBasis />

      {summary.isLoading || summary.isPlaceholderData ? (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
        </div>
      ) : summary.isError ? (
        <p role="alert" className="card text-sm text-red-400">
          Nie udało się pobrać podsumowania finansowego.{" "}
          <button
            type="button"
            className="underline"
            onClick={() => void summary.refetch()}
          >
            Spróbuj ponownie
          </button>
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
        onRetry={categorySummary.refetch}
        categories={categories.data}
      />
    </div>
  );
}
