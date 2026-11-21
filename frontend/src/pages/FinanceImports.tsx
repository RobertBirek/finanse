import { Link, useSearchParams } from "react-router-dom";
import { useImportActor, useImportHistory } from "../api/bankImports";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { listPage, setListPage } from "../lib/listPage";
import { ImportUpload } from "../components/finance/imports/ImportUpload";
import { PageHeader } from "../components/PageHeader";

export function FinanceImports() {
  const actor = useImportActor();
  const [params, setParams] = useSearchParams();
  const kind =
    params.get("kind") === "loan_schedule" ? "loan_schedule" : "statement";
  const page = listPage(params.get("page"));
  const offset = (page - 1) * 25;
  const imports = useImportHistory(kind, offset);
  const batches = imports.data?.items ?? [];
  function changePage(page: number) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      setListPage(next, "page", page);
      return next;
    });
  }
  return (
    <div className="page-workspace">
      <PageHeader
        title={
          kind === "loan_schedule" ? "Import harmonogramów" : "Import wyciągów"
        }
        description="Źródło → Decyzja → Księga. Ty wybierasz, co zostanie zapisane."
      />
      <FinanceTabs />
      <label className="mb-4 block">
        Rodzaj importu
        <select
          className="input mt-1 block w-full sm:w-auto"
          value={kind}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            next.set("kind", e.target.value);
            next.delete("page");
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
          <>
            {batches.length ? (
              <ul className="space-y-3">
                {batches.map((batch) => {
                  const detailSearch = new URLSearchParams();
                  if (kind === "loan_schedule") detailSearch.set("kind", kind);
                  setListPage(detailSearch, "page", page);
                  return (
                    <li
                      key={batch.id}
                      className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 py-3 dark:border-gray-800"
                    >
                      <Link
                        className="min-w-0 break-words underline"
                        to={{
                          pathname: `/finances/imports/${encodeURIComponent(batch.id)}`,
                          search: detailSearch.toString(),
                        }}
                      >
                        {batch.source_names.join(", ") || "Import bez źródeł"}
                      </Link>
                      <span className="text-sm">
                        {batch.archived_at
                          ? "Archiwalny"
                          : batch.commit_state === "committed"
                            ? "Zatwierdzony"
                            : `Do sprawdzenia: ${batch.unresolved_count}`}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>
                {offset
                  ? "Brak importów na tej stronie."
                  : kind === "loan_schedule"
                    ? "Brak zapisanych importów harmonogramów."
                    : "Brak zapisanych importów wyciągów."}
              </p>
            )}
            {offset || (imports.data?.total ?? 0) > 25 ? (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={!offset}
                  onClick={() => changePage(page - 1)}
                >
                  Poprzednia strona
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={offset + 25 >= (imports.data?.total ?? 0)}
                  onClick={() => changePage(page + 1)}
                >
                  Następna strona
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
