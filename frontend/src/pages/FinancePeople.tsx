import { useState } from "react";
import { Link } from "react-router-dom";
import { usePeople } from "../api/people";
import { PersonEditor } from "../components/finance/PersonEditor";
import { QueryFeedback } from "../components/QueryFeedback";

export function FinancePeople() {
  const [offset, setOffset] = useState(0);
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const people = usePeople({ include_archived: archived, offset });
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Osoby</h1>
          <p className="text-gray-400 mt-1">
            Darowizny od osób, bez dodatkowych kont i podwójnego liczenia
            pieniędzy.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          Dodaj osobę
        </button>
      </header>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={archived}
          onChange={(e) => {
            setArchived(e.target.checked);
            setOffset(0);
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
                className="text-advisor-400 underline font-medium"
                to={`/finances/people/${p.id}`}
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
            onClick={() => setOffset((v) => Math.max(0, v - 50))}
          >
            Poprzednia strona
          </button>
          <button
            className="btn-secondary"
            disabled={!people.data || offset + 50 >= people.data.total}
            onClick={() => setOffset((v) => v + 50)}
          >
            Następna strona
          </button>
        </div>
      </QueryFeedback>
      {creating ? <PersonEditor onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
