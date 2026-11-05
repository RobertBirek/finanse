import type { ReceiptReadEvidence as Evidence } from "../../../api/receiptRead";
import { useReceiptReadResult } from "../../../api/receiptRead";
const fieldNames: Record<string, string> = {
  name: "nazwa",
  amount_minor: "kwota",
  shares: "udziały rabatu",
};
export function ReceiptReadEvidence({
  billId,
  evidence,
  selected,
  disabled,
  onChange,
}: {
  billId: string;
  evidence: Evidence;
  selected: string[] | null;
  disabled: boolean;
  onChange: (keys: string[]) => void;
}) {
  const result = useReceiptReadResult(billId, evidence.job_id);
  const problems = [
    ...(result.data?.proposal.problems ?? []),
    ...evidence.pending_problems,
  ].filter(
    (p, i, a) =>
      p.requires_ack && a.findIndex((other) => other.key === p.key) === i,
  );
  const keys = selected ?? Object.keys(evidence.acknowledgements);
  return (
    <section
      aria-label="Pochodzenie pozycji i kontrola odczytu"
      className="space-y-2 rounded border border-gray-700 p-3 text-sm"
    >
      <h3 className="font-semibold">Sprawdź odczyt z oryginałem</h3>
      <p>
        Potwierdzenia dotyczą tej wersji wpisów. Każda edycja wymaga ponownego
        sprawdzenia niejasności.
      </p>
      <details>
        <summary>Tekst źródłowy i poprawki</summary>
        <ul>
          {[
            ...Object.entries(evidence.line_map),
            ...Object.entries(evidence.discount_map),
          ].map(([key, item]) => (
            <li key={key} className="py-1">
              <span>
                {item.source_text ?? `Wiersz ${item.source_index + 1}`}
              </span>
              {item.edited_fields.length ? (
                <p>
                  Zmieniono:{" "}
                  {item.edited_fields.map((f) => fieldNames[f] ?? f).join(", ")}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </details>
      {result.isError ? (
        <p role="alert">
          Nie udało się pobrać oryginalnych ostrzeżeń.{" "}
          <button type="button" onClick={() => void result.refetch()}>
            Pobierz ostrzeżenia
          </button>
        </p>
      ) : null}
      {problems.map((p) => (
        <label key={p.key} className="flex items-start gap-2">
          <input
            type="checkbox"
            disabled={disabled}
            checked={keys.includes(p.key)}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...keys, p.key]
                  : keys.filter((k) => k !== p.key),
              )
            }
          />
          <span>Sprawdzono: {p.message}</span>
        </label>
      ))}
    </section>
  );
}
