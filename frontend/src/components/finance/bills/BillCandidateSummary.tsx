import type { BillCandidate } from "../../../api/bills";

const reasons: Record<string, string> = {
  amount_exact: "Kwota płatności równa sumie dokumentu",
  amount_difference: "Kwota płatności różni się od sumy dokumentu",
  date_within_window: "Data zapisu mieści się w domyślnym oknie",
  date_older_than_window: "Data zapisu poza domyślnym oknem (wcześniejsza)",
  purchase_date_within_window:
    "Data zakupu mieści się w oknie daty sprzedaży lub wystawienia",
  eligible_expense: "Istniejący wydatek z wolną kwotą do powiązania",
  legacy_inbox_target: "Wcześniejsze powiązanie wskazane przez Inbox",
};
const sources = {
  manual: "ręcznie",
  bank: "bank",
  document: "dokument",
  import: "import",
};
const transactionBases = {
  purchase: "zakup",
  booking: "księgowanie",
  legacy: "data zapisu (znaczenie nieustalone)",
};
const documentBases = {
  sale: "sprzedaż",
  due: "termin płatności",
  issue: "wystawienie (data odniesienia)",
  today: "dziś (brak dat dokumentu)",
};

export function BillCandidateSummary({
  candidate,
}: {
  candidate: BillCandidate;
}) {
  const e = candidate.evidence;
  const comparison = e?.date_comparison;
  return (
    <span className="min-w-0 break-words [overflow-wrap:anywhere]">
      <span className="font-medium">
        {candidate.account} · {candidate.date}
      </span>
      {e ? <span className="mt-1 block">{e.description}</span> : null}
      <span className="block">
        Kwota płatności: {(candidate.amount_minor / 100).toFixed(2)} PLN
      </span>
      <span className="block">
        Nieprzydzielone: {(candidate.unallocated_minor / 100).toFixed(2)} PLN
      </span>
      {e?.purchase_date ? (
        <span className="block">
          Zakup: {e.purchase_date} (
          {e.purchase_date_source
            ? sources[e.purchase_date_source]
            : "źródło nieustalone"}
          )
        </span>
      ) : null}
      {e?.booking_date ? (
        <span className="block">
          Księgowanie: {e.booking_date} (
          {e.booking_date_source
            ? sources[e.booking_date_source]
            : "źródło nieustalone"}
          )
        </span>
      ) : (
        <span className="block">
          Data zapisu — znaczenie nieustalone: {candidate.date}
        </span>
      )}
      {comparison ? (
        <span className="mt-1 block text-gray-400">
          Porównanie: {transactionBases[comparison.transaction_basis]}{" "}
          {comparison.transaction_date} ↔{" "}
          {documentBases[comparison.document_basis]} {comparison.document_date};
          różnica {comparison.delta_days} dni (
          {comparison.within_window
            ? "w oknie porównania"
            : "poza oknem porównania"}
          ).
        </span>
      ) : null}
      {e?.supplier_name_in_description ? (
        <span className="block">
          Nazwa sprzedawcy z dokumentu występuje w opisie płatności
        </span>
      ) : null}
      {e?.planned_account_matches === false ? (
        <span className="block text-amber-200">
          Inne konto niż zaplanowane — możesz powiązać tę płatność.
        </span>
      ) : null}
      {e?.planned_account_matches === true ? (
        <span className="block">Konto zgodne z planowanym.</span>
      ) : null}
      {candidate.reasons.map((reason) =>
        reasons[reason] ? (
          <span className="block text-gray-400" key={reason}>
            {reasons[reason]}
          </span>
        ) : null,
      )}
    </span>
  );
}
