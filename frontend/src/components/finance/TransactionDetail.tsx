import { useTransaction, type Account, type Category } from "../../api/finance";
import { TRANSACTION_TYPES } from "../../lib/transactionSearch";
import { formatPLN } from "../../lib/format";
import { formatCalendarDate } from "../../lib/date";
import { QueryFeedback } from "../QueryFeedback";
import { Dialog } from "../Dialog";

export function TransactionDetail({
  id,
  accounts,
  categories,
  onClose,
}: {
  id: string;
  accounts: Account[];
  categories: Category[];
  onClose: () => void;
}) {
  const query = useTransaction(id);
  return (
    <Dialog
      label="Szczegóły transakcji"
      onClose={onClose}
      panelClassName="card w-full max-w-2xl"
    >
      <div className="flex justify-between gap-3 mb-4">
        <h2 className="text-xl font-semibold text-white">
          Szczegóły transakcji
        </h2>
        <button type="button" className="btn-secondary" onClick={onClose}>
          Zamknij szczegóły
        </button>
      </div>
      <QueryFeedback
        loading={query.isLoading}
        error={query.isError}
        errorMessage="Nie udało się pobrać szczegółów. Transakcja mogła zostać usunięta."
        onRetry={query.refetch}
      >
        {query.data && (
          <div className="space-y-4">
            <p className="text-white [overflow-wrap:anywhere]">
              {query.data.description}
            </p>
            <p className="text-sm text-gray-400">
              {formatCalendarDate(query.data.transaction_date)} ·{" "}
              {TRANSACTION_TYPES[query.data.type]} · Źródło: {query.data.source}
            </p>
            <p className="text-sm text-gray-400">
              Status: {query.data.is_pending ? "Oczekująca" : "Zaksięgowana"}
            </p>
            <ul className="space-y-3">
              {query.data.postings.map((p) => (
                <li key={p.id} className="rounded-lg bg-gray-800 p-3 text-sm">
                  <p className="text-white [overflow-wrap:anywhere]">
                    {p.account_id
                      ? `Konto: ${accounts.find((a) => a.id === p.account_id)?.name ?? "Nazwa niedostępna"}`
                      : `Kategoria: ${categories.find((c) => c.id === p.category_id)?.name ?? "Nazwa niedostępna"}`}
                  </p>
                  <dl className="grid gap-1 mt-2 text-gray-300">
                    <div>
                      <dt className="inline">Kwota źródłowa: </dt>
                      <dd className="inline">
                        {formatPLN(p.source_amount)} {p.source_currency}
                      </dd>
                    </div>
                    <div>
                      <dt className="inline">Równowartość PLN: </dt>
                      <dd className="inline">
                        {formatPLN(p.base_amount_pln)} PLN
                      </dd>
                    </div>
                    <div>
                      <dt className="inline">
                        Kurs PLN za 1 {p.source_currency}:{" "}
                      </dt>
                      <dd className="inline">{p.fx_rate}</dd>
                    </div>
                    <div>
                      <dt className="inline">Strona zapisu: </dt>
                      <dd className="inline">
                        {p.direction === "credit" ? "Uznanie" : "Obciążenie"}
                      </dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          </div>
        )}
      </QueryFeedback>
    </Dialog>
  );
}
