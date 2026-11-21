import { useState } from "react";
import { Link } from "react-router-dom";
import {
  type SpendingDays,
  useSpendingComparison,
  useSpendingExplanation,
} from "../../api/advisorDecisions";
import { formatPLN } from "../../lib/format";

export function SpendingComparison() {
  const [days, setDays] = useState<SpendingDays>(30);
  const comparison = useSpendingComparison();
  const explanation = useSpendingExplanation();
  const data = comparison.data;
  const busy = comparison.isPending || explanation.isPending;

  return (
    <details className="space-y-2 rounded-lg border border-gray-800 p-3">
      <summary className="cursor-pointer font-semibold">
        Co zmieniło moje wydatki?
      </summary>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy) return;
          explanation.reset();
          comparison.mutate(days);
        }}
      >
        <label className="grid gap-1">
          Długość porównania
          <select
            className="input-field"
            value={days}
            onChange={(event) => {
              const period = Number(event.target.value);
              if (period === 14 || period === 30 || period === 90)
                setDays(period);
            }}
          >
            {[14, 30, 90].map((period) => (
              <option value={period} key={period}>
                {period} dni
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn-secondary" disabled={busy}>
          Porównaj wydatki
        </button>
      </form>
      {comparison.isPending && <p role="status">Porównuję wydatki…</p>}
      {comparison.isError && (
        <p role="alert">Nie udało się porównać wydatków.</p>
      )}
      {data && (
        <div className="space-y-2 text-sm">
          <p>
            Okres poprzedni: od {data.previous_start} do {data.current_start}{" "}
            (bez ostatniej daty): {formatPLN(data.previous_total_pln)} PLN.
          </p>
          <p>
            Okres bieżący: od {data.current_start} do {data.end_exclusive} (bez
            ostatniej daty): {formatPLN(data.current_total_pln)} PLN.
          </p>
          <p>Różnica netto: {formatPLN(data.delta_pln)} PLN.</p>
          <p>
            Wyłącznie konta budżetowe, bez transferów. Zakupy według daty
            zakupu, a w razie jej braku według daty transakcji.
          </p>
          {data.categories.length > 0 && (
            <>
              <h3 className="font-semibold">Największe zmiany kategorii</h3>
              <ul>
                {data.categories.map((item) => (
                  <li key={item.category_id}>
                    {item.name}: {formatPLN(item.delta_pln)} PLN
                  </li>
                ))}
              </ul>
            </>
          )}
          {data.transactions.length > 0 && (
            <>
              <h3 className="font-semibold">
                Transakcje o największym wpływie na różnicę
              </h3>
              <ul>
                {data.transactions.map((item) => (
                  <li key={item.transaction_id} className="break-words">
                    {item.description} · {formatPLN(item.delta_pln)} PLN ·{" "}
                    <Link
                      className="underline"
                      to={`/finances/transactions?date_basis=purchase&date_from=${item.date}&date_to=${item.date}&budget_accounts_only=true`}
                    >
                      Transakcje z {item.date}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          {data.truncated && (
            <p>
              Pokazano tylko największe zmiany. Sumy obejmują wszystkie pozycje.
            </p>
          )}
          {data.transactions.length > 0 && (
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => {
                if (comparison.variables)
                  explanation.mutate(comparison.variables);
              }}
            >
              Objaśnij różnicę z OpenAI
            </button>
          )}
        </div>
      )}
      {explanation.isPending && <p role="status">Pobieram objaśnienie…</p>}
      {(explanation.isError || explanation.data?.status === "unavailable") && (
        <p role="alert">Objaśnienie jest niedostępne.</p>
      )}
      {explanation.data?.status === "no_facts" && (
        <p>Nie ma już różnic do objaśnienia.</p>
      )}
      {explanation.data?.status === "ok" && (
        <p className="whitespace-pre-wrap break-words">
          Komentarz OpenAI: {explanation.data.text}
        </p>
      )}
    </details>
  );
}
