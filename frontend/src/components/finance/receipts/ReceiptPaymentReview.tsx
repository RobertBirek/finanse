import type { ReceiptPaymentPreview } from "../../../api/receiptItems";
import type { Category } from "../../../api/finance";
import { categoryPath } from "../../../lib/categories";
import { formatPLN } from "../../../lib/format";
export function ReceiptPaymentReview({
  preview,
  categories,
  disabled,
  onConfirm,
  onCancel,
}: {
  preview: ReceiptPaymentPreview;
  categories: Category[];
  disabled: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <section
      className="space-y-3 rounded border border-advisor-500 p-3"
      aria-label="Podgląd podziału płatności"
    >
      <h3 className="font-semibold">
        Sprawdź podział {formatPLN(preview.total_minor)} zł
      </h3>
      <p className="text-sm">{preview.notice}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <h4 className="text-sm font-semibold">Przed zmianą</h4>
          <ul>
            {preview.before_parts.map((p) => (
              <li
                key={p.category_id}
                className="text-sm [overflow-wrap:anywhere]"
              >
                {categoryPath(p.category_id, categories)}:{" "}
                {formatPLN(p.amount_minor)} zł
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold">Po zatwierdzeniu</h4>
          <ul>
            {preview.after_parts.map((p) => (
              <li
                key={p.category_id}
                className="text-sm [overflow-wrap:anywhere]"
              >
                {preview.target_paths[p.category_id]}:{" "}
                {formatPLN(p.amount_minor)} zł
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-primary"
          disabled={disabled}
          onClick={onConfirm}
        >
          Zatwierdź podział
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled}
          onClick={onCancel}
        >
          Wróć do pozycji
        </button>
      </div>
    </section>
  );
}
