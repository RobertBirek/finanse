import type { ReceiptReadExportPreview } from "../../../api/receiptRead";
export function ReceiptReadConsent({
  preview,
  disabled,
  onConfirm,
  onBack,
}: {
  preview: ReceiptReadExportPreview;
  disabled: boolean;
  onConfirm: () => void;
  onBack: () => void;
}) {
  return (
    <section
      aria-label="Zgoda na odczyt zdjęcia"
      className="space-y-3 border-l-2 border-amber-400 pl-3 text-sm"
    >
      <h4 className="font-semibold">Dodatkowy odczyt produktów</h4>
      <p>{preview.notice}</p>
      <p>
        Odbiorca: {preview.provider} · {preview.model}
      </p>
      <p>
        Limit obrazu: {preview.limits.max_bytes} B; górna granica pikseli:{" "}
        {preview.limits.max_pixels}. Pozostałe próby dzisiaj:{" "}
        {preview.remaining_user_calls} (globalnie{" "}
        {preview.remaining_global_calls}).
      </p>
      <p>
        Podgląd nie rezerwuje limitu ani nie gwarantuje ceny w PLN. Oryginał
        pozostaje bez zmian. Produkty i podział płatności nadal zatwierdzasz
        osobno.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-primary"
          disabled={disabled}
          onClick={onConfirm}
        >
          Wyślij zdjęcie i odczytaj produkty
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled}
          onClick={onBack}
        >
          Wróć bez wysyłania
        </button>
      </div>
    </section>
  );
}
