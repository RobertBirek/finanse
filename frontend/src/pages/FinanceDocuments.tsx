import { useState } from "react";
import type { AxiosError } from "axios";
import { useSearchParams } from "react-router-dom";
import {
  useSerializedIntentKey,
  useBill,
  useBills,
  useUnlinkBillPayment,
  useUpdateBillLifecycle,
  type BillFilters,
} from "../api/bills";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { BillRegister } from "../components/finance/bills/BillRegister";
import { BillDetail } from "../components/finance/bills/BillDetail";
import { BillPaymentDialog } from "../components/finance/bills/BillPaymentDialog";
import { BillCoverageDialog } from "../components/finance/bills/BillCoverageDialog";

export function FinanceDocuments() {
  const [params, setParams] = useSearchParams();
  const [filters, setFilters] = useState<BillFilters>({ limit: 25, offset: 0 });
  const [dialog, setDialog] = useState<"payment" | "coverage" | null>(null);
  const selectedId = params.get("bill");
  const bills = useBills(filters);
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
  const updateFilter = <K extends keyof BillFilters>(
    key: K,
    value: BillFilters[K],
  ) => setFilters((current) => ({ ...current, [key]: value, offset: 0 }));
  const select = (id: string | null) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (id) next.set("bill", id);
      else next.delete("bill");
      return next;
    });
  return (
    <div className="max-w-5xl">
      <h1 className="mb-2 text-2xl font-bold text-white">Faktury i paragony</h1>
      <FinanceTabs />
      <div className="card mb-5 flex flex-wrap gap-3 p-3">
        <label className="text-sm text-gray-300">
          Typ
          <select
            aria-label="Typ dokumentu"
            className="input ml-2"
            value={filters.kind ?? ""}
            onChange={(e) =>
              setFilters((value) => ({
                ...value,
                kind: (e.target.value || undefined) as BillFilters["kind"],
                offset: 0,
              }))
            }
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
            onChange={(event) =>
              updateFilter(
                "review",
                (event.target.value || undefined) as BillFilters["review"],
              )
            }
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
              updateFilter(
                "declaration",
                (event.target.value || undefined) as BillFilters["declaration"],
              )
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
            onChange={(event) =>
              updateFilter("due_from", event.target.value || undefined)
            }
          />
        </label>
        <label className="text-sm text-gray-300">
          Termin do
          <input
            aria-label="Termin do"
            type="date"
            className="input ml-2"
            value={filters.due_to ?? ""}
            onChange={(event) =>
              updateFilter("due_to", event.target.value || undefined)
            }
          />
        </label>
        <input
          aria-label="Szukaj dokumentu"
          className="input"
          placeholder="Sprzedawca, numer lub opis"
          value={filters.query ?? ""}
          onChange={(event) =>
            updateFilter("query", event.target.value || undefined)
          }
        />
        <label className="text-sm text-gray-300">
          Stan
          <select
            aria-label="Stan dokumentu"
            className="input ml-2"
            value={filters.lifecycle ?? "active"}
            onChange={(e) =>
              setFilters((value) => ({
                ...value,
                lifecycle: (e.target.value ||
                  undefined) as BillFilters["lifecycle"],
                offset: 0,
              }))
            }
          >
            <option value="active">Aktywne</option>
            <option value="archived">Archiwalne</option>
            <option value="cancelled">Anulowane</option>
          </select>
        </label>
      </div>
      {bills.isError ? (
        <p role="alert" className="card text-sm text-red-300">
          Nie udało się pobrać rejestru dokumentów.
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
                onClick={() =>
                  setFilters((value) => ({
                    ...value,
                    offset: Math.max(
                      0,
                      (value.offset ?? 0) - (value.limit ?? 25),
                    ),
                  }))
                }
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
                onClick={() =>
                  setFilters((value) => ({
                    ...value,
                    offset: (value.offset ?? 0) + (value.limit ?? 25),
                  }))
                }
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
          Nie udało się pobrać dokumentu. Wróć do rejestru i odśwież dane.
        </p>
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
    </div>
  );
}
