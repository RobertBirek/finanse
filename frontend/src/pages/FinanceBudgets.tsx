import { useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import {
  budgetProgress,
  parsePlnToGrosze,
  useBudgets,
  useBudgetStatus,
  useCategories,
  useCategorySummary,
  useCreateBudget,
  useDeleteBudget,
  useUpdateBudget,
  type CategorySummary,
  type FinancialPeriod,
} from "../api/finance";
import { formatPLN } from "../lib/format";
import { CategorySpendTree } from "../components/finance/CategorySpendTree";
import { MonthPicker } from "../components/finance/MonthPicker";

function currentPeriod(): FinancialPeriod {
  const today = new Date();
  return { month: today.getMonth() + 1, year: today.getFullYear() };
}

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

function withoutBudgetedCategories(
  summary: CategorySummary | undefined,
  budgetedIds: Set<string>,
): CategorySummary | undefined {
  if (!summary) return undefined;
  return {
    ...summary,
    groups: summary.groups.filter(
      (group) => !budgetedIds.has(group.category_id),
    ),
    categories: summary.categories.filter(
      (category) => !budgetedIds.has(category.category_id),
    ),
  };
}

export function FinanceBudgets() {
  const [period, setPeriod] = useState(currentPeriod);
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [editingBudgetId, setEditingBudgetId] = useState<string | null>(null);
  const [editAmount, setEditAmount] = useState("");

  const budgetsQuery = useBudgets();
  const statusQuery = useBudgetStatus(period);
  const categoriesQuery = useCategories();
  const categorySummary = useCategorySummary(period);
  const createBudget = useCreateBudget();
  const updateBudget = useUpdateBudget();
  const deleteBudget = useDeleteBudget();

  const budgets = budgetsQuery.data ?? [];
  const budgetByCategory = new Map(
    budgets.map((budget) => [budget.category_id, budget]),
  );
  const budgetedCategoryIds = new Set(
    budgets.map((budget) => budget.category_id),
  );

  const expenseCategories = (categoriesQuery.data ?? []).filter(
    (category) => category.type === "expense",
  );
  const availableCategories = expenseCategories.filter(
    (category) => !budgetedCategoryIds.has(category.id),
  );

  const amountInGrosze = parsePlnToGrosze(amount);
  const canSubmit = !!categoryId && amountInGrosze !== null;

  const createError = apiErrorDetail(createBudget.error);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!categoryId || amountInGrosze === null) return;
    createBudget.mutate(
      { category_id: categoryId, amount_pln: amountInGrosze },
      {
        onSuccess: () => {
          setCategoryId("");
          setAmount("");
        },
      },
    );
  }

  function handleDelete(budgetId: string, name: string) {
    if (window.confirm(`Usunąć budżet dla "${name}"?`)) {
      deleteBudget.mutate(budgetId);
    }
  }

  function startEdit(budgetId: string, currentAmount: number) {
    setEditingBudgetId(budgetId);
    setEditAmount((currentAmount / 100).toFixed(2));
  }

  function handleSaveEdit(budgetId: string) {
    const grosze = parsePlnToGrosze(editAmount);
    if (grosze === null) return;
    updateBudget.mutate(
      { id: budgetId, amount_pln: grosze },
      { onSuccess: () => setEditingBudgetId(null) },
    );
  }

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-white">Budżet</h1>
        <MonthPicker period={period} onChange={setPeriod} />
      </div>

      <section className="card mb-4">
        <h2 className="mb-4 text-lg font-semibold text-white">Budżety</h2>
        {statusQuery.isLoading ? (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
          </div>
        ) : statusQuery.isError ? (
          <p className="py-4 text-sm text-red-400">
            Nie udało się pobrać budżetów.
          </p>
        ) : (statusQuery.data?.items.length ?? 0) === 0 ? (
          <p className="py-4 text-sm text-gray-500">
            Brak budżetów w tym miesiącu.
          </p>
        ) : (
          <div className="space-y-4">
            {(statusQuery.data?.items ?? []).map((item) => {
              const budget = budgetByCategory.get(item.category_id);
              const progress = budgetProgress(
                item.budget_amount_pln,
                item.spent_pln,
              );
              const isEditing =
                budget !== undefined && editingBudgetId === budget.id;

              return (
                <div
                  key={item.category_id}
                  className="border-b border-gray-800 pb-4 last:border-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <h3 className="font-medium text-white">{item.name}</h3>
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
                      <div>
                        <p className="mb-1 text-xs text-gray-500">Limit</p>
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <label
                              htmlFor={`limit-${item.category_id}`}
                              className="sr-only"
                            >
                              Limit (PLN)
                            </label>
                            <input
                              id={`limit-${item.category_id}`}
                              className="input w-28"
                              value={editAmount}
                              onChange={(event) =>
                                setEditAmount(event.target.value)
                              }
                            />
                            <button
                              type="button"
                              className="btn-secondary"
                              disabled={updateBudget.isPending}
                              onClick={() => {
                                if (budget) handleSaveEdit(budget.id);
                              }}
                            >
                              Zapisz
                            </button>
                            <button
                              type="button"
                              className="btn-secondary"
                              onClick={() => setEditingBudgetId(null)}
                            >
                              Anuluj
                            </button>
                          </div>
                        ) : (
                          <p className="font-mono text-gray-200">
                            {formatPLN(item.budget_amount_pln)} PLN
                          </p>
                        )}
                      </div>
                      <div>
                        <p className="mb-1 text-xs text-gray-500">Wydane</p>
                        <p className="font-mono text-gray-200">
                          {formatPLN(item.spent_pln)} PLN
                        </p>
                      </div>
                      <div>
                        <p className="mb-1 text-xs text-gray-500">Pozostało</p>
                        <p
                          className={`font-mono ${
                            item.remaining_pln < 0
                              ? "text-red-400"
                              : "text-gray-200"
                          }`}
                        >
                          {formatPLN(item.remaining_pln)} PLN
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {budget ? (
                          <>
                            {!isEditing ? (
                              <button
                                type="button"
                                aria-label={`Edytuj limit ${item.name}`}
                                className="btn-secondary"
                                onClick={() =>
                                  startEdit(budget.id, item.budget_amount_pln)
                                }
                              >
                                Edytuj
                              </button>
                            ) : null}
                            <button
                              type="button"
                              aria-label={`Usuń budżet ${item.name}`}
                              className="btn-secondary"
                              onClick={() => handleDelete(budget.id, item.name)}
                            >
                              Usuń
                            </button>
                          </>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-800">
                    <div
                      data-testid={`budget-progress-${item.category_id}`}
                      className={`h-full rounded-full ${
                        progress.over ? "bg-red-500" : "bg-advisor-500"
                      }`}
                      style={{ width: `${progress.percent}%` }}
                    />
                  </div>
                  {item.remaining_pln < 0 ? (
                    <p className="mt-2 text-sm text-red-400">
                      Przekroczono o {formatPLN(Math.abs(item.remaining_pln))}{" "}
                      PLN
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <form onSubmit={handleSubmit} className="card mb-4">
        <h2 className="mb-4 text-lg font-semibold text-white">Nowy budżet</h2>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label
              htmlFor="budget-category"
              className="mb-1 block text-sm text-gray-400"
            >
              Kategoria
            </label>
            <select
              id="budget-category"
              className="input"
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
            >
              <option value="">Wybierz kategorię</option>
              {availableCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="budget-amount"
              className="mb-1 block text-sm text-gray-400"
            >
              Kwota (PLN)
            </label>
            <input
              id="budget-amount"
              className="input"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="np. 1 234,56"
            />
          </div>
          <button
            type="submit"
            className="btn-primary"
            disabled={createBudget.isPending || !canSubmit}
          >
            Dodaj budżet
          </button>
        </div>
        {createError ? (
          <p className="mt-4 text-sm text-red-400">{createError}</p>
        ) : null}
      </form>

      <CategorySpendTree
        title="Wydatki bez budżetu"
        summary={withoutBudgetedCategories(
          categorySummary.data,
          budgetedCategoryIds,
        )}
        loading={categorySummary.isLoading}
        error={categorySummary.isError}
      />
    </div>
  );
}
