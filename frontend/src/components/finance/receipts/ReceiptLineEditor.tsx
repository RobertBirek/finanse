import type { Category } from "../../../api/finance";
import { categoryPath } from "../../../lib/categories";
import { CategoryPicker } from "../CategoryPicker";
import { ReceiptHistoryHints } from "./ReceiptHistoryHints";
import type { DraftLine } from "./receiptDraft";
export function ReceiptLineEditor({
  line,
  index,
  billId,
  storeId,
  categories,
  excludedIds,
  disabled,
  maxName,
  onChange,
  onDelete,
}: {
  line: DraftLine;
  index: number;
  billId: string;
  storeId: string | null;
  categories: Category[];
  excludedIds: ReadonlySet<string>;
  disabled: boolean;
  maxName: number;
  onChange: (line: DraftLine) => void;
  onDelete: () => void;
}) {
  const n = index + 1;
  return (
    <fieldset
      disabled={disabled}
      className="space-y-3 rounded border border-gray-700 p-3"
    >
      <legend className="px-1 text-sm">Pozycja {n}</legend>
      <label className="block text-sm">
        Produkt {n}
        <input
          className="input mt-1"
          value={line.name}
          maxLength={maxName}
          onChange={(e) =>
            onChange({ ...line, name: e.target.value, hint: null })
          }
        />
      </label>
      <label className="block text-sm">
        Kwota produktu {n}
        <input
          className="input mt-1"
          inputMode="decimal"
          value={line.amount}
          onChange={(e) => onChange({ ...line, amount: e.target.value })}
        />
      </label>
      <p className="text-xs text-gray-400">
        Kwota pozycji przed rabatami wpisanymi osobno. Rabatu już wliczonego w
        cenę nie wpisuj ponownie.
      </p>
      {line.category_id ? (
        <p className="text-sm [overflow-wrap:anywhere]">
          Wybrano: {categoryPath(line.category_id, categories)}
          {line.hint ? " · wskazówka z historii sklepu" : ""}
        </p>
      ) : null}
      <CategoryPicker
        id={`receipt-category-${line.line_key}`}
        label={`Kategoria produktu ${n}`}
        categories={categories}
        value={line.category_id ?? ""}
        onChange={(id) =>
          onChange({ ...line, category_id: id || null, hint: null })
        }
        type="expense"
        excludedIds={excludedIds}
        retainSelectedOption={false}
      />
      <ReceiptHistoryHints
        billId={billId}
        storeId={storeId}
        name={line.name}
        categoryId={line.category_id}
        disabled={disabled}
        onChoose={(ref) =>
          onChange({ ...line, category_id: ref.category_id, hint: ref })
        }
      />
      <button type="button" className="btn-secondary" onClick={onDelete}>
        Usuń produkt {n}
      </button>
    </fieldset>
  );
}
