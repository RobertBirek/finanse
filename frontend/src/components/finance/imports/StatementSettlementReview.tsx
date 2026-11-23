import { isAxiosError } from "axios";
import { useState } from "react";
import {
  importError,
  type SettlementIntent,
  type SettlementPreview,
  useConfirmSettlement,
  useReadSettlement,
} from "../../../api/bankImports";
import type { Account, Category } from "../../../api/finance";
import { categoryPath } from "../../../lib/categories";
import { sourceMoney } from "./importPresentation";

const sectionNames = {
  settled: "Już rozliczone",
  link: "Proponowane powiązania",
  create: "Nowe transakcje",
  review: "Do sprawdzenia",
} as const;

const reasons: Record<string, string> = {
  recorded_evidence: "Wiersz ma zapisane rozliczenie w księdze.",
  saved_decision:
    "Ten wiersz ma wcześniejszą decyzję. Nie zmieniamy jej tutaj.",
  source_or_account_review: "Sprawdź rachunek oraz bieżący odczyt źródła.",
  movement_unclear:
    "Ta operacja wymaga osobnej decyzji, np. spłata, gotówka lub kapitał raty.",
  possible_duplicate:
    "Możliwy duplikat lub więcej niż jedno pasujące powiązanie.",
  fx_review: "Operacja nie jest w PLN.",
  no_existing_candidate:
    "Nie znaleziono pasującego wpisu na wybranym rachunku.",
  same_bank_reference: "Zgodny identyfikator bankowy, data i kwota.",
  exact_statement_match:
    "Zgodne: rachunek, waluta, kierunek, kwota, data i opis.",
};

