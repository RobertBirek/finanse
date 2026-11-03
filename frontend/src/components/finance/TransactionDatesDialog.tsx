import { useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import { useQueryClient } from "@tanstack/react-query";
import {
  type Transaction,
  useUpdateTransactionDates,
  invalidateFinanceLedger,
} from "../../api/finance";
import { useAuthStore } from "../../stores/authStore";
import { Dialog } from "../Dialog";

export function TransactionDatesDialog({
  transaction,
  onClose,
}: {
  transaction: Transaction;
  onClose: () => void;
}) {
  // Freeze the reviewed snapshot; a background refetch must not approve newer data.
  const [snapshot] = useState(transaction);
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const currentSession = useAuthStore((state) => state.sessionVersion);
  const [purchase, setPurchase] = useState(
    snapshot.date_metadata?.purchase_date ?? "",
  );
  const [booking, setBooking] = useState(
    snapshot.date_metadata?.booking_date ?? snapshot.transaction_date,
  );
  const [confirmed, setConfirmed] = useState(
    !!snapshot.date_metadata?.booking_date,
  );
  const [failure, setFailure] = useState<string | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const mutation = useUpdateTransactionDates();
  const queryClient = useQueryClient();
  const active = currentSession === session;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !active ||
      needsRefresh ||
      !confirmed ||
      !booking ||
      !snapshot.updated_at
    )
      return;
    mutation.mutate(
      {
        id: snapshot.id,
        purchase_date: purchase || null,
        booking_date: booking,
        expected_version: snapshot.date_metadata?.version ?? 0,
        expected_updated_at: snapshot.updated_at,
      },
      {
        onSuccess: () => {
          if (useAuthStore.getState().sessionVersion === session) onClose();
        },
        onError: (error) => {
          if (useAuthStore.getState().sessionVersion !== session) return;
          const response = (error as AxiosError<{ detail?: string }>).response;
          setFailure(
            response?.data?.detail ??
              "Nie udało się zapisać dat. Wprowadzone wartości zachowano.",
          );
          setNeedsRefresh(response?.status === 409);
        },
      },
    );
  }
  return (
    <Dialog
      label="Daty zakupu i księgowania"
      onClose={onClose}
      busy={mutation.isPending}
      panelClassName="card max-w-lg w-full"
    >
      <h2 className="text-lg font-semibold">Daty zakupu i księgowania</h2>
      {!active ? (
        <p role="alert">
          Sesja zmieniła się. Zamknij okno i wczytaj aktualne dane.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-4">
          <p className="text-sm text-gray-400">
            Zmiana daty zakupu może przenieść wydatek między budżetami miesięcy.
            Nie zmienia kwot, kategorii ani liczby płatności.
          </p>
          {!snapshot.date_metadata?.booking_date ? (
            <p className="text-sm text-gray-300">
              Znaczenie dotychczasowej daty jest nieustalone. Sprawdź ją z
              wyciągiem i świadomie potwierdź datę księgowania.
            </p>
          ) : null}
          <label className="block">
            Data zakupu
            <input
              className="input mt-1"
              type="date"
              value={purchase}
              onChange={(event) => setPurchase(event.target.value)}
            />
          </label>
          <p className="text-sm text-gray-400">
            Może pozostać pusta, jeśli nie jest znana. Wtedy analiza korzysta z
            daty księgowania.
          </p>
          <label className="block">
            Data księgowania
            <input
              className="input mt-1"
              type="date"
              required
              value={booking}
              onChange={(event) => setBooking(event.target.value)}
            />
          </label>
          {!snapshot.date_metadata?.booking_date ? (
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              Potwierdzam datę księgowania
            </label>
          ) : null}
          {failure ? (
            <p role="alert" className="text-red-300">
              {failure}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-primary"
              disabled={
                !confirmed ||
                !booking ||
                needsRefresh ||
                mutation.isPending ||
                !snapshot.updated_at
              }
            >
              Zapisz daty
            </button>
            {needsRefresh ? (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  if (useAuthStore.getState().sessionVersion === session)
                    invalidateFinanceLedger(queryClient);
                  onClose();
                }}
              >
                Zamknij i odśwież
              </button>
            ) : null}
            <button
              type="button"
              className="btn-secondary"
              disabled={mutation.isPending}
              onClick={onClose}
            >
              Zamknij
            </button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
