import { Link, Navigate, useLocation } from "react-router-dom";
import { useCreditCards } from "../api/creditCards";
import { formatPLN } from "../lib/format";
import { entityColor } from "../lib/financeColors";

function CardList() {
  const query = useCreditCards();
  if (query.isLoading) return <p role="status">Ładowanie kart…</p>;
  if (query.isError)
    return <p role="alert">Nie udało się pobrać kart. Odśwież stronę.</p>;
  if (!query.data?.length)
    return (
      <div className="card space-y-3">
        <p className="text-gray-400">
          Brak kart kredytowych. W kontach dodaj lub edytuj rachunek i wybierz
          typ „Karta kredytowa”.
        </p>
        <Link
          to="/settings/finances/accounts"
          className="btn-secondary inline-flex"
        >
          Przejdź do kont
        </Link>
      </div>
    );
  return (
    <div className="space-y-4">
      {query.data.map((card) => (
        <article
          key={card.account_id}
          aria-label={card.name}
          className="card min-w-0"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex min-w-0 items-center gap-3 text-lg font-semibold text-white">
              <span
                aria-hidden="true"
                className="h-3 w-3 shrink-0 rounded-full border border-gray-500/40"
                style={{
                  backgroundColor: entityColor(card.account_id, card.color),
                }}
              />
              <span className="break-words [overflow-wrap:anywhere]">
                {card.name}
              </span>
            </h2>
            {!card.is_active ? (
              <span className="text-sm text-gray-400">Nieaktywna</span>
            ) : null}
          </div>
          <dl className="my-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              ["Limit", card.limit_pln],
              ["Zadłużenie", card.debt_pln],
              ["Dostępny limit", card.available_pln],
            ].map(([label, value]) => (
              <div key={String(label)} className="min-w-0">
                <dt className="text-sm text-gray-400">{label}</dt>
                <dd className="mt-1 break-words font-mono text-xl tabular-nums text-white">
                  {value === null ? "—" : `${formatPLN(Number(value))} PLN`}
                </dd>
              </div>
            ))}
          </dl>
          {!card.configured ? (
            <p className="mb-4 text-sm text-gray-400">
              Uzupełnij warunki karty w edycji konta.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-3 border-t border-gray-700 pt-4">
            <Link
              className="btn-secondary"
              to={`/settings/finances/cards/${encodeURIComponent(card.account_id)}`}
            >
              Wyciągi i raty
            </Link>
            <Link
              className="btn-secondary"
              to={`/settings/finances/accounts?edit=${encodeURIComponent(card.account_id)}`}
            >
              Edytuj konto
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}

export function FinanceCreditCards() {
  const legacyAccount = new URLSearchParams(useLocation().search).get(
    "account",
  );
  if (legacyAccount)
    return (
      <Navigate
        replace
        to={`/settings/finances/cards/${encodeURIComponent(legacyAccount)}`}
      />
    );
  return (
    <div className="max-w-5xl space-y-6">
      <h1 className="text-2xl font-bold text-white">Karty kredytowe</h1>
      <p className="text-sm text-gray-400">
        Bieżące wykorzystanie każdej karty. Dostępny limit uwzględnia
        rezerwacje; warunki zmienisz w edycji konta.
      </p>
      <CardList />
    </div>
  );
}
