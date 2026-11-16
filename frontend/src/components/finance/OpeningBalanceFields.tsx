import { useId } from "react";
import {
  openingBalancePayload,
  parseSignedMinor,
  type OpeningBalanceDraft,
} from "../../lib/openingBalances";

export function OpeningBalanceFields({
  value,
  onChange,
  currency,
  disabled = false,
}: {
  value: OpeningBalanceDraft;
  onChange: (value: OpeningBalanceDraft) => void;
  currency: string;
  disabled?: boolean;
}) {
  const id = useId();
  const amount = parseSignedMinor(value.amount);
  return (
    <fieldset
      disabled={disabled}
      className="mt-4 min-w-0 border-t border-gray-700 pt-3"
    >
      <legend className="text-sm font-medium text-gray-300">
        Bilans otwarcia (BO)
      </legend>
      <div className="mt-2 grid min-w-0 gap-3 sm:grid-cols-2">
        <label
          htmlFor={`${id}-amount`}
          className="min-w-0 text-sm text-gray-400"
        >
          Kwota BO ({currency})
          <input
            id={`${id}-amount`}
            type="text"
            inputMode="text"
            className="input mt-1 w-full min-w-0 text-base"
            placeholder="0,00"
            value={value.amount}
            onChange={(event) =>
              onChange({ ...value, amount: event.target.value })
            }
          />
        </label>
        <label htmlFor={`${id}-date`} className="min-w-0 text-sm text-gray-400">
          Data BO
          <input
            id={`${id}-date`}
            type="date"
            className="input mt-1 w-full min-w-0 text-base"
            value={value.date}
            required
            onChange={(event) =>
              onChange({ ...value, date: event.target.value })
            }
          />
        </label>
        {currency !== "PLN" && amount !== null && amount !== 0 ? (
          <label
            htmlFor={`${id}-rate`}
            className="min-w-0 text-sm text-gray-400"
          >
            Kurs BO (PLN za 1 {currency})
            <input
              id={`${id}-rate`}
              type="text"
              inputMode="decimal"
              className="input mt-1 w-full min-w-0 text-base"
              value={value.fxRate}
              onChange={(event) =>
                onChange({ ...value, fxRate: event.target.value })
              }
            />
          </label>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-gray-400">
        Kwota może być dodatnia lub ujemna. Puste pole oznacza 0. BO nie jest
        przychodem ani wydatkiem.
      </p>
      {!openingBalancePayload(value, currency) ? (
        <p role="alert" className="mt-2 text-sm text-red-400">
          Sprawdź kwotę BO (maksymalnie 2 miejsca), datę i wymagany kurs
          (maksymalnie 6 miejsc).
        </p>
      ) : null}
    </fieldset>
  );
}
