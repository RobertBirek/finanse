import { useState } from "react";
import type { Account, Category } from "../../../api/finance";
import {
  useImportCandidates,
  useImportExistingTransaction,
  type ImportDecision,
  type ImportRow,
  type ImportTransactionKind,
  type ImportSource,
  type CardHeaderDecision,
} from "../../../api/bankImports";
import { ImportAccountMapping } from "./ImportAccountMapping";
import { ImportCardHeader } from "./ImportCardHeader";
import { sourceMoney } from "./importPresentation";
import { categoryOptions } from "../../../lib/categories";

export function ImportGroupEditor({
  batchId,
  rows,
  accounts,
  categories,
  sources,
  accountSuggestion,
  pending,
  onSave,
}: {
  batchId: string;
  rows: ImportRow[];
  accounts: Account[];
  categories: Category[];
  sources: ImportSource[];
  accountSuggestion?: string | null;
  pending: boolean;
  onSave: (decision: ImportDecision) => void;
}) {
  const saved = rows[0]?.decision;
  const [groupId] = useState(() => saved?.group_id ?? crypto.randomUUID());
  const [action, setAction] = useState<ImportDecision["action"] | "">(
    saved?.action ?? "",
  );
  const [kind, setKind] = useState<ImportTransactionKind | "">(
    saved?.kind ?? "",
  );
  const outgoing =
    rows.find(
      (row) =>
        row.bank_fields && row.bank_fields.amount + row.bank_fields.fee < 0,
    ) ?? rows[0];
  const [account, setAccount] = useState(
    saved?.account_id ?? accountSuggestion ?? "",
  );
  const [other, setOther] = useState(saved?.other_account_id ?? "");
  const [category, setCategory] = useState(saved?.category_id ?? "");
  const [feeCategory, setFeeCategory] = useState(saved?.fee_category_id ?? "");
  const [existing, setExisting] = useState(
    saved?.existing_transaction_id ?? "",
  );
  const [rate, setRate] = useState(saved?.manual_rate ?? "");
  const [headerEnabled, setHeaderEnabled] = useState(!!saved?.card_header);
  const [acknowledgements, setAcknowledgements] = useState(
    saved?.acknowledgements ?? [],
  );
  const reparseSources = sources.filter(
    (source) =>
      source.candidate_revision_id &&
      rows.some((row) => row.source_id === source.id),
  );
  const missingComparison =
    action !== "defer" &&
    reparseSources.some(
      (source) =>
        !acknowledgements.includes(
          `reparse_comparison:${source.id}:${source.candidate_revision_id}`,
        ),
    );
  const [header, setHeader] = useState<CardHeaderDecision | null>(
    saved?.card_header ?? null,
  );
  const headerEligible =
    accounts.find((item) => item.id === account)?.type === "credit_card" &&
    rows.every((row) => row.source_id === rows[0].source_id) &&
    sources.find((item) => item.id === rows[0]?.source_id)?.layout ===
      "velo_card_v1";
  const candidates = useImportCandidates(
    batchId,
    action === "link" ? (rows[0]?.id ?? null) : null,
  );
  const internal = kind === "transfer" || kind === "exchange";
  const categoryChoices = categoryOptions(categories);
  const existingPayment = useImportExistingTransaction(
    batchId,
    action === "link" ? existing || null : null,
  );
  const old = existingPayment.data;
  const linkDateDifference =
    !!old &&
    rows.some(
      (row) =>
        row.bank_fields?.booking_date &&
        row.bank_fields.booking_date !== old.transaction_date,
    );
  const linkMismatch =
    action === "link" &&
    (!old ||
      old.is_pending ||
      old.type !== (kind === "expense_refund" ? "expense" : kind) ||
      !rows.every((row) => {
        const value = row.bank_fields;
        if (!value) return false;
        const mappedAccount =
          internal && rows.length === 2 && value.amount + value.fee > 0
            ? other
            : account;
        return old.postings.some(
          (posting) =>
            posting.account_id === mappedAccount &&
            posting.source_currency === value.currency &&
            posting.source_amount === Math.abs(value.amount) &&
            posting.direction === (value.amount < 0 ? "debit" : "credit"),
        );
      }));
  const incomplete =
    action !== "defer" &&
    (!kind ||
      !account ||
      (action === "link"
        ? !existing
        : internal
          ? !other || other === account
          : !category) ||
      (kind === "exchange" && rows.length !== 2) ||
      (internal && rows.length > 2) ||
      (!internal && rows.length !== 1) ||
      (action === "create" &&
        rows.some((row) => row.bank_fields?.fee) &&
        !feeCategory));
  return (
    <form
      className="card space-y-3"
      aria-label="Decyzja dla wybranych wierszy"
      onSubmit={(event) => {
        event.preventDefault();
        if (
          pending ||
          !action ||
          incomplete ||
          missingComparison ||
          linkMismatch ||
          (action === "link" &&
            linkDateDifference &&
            !acknowledgements.includes("link_date_difference")) ||
          (action !== "defer" &&
            headerEnabled &&
            (!headerEligible || !header || header.account_id !== account))
        )
          return;
        onSave({
          group_id: groupId,
          row_ids: rows.map((row) => row.id),
          action,
          kind: kind || null,
          account_id: account || null,
          other_account_id: internal ? other || null : null,
          category_id:
            action === "create" && !internal ? category || null : null,
          existing_transaction_id: action === "link" ? existing : null,
          fee_category_id: feeCategory || null,
          manual_rate: rate || null,
          acknowledgements,
          card_header: headerEnabled && action !== "defer" ? header : null,
        });
      }}
    >
      <fieldset disabled={pending} className="space-y-3">
        <h2 className="text-xl">Decyzja dla {rows.length} wierszy</h2>
        <label className="block text-sm">
          Co zrobić z wierszem?
          <select
            className="input mt-1 block w-full"
            value={action}
            onChange={(event) => setAction(event.target.value as typeof action)}
          >
            <option value="">Wybierz decyzję</option>
            <option value="create">Zarejestruj odrębną operację</option>
            <option value="link">Powiąż z istniejącą operacją</option>
            <option value="defer">Pozostaw otwarte</option>
          </select>
        </label>
        {action && action !== "defer" ? (
          <>
            <label className="block text-sm">
              Rodzaj operacji
              <select
                className="input mt-1 block w-full"
                value={kind}
                onChange={(event) => setKind(event.target.value as typeof kind)}
              >
                <option value="">Wybierz klasyfikację</option>
                <option value="expense">Wydatek zewnętrzny</option>
                <option value="income">Wpływ zewnętrzny</option>
                <option value="expense_refund">
                  Zwrot wydatku lub prowizji
                </option>
                <option value="transfer">Transfer własny / gotówka</option>
                <option value="exchange">Wymiana walut — obie nogi</option>
              </select>
            </label>
            <ImportAccountMapping
              accounts={accounts}
              value={account}
              onChange={setAccount}
              currency={outgoing?.bank_fields?.currency}
            />
            {internal ? (
              <ImportAccountMapping
                accounts={accounts}
                label="Drugi własny rachunek"
                value={other}
                onChange={setOther}
                exclude={account}
                currency={
                  kind === "transfer"
                    ? outgoing?.bank_fields?.currency
                    : undefined
                }
              />
            ) : null}
            {action === "create" && !internal ? (
              <label className="block text-sm">
                Kategoria
                <select
                  className="input mt-1 block w-full"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  <option value="">Wybierz kategorię</option>
                  {categoryChoices
                    .filter(
                      (item) =>
                        item.is_active &&
                        item.type ===
                          (kind === "income" ? "income" : "expense"),
                    )
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                </select>
              </label>
            ) : null}
            {action === "create" && rows.some((row) => row.bank_fields?.fee) ? (
              <label className="block text-sm">
                Kategoria opłaty / zwrotu opłaty
                <select
                  className="input mt-1 block w-full"
                  value={feeCategory}
                  onChange={(event) => setFeeCategory(event.target.value)}
                >
                  <option value="">Wybierz kategorię kosztu</option>
                  {categoryChoices
                    .filter((item) => item.is_active && item.type === "expense")
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                </select>
              </label>
            ) : null}
            {action === "link" ? (
              <label className="block text-sm">
                Istniejąca operacja
                <select
                  className="input mt-1 block w-full"
                  value={existing}
                  onChange={(event) => {
                    setExisting(event.target.value);
                    setAcknowledgements((current) =>
                      current.filter(
                        (value) => value !== "link_date_difference",
                      ),
                    );
                  }}
                >
                  <option value="">
                    Wybierz po sprawdzeniu konta, kwoty i dat
                  </option>
                  {(candidates.data ?? []).map((candidate) => (
                    <option
                      key={candidate.account_posting_id}
                      value={candidate.transaction_id}
                    >
                      {candidate.transaction_id} ·{" "}
                      {candidate.strength === "strong"
                        ? "referencja bankowa"
                        : "możliwe dopasowanie"}
                      {candidate.conflicts.length
                        ? ` · różnice: ${candidate.conflicts.join(", ")}`
                        : ""}
                    </option>
                  ))}
                </select>
                <span>
                  Podobna kwota i data nie potwierdzają tożsamości płatności.
                </span>
              </label>
            ) : null}
            {action === "create" &&
            rows.some((row) => row.bank_fields?.currency !== "PLN") ? (
              <label className="block text-sm">
                Ręczny kurs PLN (opcjonalny)
                <input
                  className="input mt-1 block w-full"
                  inputMode="decimal"
                  value={rate}
                  onChange={(event) =>
                    setRate(event.target.value.replace(",", "."))
                  }
                />
                <span>
                  Puste pole: historyczny NBP. Wymiana z PLN zachowuje kurs
                  wynikający z rzeczywistych nóg.
                </span>
              </label>
            ) : null}
            {kind === "exchange" && rows.length !== 2 ? (
              <p role="alert">
                Wybierz dwa rzeczywiste wiersze wymiany, wychodzący i
                przychodzący. Nie szacujemy brakującej nogi.
              </p>
            ) : null}
            {kind === "transfer" ? (
              <p className="text-sm">
                Transfer nie jest przychodem ani wydatkiem. Dla wypłaty wybierz
                własny rachunek gotówki.
              </p>
            ) : null}
          </>
        ) : null}
        {action === "link" && existing ? (
          <section
            className="space-y-2 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700"
            aria-label="Fakty istniejącej płatności"
          >
            {existingPayment.isLoading ? (
              <p role="status">Ładowanie istniejącej płatności…</p>
            ) : old ? (
              <>
                <h3>{old.description}</h3>
                <p>
                  Data starej operacji: {old.transaction_date} · źródło:{" "}
                  {old.source}
                </p>
                {old.date_metadata?.purchase_date ? (
                  <p>
                    Zakup starej operacji: {old.date_metadata.purchase_date} (
                    {old.date_metadata.purchase_date_source})
                  </p>
                ) : null}
                <ul>
                  {old.postings
                    .filter((posting) => posting.account_id)
                    .map((posting) => (
                      <li key={posting.id}>
                        Ruch starego rachunku:{" "}
                        {sourceMoney(
                          posting.direction === "debit"
                            ? -posting.source_amount
                            : posting.source_amount,
                          posting.source_currency,
                        )}
                      </li>
                    ))}
                </ul>
                <p>
                  Powiązanie doda dowód bankowy. Nie zmieni tych kwot, dat,
                  kategorii ani wcześniejszych powiązań.
                </p>
                {linkMismatch ? (
                  <p role="alert">
                    Konto, waluta, rodzaj lub rzeczywista kwota nie pasują do
                    wybranych wierszy.
                  </p>
                ) : null}
                {linkDateDifference ? (
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={acknowledgements.includes(
                        "link_date_difference",
                      )}
                      onChange={(event) =>
                        setAcknowledgements((current) =>
                          event.target.checked
                            ? [...current, "link_date_difference"]
                            : current.filter(
                                (value) => value !== "link_date_difference",
                              ),
                        )
                      }
                    />
                    Akceptuję różnicę dat banku i starej operacji. Zachowaj
                    stare daty bez zmian.
                  </label>
                ) : null}
              </>
            ) : (
              <p role="alert">
                Nie udało się pobrać płatności.{" "}
                <button
                  type="button"
                  onClick={() => existingPayment.refetch()}
                  className="underline"
                >
                  Ponów odczyt
                </button>
              </p>
            )}
          </section>
        ) : null}
        {action && action !== "defer"
          ? reparseSources.map((source) => {
              const token = `reparse_comparison:${source.id}:${source.candidate_revision_id}`;
              return (
                <label
                  className="flex items-start gap-2 text-sm"
                  key={source.id}
                >
                  <input
                    type="checkbox"
                    checked={acknowledgements.includes(token)}
                    onChange={(event) =>
                      setAcknowledgements((current) =>
                        event.target.checked
                          ? [...current, token]
                          : current.filter((value) => value !== token),
                      )
                    }
                  />
                  Porównałem bieżący wiersz z ponownym odczytem{" "}
                  {source.original_name} ({source.candidate_parser_version}).
                  Serwer nadal zablokuje każdą różnicę pól lub kontroli.
                </label>
              );
            })
          : null}
        {headerEligible && action && action !== "defer" ? (
          <div className="space-y-3">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={headerEnabled}
                onChange={(event) => setHeaderEnabled(event.target.checked)}
              />
              Dodaj osobny rekord wyciągu karty
            </label>
            {headerEnabled ? (
              <ImportCardHeader
                key={account}
                accountId={account}
                initial={saved?.card_header}
                onChange={setHeader}
              />
            ) : null}
          </div>
        ) : null}
        <button
          className="btn-primary"
          disabled={
            pending ||
            !action ||
            incomplete ||
            missingComparison ||
            linkMismatch ||
            (action === "link" &&
              linkDateDifference &&
              !acknowledgements.includes("link_date_difference")) ||
            (action !== "defer" &&
              headerEnabled &&
              (!headerEligible || !header || header.account_id !== account))
          }
          type="submit"
        >
          Zapisz decyzję
        </button>
        <p className="text-xs">Zapisanie decyzji nie księguje operacji.</p>
      </fieldset>
    </form>
  );
}
