import { useState } from "react";
import type { ImportPreview as PreviewData } from "../../../api/bankImports";
import { sourceMoney } from "./importPresentation";

export function ImportPreview({
  preview,
  current,
  pending,
  onCommit,
}: {
  preview: PreviewData;
  current: boolean;
  pending: boolean;
  onCommit: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  return (
    <section
      className="card space-y-4"
      role="region"
      aria-label="Podgląd zatwierdzenia"
    >
      <h2 className="text-xl">Podgląd zatwierdzenia</h2>
      <p>
        Nowe transakcje: {preview.new_transaction_count} · Powiązania:{" "}
        {preview.linked_count} · Otwarte wiersze przed zapisem:{" "}
        {preview.unresolved_count}
      </p>
      <p className="text-sm">
        To zamrożona wycena wybranych grup. Sam podgląd nie zmienił księgi.
      </p>
      {preview.groups.map((group) => (
        <article
          key={group.group_id}
          className="space-y-2 border-t border-gray-200 pt-3 dark:border-gray-700"
        >
          {group.action === "link" ? (
            <p>
              Powiąż z istniejącą operacją {group.transaction_id}. Jej kwoty i
              daty pozostają bez zmian.
            </p>
          ) : (
            group.operations.map((operation, index) => (
              <div key={index} className="space-y-1">
                <h3>
                  {operation.description} ·{" "}
                  {operation.component === "fee"
                    ? "opłata / zwrot opłaty"
                    : operation.kind}
                </h3>
                <p className="text-sm">
                  Księgowanie: {operation.booking_date} · Operacja:{" "}
                  {operation.purchase_date ?? "Nie podano"}
                </p>
                <ul>
                  {operation.postings
                    .filter((posting) => posting.account_id)
                    .map((posting, postingIndex) => (
                      <li key={postingIndex} className="font-mono text-sm">
                        {posting.direction === "debit" ? "Wypływ" : "Wpływ"}:{" "}
                        {sourceMoney(
                          posting.source_amount,
                          posting.source_currency,
                        )}{" "}
                        · wycena {sourceMoney(posting.base_amount_pln, "PLN")} ·
                        kurs {posting.fx_rate} ({posting.fx_rate_source})
                      </li>
                    ))}
                </ul>
              </div>
            ))
          )}
          {group.card_statement ? (
            <p className="text-sm">
              Osobny rekord wyciągu karty — nie korekta salda ani potwierdzenie
              spłaty.
            </p>
          ) : null}
        </article>
      ))}
      {preview.quotes.map((quote, index) => (
        <p className="text-xs" key={index}>
          {quote.currency
            ? `${quote.currency}: ${quote.rate} PLN · ${quote.source} · żądana data ${quote.requested_date}, notowanie ${quote.effective_date}`
            : `Wspólna wycena FX: ${sourceMoney(quote.base_pln ?? 0, "PLN")} · kurs wychodzący ${quote.from_rate} (${quote.from_source}), przychodzący ${quote.to_rate} (${quote.to_source}) · ${quote.quote_date}`}
        </p>
      ))}
      {preview.warnings.map((warning) => (
        <p className="break-words text-sm" key={warning}>
          Ostrzeżenie: {warning}
        </p>
      ))}
      {!current ? (
        <p role="alert">
          Dane lub wybór grup zmieniły się. Przygotuj podgląd ponownie.
        </p>
      ) : null}
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={!current || pending}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Potwierdzam wybrane grupy, rzeczywiste kwoty i zamrożone kursy. Chcę
        zapisać ten wynik do księgi.
      </label>
      <button
        type="button"
        className="btn-primary"
        disabled={!confirmed || !current || pending}
        onClick={onCommit}
      >
        {pending ? "Sprawdzanie i zapisywanie…" : "Zatwierdź wybrane grupy"}
      </button>
    </section>
  );
}
