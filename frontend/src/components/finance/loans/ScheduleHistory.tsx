import { useState } from "react";
import {
  useLoanScheduleRevision,
  useLoanScheduleRevisions,
} from "../../../api/loanScheduleImports";
import { formatPLN } from "../../../lib/format";

function HistoryContent({ loanId }: { loanId: string }) {
  const list = useLoanScheduleRevisions(loanId);
  const [selected, setSelected] = useState<string | null>(null);
  const id = selected ?? list.data?.[0]?.id ?? null;
  const detail = useLoanScheduleRevision(loanId, id);
  return (
    <div className="mt-4 space-y-4">
      <p className="text-sm">
        Historyczne kwoty są snapshotem wersji. Nie są doliczane ponownie do
        bieżącego planu i nie oznaczają zapłaty.
      </p>
      {list.isLoading ? (
        <p role="status">Ładowanie historii…</p>
      ) : list.isError ? (
        <p role="alert">Nie udało się pobrać historii wersji.</p>
      ) : list.data?.length ? (
        <label className="block">
          Wersja harmonogramu
          <select
            className="input mt-1 w-full"
            value={id ?? ""}
            onChange={(e) => setSelected(e.target.value)}
          >
            {list.data.map((v) => (
              <option key={v.id} value={v.id}>
                Wersja {v.ordinal} ·{" "}
                {v.kind === "manual_baseline"
                  ? "Baza ręczna"
                  : "Harmonogram bankowy"}{" "}
                · {v.state === "active" ? "Aktywna" : "Zastąpiona"}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p>
          Brak wersji bankowych. Ręcznie zapisane raty pozostają bieżącym
          planem.
        </p>
      )}
      {detail.isError ? (
        <p role="alert">Nie udało się pobrać snapshotu wersji.</p>
      ) : detail.isLoading && id ? (
        <p role="status">Ładowanie snapshotu…</p>
      ) : detail.data ? (
        <div className="space-y-3">
          <p className="text-sm">
            Data banku:{" "}
            {detail.data.bank_effective_date ?? "nie dotyczy bazy ręcznej"} ·
            aktywacja: {detail.data.activated_on} · granica zmiany:{" "}
            {detail.data.cutover_date}
          </p>
          {detail.data.document_id ? (
            <a
              className="underline"
              href={`/api/documents/${encodeURIComponent(detail.data.document_id)}/original`}
              target="_blank"
              rel="noreferrer"
            >
              Pobierz oryginał wersji: {detail.data.original_name}
            </a>
          ) : (
            <p className="text-sm">
              Baza ręczna — bez bankowego oryginału PDF.
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="text-left">
                Snapshot rat — nie bieżące saldo
              </caption>
              <thead>
                <tr>
                  {[
                    "Numer bankowy w wersji",
                    "Termin",
                    "Kapitał PLN",
                    "Odsetki PLN",
                    "Opłaty PLN",
                  ].map((t) => (
                    <th className="p-2 text-left" key={t}>
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detail.data.installments.map((i) => (
                  <tr key={i.installment_id}>
                    <td className="p-2">{i.bank_number ?? "baza ręczna"}</td>
                    <td className="p-2 whitespace-nowrap">{i.due_date}</td>
                    {[i.principal_pln, i.interest_pln, i.fees_pln].map(
                      (v, n) => (
                        <td
                          className="p-2 text-right font-mono whitespace-nowrap"
                          key={n}
                        >
                          {formatPLN(v)}
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
export function ScheduleHistory({ loanId }: { loanId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="card mt-4">
      <button
        type="button"
        className="btn-secondary"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        Historia wersji harmonogramu
      </button>
      {open ? <HistoryContent key={loanId} loanId={loanId} /> : null}
    </section>
  );
}
