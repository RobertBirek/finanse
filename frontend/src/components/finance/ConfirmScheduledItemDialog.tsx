import { useEffect, useRef } from "react";
import type { AxiosError } from "axios";
import {
  canConfirmSuggestion,
  useConfirmScheduledFinanceItem,
  type CashflowSuggestion,
  type ScheduledFinanceItem,
} from "../../api/finance";
import { localTodayIso } from "../../lib/date";
import { formatPLN } from "../../lib/format";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

const typeLabel = { income: "Przychód", expense: "Wydatek" } as const;

type ConfirmScheduledItemDialogProps = {
  suggestion: CashflowSuggestion;
  item: ScheduledFinanceItem;
  onClose: () => void;
};

export function ConfirmScheduledItemDialog({
  suggestion,
  item,
  onClose,
}: ConfirmScheduledItemDialogProps) {
  const confirmMutation = useConfirmScheduledFinanceItem();
  const dialogRef = useRef<HTMLDivElement>(null);
  const canConfirm = canConfirmSuggestion(suggestion, localTodayIso());
  const errorMessage = apiErrorDetail(confirmMutation.error);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-item-title"
        tabIndex={-1}
        className="card w-full max-w-md border-advisor-500/30 focus:outline-none"
      >
        <h2
          id="confirm-item-title"
          className="mb-1 text-lg font-semibold text-white"
        >
          Potwierdź pozycję
        </h2>
        <p className="mb-4 text-sm text-gray-400">
          Zaksięguj zaplanowaną transakcję jako rzeczywistą.
        </p>
        <dl className="mb-4 space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-gray-400">Nazwa</dt>
            <dd className="text-right text-white">{suggestion.name}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-gray-400">Termin</dt>
            <dd className="text-white">
              {new Date(suggestion.due_date).toLocaleDateString("pl-PL")}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-gray-400">Typ</dt>
            <dd className="text-white">{typeLabel[suggestion.type]}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-gray-400">Kwota</dt>
            <dd className="text-white">
              {suggestion.amount_pln != null
                ? `${formatPLN(suggestion.amount_pln)} PLN`
                : "—"}
            </dd>
          </div>
        </dl>
        {errorMessage ? (
          <p className="mb-4 text-sm text-red-400">{errorMessage}</p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary"
            disabled={confirmMutation.isPending}
            onClick={onClose}
          >
            Anuluj
          </button>
          {canConfirm ? (
            <button
              type="button"
              className="btn-primary"
              disabled={confirmMutation.isPending}
              onClick={() =>
                confirmMutation.mutate(item.id, { onSuccess: onClose })
              }
            >
              Potwierdź i zapisz transakcję
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
