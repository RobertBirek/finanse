import { useEffect, useState } from "react";
import type { AxiosError } from "axios";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import {
  useSerializedIntentKey,
  useBill,
  useBills,
  useUnlinkBillPayment,
  useUpdateBillLifecycle,
  type BillFilters,
} from "../api/bills";
import { BillRegister } from "../components/finance/bills/BillRegister";
import { BillDetail } from "../components/finance/bills/BillDetail";
import { BillPaymentDialog } from "../components/finance/bills/BillPaymentDialog";
import { BillCoverageDialog } from "../components/finance/bills/BillCoverageDialog";
import { BillDeclarationDialog } from "../components/finance/bills/BillDeclarationDialog";
import { ReceiptItemsPanel } from "../components/finance/receipts/ReceiptItemsPanel";
import { listPage, setListPage } from "../lib/listPage";
import { useAuthStore } from "../stores/authStore";

function calendarFilter(value: string | null): string | undefined {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const date = new Date(value + "T00:00:00Z");
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toISOString().slice(0, 10) === value ? value : undefined;
}

export function FinanceDocuments() {
  const [params, setParams] = useSearchParams();
  const page = listPage(params.get("page"));
  const query = params.get("query")?.slice(0, 200) ?? "";
  const [draft, setDraft] = useState<{ base: string; text: string } | null>(
    null,
  );
  const searchText = draft?.base === query ? draft.text : query;
  useEffect(() => {
    if (!draft || draft.base !== query || draft.text === query) return;
    const timer = window.setTimeout(() => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (draft.text.trim()) next.set("query", draft.text.trim());
          else next.delete("query");
          next.delete("page");
          return next;
        },
        { replace: true },
      );
      setDraft(null);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [draft, query, setParams]);

  const kind = params.get("kind");
  const review = params.get("review");
  const declaration = params.get("declaration");
  const lifecycleParam = params.get("lifecycle");
  const dueFrom = calendarFilter(params.get("due_from"));
  const dueTo = calendarFilter(params.get("due_to"));
  const filters: BillFilters = {
    limit: 25,
    offset: (page - 1) * 25,
    kind: kind === "invoice" || kind === "receipt" ? kind : undefined,
    review:
      review === "draft" || review === "approved" || review === "rejected"
        ? review
        : undefined,
    declaration:
      declaration === "unknown" ||
      declaration === "payable" ||
      declaration === "declared_paid"
        ? declaration
        : undefined,
    lifecycle:
      lifecycleParam === "archived" || lifecycleParam === "cancelled"
        ? lifecycleParam
        : "active",
    due_from: dueFrom,
    due_to: dueTo,
    query: query || undefined,
  };
  const validRange = !dueFrom || !dueTo || dueFrom <= dueTo;
  function changePage(page: number) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      setListPage(next, "page", page);
      return next;
    });
  }
  const [dialog, setDialog] = useState<
    "payment" | "coverage" | "items" | "declared_paid" | "payable" | null
  >(null);
  const session = useAuthStore((s) => s.sessionVersion);
  const selectedId = params.get("bill");
  const bills = useBills(filters, validRange);
  const selected = useBill(selectedId);
  const lifecycle = useUpdateBillLifecycle();
  const unlinkPayment = useUnlinkBillPayment();
  const keyFor = useSerializedIntentKey();
  const [stale, setStale] = useState<{
    before: number;
    current?: number;
  } | null>(null);
  const staleError = (error: unknown) => {
    if ((error as AxiosError).response?.status === 409 && selected.data)
      setStale({ before: selected.data.version });
  };
  function updateFilter(key: keyof BillFilters, value: string) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(key, value);
      else next.delete(key);
      next.delete("page");
      return next;
    });
  }
  function select(id: string | null) {
    setDialog(null);
    setStale(null);
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (id) next.set("bill", id);
      else next.delete("bill");
      return next;
    });
  }
  return (
    <div className="page-workspace">
      <PageHeader title="Faktury i paragony" />
      <div className="card mb-5 flex flex-wrap gap-3 p-3">
        <label className="text-sm text-gray-300">
          Typ
          <select
            aria-label="Typ dokumentu"
            className="input ml-2"
            value={filters.kind ?? ""}
            onChange={(event) => updateFilter("kind", event.target.value)}
          >
            <option value="">Wszystkie</option>
            <option value="invoice">Faktury</option>
            <option value="receipt">Paragony</option>
          </select>
        </label>
        <label className="text-sm text-gray-300">
          Przegląd
          <select
            aria-label="Przegląd"
            className="input ml-2"
            value={filters.review ?? ""}
            onChange={(event) => updateFilter("review", event.target.value)}
          >
            <option value="">Wszystkie</option>
            <option value="draft">Szkice</option>
            <option value="approved">Zatwierdzone</option>
            <option value="rejected">Odrzucone</option>
          </select>
        </label>
        <label className="text-sm text-gray-300">
          Deklaracja płatności
          <select
            aria-label="Deklaracja płatności"
            className="input ml-2"
            value={filters.declaration ?? ""}
            onChange={(event) =>
              updateFilter("declaration", event.target.value)
            }
          >
            <option value="">Wszystkie</option>
            <option value="unknown">Nieznana</option>
            <option value="payable">Do zapłaty</option>
            <option value="declared_paid">Deklarowana zapłata</option>
          </select>
        </label>
        <label className="text-sm text-gray-300">
          Termin od
          <input
            aria-label="Termin od"
            type="date"
            className="input ml-2"
            value={filters.due_from ?? ""}
            onChange={(event) => updateFilter("due_from", event.target.value)}
          />
        </label>
        <label className="text-sm text-gray-300">
          Termin do
          <input
            aria-label="Termin do"
            type="date"
            className="input ml-2"
            value={filters.due_to ?? ""}
            onChange={(event) => updateFilter("due_to", event.target.value)}
          />
        </label>
        <input
          aria-label="Szukaj dokumentu"
          className="input"
          placeholder="Sprzedawca, numer lub opis"
          maxLength={200}
          value={searchText}
          onChange={(event) =>
            setDraft({ base: query, text: event.target.value })
          }
        />
        <label className="text-sm text-gray-300">
          Stan
          <select
            aria-label="Stan dokumentu"
            className="input ml-2"
            value={filters.lifecycle ?? "active"}
            onChange={(event) => updateFilter("lifecycle", event.target.value)}
          >
            <option value="active">Aktywne</option>
            <option value="archived">Archiwalne</option>
            <option value="cancelled">Anulowane</option>
          </select>
        </label>
      </div>
      {!validRange ? (
        <p role="alert" className="card text-sm text-red-300">
          Termin „od” musi przypadać przed terminem „do” lub tego samego dnia.
        </p>
      ) : bills.isError ? (
        <p role="alert" className="card text-sm text-red-300">
          Nie udało się pobrać rejestru dokumentów.{" "}
          <button
            type="button"
            className="underline"
            onClick={() => void bills.refetch()}
          >
            Spróbuj ponownie
          </button>
        </p>
      ) : bills.isLoading ? (
        <p className="text-sm text-gray-400">Ładowanie rejestru…</p>
      ) : (
        <>
          <BillRegister bills={bills.data?.items ?? []} onSelect={select} />
          <div className="mt-4 flex justify-between text-sm text-gray-400">
            <span>Łącznie: {bills.data?.total ?? 0}</span>
            <div className="flex gap-2">
              <button
                className="btn-secondary"
                type="button"
                disabled={!filters.offset}
                onClick={() => changePage(page - 1)}
              >
                Poprzednie
              </button>
              <button
                className="btn-secondary"
                type="button"
                disabled={
                  (filters.offset ?? 0) + (filters.limit ?? 25) >=
                  (bills.data?.total ?? 0)
                }
                onClick={() => changePage(page + 1)}
              >
                Następne
              </button>
            </div>
          </div>
        </>
      )}
      {selected.data ? (
        <>
          <BillDetail
            bill={selected.data}
            onClose={() => select(null)}
            onPayment={() => setDialog("payment")}
            onCoverage={() => setDialog("coverage")}
            onReceipt={() => setDialog("items")}
            onDeclaration={setDialog}
            onLifecycle={(nextLifecycle, confirmForecastEffect) =>
              lifecycle.mutate(
                {
                  billId: selected.data.id,
                  expected_version: selected.data.version,
                  lifecycle: nextLifecycle,
                  ...(confirmForecastEffect
                    ? { confirm_forecast_effect: true as const }
                    : {}),
                  idempotencyKey: keyFor({
                    action: "lifecycle",
                    billId: selected.data.id,
                    version: selected.data.version,
                    lifecycle: nextLifecycle,
                    confirm_forecast_effect: confirmForecastEffect ?? null,
                  }),
                },
                { onError: staleError },
              )
            }
            onUnlink={(allocationId) =>
              unlinkPayment.mutate(
                {
                  billId: selected.data.id,
                  allocationId,
                  expected_version: selected.data.version,
                  idempotencyKey: keyFor({
                    action: "unlink-allocation",
                    billId: selected.data.id,
                    version: selected.data.version,
                    allocationId,
                  }),
                },
                { onError: staleError },
              )
            }
            actionsDisabled={!!stale}
          />
          {stale ? (
            <div className="mt-3 rounded border border-amber-700 p-3 text-sm text-amber-100">
              Wersja przed zmianą: {stale.before}.
              {stale.current != null
                ? ` Aktualna wersja: ${stale.current}.`
                : ""}
              <div className="mt-2 flex gap-2">
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={async () => {
                    const result = await selected.refetch();
                    if (result.data)
                      setStale((value) =>
                        value
                          ? { ...value, current: result.data.version }
                          : value,
                      );
                  }}
                >
                  Odśwież aktualny dokument
                </button>
                {stale.current != null ? (
                  <button
                    className="btn-primary"
                    type="button"
                    onClick={() => setStale(null)}
                  >
                    Rozumiem — podejmuję nową decyzję
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
          {lifecycle.error || unlinkPayment.error ? (
            <p role="alert" className="mt-3 text-sm text-red-300">
              Nie udało się zmienić dokumentu. Pola pozostają bez zmian.{" "}
              {((lifecycle.error || unlinkPayment.error) as AxiosError).response
                ?.status === 409
                ? "Odśwież dokument i porównaj stan przed ponowną próbą."
                : "Spróbuj ponownie tym samym zamiarem."}
            </p>
          ) : null}
        </>
      ) : selected.isError ? (
        <p role="alert" className="mt-4 text-sm text-red-300">
          Nie udało się pobrać dokumentu.{" "}
          <button
            type="button"
            className="underline"
            onClick={() => void selected.refetch()}
          >
            Spróbuj ponownie
          </button>
        </p>
      ) : null}
      {(dialog === "declared_paid" || dialog === "payable") && selected.data ? (
        <BillDeclarationDialog
          key={`${session}:${selected.data.id}:${dialog}`}
          bill={selected.data}
          declaration={dialog}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "payment" && selected.data ? (
        <BillPaymentDialog
          bill={selected.data}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "coverage" && selected.data ? (
        <BillCoverageDialog
          bill={selected.data}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "items" && selected.data ? (
        <ReceiptItemsPanel
          key={`${session}:${selected.data.id}`}
          billId={selected.data.id}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}
