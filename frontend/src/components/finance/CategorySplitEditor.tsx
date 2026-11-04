import type { Category } from "../../api/finance";
import { CategoryPicker } from "./CategoryPicker";

export interface SplitRow {
  key: string;
  category: string;
  amount: string;
}
export function CategorySplitEditor({
  rows,
  categories,
  onChange,
  disabled,
  maxParts,
}: {
  rows: SplitRow[];
  categories: Category[];
  onChange: (rows: SplitRow[]) => void;
  disabled: boolean;
  maxParts: number;
}) {
  return (
    <fieldset disabled={disabled} className="space-y-4">
      {rows.map((row, index) => (
        <div
          key={row.key}
          className="rounded-lg border border-gray-700 p-3 space-y-2"
        >
          <CategoryPicker
            id={`split-${row.key}`}
            label={`Kategoria ${index + 1}`}
            categories={categories}
            type="expense"
            value={row.category}
            onChange={(value) =>
              onChange(
                rows.map((r) =>
                  r.key === row.key ? { ...r, category: value } : r,
                ),
              )
            }
          />
          <label className="block text-sm text-gray-400">
            Kwota PLN {index + 1}
            <input
              className="input mt-1"
              inputMode="decimal"
              value={row.amount}
              onChange={(event) =>
                onChange(
                  rows.map((r) =>
                    r.key === row.key
                      ? { ...r, amount: event.target.value }
                      : r,
                  ),
                )
              }
            />
          </label>
          {rows.length > 1 ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
            >
              Usuń część {index + 1}
            </button>
          ) : null}
        </div>
      ))}
      <button
        type="button"
        className="btn-secondary"
        disabled={rows.length >= maxParts}
        onClick={() =>
          onChange([
            ...rows,
            { key: crypto.randomUUID(), category: "", amount: "" },
          ])
        }
      >
        Dodaj kategorię
      </button>
    </fieldset>
  );
}
