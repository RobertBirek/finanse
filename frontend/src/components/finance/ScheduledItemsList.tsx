import type { AxiosError } from "axios";
import {
  cashflowStatusLabel,
  useDeleteScheduledFinanceItem,
  useUpdateScheduledFinanceItem,
  type CashflowSuggestion,
  type ScheduledFinanceItem,
} from "../../api/finance";
import { formatPLN } from "../../lib/format";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

const typeLabel = { income: "Przychód", expense: "Wydatek" } as const;
const methodLabel = {
  fixed: "Stała kwota",
  last_actual: "Ostatnia kwota",
} as const;

type ScheduledItemsListProps = {
  items: ScheduledFinanceItem[];
  suggestions: CashflowSuggestion[];
  loading: boolean;
  error: boolean;
  onEdit: (item: ScheduledFinanceItem) => void;
};

export function ScheduledItemsList({
  items,
  suggestions,
  loading,
  error,
  onEdit,
}: ScheduledItemsListProps) {
  const deleteMutation = useDeleteScheduledFinanceItem();
  const updateMutation = useUpdateScheduledFinanceItem();

  const updateError = apiErrorDetail(updateMutation.error);
  const deleteError = apiErrorDetail(deleteMutation.error);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="card text-sm text-red-400">
        Nie udało się pobrać zaplanowanych pozycji.
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p className="card py-8 text-center text-sm text-gray-500">
        Brak zaplanowanych pozycji.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const suggestion = suggestions.find(
          (s) => s.scheduled_item_id === item.id,
        );
        const displayAmount =
          suggestion?.amount_pln != null
            ? suggestion.amount_pln
            : item.amount_method === "fixed" && item.fixed_amount_pln != null
              ? item.fixed_amount_pln
              : null;

        const isTogglePending =
          updateMutation.isPending && updateMutation.variables?.id === item.id;
        const isDeletePending =
          deleteMutation.isPending && deleteMutation.variables === item.id;
        const toggleError =
          updateMutation.variables?.id === item.id ? updateError : null;
        const deleteErrorForItem =
          deleteMutation.variables === item.id ? deleteError : null;

        function handleToggle() {
          updateMutation.mutate({
            id: item.id,
            name: item.name,
            type: item.type,
            account_id: item.account_id,
            category_id: item.category_id,
            currency: item.currency,
            due_day: item.due_day,
            amount_method: item.amount_method,
            fixed_amount_pln: item.fixed_amount_pln,
            is_active: !item.is_active,
          });
        }

        function handleDelete() {
          if (window.confirm(`Usunąć pozycję "${item.name}"?`)) {
            deleteMutation.mutate(item.id);
          }
        }

        return (
          <div
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-800 bg-gray-800/40 p-3"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-medium text-white">
                  {item.name}
                </p>
                {!item.is_active ? (
                  <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
                    nieaktywna
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 text-xs text-gray-500">
                {typeLabel[item.type]} · dzień {item.due_day} ·{" "}
                {methodLabel[item.amount_method]}
              </p>
            </div>
            <div className="shrink-0 text-right">
              {displayAmount != null ? (
                <p
                  className={`font-mono text-sm font-medium ${item.type === "income" ? "text-green-400" : "text-red-400"}`}
                >
                  {item.type === "income" ? "+" : "−"}
                  {formatPLN(displayAmount)} PLN
                </p>
              ) : (
                <p className="text-xs text-gray-500">—</p>
              )}
              {suggestion ? (
                <p className="text-[11px] text-gray-500">
                  {cashflowStatusLabel(suggestion.status)}
                </p>
              ) : null}
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => onEdit(item)}
                className="btn-secondary px-3 py-1.5 text-sm"
              >
                Edytuj
              </button>
              <button
                type="button"
                onClick={handleToggle}
                disabled={isTogglePending || isDeletePending}
                className="btn-secondary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                {item.is_active ? "Dezaktywuj" : "Aktywuj"}
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={isTogglePending || isDeletePending}
                className="btn-danger px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                Usuń
              </button>
            </div>
            {toggleError || deleteErrorForItem ? (
              <p className="w-full text-xs text-red-400">
                {toggleError ?? deleteErrorForItem}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
