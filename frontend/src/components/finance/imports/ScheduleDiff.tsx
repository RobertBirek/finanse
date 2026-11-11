import type { ScheduleDifference } from "../../../api/loanScheduleImports";
import type { LoanInstallment } from "../../../api/loans";
import { formatPLN } from "../../../lib/format";

export function ScheduleDiff({
  diff,
  installments = [],
}: {
  diff: ScheduleDifference;
  installments?: LoanInstallment[];
}) {
  return (
    <section className="card space-y-4" aria-label="Porównanie harmonogramów">
      <h2 className="text-xl">Zakres zmiany od {diff.cutover_date}</h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Zgodne raty — te same UUID", diff.reused_ids.length],
          ["Nowe raty", diff.new_rows.length],
          ["Wycofane przyszłe raty", diff.superseded_ids.length],
          ["Zachowana historia", diff.retained_history_ids.length],
        ].map(([label, count]) => (
          <div key={label}>
            <dt className="text-sm text-gray-500 dark:text-gray-400">
              {label}
            </dt>
            <dd className="font-mono text-xl">{count}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm">
        Nie oznaczamy rat jako zapłaconych. Przeszłe niepokryte raty i
        istniejące powiązania pozostają zachowane; wycofana przyszłość nie
        wejdzie do aktywnych sum.
      </p>
      {diff.conflicts.length ? (
        <div role="alert" className="rounded-lg border border-red-400 p-3">
          <h3 className="font-semibold">Konflikty blokują aktywację</h3>
          <ul>
            {diff.conflicts.map((c, i) => (
              <li className="break-words text-sm" key={i}>
                {c.code === "linked_future_missing_or_changed"
                  ? "Powiązana rata nie jest zgodna z nowym planem"
                  : c.code === "historical_unpaid_missing"
                    ? "Brak zgodności przeszłej niepokrytej raty"
                    : c.code}
                {c.row_key ? ` · numer bankowy ${c.row_key}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {diff.new_rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="text-left">Nowe planowe raty — PLN</caption>
            <thead>
              <tr>
                {[
                  "Numer bankowy",
                  "Termin",
                  "Kapitał",
                  "Odsetki",
                  "Opłaty",
                  "Razem",
                ].map((t) => (
                  <th className="p-2 text-left" key={t}>
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {diff.new_rows.map((r) => (
                <tr key={r.bank_number}>
                  <td className="p-2">{r.bank_number}</td>
                  <td className="p-2 whitespace-nowrap">{r.due_date}</td>
                  {[r.principal, r.interest, r.fees, r.total].map((v, i) => (
                    <td
                      key={i}
                      className="p-2 text-right font-mono whitespace-nowrap"
                    >
                      {formatPLN(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {installments
        .filter(
          (i) =>
            diff.superseded_ids.includes(i.id) ||
            diff.retained_history_ids.includes(i.id),
        )
        .map((i) => (
          <p className="text-sm" key={i.id}>
            {diff.retained_history_ids.includes(i.id)
              ? "Zachowana historia"
              : "Wycofana przyszła rata"}{" "}
            · rata wewnętrzna {i.number} · {i.due_date} ·{" "}
            {formatPLN(i.total_pln)} PLN
          </p>
        ))}
    </section>
  );
}
