import type { ImportRow } from "../../../api/bankImports";
import type { ScheduleRow } from "../../../api/loanScheduleImports";
import { formatPLN } from "../../../lib/format";

export function ScheduleSourceComparison({
  previous,
  candidate,
  loading,
  error,
}: {
  previous: ImportRow[];
  candidate: ImportRow[];
  loading: boolean;
  error: boolean;
}) {
  return (
    <section className="card space-y-3" aria-label="Porównanie odczytów źródła">
      <h2 className="text-xl">Porównanie odczytów źródła</h2>
      <p>
        Sprawdź obie tabele z oryginałem. Wybór kandydata nie zmienia
        poprzedniego odczytu ani aktywnego planu. Aktywacja nadal wymaga
        osobnego podglądu i potwierdzenia.
      </p>
      {loading ? (
        <p role="status">Ładowanie obu odczytów…</p>
      ) : error ? (
        <p role="alert">
          Nie udało się pobrać kompletnych tabel. Nie potwierdzaj porównania.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {(
            [
              ["Zachowany odczyt", previous],
              ["Kandydat nowego odczytu", candidate],
            ] as const
          ).map(([label, rows]) => (
            <div key={label} className="min-w-0 overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="text-left font-semibold">
                  {label} · {rows.length} rat
                </caption>
                <thead>
                  <tr>
                    {[
                      "Nr bankowy",
                      "Termin",
                      "Kapitał PLN",
                      "Odsetki PLN",
                      "Opłaty PLN",
                      "Razem PLN",
                      "Saldo po PLN",
                    ].map((h) => (
                      <th className="p-2 text-left" key={h}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => {
                    const r =
                      item.schedule_fields as unknown as ScheduleRow | null;
                    return r ? (
                      <tr key={item.id}>
                        <td className="p-2">{r.bank_number}</td>
                        <td className="p-2 whitespace-nowrap">{r.due_date}</td>
                        {[
                          r.principal,
                          r.interest,
                          r.fees,
                          r.total,
                          r.balance_after,
                        ].map((v, n) => (
                          <td
                            className="p-2 text-right whitespace-nowrap font-mono"
                            key={n}
                          >
                            {v == null ? "brak" : formatPLN(v)}
                          </td>
                        ))}
                      </tr>
                    ) : null;
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
