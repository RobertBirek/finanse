import type { ReceiptReadResult as ReadResult } from "../../../api/receiptRead";
export function ReceiptReadResult({
  result,
  disabled,
  onUse,
}: {
  result: ReadResult;
  disabled: boolean;
  onUse: () => void;
}) {
  return (
    <section aria-label="Wynik odczytu produktów" className="space-y-2 text-sm">
      <h4 className="font-semibold">
        {result.quality === "partial"
          ? "Wynik częściowy — uzupełnij ręcznie"
          : result.quality === "unsupported"
            ? "Nieobsługiwany materiał"
            : "Produkty gotowe do przejrzenia"}
      </h4>
      <p>To propozycja, nie zatwierdzone pozycje ani opłacony paragon.</p>
      <p>
        {result.provider} · {result.model} · prompt {result.prompt_version} /
        schemat {result.schema_version}
      </p>
      {result.payload ? (
        <p>
          Suma przepisana z obrazu:{" "}
          {result.payload.printed_total ?? "nieczytelna"}{" "}
          {result.payload.currency ?? ""}. Kwota nagłówka nie została zmieniona.
        </p>
      ) : null}
      <ul className="space-y-1">
        {result.proposal.body.lines.map((l) => (
          <li key={l.line_key}>
            {l.name || "Nieczytelna nazwa"} —{" "}
            {l.amount_minor === null
              ? "uzupełnij kwotę"
              : `${(l.amount_minor / 100).toFixed(2)} zł`}
          </li>
        ))}
      </ul>
      <ul>
        {result.proposal.problems.map((p) => (
          <li key={p.key}>{p.message}</li>
        ))}
      </ul>
      <details>
        <summary>Pochodzenie odczytu</summary>
        <p className="break-all">Źródło {result.source_sha256}</p>
        <p className="break-all">
          Znormalizowany obraz {result.derivative_sha256}
        </p>
      </details>
      <button
        type="button"
        className="btn-secondary"
        disabled={disabled || !result.proposal.importable}
        onClick={onUse}
      >
        Użyj w szkicu
      </button>
    </section>
  );
}