export function StatementSettlementReview({
  batchId,
  version,
  accounts,
  categories,
  disabled,
}: {
  batchId: string;
  version: number;
  accounts: Account[];
  categories: Category[];
  disabled: boolean;
}) {
  const [accountId, setAccount] = useState("");
  const [review, setReview] = useState<SettlementPreview | null>(null);
  const [selection, setSelection] = useState<Record<string, boolean>>({});
  const [categoryIds, setCategories] = useState<Record<string, string>>({});
  const [acks, setAcks] = useState<string[]>([]);
  const [attempt, setAttempt] = useState<{
    idempotencyKey: string;
    data: SettlementIntent;
  } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [failed, setFailed] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const read = useReadSettlement(batchId);
  const confirm = useConfirmSettlement(batchId);
  const busy = read.isPending || confirm.isPending;
  const stale = !!review && review.version !== version;
  const selected = review?.rows.filter((row) => selection[row.id]) ?? [];
  const needed = [
    ...new Set(
      selected.flatMap((row) =>
        row.acknowledgement ? [row.acknowledgement] : [],
      ),
    ),
  ];
  const canConfirm =
    !!review &&
    selected.length > 0 &&
    selected.every(
      (row) =>
        row.status === "link" ||
        (row.status === "create" && categoryIds[row.id]),
    ) &&
    needed.every((item) => acks.includes(item));

  async function load() {
    if (!accountId || busy || disabled || unknown) return;
    setReview(null);
    setMessage(null);
    setCompleted(false);
    setFailed(false);
    setAttempt(null);
    setAcks([]);
    try {
      const result = await read.mutateAsync(accountId);
      setCategories(
        Object.fromEntries(
          result.rows.flatMap((row) =>
            row.category_id ? [[row.id, row.category_id]] : [],
          ),
        ),
      );
      setSelection(
        Object.fromEntries(
          result.rows.map((row) => [
            row.id,
            !row.acknowledgement &&
              (row.status === "link" ||
                (row.status === "create" && !!row.category_id)),
          ]),
        ),
      );
      setReview(result);
    } catch (error) {
      setFailed(true);
      setMessage(importError(error));
    }
  }

  async function save(retry?: NonNullable<typeof attempt>) {
    if (
      !review ||
      busy ||
      disabled ||
      (!retry && (!canConfirm || stale || unknown))
    )
      return;
    const request = retry ?? {
      idempotencyKey: crypto.randomUUID(),
      data: {
        account_id: review.account_id,
        fingerprint: review.fingerprint,
        selection: selected.map((row) =>
          row.status === "create"
            ? { row_id: row.id, category_id: categoryIds[row.id] }
            : { row_id: row.id },
        ),
        acknowledgements: needed,
        confirmed: true as const,
      },
    };
    setAttempt(request);
    setMessage(null);
    setFailed(false);
    try {
      const result = await confirm.mutateAsync(request);
      setUnknown(false);
      setAttempt(null);
      setReview(null);
      setCompleted(true);
      setMessage(
        `Rozliczenie zapisane. Powiązania: ${result.linked_row_ids.length} · Nowe transakcje: ${result.transaction_ids.length}.`,
      );
    } catch (error) {
      const response = isAxiosError(error) ? error.response : undefined;
      const uncertain = !response || response.status >= 500;
      setUnknown(uncertain);
      setFailed(true);
      if (!uncertain) {
        setReview(null);
        setAttempt(null);
      }
      setMessage(
        uncertain
          ? "Wynik jest nieznany. Ponów tę samą decyzję, żeby nie tworzyć drugiego zapisu."
          : importError(error),
      );
    }
  }

  return (
    <section
      className="card space-y-3"
      aria-label="Zbiorcze rozliczenie wyciągu"
    >
      <h2 className="text-xl">Zbiorcze rozliczenie wyciągu</h2>
      <p className="text-sm">
        Przygotowanie propozycji nic nie księguje. Jeden wiersz rozliczamy jedną
        transakcją, bez sumowania.
      </p>
      <label className="block">
        Rachunek wyciągu
        <select
          className="input mt-1 block w-full sm:w-auto"
          disabled={busy || disabled || unknown}
          value={accountId}
          onChange={(event) => {
            setAccount(event.target.value);
            setReview(null);
            setCompleted(false);
            setMessage(null);
          }}
        >
          <option value="">Wybierz rachunek lub kartę</option>
          {accounts
            .filter(
              (account) =>
                account.is_active &&
                account.currency === "PLN" &&
                ["checking", "savings", "credit_card"].includes(account.type),
            )
            .map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
        </select>
      </label>
      <button
        type="button"
        className="btn-secondary"
        disabled={!accountId || busy || disabled || unknown}
        onClick={() => void load()}
      >
        {read.isPending ? "Przygotowywanie…" : "Przygotuj rozliczenie"}
      </button>
      {message ? <p role={failed ? "alert" : "status"}>{message}</p> : null}
      {unknown && attempt ? (
        <button
          className="btn-primary"
          type="button"
          disabled={busy || disabled}
          onClick={() => void save(attempt)}
        >
          Ponów tę samą decyzję zbiorczą
        </button>
      ) : null}
      {review && !completed ? (
        <div className="space-y-4">
          {stale ? (
            <p role="alert">
              Import się zmienił. Przygotuj rozliczenie ponownie.
            </p>
          ) : null}
          {review.rows.length === 0 ? (
            <p>Nie ma jeszcze odczytanych wierszy.</p>
          ) : null}
          {(Object.keys(sectionNames) as (keyof typeof sectionNames)[]).map(
            (status) => {
              const rows = review.rows.filter((row) => row.status === status);
              if (rows.length === 0) return null;
              return (
                <div key={status} className="space-y-2">
                  <h3 className="font-semibold">{sectionNames[status]}</h3>
                  <ul className="space-y-2">
                    {rows.map((row) => (
                      <li
                        key={row.id}
                        className="space-y-1 border-b border-gray-200 pb-2 text-sm dark:border-gray-700"
                      >
                        <div className="flex flex-wrap justify-between gap-2">
                          <span className="min-w-0 break-words">
                            {status === "link" || status === "create" ? (
                              <input
                                type="checkbox"
                                className="mr-2"
                                aria-label={`Wybierz ${row.description}`}
                                checked={!!selection[row.id]}
                                disabled={disabled || busy || stale || unknown}
                                onChange={(event) =>
                                  setSelection({
                                    ...selection,
                                    [row.id]: event.target.checked,
                                  })
                                }
                              />
                            ) : null}
                            {row.date ? `${row.date} · ` : ""}
                            {row.description}
                          </span>
                          <span className="font-mono">
                            {sourceMoney(row.amount, row.currency)}
                          </span>
                        </div>
                        <p>
                          {reasons[row.reason] ??
                            "Sprawdź ten wiersz w trybie ręcznym."}
                        </p>
                        {row.target ? (
                          <p>
                            Istniejąca transakcja: {row.target.date} ·{" "}
                            {row.target.description}
                          </p>
                        ) : null}
                        {row.acknowledgement ? (
                          <p>Wymaga potwierdzenia różnicy salda otwarcia.</p>
                        ) : null}
                        {status === "create" ? (
                          <label className="block">
                            <span className="sr-only">
                              Kategoria: {row.description}
                            </span>
                            <select
                              className="input mt-1 block w-full sm:w-auto"
                              value={categoryIds[row.id] ?? ""}
                              disabled={disabled || busy || stale || unknown}
                              onChange={(event) => {
                                const id = event.target.value;
                                setCategories({ ...categoryIds, [row.id]: id });
                                setSelection({
                                  ...selection,
                                  [row.id]:
                                    !!id &&
                                    (!row.acknowledgement ||
                                      !!selection[row.id]),
                                });
                              }}
                            >
                              <option value="">
                                Wybierz kategorię lub zostaw otwarte
                              </option>
                              {categories
                                .filter(
                                  (category) =>
                                    category.is_active &&
                                    category.type === row.kind,
                                )
                                .map((category) => (
                                  <option key={category.id} value={category.id}>
                                    {categoryPath(category.id, categories)}
                                  </option>
                                ))}
                            </select>
                          </label>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            },
          )}
          {needed.length ? (
            <label className="flex gap-2 text-sm">
              <input
                type="checkbox"
                disabled={disabled || busy || stale || unknown}
                checked={needed.every((item) => acks.includes(item))}
                onChange={(event) =>
                  setAcks(event.target.checked ? needed : [])
                }
              />
              Akceptuję różnicę salda otwarcia wybranych źródeł bez korekty
              księgi.
            </label>
          ) : null}
          <p className="text-sm" aria-live="polite">
            Powiązania: {selected.filter((row) => row.status === "link").length}{" "}
            · Nowe transakcje:{" "}
            {selected.filter((row) => row.status === "create").length} · Bez
            nowego zapisu:{" "}
            {review.rows.filter((row) => row.status !== "settled").length -
              selected.length}
          </p>
          <button
            className="btn-primary"
            type="button"
            disabled={disabled || stale || busy || !canConfirm || unknown}
            onClick={() => void save()}
          >
            Zatwierdź wybrane
          </button>
        </div>
      ) : null}
    </section>
  );
}
