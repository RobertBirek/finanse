import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import {
  useSerializedIntentKey,
  useAllocateBillPayment,
  useBillCandidates,
  useBill,
  useRecordBillPayment,
  type BillResponse,
  type BillCandidatePage,
} from "../../../api/bills";
import { useAccounts, useCategories } from "../../../api/finance";
import { Dialog } from "../../Dialog";
import { BillCandidateSummary } from "./BillCandidateSummary";
import { categoryOptions } from "../../../lib/categories";

const unavailableText = {
  document_inactive: "Dokument nie jest aktywny. Nie można powiązać płatności.",
  document_unapproved: "Zatwierdź dokument, aby powiązać płatność.",
  currency_unsupported: "Rozliczanie obsługuje tylko PLN.",
  document_reconciled: "Dokument jest już rozliczony.",
};

const errorText = (error: unknown) =>
  (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ??
  "Nie udało się zapisać rozliczenia. Pola pozostają do poprawy.";
const minor = (raw: string) =>
  /^\d+(\.\d{1,2})?$/.test(raw) ? Math.round(Number(raw) * 100) : null;
export function BillPaymentDialog({
  bill,
  onClose,
}: {
  bill: BillResponse;
  onClose: () => void;
}) {
  const [candidateQuery, setCandidateQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [includeOlder, setIncludeOlder] = useState(false);
  const [candidateOffset, setCandidateOffset] = useState(0);
  const client = useQueryClient();
  const filters = {
    limit: 20,
    offset: candidateOffset,
    query: candidateQuery || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    include_older: includeOlder,
  };
  const candidateKey = ["finance", "bills", bill.id, "candidates", filters];
  const filterKey = JSON.stringify(candidateKey);
  const candidates = useBillCandidates(bill.id, filters);
  const currentBill = useBill(bill.id, false);
  const allocate = useAllocateBillPayment();
  const record = useRecordBillPayment();
  const accounts = useAccounts();
  const categories = useCategories();
  const [amount, setAmount] = useState((bill.remaining_minor / 100).toFixed(2));
  const [account, setAccount] = useState(bill.payment_account_id ?? "");
  const [category, setCategory] = useState(bill.category_id ?? "");
  const [mode, setMode] = useState<"link" | "record">("link");
  const [selected, setSelected] = useState<{
    postingId: string;
    filterKey: string;
    revision: number;
    epoch: number;
  } | null>(null);
  const epoch = useRef(0);
  const keyFor = useSerializedIntentKey();
  const [conflict, setConflict] = useState(false);
  const clearDecision = useCallback(() => {
    epoch.current += 1;
    setSelected(null);
    setConflict(false);
  }, []);
  // Fetch-start invalidates even if a fast/identical response is batched by React.
  useEffect(
    () =>
      client.getQueryCache().subscribe((event) => {
        const key = event.query.queryKey;
        if (
          key[0] === "finance" &&
          key[1] === "bills" &&
          key[2] === bill.id &&
          key[3] === "candidates" &&
          event.type === "updated" &&
          ["fetch", "success", "error"].includes(event.action.type)
        ) {
          clearDecision();
        }
      }),
    [client, bill.id, clearDecision],
  );
  const [comparison, setComparison] = useState<BillResponse | null>(null);
  const [needsNewDecision, setNeedsNewDecision] = useState(false);
  const activeBill = comparison ?? bill;
  const validDates =
    (!dateFrom || /^\d{4}-\d{2}-\d{2}$/.test(dateFrom)) &&
    (!dateTo || /^\d{4}-\d{2}-\d{2}$/.test(dateTo)) &&
    !(dateFrom && dateTo && dateFrom > dateTo);
  // Read live state again in submit: cache changes may precede React's next render.
  const currentSelection = () => {
    const state = client.getQueryState<BillCandidatePage>(candidateKey);
    if (
      !selected ||
      selected.filterKey !== filterKey ||
      selected.epoch !== epoch.current ||
      state?.dataUpdateCount !== selected.revision ||
      state?.status !== "success" ||
      state.fetchStatus !== "idle" ||
      state.data?.unavailable_reason ||
      !validDates
    )
      return undefined;
    return state.data?.items.find(
      (candidate) => candidate.posting_id === selected.postingId,
    );
  };
  const selectedCandidate = currentSelection();
  const value = minor(amount);
  const mutationError = allocate.error || record.error;
  const submit = () => {
    if (
      value == null ||
      value <= 0 ||
      !Number.isSafeInteger(value) ||
      needsNewDecision ||
      allocate.isPending ||
      record.isPending
    )
      return;
    if (mode === "link") {
      const candidate = currentSelection();
      if (!candidate || (candidate.recurring_conflicts.length && !conflict))
        return;
      const confirm_recurring_conflict =
        candidate.recurring_conflicts.length && conflict ? true : undefined;
      allocate.mutate(
        {
          billId: activeBill.id,
          version: activeBill.version,
          posting_id: candidate.posting_id,
          amount_minor: value,
          ...(confirm_recurring_conflict ? { confirm_recurring_conflict } : {}),
          idempotencyKey: keyFor({
            mode,
            billId: activeBill.id,
            version: activeBill.version,
            posting_id: candidate.posting_id,
            amount_minor: value,
            confirm_recurring_conflict,
          }),
        },
        {
          onSuccess: onClose,
          onError: (error) => {
            if ((error as AxiosError).response?.status === 409) {
              clearDecision();
              setNeedsNewDecision(true);
            }
          },
        },
      );
    }
    if (mode === "record" && account && category) {
      const payment_date = new Date().toISOString().slice(0, 10);
      const description =
        bill.description ?? bill.supplier_name ?? "Płatność dokumentu";
      record.mutate(
        {
          billId: activeBill.id,
          version: activeBill.version,
          account_id: account,
          category_id: category,
          payment_date,
          amount_minor: value,
          description,
          confirm_new_payment: true,
          idempotencyKey: keyFor({
            mode,
            billId: activeBill.id,
            version: activeBill.version,
            account_id: account,
            category_id: category,
            payment_date,
            amount_minor: value,
            description,
            confirm_new_payment: true,
          }),
        },
        {
          onSuccess: onClose,
          onError: (error) => {
            if ((error as AxiosError).response?.status === 409)
              setNeedsNewDecision(true);
          },
        },
      );
    }
  };
  return (
    <Dialog
      label="Rozlicz płatność"
      onClose={onClose}
      busy={allocate.isPending || record.isPending}
    >
      <h2 className="text-lg font-semibold text-white">Rozlicz płatność</h2>
      <p className="mt-1 text-sm text-gray-400">
        Powiązanie nie zleca przelewu. Rejestracja tworzy osobny wydatek w
        księdze.
      </p>
      <p className="mt-2 text-sm text-gray-300 break-words">
        {activeBill.supplier_name}
        {activeBill.total_minor != null
          ? ` · Suma dokumentu: ${(activeBill.total_minor / 100).toFixed(2)} ${activeBill.currency}`
          : ""}
        {` · Pozostało do powiązania: ${(activeBill.remaining_minor / 100).toFixed(2)} ${activeBill.currency ?? "PLN"}`}
      </p>
      <p className="text-sm text-gray-400">
        {activeBill.sale_date ? `Sprzedaż: ${activeBill.sale_date}. ` : ""}
        {activeBill.issue_date ? `Wystawienie: ${activeBill.issue_date}. ` : ""}
        {activeBill.due_date ? `Termin płatności: ${activeBill.due_date}.` : ""}
      </p>
      <div className="mt-4 flex gap-2">
        <button
          className={mode === "link" ? "btn-primary" : "btn-secondary"}
          type="button"
          onClick={() => {
            clearDecision();
            setMode("link");
          }}
        >
          Powiąż istniejącą
        </button>
        <button
          className={mode === "record" ? "btn-primary" : "btn-secondary"}
          type="button"
          onClick={() => {
            clearDecision();
            setMode("record");
          }}
        >
          Zarejestruj płatność
        </button>
      </div>
      <label className="mt-4 block text-sm text-gray-300">
        Kwota (PLN)
        <input
          aria-label="Kwota (PLN)"
          className="input mt-1 w-full"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      {mode === "link" ? (
        <div className="mt-4 space-y-2">
          <p className="text-sm text-gray-400">
            Powiązanie nie tworzy transakcji i nie zmienia księgi. Zakres dat
            dotyczy daty zapisu w historii.
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input
              aria-label="Szukaj istniejącej płatności"
              className="input"
              placeholder="Szukaj płatności"
              value={candidateQuery}
              onChange={(event) => {
                clearDecision();
                setCandidateQuery(event.target.value);
                setCandidateOffset(0);
              }}
            />
            <label className="text-sm text-gray-300">
              Od
              <input
                aria-label="Data od"
                type="date"
                className="input mt-1 w-full"
                value={dateFrom}
                onChange={(event) => {
                  clearDecision();
                  setDateFrom(event.target.value);
                  setCandidateOffset(0);
                }}
              />
            </label>
            <label className="text-sm text-gray-300">
              Do
              <input
                aria-label="Data do"
                type="date"
                className="input mt-1 w-full"
                value={dateTo}
                onChange={(event) => {
                  clearDecision();
                  setDateTo(event.target.value);
                  setCandidateOffset(0);
                }}
              />
            </label>
            <label className="self-end text-sm text-gray-300">
              <input
                type="checkbox"
                checked={includeOlder}
                onChange={(event) => {
                  clearDecision();
                  setIncludeOlder(event.target.checked);
                  setCandidateOffset(0);
                }}
              />{" "}
              Uwzględnij starsze
            </label>
          </div>
          {!validDates ? (
            <p role="alert">
              Data od nie może być późniejsza niż data do. Sprawdź zakres dat.
            </p>
          ) : null}
          {candidates.isFetching ? (
            <p role="status">Pobieranie płatności…</p>
          ) : candidates.isError ? (
            <div role="alert">
              Nie udało się pobrać płatności. Spróbuj ponownie przy tych samych
              filtrach.
              <button
                type="button"
                className="btn-secondary ml-2"
                onClick={() => {
                  clearDecision();
                  void candidates.refetch();
                }}
              >
                Spróbuj ponownie
              </button>
            </div>
          ) : candidates.data?.unavailable_reason ? (
            <p>{unavailableText[candidates.data.unavailable_reason]}</p>
          ) : candidates.isSuccess && !candidates.data.items.length ? (
            <p>Brak płatności w wybranych filtrach.</p>
          ) : null}
          {!candidates.isFetching &&
          !candidates.isError &&
          !candidates.data?.unavailable_reason
            ? candidates.data?.items.map((candidate) => (
                <label
                  key={candidate.posting_id}
                  className="block rounded border border-gray-700 p-3 text-sm text-gray-300"
                >
                  <input
                    type="radio"
                    name="candidate"
                    checked={
                      selectedCandidate?.posting_id === candidate.posting_id
                    }
                    disabled={
                      !validDates || needsNewDecision || allocate.isPending
                    }
                    onChange={() => {
                      setConflict(false);
                      const state =
                        client.getQueryState<BillCandidatePage>(candidateKey);
                      if (
                        state?.status === "success" &&
                        state.fetchStatus === "idle" &&
                        !state.data?.unavailable_reason
                      )
                        setSelected({
                          postingId: candidate.posting_id,
                          filterKey,
                          revision: state.dataUpdateCount,
                          epoch: epoch.current,
                        });
                    }}
                  />{" "}
                  <BillCandidateSummary candidate={candidate} />
                  {candidate.recurring_conflicts.length ? (
                    <span className="block mt-1 text-amber-300">
                      Zmieni prognozę:{" "}
                      {candidate.recurring_forecast_before_pln ?? "—"} →{" "}
                      {candidate.recurring_forecast_after_pln ?? "—"} PLN
                    </span>
                  ) : null}
                </label>
              ))
            : null}
          {selectedCandidate?.recurring_conflicts.length ? (
            <label className="block text-sm text-amber-200">
              <input
                type="checkbox"
                checked={conflict}
                onChange={(e) => setConflict(e.target.checked)}
              />{" "}
              Rozumiem wpływ na prognozę cykliczną.
            </label>
          ) : null}
          <div className="flex justify-between text-sm">
            <button
              className="btn-secondary"
              type="button"
              disabled={!candidateOffset || candidates.isFetching}
              onClick={() => {
                clearDecision();
                setCandidateOffset(Math.max(0, candidateOffset - 20));
              }}
            >
              Poprzednie
            </button>
            <button
              className="btn-secondary"
              type="button"
              disabled={
                candidates.isFetching ||
                candidateOffset + 20 >= (candidates.data?.total ?? 0)
              }
              onClick={() => {
                clearDecision();
                setCandidateOffset(candidateOffset + 20);
              }}
            >
              Następne
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          <label className="block text-sm text-gray-300">
            Aktywne konto
            <select
              aria-label="Aktywne konto"
              className="input mt-1 w-full"
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            >
              <option value="">Wybierz konto</option>
              {accounts.data
                ?.filter((item) => item.is_active && item.currency === "PLN")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} (
                    {item.type === "cash" ? "gotówka" : "konto/karta"})
                  </option>
                ))}
            </select>
          </label>
          <label className="block text-sm text-gray-300">
            Kategoria
            <select
              aria-label="Kategoria"
              className="input mt-1 w-full"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">Wybierz kategorię</option>
              {categoryOptions(categories.data ?? [])
                .filter((item) => item.is_active && item.type === "expense")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
            </select>
          </label>
        </div>
      )}
      {mutationError ? (
        <p role="alert" className="mt-3 text-sm text-red-300">
          {errorText(mutationError)}{" "}
          {(mutationError as AxiosError).response?.status === 409
            ? "Odśwież dokument i porównaj stan przed ponowną próbą."
            : ""}
        </p>
      ) : null}
      {needsNewDecision ? (
        <div className="mt-3 rounded border border-amber-700 p-3 text-sm text-amber-100">
          Wersja przed zmianą: {bill.version}. Zapis jest zablokowany do
          odświeżenia i świadomej nowej decyzji.
          {comparison ? (
            <p className="mt-1">
              Aktualna wersja: {comparison.version}; pozostało:{" "}
              {(comparison.remaining_minor / 100).toFixed(2)} PLN.
            </p>
          ) : null}
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="btn-secondary"
              onClick={async () => {
                clearDecision();
                const [result] = await Promise.all([
                  currentBill.refetch(),
                  candidates.refetch(),
                ]);
                if (result.isSuccess && result.data) setComparison(result.data);
              }}
            >
              Odśwież aktualny dokument
            </button>
            {comparison ? (
              <button
                type="button"
                className="btn-primary"
                onClick={() => setNeedsNewDecision(false)}
              >
                Rozumiem — podejmuję nową decyzję
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onClose}>
          Anuluj
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={
            value == null ||
            value <= 0 ||
            !Number.isSafeInteger(value) ||
            allocate.isPending ||
            record.isPending ||
            needsNewDecision ||
            (mode === "link"
              ? !selectedCandidate ||
                (!!selectedCandidate.recurring_conflicts.length && !conflict)
              : !account || !category)
          }
          onClick={submit}
        >
          {mode === "link" ? "Powiąż płatność" : "Zarejestruj wydatek"}
        </button>
      </div>
    </Dialog>
  );
}
