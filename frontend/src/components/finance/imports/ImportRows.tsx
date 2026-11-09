import type { ImportRow } from "../../../api/bankImports";

import { sourceMoney } from "./importPresentation";
export function ImportRows({
  rows,
  selectedIds,
  onSelect,
  readOnly = false,
}: {
  rows: ImportRow[];
  selectedIds: Set<string>;
  onSelect: (row: ImportRow, checked: boolean) => void;
  readOnly?: boolean;
}) {
  return (
    <section className="space-y-3" aria-label="Wiersze źródłowe">
      <h2 className="text-xl">Wiersze źródłowe</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Kwoty i daty pochodzą z banku. Nie można ich poprawiać w formularzu
        importu.
      </p>
      {rows.map((row) => {
        const value = row.bank_fields;
        if (!value) return null;
        return (
          <article className="card space-y-2" key={row.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <label className="flex min-w-0 items-start gap-2">
                <input
                  type="checkbox"
                  aria-label={`Wybierz wiersz ${value.description}`}
                  checked={selectedIds.has(row.id)}
                  disabled={readOnly || value.state !== "posted"}
                  onChange={(event) => onSelect(row, event.target.checked)}
                />
                <strong className="break-words">{value.description}</strong>
              </label>
              <span className="shrink-0 font-mono tabular-nums">
                {sourceMoney(value.amount, value.currency)}
              </span>
            </div>
            <p className="text-sm">
              Księgowanie: {value.booking_date ?? "Brak daty"} · Operacja:{" "}
              {value.operation_date ?? "Nie podano"} · Stan banku: {value.state}
            </p>
            {value.fee !== 0 ? (
              <p className="text-sm">
                Opłata bankowa: {sourceMoney(value.fee, value.currency)} —
                zawarta w ruchu netto powyżej, nie jest doliczana drugi raz.
              </p>
            ) : null}
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Źródło: {row.source_key} · strona {row.position.page ?? "CSV"},
              wiersz {row.position.line}
              {row.position.section ? ` · ${row.position.section}` : ""}
            </p>
            {row.decision ? (
              <p className="text-sm">
                Zapisana decyzja:{" "}
                {row.decision.action === "link"
                  ? "Powiąż z istniejącą"
                  : row.decision.action === "defer"
                    ? "Pozostaw otwarte"
                    : "Nowa operacja"}
              </p>
            ) : null}
            <details>
              <summary className="cursor-pointer text-sm underline">
                Surowe pola banku
              </summary>
              <dl className="space-y-1 break-all text-xs">
                {Object.entries(value.raw).map(([key, field]) => (
                  <div key={key}>
                    <dt className="font-semibold">{key}</dt>
                    <dd>
                      {typeof field === "object"
                        ? JSON.stringify(field)
                        : String(field ?? "—")}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          </article>
        );
      })}
      {rows.length === 0 ? (
        <p>
          Brak wierszy w tym widoku. Poczekaj na zakończenie odczytu lub wybierz
          inne źródło.
        </p>
      ) : null}
    </section>
  );
}
