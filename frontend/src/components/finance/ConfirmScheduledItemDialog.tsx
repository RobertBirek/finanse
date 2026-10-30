import { Dialog } from "../Dialog";
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
  const canConfirm = canConfirmSuggestion(suggestion, localTodayIso());
  const errorMessage = apiErrorDetail(confirmMutation.error);

  return (
    <Dialog
      label="Potwierdź pozycję"
      onClose={onClose}
      busy={confirmMutation.isPending}
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
            {suggestion.due_date
              ? new Date(suggestion.due_date).toLocaleDateString("pl-PL")
              : "Brak terminu"}
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
      <div className="flex flex-wrap justify-end gap-2">
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
    </Dialog>
  );
}
