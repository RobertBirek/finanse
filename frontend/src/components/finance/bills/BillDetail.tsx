import { useEffect, useMemo, useState } from "react";
import {
  useDocumentOriginal,
  useDocumentPreview,
} from "../../../api/documents";
import { type BillResponse } from "../../../api/bills";

const amount = (value: number | null, currency: string | null) =>
  value == null || currency == null
    ? "—"
    : new Intl.NumberFormat("pl-PL", { style: "currency", currency }).format(
        value / 100,
      );
const lifecycleEffect = (bill: BillResponse) => {
  const remaining = amount(bill.remaining_minor, bill.currency);
  const coverage = bill.coverage;
  return (
    <>
      Zmiana stanu usunie z prognozy pozostałe {remaining} faktury.
      {coverage
        ? ` Zastąpienie wystąpienia ${coverage.occurrence_date} pozostanie, więc estymata cykliczna nie wróci automatycznie.`
        : ""}{" "}
      Potwierdź świadomie.
    </>
  );
};
function SourceFile({ documentId }: { documentId: string }) {
  const preview = useDocumentPreview(documentId);
  const original = useDocumentOriginal(documentId);
  const previewUrl = useMemo(
    () => (preview.data ? URL.createObjectURL(preview.data) : null),
    [preview.data],
  );
  const originalUrl = useMemo(
    () => (original.data ? URL.createObjectURL(original.data) : null),
    [original.data],
  );
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      if (originalUrl) URL.revokeObjectURL(originalUrl);
    },
    [previewUrl, originalUrl],
  );
  return (
    <li className="mt-2 text-sm text-gray-400">
      Plik {documentId}
      {previewUrl ? (
        <a
          className="ml-3 text-advisor-400 hover:underline"
          href={previewUrl}
          target="_blank"
          rel="noreferrer"
        >
          Podgląd
        </a>
      ) : null}
      {originalUrl ? (
        <a
          className="ml-3 text-advisor-400 hover:underline"
          href={originalUrl}
          download="dokument"
        >
          Oryginał
        </a>
      ) : null}
      {preview.isError || original.isError ? (
        <span className="ml-3 text-red-300">Nie udało się pobrać pliku.</span>
      ) : null}
    </li>
  );
}
export function BillDetail({
  bill,
  onClose,
  onPayment,
  onCoverage,
  onLifecycle,
  onUnlink,
  actionsDisabled = false,
}: {
  bill: BillResponse;
  onClose: () => void;
  onPayment: () => void;
  onCoverage: () => void;
  onLifecycle: (
    lifecycle: BillResponse["lifecycle"],
    confirmForecastEffect?: true,
  ) => void;
  onUnlink: (allocationId: string) => void;
  actionsDisabled?: boolean;
}) {
  const currency = bill.currency;
  const [pendingAction, setPendingAction] = useState<
    | { kind: "lifecycle"; lifecycle: BillResponse["lifecycle"] }
    | { kind: "unlink"; allocationId: string }
    | null
  >(null);
  return (
    <section className="card mt-5 p-5" aria-label="Szczegóły dokumentu">
      <div className="flex justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">
            {bill.supplier_name ?? "Dokument"}
          </h2>
          <p className="text-sm text-gray-400">
            {bill.description ?? "Brak opisu"}
          </p>
        </div>
        <button className="btn-secondary" type="button" onClick={onClose}>
          Zamknij
        </button>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-gray-500">Do zapłaty</dt>
          <dd className="font-mono text-white">
            {bill.total_minor == null
              ? "—"
              : amount(bill.total_minor, currency)}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">Pozostało</dt>
          <dd className="font-mono text-white">
            {amount(bill.remaining_minor, currency)}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">Termin</dt>
          <dd className="text-white">{bill.due_date ?? "Brak terminu"}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Uzgodnienie</dt>
          <dd className="text-white">{bill.reconciliation}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Deklaracja</dt>
          <dd className="text-white">{bill.declaration}</dd>
        </div>
      </dl>
      {bill.forecast_exclusion_reasons.length ? (
        <p className="mt-4 text-sm text-amber-300">
          Pozycja nie jest uwzględniona w prognozie:{" "}
          {bill.forecast_exclusion_reasons.join(", ")}.
        </p>
      ) : null}
      <section
        className="mt-4 border-t border-gray-800 pt-4"
        aria-label="Źródła dokumentu"
      >
        <h3 className="text-sm font-medium text-gray-200">Źródła</h3>
        <p className="mt-1 text-sm text-gray-400">
          Powiązane pliki potwierdzają ten sam zakup; nie tworzą nowej
          płatności.
        </p>
        <ul>
          {bill.sources.map((source) => (
            <SourceFile
              key={source.document_id}
              documentId={source.document_id}
            />
          ))}
        </ul>
      </section>
      <section className="mt-4 border-t border-gray-800 pt-4">
        <h3 className="text-sm font-medium text-gray-200">Historia alokacji</h3>
        {bill.allocations.length ? (
          <ul className="mt-2 text-sm text-gray-400">
            {bill.allocations.map((allocation) => (
              <li key={allocation.id}>
                {amount(allocation.amount_minor, currency)} · posting{" "}
                {allocation.posting_id}{" "}
                <button
                  type="button"
                  className="ml-2 text-advisor-400 hover:underline"
                  onClick={() =>
                    setPendingAction({
                      kind: "unlink",
                      allocationId: allocation.id,
                    })
                  }
                >
                  Odłącz alokację
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-gray-500">
            Nie powiązano jeszcze płatności.
          </p>
        )}
      </section>
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-primary"
          disabled={
            actionsDisabled || currency !== "PLN" || bill.lifecycle !== "active"
          }
          onClick={onPayment}
        >
          Powiąż płatność
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={actionsDisabled || bill.lifecycle !== "active"}
          onClick={onCoverage}
        >
          Wpływ na prognozę
        </button>
        {bill.lifecycle === "active" ? (
          <>
            <button
              type="button"
              className="btn-secondary"
              disabled={actionsDisabled}
              onClick={() =>
                setPendingAction({ kind: "lifecycle", lifecycle: "archived" })
              }
            >
              Archiwizuj
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={actionsDisabled}
              onClick={() =>
                setPendingAction({ kind: "lifecycle", lifecycle: "cancelled" })
              }
            >
              Anuluj dokument
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn-secondary"
            disabled={actionsDisabled}
            onClick={() =>
              setPendingAction({ kind: "lifecycle", lifecycle: "active" })
            }
          >
            Otwórz ponownie
          </button>
        )}
      </div>
      {currency !== "PLN" ? (
        <p className="mt-2 text-xs text-gray-500">
          Rozliczanie z księgą jest obecnie dostępne tylko dla PLN.
        </p>
      ) : null}
      {pendingAction ? (
        <div
          className="mt-4 rounded border border-amber-700 p-3 text-sm text-amber-100"
          role="alert"
        >
          {pendingAction.kind === "unlink"
            ? "Odłączenie zmieni wyłącznie powiązanie dokumentu; zapis księgi pozostanie bez zmian."
            : lifecycleEffect(bill)}
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                if (pendingAction.kind === "unlink")
                  onUnlink(pendingAction.allocationId);
                else
                  onLifecycle(
                    pendingAction.lifecycle,
                    pendingAction.lifecycle !== "active" &&
                      bill.lifecycle === "active" &&
                      bill.declaration === "payable" &&
                      bill.remaining_minor > 0
                      ? true
                      : undefined,
                  );
                setPendingAction(null);
              }}
            >
              {pendingAction.kind === "unlink"
                ? "Potwierdź odłączenie"
                : "Potwierdź zmianę stanu"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setPendingAction(null)}
            >
              Wróć
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
