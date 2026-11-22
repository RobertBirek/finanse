import { useState } from "react";
import type { ImportSource } from "../../../api/bankImports";
import type { Account } from "../../../api/finance";

import { isSourceBlocked } from "./importPresentation";
import { importAutoPostReason } from "./importAutoPostReason";

function AutoPostSource({
  source,
  accounts,
  disabled,
  onAutoPost,
}: {
  source: ImportSource;
  accounts: Account[];
  disabled: boolean;
  onAutoPost: (source: ImportSource, accountId: string | null) => void;
}) {
  const [accountId, setAccountId] = useState("");
  const status = source.auto_post;
  const chooseAccount = source.has_account_reference === false;
  const eligible =
    source.processing_state === "ready" &&
    !!source.current_revision_id &&
    !source.candidate_revision_id &&
    !isSourceBlocked(source) &&
    source.layout !== "velo_card_v1" &&
    status?.state !== "queued" &&
    !status?.manual;
  return (
    <div className="space-y-2 text-sm">
      {status ? (
        <div role="status">
          {status.state === "queued"
            ? "Księgowanie automatyczne w kolejce."
            : `Zaksięgowano automatycznie: ${status.posted_count}${status.reason ? "." : ` · Skierowano do sprawdzenia: ${status.review_count}.`}`}
          {status.reason ? (
            <p>
              Nie zakończono automatycznego księgowania:{" "}
              {importAutoPostReason(status.reason)}
            </p>
          ) : null}
        </div>
      ) : null}
      {eligible && chooseAccount ? (
        <label className="block">
          Rachunek do jednorazowego księgowania
          <select
            className="input mt-1 block w-full"
            value={accountId}
            disabled={disabled}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">Wybierz własny rachunek</option>
            {accounts
              .filter(
                (account) =>
                  account.is_active &&
                  ["checking", "savings"].includes(account.type) &&
                  !!source.bank &&
                  (account.bank_name ?? "").toLowerCase().includes(source.bank),
              )
              .map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} · {account.currency}
                </option>
              ))}
          </select>
        </label>
      ) : null}
      {eligible ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled || (chooseAccount && !accountId)}
          onClick={() => onAutoPost(source, chooseAccount ? accountId : null)}
        >
          Zaksięguj jednoznaczne operacje
        </button>
      ) : null}
    </div>
  );
}

export function ImportSources({
  sources,
  selected,
  onSelect,
  onCompare,
  onPrepare,
  onAutoPost,
  accounts = [],
  disabled = false,
}: {
  sources: ImportSource[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onCompare?: (source: ImportSource) => void;
  onPrepare?: (id: string) => void;
  onAutoPost?: (source: ImportSource, accountId: string | null) => void;
  accounts?: Account[];
  disabled?: boolean;
}) {
  return (
    <section className="card space-y-3" aria-label="Źródła i kontrole">
      <h2 className="text-xl">Źródła i kontrole</h2>
      <button
        type="button"
        className="btn-secondary"
        aria-pressed={!selected}
        onClick={() => onSelect(null)}
      >
        Wszystkie źródła
      </button>
      {sources.map((source) => (
        <article
          className="space-y-2 rounded-lg border border-gray-200 p-3 dark:border-gray-700"
          key={source.id}
        >
          <button
            type="button"
            className="max-w-full break-all text-left font-semibold underline"
            aria-pressed={selected === source.id}
            onClick={() => onSelect(source.id)}
          >
            {source.original_name}
          </button>
          <p className="text-sm">
            {isSourceBlocked(source)
              ? "Błąd kontroli źródła — zatwierdzenie zablokowane"
              : source.processing_state !== "ready"
                ? `Odczyt: ${source.processing_state}`
                : source.validation_state === "needs_review"
                  ? "Wymaga porównania odczytu"
                  : "Kontrole źródła zgodne"}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {source.bank ?? "Nieznany bank"} ·{" "}
            {source.layout ?? "Nierozpoznany układ"} ·{" "}
            {source.parser_version ?? "Brak wersji odczytu"}
          </p>
          <ul className="text-xs">
            {source.checks.map((check) => (
              <li key={check.code}>
                {check.code}:{" "}
                {check.result === "passed"
                  ? "zgodna"
                  : check.result === "failed"
                    ? "błąd"
                    : "niedostępna"}
                {check.expected !== null
                  ? ` · oczekiwano ${check.expected}, odczytano ${check.actual ?? "brak"}`
                  : ""}
              </li>
            ))}
          </ul>
          {source.warnings.map((warning) => (
            <p key={warning} className="break-words text-sm">
              Uwaga źródła: {warning}
            </p>
          ))}
          <div className="flex flex-wrap gap-3 text-sm">
            {onPrepare ? (
              <button
                type="button"
                className="underline disabled:opacity-50"
                aria-label={`Ponów odczyt: ${source.original_name}`}
                disabled={
                  disabled ||
                  source.processing_state === "queued" ||
                  source.processing_state === "processing"
                }
                onClick={() => onPrepare(source.id)}
              >
                Ponów odczyt
              </button>
            ) : null}
            <a
              className="underline"
              href={`/api/documents/${encodeURIComponent(source.document_id)}/original`}
              target="_blank"
              rel="noreferrer"
            >
              Pobierz oryginał
            </a>
            {source.original_name.toLowerCase().endsWith(".pdf") ? (
              <a
                className="underline"
                href={`/api/documents/${encodeURIComponent(source.document_id)}/preview`}
                target="_blank"
                rel="noreferrer"
              >
                Podgląd PDF
              </a>
            ) : null}
          </div>
          {onAutoPost ? (
            <AutoPostSource
              key={source.current_revision_id}
              source={source}
              disabled={disabled}
              accounts={accounts}
              onAutoPost={onAutoPost}
            />
          ) : null}
          {source.candidate_revision_id ? (
            <div className="space-y-2">
              <p className="break-all text-sm">
                Dostępny ponowny odczyt: {source.candidate_parser_version}.
                Zmiany nie zastępują zatwierdzonej historii.
              </p>
              {onCompare ? (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => onCompare(source)}
                >
                  Porównaj ponowny odczyt: {source.original_name}
                </button>
              ) : null}
            </div>
          ) : null}
        </article>
      ))}
      {sources.length === 0 ? <p>Dodaj źródło, aby rozpocząć odczyt.</p> : null}
    </section>
  );
}
