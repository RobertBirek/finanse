import { useState, type SelectHTMLAttributes } from "react";
import type { TransactionSearchParams } from "../../api/finance";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  useAccounts,
  useCategories,
  useTransactionSearch,
  useTransaction,
  type Account,
  type Category,
} from "../../api/finance";
import {
  SEARCH_FIELDS,
  transactionSearchParams,
} from "../../lib/transactionSearch";
import { formatPLN } from "../../lib/format";
import { formatCalendarDate } from "../../lib/date";
import { QueryFeedback } from "../QueryFeedback";
import { Dialog } from "../Dialog";
import { TransactionList } from "./AccountTransactions";

const TYPES = {
  expense: "Wydatek",
  income: "Przychód",
  transfer: "Transfer",
  exchange: "Przewalutowanie",
};

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
  const activeFilters = SEARCH_FIELDS.filter(
    (field) => !["q", "size"].includes(field) && search.get(field),
  ).length;
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
      <form
        key={formKey}
        className="card space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget),
            next = new URLSearchParams();
          for (const field of SEARCH_FIELDS) {
            const value = String(form.get(field) ?? "").trim();
            if (value) next.set(field, value);
          }
          setSearch(next);
        }}
      >
        <h2 className="text-lg font-semibold text-white">Znajdź transakcję</h2>
        <label className="block text-sm text-gray-300">
          Szukaj po opisie, koncie lub kategorii
          <input
            name="q"
            type="search"
            maxLength={200}
            defaultValue={search.get("q") ?? ""}
            className="input w-full mt-1"
          />
        </label>
        <details>
          <summary className="cursor-pointer text-sm text-gray-300">
            Filtry szczegółowe
            {activeFilters ? ` (${activeFilters} aktywne)` : ""}
          </summary>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 mt-4">
            <label className="text-sm text-gray-300">
              Konto
              <SearchSelect
                name="account_id"
                defaultValue={search.get("account_id") ?? ""}
                className="input w-full mt-1"
              >
                <option value="">Wszystkie konta</option>
                {search.get("account_id") &&
                  !accounts.data?.some(
                    (a) => a.id === search.get("account_id"),
                  ) && (
                    <option value={search.get("account_id")!}>
                      Wybrane konto — nazwa niedostępna
                    </option>
                  )}
                {accounts.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                    {a.is_active === false ? " (archiwalne)" : ""}
                  </option>
                ))}
              </SearchSelect>
            </label>
            <label className="text-sm text-gray-300">
              Kategoria
              <SearchSelect
                name="category_id"
                defaultValue={search.get("category_id") ?? ""}
                className="input w-full mt-1"
              >
                <option value="">Wszystkie kategorie</option>
                {search.get("category_id") &&
                  !categories.data?.some(
                    (c) => c.id === search.get("category_id"),
                  ) && (
                    <option value={search.get("category_id")!}>
                      Wybrana kategoria — nazwa niedostępna
                    </option>
                  )}
                {categories.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.is_active === false ? " (archiwalna)" : ""}
                  </option>
                ))}
              </SearchSelect>
            </label>
            <label className="text-sm text-gray-300">
              Typ
              <SearchSelect
                name="type"
                defaultValue={search.get("type") ?? ""}
                className="input w-full mt-1"
              >
                <option value="">Wszystkie typy</option>
                {Object.entries(TYPES).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </SearchSelect>
            </label>
            <label className="text-sm text-gray-300">
              Data od
              <input
                type="date"
                name="date_from"
                defaultValue={search.get("date_from") ?? ""}
                className="input w-full min-w-0 mt-1"
              />
            </label>
            <label className="text-sm text-gray-300">
              Data do
              <input
                type="date"
                name="date_to"
                defaultValue={search.get("date_to") ?? ""}
                className="input w-full min-w-0 mt-1"
              />
            </label>
            <label className="text-sm text-gray-300">
              Waluta źródłowa
              <SearchSelect
                name="currency"
                defaultValue={search.get("currency") ?? ""}
                className="input w-full mt-1"
              >
                <option value="">Wszystkie waluty</option>
                {["PLN", "EUR", "USD"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </SearchSelect>
            </label>
            <label className="text-sm text-gray-300">
              Kwota od (PLN)
              <input
                name="min"
                inputMode="decimal"
                maxLength={18}
                defaultValue={search.get("min") ?? ""}
                aria-describedby="amount-filter-help"
                className="input w-full mt-1"
              />
            </label>
            <label className="text-sm text-gray-300">
              Kwota do (PLN)
              <input
                name="max"
                inputMode="decimal"
                maxLength={18}
                defaultValue={search.get("max") ?? ""}
                aria-describedby="amount-filter-help"
                className="input w-full mt-1"
              />
            </label>
            <label className="text-sm text-gray-300">
              Wyników na stronę
              <SearchSelect
                name="size"
                defaultValue={search.get("size") ?? "25"}
                className="input w-full mt-1"
              >
                {[25, 50, 100].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </SearchSelect>
            </label>
          </div>
          <p id="amount-filter-help" className="text-xs text-gray-400">
            Kwoty to równowartości PLN bez znaku, dla pojedynczego zapisu na
            koncie — nie suma obu stron księgi. Daty obejmują oba wskazane dni.
            Wyszukiwanie obejmuje całą historię, także konta archiwalne.
          </p>
        </details>
        <div className="flex flex-wrap gap-3">
          <button className="btn-primary" type="submit">
            Zastosuj filtry
          </button>
          <button
            className="btn-secondary"
            type="button"
            onClick={() => setSearch({})}
          >
            Wyczyść filtry
          </button>
        </div>
      </form>
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

function SearchSelect({
  defaultValue,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const [value, setValue] = useState(String(defaultValue ?? ""));
  return (
    <select
      {...props}
      value={value}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}

function TransactionDetail({
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
              {TYPES[query.data.type]} · Źródło: {query.data.source}
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
