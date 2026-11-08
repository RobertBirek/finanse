import { useId } from "react";
import type { CardDraft } from "./creditCardSettings";

const fields: { key: keyof CardDraft; label: string; decimal?: boolean }[] = [
  { key: "limit", label: "Limit PLN", decimal: true },
  { key: "apr", label: "Oprocentowanie roczne %", decimal: true },
  { key: "cycle", label: "Dzień zamknięcia cyklu" },
  { key: "due", label: "Domyślny dzień spłaty" },
  { key: "grace", label: "Maksymalny okres bezodsetkowy (dni)" },
];

export function CreditCardFields({
  value,
  onChange,
  disabled = false,
}: {
  value: CardDraft;
  onChange: (draft: CardDraft) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <fieldset
      disabled={disabled}
      className="mt-4 border-t border-gray-700 pt-4"
    >
      <legend className="px-1 text-sm font-semibold text-white">
        Warunki karty kredytowej
      </legend>
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((field) => (
          <label
            key={field.key}
            htmlFor={`${id}-${field.key}`}
            className="min-w-0 text-sm text-gray-300"
          >
            {field.label}
            <input
              id={`${id}-${field.key}`}
              className="input mt-1 w-full"
              inputMode={field.decimal ? "decimal" : "numeric"}
              required
              value={value[field.key]}
              onChange={(event) =>
                onChange({ ...value, [field.key]: event.target.value })
              }
            />
          </label>
        ))}
      </div>
      <p className="mt-3 text-xs text-gray-400">
        Karty obsługują PLN. Saldo pochodzi z księgi; zapis warunków nie zmienia
        historii. Daty i warunki bankowego wyciągu mają pierwszeństwo.
      </p>
    </fieldset>
  );
}
