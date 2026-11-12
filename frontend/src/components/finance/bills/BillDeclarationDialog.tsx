import { useRef, useState } from "react";
import type { AxiosError } from "axios";
import {
  type BillResponse,
  useBill,
  useSerializedIntentKey,
  useSetBillPaymentDeclaration,
} from "../../../api/bills";
import { useAuthStore } from "../../../stores/authStore";
import { Dialog } from "../../Dialog";

export function BillDeclarationDialog({
  bill,
  declaration,
  onClose,
}: {
  bill: BillResponse;
  declaration: "declared_paid" | "payable";
  onClose: () => void;
}) {
  const session = useAuthStore((state) => state.sessionVersion);
  const [origin] = useState(() => ({ id: bill.id, session, declaration }));
  // A failed transport may have committed: retries must retain this exact version.
  const [decisionBill, setDecisionBill] = useState(bill);
  const [confirmed, setConfirmed] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [refreshError, setRefreshError] = useState(false);
  const [decisionEpoch, setDecisionEpoch] = useState(0);
  const inFlight = useRef(false);
  const current = useRef({ id: bill.id, session, declaration });
  current.current = { id: bill.id, session, declaration };
  const mutation = useSetBillPaymentDeclaration();
  const query = useBill(bill.id, false);
  const keyFor = useSerializedIntentKey();
  const changedContext =
    origin.id !== bill.id ||
    origin.session !== session ||
    origin.declaration !== declaration;
  const needsRefresh = conflict || bill.version > decisionBill.version;
  const eligible =
    decisionBill.review === "approved" &&
    decisionBill.lifecycle === "active" &&
    decisionBill.remaining_minor > 0 &&
    decisionBill.currency !== null;
  const busy = mutation.isPending || query.isFetching;
  const marking = declaration === "declared_paid";
  const title = marking
    ? "Oznacz jako opłaconą bez transakcji"
    : "Cofnij oznaczenie opłacenia";
  const sameContext = () =>
    current.current.id === origin.id &&
    current.current.declaration === origin.declaration &&
    useAuthStore.getState().sessionVersion === origin.session;
  const submit = () => {
    if (
      inFlight.current ||
      busy ||
      !confirmed ||
      needsRefresh ||
      changedContext ||
      !eligible ||
      !sameContext()
    )
      return;
    inFlight.current = true;
    const intent = {
      billId: decisionBill.id,
      expected_version: decisionBill.version,
      declaration,
      confirm_forecast_effect: true as const,
    };
    mutation.mutate(
      {
        ...intent,
        idempotencyKey: keyFor({ ...intent, session, decisionEpoch }),
      },
      {
        onSuccess: () => {
          if (sameContext()) onClose();
        },
        onError: (error) => {
          if ((error as AxiosError).response?.status === 409) {
            setConflict(true);
            setConfirmed(false);
          }
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  };
  const refresh = async () => {
    if (busy || changedContext) return;
    setConfirmed(false);
    setRefreshError(false);
    const result = await query.refetch();
    if (result.isSuccess && sameContext()) {
      setDecisionBill(result.data);
      setDecisionEpoch((value) => value + 1);
      setConflict(false);
      mutation.reset();
    } else setRefreshError(true);
  };
  const amount = decisionBill.currency
    ? new Intl.NumberFormat("pl-PL", {
        style: "currency",
        currency: decisionBill.currency,
      }).format(decisionBill.remaining_minor / 100)
    : "—";
  return (
    <Dialog label={title} onClose={onClose} busy={busy}>
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      <p className="mt-3 text-sm text-gray-300">
        {marking
          ? `Oznaczasz całą pozostałą kwotę ${amount} jako opłaconą deklaracyjnie. Dokument zniknie z pozycji do zapłaty i prognozy.`
          : `Przywracasz do zapłaty pozostałe ${amount}. Kwota może wrócić do prognozy, jeśli spełnia jej warunki. Ta operacja nie cofa przelewów ani istniejących powiązań.`}{" "}
        Nie powstanie transakcja ani wydatek. Salda kont i księga pozostaną bez
        zmian.
      </p>
      {decisionBill.coverage ? (
        <p className="mt-2 text-sm text-gray-400">
          Zastąpienie pozycji cyklicznej pozostaje bez zmian; jej estymata nie
          wróci automatycznie.
        </p>
      ) : null}
      {changedContext ? (
        <p role="alert" className="mt-3 text-sm text-amber-300">
          Dokument lub sesja zmieniły się. Zamknij okno i podejmij nową decyzję.
        </p>
      ) : needsRefresh ? (
        <div className="mt-3 text-sm text-amber-300" role="alert">
          Dokument zmienił się. Odśwież go i ponownie potwierdź aktualną kwotę.
          <button
            type="button"
            className="btn-secondary mt-2"
            disabled={busy}
            onClick={refresh}
          >
            Odśwież dokument
          </button>
        </div>
      ) : null}
      {!eligible ? (
        <p role="alert" className="mt-3 text-sm text-amber-300">
          Dokument nie pozwala na tę zmianę deklaracji.
        </p>
      ) : null}
      {refreshError || (mutation.isError && !conflict) ? (
        <p role="alert" className="mt-3 text-sm text-red-300">
          Nie udało się zapisać lub odświeżyć dokumentu. Spróbuj ponownie tym
          samym zamiarem.
        </p>
      ) : null}
      <label className="mt-4 flex items-start gap-2 text-sm text-gray-300">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy || needsRefresh || changedContext || !eligible}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Potwierdzam zmianę całej pozostałej kwoty bez księgowania.
      </label>
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-primary"
          onClick={submit}
          disabled={
            busy || !confirmed || needsRefresh || changedContext || !eligible
          }
        >
          {marking ? "Potwierdź oznaczenie" : "Przywróć do zapłaty"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={onClose}
        >
          Wróć
        </button>
      </div>
    </Dialog>
  );
}
