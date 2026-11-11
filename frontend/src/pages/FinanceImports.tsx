import { Link, useSearchParams } from "react-router-dom";
import { useImportActor, useImports } from "../api/bankImports";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { ImportUpload } from "../components/finance/imports/ImportUpload";

export function FinanceImports() {
  const actor = useImportActor();
  const imports = useImports();
  const [params, setParams] = useSearchParams();
  const kind =
    params.get("kind") === "loan_schedule" ? "loan_schedule" : "statement";
  return (
    <div className="max-w-6xl">
      <header className="finance-page-heading">
        <div>
          <h1>
            {kind === "loan_schedule"
              ? "Import harmonogramów"
              : "Import wyciągów"}
          </h1>
          <p>Źródło → Decyzja → Księga. Ty wybierasz, co zostanie zapisane.</p>
        </div>
      </header>
      <FinanceTabs />
      <label className="mb-4 block">
        Rodzaj importu
        <select
          className="input mt-1 block w-full sm:w-auto"
          value={kind}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            next.set("kind", e.target.value);
            setParams(next);
          }}
        >
          <option value="statement">Wyciąg bankowy</option>
          <option value="loan_schedule">Harmonogram kredytu</option>
        </select>
      </label>
      {kind === "loan_schedule" ? (
        <p className="card mb-4">Harmonogram nie księguje spłat</p>
      ) : null}
      <ImportUpload
        key={`${actor.ownerId}:${actor.generation}:${kind}`}
        kind={kind}
        documentId={params.get("document")}
      />
      <section className="card mt-5" aria-label="Zapisane importy">
        <h2 className="mb-3 text-xl">Zapisane importy</h2>
        {imports.isLoading ? (
          <p role="status">Ładowanie importów…</p>
        ) : imports.isError ? (
          <p role="alert">
            Nie udało się pobrać importów.{" "}
            <button
              type="button"
              onClick={() => imports.refetch()}
              className="underline"
            >
              Ponów
            </button>
          </p>
        ) : (
          <ul className="space-y-3">
            {(imports.data ?? [])
              .filter((batch) => batch.kind === kind)
              .map((batch) => (
                <li
                  key={batch.id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 py-3 dark:border-gray-800"
                >
                  <Link
                    className="min-w-0 break-words underline"
                    to={`/finances/imports/${encodeURIComponent(batch.id)}`}
                  >
                    {batch.sources
                      .map((source) => source.original_name)
                      .join(", ") || "Import bez źródeł"}
                  </Link>
                  <span className="text-sm">
                    {batch.archived_at
                      ? "Archiwalny"
                      : batch.commit_state === "committed"
                        ? "Zatwierdzony"
                        : `Do sprawdzenia: ${batch.unresolved_count}`}
                  </span>
                </li>
              ))}
          </ul>
        )}
        {!imports.isLoading && imports.data?.length === 0 ? (
          <p>
            Nie masz jeszcze importów. Dodaj tekstowy wyciąg lub CSV powyżej.
          </p>
        ) : null}
      </section>
    </div>
  );
}
