import { useState } from "react";
import { isAxiosError } from "axios";
import {
  useScenario,
  useScenarioExplanation,
} from "../../api/advisorDecisions";
import { localTodayIso } from "../../lib/date";
import { formatPLN } from "../../lib/format";
import { parseSignedMinor } from "../../lib/openingBalances";

export function CashflowScenario() {
  const [date, setDate] = useState(localTodayIso);
  const [amount, setAmount] = useState("");
  const calculation = useScenario();
  const explanation = useScenarioExplanation();
  const cents = parseSignedMinor(amount);
  const data = calculation.data;
  const busy = calculation.isPending || explanation.isPending;
  const error = calculation.error;

  return (
    <details className="space-y-2 rounded-lg border border-gray-800 p-3">
      <summary className="cursor-pointer font-semibold">
        Symulator „co jeśli?”
      </summary>
      <p className="text-sm text-gray-400">
        Jednorazowy wydatek. Wynik nie jest zapisywany w księdze.
      </p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy || cents === null || cents <= 0 || !date) return;
          explanation.reset();
          calculation.mutate({ expense_date: date, amount_pln_minor: cents });
        }}
      >
        <label className="grid gap-1 text-sm">
          Data wydatku
          <input
            className="input-field"
            type="date"
            required
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-sm">
          Kwota wydatku (PLN)
          <input
            className="input-field"
            inputMode="decimal"
            required
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="btn-secondary"
          disabled={busy || cents === null || cents <= 0 || !date}
        >
          Oblicz wariant
        </button>
      </form>
      {calculation.isPending && <p role="status">Obliczam prognozę…</p>}
      {error && (
        <p role="alert">
          {isAxiosError(error) &&
          error.response?.status === 422 &&
          typeof error.response.data?.detail === "string"
            ? error.response.data.detail
            : "Nie udało się obliczyć wariantu."}
        </p>
      )}
      {data && (
        <div className="space-y-1 text-sm">
          <p>
            Scenariusz:{" "}
            {formatPLN(calculation.variables?.amount_pln_minor ?? 0)} PLN,{" "}
            {calculation.variables?.expense_date}.
          </p>
          <p>
            Najniższe saldo bez wydatku:{" "}
            {formatPLN(data.baseline_minimum.projected_balance_pln)} PLN (
            {data.baseline_minimum.date}).
          </p>
          <p>
            Najniższe saldo z wydatkiem:{" "}
            {formatPLN(data.scenario_minimum.projected_balance_pln)} PLN (
            {data.scenario_minimum.date}).
          </p>
          <p>
            {data.first_negative_date
              ? `Pierwsze ujemne saldo na koniec dnia: ${data.first_negative_date}.`
              : "Brak ujemnego salda na koniec dnia w tym wariancie."}
          </p>
          {data.opening_balance_negative && (
            <p>Saldo otwarcia jest już ujemne.</p>
          )}
          {data.excluded_obligation_reasons.length > 0 && (
            <p>
              Prognoza pomija niektóre zobowiązania — szczegóły są w prognozie
              przepływów.
            </p>
          )}
          {!data.covers_day_before_payday && (
            <p>
              Prognoza nie obejmuje dnia przed wypłatą ({data.next_payday}).
            </p>
          )}
          <p className="text-gray-400">
            Salda zamknięcia od {data.forecast_start} do {data.forecast_end};
            bez kolejności godzinowej. To nie gwarancja płynności.
          </p>
          <button
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={() => {
              if (calculation.variables)
                explanation.mutate(calculation.variables);
            }}
          >
            Objaśnij wariant z OpenAI
          </button>
        </div>
      )}
      {explanation.isPending && <p role="status">Pobieram objaśnienie…</p>}
      {(explanation.isError || explanation.data?.status === "unavailable") && (
        <p role="alert">Objaśnienie jest niedostępne.</p>
      )}
      {explanation.data?.status === "ok" && (
        <p className="whitespace-pre-wrap break-words">
          Komentarz OpenAI: {explanation.data.text}
        </p>
      )}
    </details>
  );
}
