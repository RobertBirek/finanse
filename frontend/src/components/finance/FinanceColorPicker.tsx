import { FINANCE_PALETTE } from "../../lib/financeColors";

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
  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-2">
      <legend className="mb-1 text-sm text-gray-400">{label}</legend>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="color"
          aria-label={label}
          value={value ?? previewColor}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-11 w-12 cursor-pointer rounded-md border border-gray-600 bg-transparent p-1 disabled:cursor-not-allowed"
        />
        <span className="font-mono text-xs text-gray-400">
          {value ?? previewColor}
        </span>
        <button
          type="button"
          aria-pressed={value === null}
          className="btn-secondary min-h-11 px-3 text-xs"
          onClick={() => onChange(null)}
        >
          {automaticLabel}
        </button>
      </div>
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
