import { Link } from "react-router-dom";
import { useAllegroPay } from "../../api/allegroPay";
import { formatPLN } from "../../lib/format";
import { formatCalendarDate } from "../../lib/date";

export function AllegroPaySummary() {
  const query = useAllegroPay();
  if (query.isLoading) return <p role="status">Ładowanie Allegro Pay…</p>;
  if (query.isError)
    return (
      <p role="alert">
        Nie udało się pobrać danych Allegro Pay.{" "}
        <button
          type="button"
          className="underline"
          onClick={() => void query.refetch()}
        >
          Ponów
        </button>
      </p>
    );
  if (!query.data?.length) return null;
  return (
    <section className="card mb-4 space-y-3" aria-label="Allegro Pay">
      <h2 className="text-lg font-semibold">Allegro Pay</h2>
      {query.data.map((profile) => {
        const due = profile.purchases
          .flatMap((purchase) => purchase.installments)
          .filter((item) => item.remaining_pln > 0)
          .sort((a, b) => a.due_date.localeCompare(b.due_date))[0];
        return (
          <article key={profile.id}>
            <h3 className="font-semibold">{profile.account_name}</h3>
            <p>
              Saldo księgowe {formatPLN(profile.ledger_balance_pln)} PLN · Do
              pokrycia w harmonogramach{" "}
              {formatPLN(profile.scheduled_remaining_pln)} PLN
            </p>
            <p>
              Limit{" "}
              {profile.limit_pln === null
                ? "nieustalony"
                : `${formatPLN(profile.limit_pln)} PLN`}{" "}
              · Dostępne według księgi{" "}
              {profile.available_pln === null
                ? "nieustalone"
                : `${formatPLN(profile.available_pln)} PLN`}
            </p>
            {due ? (
              <p>
                Najbliższa rata {formatCalendarDate(due.due_date)} ·{" "}
                {formatPLN(due.remaining_pln)} PLN
              </p>
            ) : null}
          </article>
        );
      })}
      <Link className="underline" to="/finances/allegro-pay">
        Otwórz zakupy i spłaty
      </Link>
    </section>
  );
}
