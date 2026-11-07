import { useCreditCard } from "../../api/creditCards";
import { formatPLN } from "../../lib/format";

export function CardAccountSummary({ accountId }: { accountId: string }) {
  const query = useCreditCard(accountId);
  return (
    <aside className="mb-4 border-t border-gray-700 pt-3 text-sm">
      {query.isLoading ? (
        <p role="status">Ładowanie limitu karty…</p>
      ) : query.isError ? (
        <p role="alert">Nie udało się pobrać limitu karty.</p>
      ) : query.data ? (
        <p>
          Limit: {formatPLN(query.data.limit_pln)} PLN · Zadłużenie:{" "}
          {formatPLN(query.data.debt_pln)} PLN · Dostępne:{" "}
          {formatPLN(query.data.available_pln)} PLN
        </p>
      ) : null}
      <a
        className="text-advisor-400 underline"
        href={`/settings/finances/cards?account=${encodeURIComponent(accountId)}`}
      >
        Rozliczenia karty i plany ratalne
      </a>
    </aside>
  );
}
