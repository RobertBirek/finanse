import { useState } from "react";
import type { CardHeaderDecision } from "../../../api/bankImports";
import { parsePlnToGrosze } from "../../../api/finance";

export function ImportCardHeader({
  accountId,
  initial,
  onChange,
}: {
  accountId: string;
  initial?: CardHeaderDecision | null;
  onChange: (value: CardHeaderDecision | null) => void;
}) {
  const [fields, setFields] = useState(() => ({
    start: initial?.period_start ?? "",
    end: initial?.period_end ?? "",
    due: initial?.due_date ?? "",
    debt: initial ? String(initial.debt_pln / 100) : "",
    minimum: initial ? String(initial.minimum_pln / 100) : "",
    confirmed: initial?.debt_definition_confirmed ?? false,
  }));
  function update(next: typeof fields) {
    setFields(next);
    const debt = parsePlnToGrosze(next.debt, true);
    const minimum = parsePlnToGrosze(next.minimum, true);
    onChange(
      next.start &&
        next.end &&
        next.due &&
        debt !== null &&
        minimum !== null &&
        next.confirmed
        ? {
            account_id: accountId,
            period_start: next.start,
            period_end: next.end,
            due_date: next.due,
            debt_pln: debt,
            minimum_pln: minimum,
            debt_definition_confirmed: true,
          }
        : null,
    );
  }
  return (
    <fieldset className="space-y-3 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
      <legend className="px-1">Potwierdź nagłówek z oryginałem</legend>
      <p className="text-sm">
        To osobne metadane okresu i minimum, nie operacja księgi. Nie wpisuj
        limitu ani kapitału przyszłych rat zamiast długu cyklu. Serwer porówna
        wszystkie pola z odczytem banku.
      </p>
      {(
        [
          ["start", "Początek okresu karty"],
          ["end", "Koniec okresu karty"],
          ["due", "Termin z nagłówka karty"],
        ] as const
      ).map(([key, label]) => (
        <label key={key} className="block text-sm">
          {label}
          <input
            type="date"
            className="input mt-1 block w-full"
            value={fields[key]}
            onChange={(event) =>
              update({ ...fields, [key]: event.target.value })
            }
          />
        </label>
      ))}
      {(
        [
          ["debt", "Dług bieżącego cyklu PLN"],
          ["minimum", "Minimum z nagłówka PLN"],
        ] as const
      ).map(([key, label]) => (
        <label key={key} className="block text-sm">
          {label}
          <input
            className="input mt-1 block w-full"
            inputMode="decimal"
            value={fields[key]}
            onChange={(event) =>
              update({ ...fields, [key]: event.target.value })
            }
          />
        </label>
      ))}
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={fields.confirmed}
          onChange={(event) =>
            update({ ...fields, confirmed: event.target.checked })
          }
        />
        Potwierdzam znaczenie zadłużenia bieżącego cyklu i zgodność okresu,
        terminu oraz minimum z nagłówkiem.
      </label>
    </fieldset>
  );
}
