import { useState } from "react";
import type { AxiosError } from "axios";
import {
  useSerializedIntentKey,
  useAllocateBillPayment,
  useBillCandidates,
  useBill,
  useRecordBillPayment,
  type BillResponse,
} from "../../../api/bills";
import { useAccounts, useCategories } from "../../../api/finance";
import { Dialog } from "../../Dialog";

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
  const candidates = useBillCandidates(bill.id, {
    limit: 20,
    offset: candidateOffset,
    query: candidateQuery || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    include_older: includeOlder,
  });
  const currentBill = useBill(bill.id, false);
  const allocate = useAllocateBillPayment();
  const record = useRecordBillPayment();
  const accounts = useAccounts();
  const categories = useCategories();
  const [amount, setAmount] = useState((bill.remaining_minor / 100).toFixed(2));
  const [account, setAccount] = useState(bill.payment_account_id ?? "");
  const [category, setCategory] = useState(bill.category_id ?? "");
  const [mode, setMode] = useState<"link" | "record">("link");
  const [selected, setSelected] = useState<string | null>(null);
  const keyFor = useSerializedIntentKey();
  const [conflict, setConflict] = useState(false);
  const [comparison, setComparison] = useState<BillResponse | null>(null);
  const [needsNewDecision, setNeedsNewDecision] = useState(false);
  const activeBill = comparison ?? bill;
  const selectedCandidate = candidates.data?.items.find(
    (candidate) => candidate.posting_id === selected,
  );
  const value = minor(amount);
  const mutationError = allocate.error || record.error;
  const submit = () => {
    if (value == null || needsNewDecision) return;
    if (mode === "link" && selectedCandidate) {
      const confirm_recurring_conflict =
        selectedCandidate.recurring_conflicts.length && conflict
          ? true
          : undefined;
      allocate.mutate(
        {
          billId: activeBill.id,
          version: activeBill.version,
          posting_id: selectedCandidate.posting_id,
          amount_minor: value,
          ...(confirm_recurring_conflict ? { confirm_recurring_conflict } : {}),
          idempotencyKey: keyFor({
            mode,
            billId: activeBill.id,
            version: activeBill.version,
            posting_id: selectedCandidate.posting_id,
            amount_minor: value,
            confirm_recurring_conflict,
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
      <div className="mt-4 flex gap-2">
        <button
          className={mode === "link" ? "btn-primary" : "btn-secondary"}
          type="button"
          onClick={() => setMode("link")}
        >
          Powiąż istniejącą
        </button>
        <button
          className={mode === "record" ? "btn-primary" : "btn-secondary"}
          type="button"
          onClick={() => setMode("record")}
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
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input
              aria-label="Szukaj istniejącej płatności"
              className="input"
              placeholder="Szukaj płatności"
              value={candidateQuery}
              onChange={(event) => {
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
                  setIncludeOlder(event.target.checked);
                  setCandidateOffset(0);
                }}
              />{" "}
              Uwzględnij starsze
            </label>
          </div>
          {candidates.data?.items.map((candidate) => (
            <label
              key={candidate.posting_id}
              className="block rounded border border-gray-700 p-3 text-sm text-gray-300"
            >
              <input
                type="radio"
                name="candidate"
                checked={selected === candidate.posting_id}
                onChange={() => setSelected(candidate.posting_id)}
              />{" "}
              {candidate.account} · {candidate.date} ·{" "}
              {(candidate.unallocated_minor / 100).toFixed(2)} PLN
              {candidate.recurring_conflicts.length ? (
                <span className="block mt-1 text-amber-300">
                  Zmieni prognozę:{" "}
                  {candidate.recurring_forecast_before_pln ?? "—"} →{" "}
                  {candidate.recurring_forecast_after_pln ?? "—"} PLN
                </span>
              ) : null}
            </label>
          ))}
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
              disabled={!candidateOffset}
              onClick={() =>
                setCandidateOffset(Math.max(0, candidateOffset - 20))
              }
            >
              Poprzednie
            </button>
            <button
              className="btn-secondary"
              type="button"
              disabled={candidateOffset + 20 >= (candidates.data?.total ?? 0)}
              onClick={() => setCandidateOffset(candidateOffset + 20)}
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
              {categories.data
                ?.filter((item) => item.is_active && item.type === "expense")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
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
                const result = await currentBill.refetch();
                if (result.data) setComparison(result.data);
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
