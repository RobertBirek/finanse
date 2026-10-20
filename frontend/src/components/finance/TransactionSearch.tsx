import { TransactionDetail } from "./TransactionDetail";
import { TransactionFilters } from "./TransactionFilters";
import type { TransactionSearchParams } from "../../api/finance";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  useAccounts,
  useCategories,
  useTransactionSearch,
} from "../../api/finance";
import {
  SEARCH_FIELDS,
  transactionSearchParams,
} from "../../lib/transactionSearch";
import { QueryFeedback } from "../QueryFeedback";
import { TransactionList } from "./AccountTransactions";

export function TransactionSearch() {
  const [search, setSearch] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const accounts = useAccounts();
  const categories = useCategories();
  let validation: string | null = null;
  let params: TransactionSearchParams;
  try {
    params = transactionSearchParams(search);
  } catch (error) {
    validation = (error as Error).message;
    params = { limit: 25, offset: 0 };
  }
  const results = useTransactionSearch(params, !validation);
  const page = results.data;
  const pageNumber = params.offset / params.limit + 1;
  const formKey = JSON.stringify(
    SEARCH_FIELDS.map((field) => search.get(field) ?? ""),
  );
  function changePage(number: number) {
    const next = new URLSearchParams(search);
    next.set("page", String(number));
    next.delete("detail");
    setSearch(next);
  }
  function openDetail(id: string) {
    const next = new URLSearchParams(search);
    next.set("detail", id);
    setSearch(next, {
      preventScrollReset: true,
      state: { transactionDetail: true },
    });
  }
  function closeDetail() {
    if (location.state?.transactionDetail) {
      navigate(-1);
      return;
    }
    const next = new URLSearchParams(search);
    next.delete("detail");
    setSearch(next, { replace: true, preventScrollReset: true });
  }
  return (
    <section aria-label="Historia transakcji" className="space-y-4">
      <TransactionFilters
        key={formKey}
        search={search}
        accounts={accounts.data ?? []}
        categories={categories.data ?? []}
        onApply={setSearch}
        onClear={() => setSearch({})}
      />
      {(accounts.isError || categories.isError) && (
        <p role="alert" className="text-sm text-red-300">
          Nie udało się pobrać nazw kont lub kategorii.{" "}
          <button
            className="underline"
            type="button"
            onClick={() => {
              void accounts.refetch();
              void categories.refetch();
            }}
          >
            Ponów pobieranie nazw
          </button>
        </p>
      )}
      {validation ? (
        <p role="alert" className="text-red-300">
          {validation}
        </p>
      ) : (
        <QueryFeedback
          loading={results.isLoading}
          error={results.isError}
          errorMessage="Nie udało się wyszukać transakcji. Filtry zostały zachowane."
          onRetry={results.refetch}
        >
          {page && (
            <div
              role="region"
              className="card space-y-4"
              aria-label="Wyniki wyszukiwania"
            >
              <p role="status" className="text-sm text-gray-300">
                {page.items.length
                  ? `Wyniki ${page.offset + 1}–${page.offset + page.items.length} z ${page.total}`
                  : `Wyniki: 0 z ${page.total}`}
              </p>
              {page.items.length ? (
                <TransactionList
                  key={JSON.stringify(params)}
                  accounts={accounts.data}
                  accountId={params.account_id}
                  currency={params.currency}
                  transactions={page.items}
                  loading={false}
                  error={false}
                  onDetails={openDetail}
                />
              ) : (
                <p className="text-gray-400">
                  {page.total
                    ? "Ta strona jest już pusta. Wróć na pierwszą stronę."
                    : "Brak transakcji spełniających filtry. Zmień lub wyczyść filtry."}
                </p>
              )}
              <nav
                aria-label="Strony transakcji"
                className="flex flex-wrap gap-3 items-center"
              >
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={pageNumber <= 1 || results.isFetching}
                  onClick={() => changePage(pageNumber - 1)}
                >
                  Poprzednia
                </button>
                <span className="text-sm text-gray-400">
                  Strona {pageNumber} z{" "}
                  {Math.max(1, Math.ceil(page.total / page.limit))}
                </span>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={
                    params.offset + page.items.length >= page.total ||
                    results.isFetching
                  }
                  onClick={() => changePage(pageNumber + 1)}
                >
                  Następna
                </button>
                {pageNumber > 1 && (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => changePage(1)}
                  >
                    Pierwsza strona
                  </button>
                )}
              </nav>
            </div>
          )}
        </QueryFeedback>
      )}
      {search.get("detail") && (
        <TransactionDetail
          id={search.get("detail")!}
          accounts={accounts.data ?? []}
          categories={categories.data ?? []}
          onClose={closeDetail}
        />
      )}
    </section>
  );
}
