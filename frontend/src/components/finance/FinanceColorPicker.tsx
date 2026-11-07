import { useId } from "react";
import { FINANCE_PALETTE, isValidFinanceColor } from "../../lib/financeColors";

export function FinanceColorPicker({
  label,
  value,
  previewColor,
  onChange,
  automaticLabel = "Automatycznie",
  disabled = false,
}: {
  label: string;
  value: string | null;
  previewColor: string;
  onChange: (color: string | null) => void;
  automaticLabel?: string;
  disabled?: boolean;
}) {
  const errorId = useId();
  const valid = isValidFinanceColor(value);
  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-2">
      <legend className="mb-1 text-sm text-gray-400">{label}</legend>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="color"
          aria-label={label}
          value={valid && value !== null ? value : previewColor}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-11 w-12 cursor-pointer rounded-md border border-gray-600 bg-transparent p-1 disabled:cursor-not-allowed"
        />
        <input
          type="text"
          aria-label={`${label} HEX`}
          value={value ?? previewColor}
          onChange={(event) => onChange(event.target.value)}
          pattern="#[0-9A-Fa-f]{6}"
          required
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="characters"
          aria-invalid={!valid}
          aria-describedby={!valid ? errorId : undefined}
          className="input h-11 w-28 font-mono text-base sm:text-sm"
        />
        <button
          type="button"
          aria-pressed={value === null}
          className="btn-secondary min-h-11 px-3 text-xs"
          onClick={() => onChange(null)}
        >
          {automaticLabel}
        </button>
      </div>
      {!valid ? (
        <p id={errorId} role="alert" className="text-xs text-red-400">
          Podaj kolor w formacie #RRGGBB, np. #000000.
        </p>
      ) : null}
      <div className="flex flex-wrap gap-1">
        {FINANCE_PALETTE.map(({ name, hex }) => (
          <button
            type="button"
            key={hex}
            aria-label={`${label}: ${name}`}
            title={name}
            aria-pressed={value?.toUpperCase() === hex}
            onClick={() => onChange(hex)}
            className="flex h-11 w-11 items-center justify-center rounded-md border border-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-advisor-500 aria-pressed:border-gray-400 disabled:opacity-50"
          >
            <span
              aria-hidden="true"
              className="h-5 w-5 rounded-full border border-black/20"
              style={{ backgroundColor: hex }}
            />
          </button>
        ))}
      </div>
    </fieldset>
  );
}
