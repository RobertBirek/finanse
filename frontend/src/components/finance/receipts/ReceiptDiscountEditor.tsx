import type { DraftLine, DraftDiscount } from "./receiptDraft";
export function ReceiptDiscountEditor({
  discount,
  index,
  lines,
  disabled,
  maxName,
  onChange,
  onDelete,
}: {
  discount: DraftDiscount;
  index: number;
  lines: DraftLine[];
  disabled: boolean;
  maxName: number;
  onChange: (d: DraftDiscount) => void;
  onDelete: () => void;
}) {
  const n = index + 1;
  return (
    <fieldset
      disabled={disabled}
      className="space-y-2 rounded border border-gray-700 p-3"
    >
      <legend className="px-1 text-sm">Rabat {n}</legend>
      <label className="block text-sm">
        Nazwa rabatu {n}
        <input
          className="input mt-1"
          maxLength={maxName}
          value={discount.name}
          onChange={(e) => onChange({ ...discount, name: e.target.value })}
        />
      </label>
      <label className="block text-sm">
        Kwota rabatu {n}
        <input
          className="input mt-1"
          inputMode="decimal"
          value={discount.amount}
          onChange={(e) => onChange({ ...discount, amount: e.target.value })}
        />
      </label>
      <p className="text-xs text-gray-400">
        Wpisz udziały tylko przy produktach objętych rabatem. Suma udziałów musi
        zgadzać się z kwotą rabatu.
      </p>
      {lines.map((line, i) => (
        <label
          key={line.line_key}
          className="block text-sm [overflow-wrap:anywhere]"
        >
          Udział rabatu {n}, produkt {i + 1}
          <span className="ml-2 text-gray-400">{line.name || "Bez nazwy"}</span>
          <input
            aria-label={`Udział rabatu ${n}, produkt ${i + 1}`}
            className="input mt-1"
            inputMode="decimal"
            value={discount.shares[line.line_key] ?? ""}
            onChange={(e) =>
              onChange({
                ...discount,
                shares: { ...discount.shares, [line.line_key]: e.target.value },
              })
            }
          />
        </label>
      ))}
      <button type="button" className="btn-secondary" onClick={onDelete}>
        Usuń rabat {n}
      </button>
    </fieldset>
  );
}
