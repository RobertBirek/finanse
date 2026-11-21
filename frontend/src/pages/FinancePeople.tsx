import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { usePeople } from "../api/people";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { PersonEditor } from "../components/finance/PersonEditor";
import { retainFinancePeriod } from "../components/finance/useFinancePeriod";
import { listPage, setListPage } from "../lib/listPage";
import { QueryFeedback } from "../components/QueryFeedback";
import { PageHeader } from "../components/PageHeader";

export function FinancePeople() {
  const [search, setSearch] = useSearchParams();
  const page = listPage(search.get("page"));
  const offset = (page - 1) * 50;
  const archived = search.get("archived") === "1";
  const detailsSearch = retainFinancePeriod(search);
  if (archived) detailsSearch.set("archived", "1");
  setListPage(detailsSearch, "page", page);
  function changePage(page: number) {
    setSearch((current) => {
      const next = new URLSearchParams(current);
      setListPage(next, "page", page);
      return next;
    });
  }
  const [creating, setCreating] = useState(false);
  const people = usePeople({ include_archived: archived, offset });
  return (
    <div className="page-workspace space-y-6">
      <PageHeader
        title="Osoby"
        description="Darowizny od osób, bez dodatkowych kont i podwójnego liczenia pieniędzy."
        actions={
          <button className="btn-primary" onClick={() => setCreating(true)}>
            Dodaj osobę
          </button>
        }
      />
      <FinanceTabs />
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={archived}
          onChange={(e) => {
            const includeArchived = e.target.checked;
            setSearch((current) => {
              const next = new URLSearchParams(current);
              if (includeArchived) next.set("archived", "1");
              else next.delete("archived");
              next.delete("page");
              return next;
            });
          }}
        />
        Pokaż również archiwalne
      </label>
      <QueryFeedback
        loading={people.isLoading}
        error={people.isError}
        onRetry={people.refetch}
        errorMessage="Nie udało się pobrać osób."
      >
        {people.data?.items.length === 0 ? (
          <p className="card">
            Brak osób. Dodaj osobę, a następnie przypisz jej przychody w
            szczegółach transakcji.
          </p>
        ) : null}
        <ul className="space-y-2">
          {people.data?.items.map((p) => (
            <li
              className="card flex flex-wrap justify-between gap-2"
              key={p.id}
            >
              <Link
                className="text-advisor-700 dark:text-advisor-400 underline font-medium"
                to={{
                  pathname: `/finances/people/${p.id}`,
                  search: detailsSearch.toString(),
                }}
              >
                {p.name}
              </Link>
              {!p.is_active ? (
                <span className="text-sm text-gray-400">Archiwalna</span>
              ) : null}
            </li>
          ))}
        </ul>
        <div className="flex gap-3 mt-4">
          <button
            className="btn-secondary"
            disabled={!offset}
            onClick={() => changePage(page - 1)}
          >
            Poprzednia strona
          </button>
          <button
            className="btn-secondary"
            disabled={!people.data || offset + 50 >= people.data.total}
            onClick={() => changePage(page + 1)}
          >
            Następna strona
          </button>
        </div>
      </QueryFeedback>
      {creating ? <PersonEditor onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
