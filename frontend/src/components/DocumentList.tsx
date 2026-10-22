import { useState } from "react";
import {
  useDocuments,
  useDeleteDocument,
  formatFileSize,
  STATUS_LABELS,
  STATUS_COLORS,
} from "../api/documents";
import { DocumentViewer } from "./DocumentViewer";
import { QueryFeedback } from "./QueryFeedback";

export function DocumentList() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [viewingId, setViewingId] = useState<string | null>(null);
  const query = useDocuments(
    statusFilter ? { status: statusFilter } : undefined,
  );
  const deleteDoc = useDeleteDocument();
  const documents = query.data ?? [];
  // Resolve from current query data so a polling result also updates an open viewer.
  const viewingDoc = documents.find((doc) => doc.id === viewingId);

  return (
    <div>
      <div
        className="flex gap-2 mb-4 flex-wrap"
        role="group"
        aria-label="Status dokumentów"
      >
        {[undefined, "pending", "processing", "done", "error"].map((status) => (
          <button
            key={status ?? "all"}
            type="button"
            aria-pressed={statusFilter === status}
            onClick={() => {
              setStatusFilter(status);
              setViewingId(null);
            }}
            className={`min-h-11 px-3 py-2 rounded-lg text-sm ${statusFilter === status ? "bg-advisor-700 text-white" : "bg-gray-800 text-gray-300 hover:bg-gray-700"}`}
          >
            {status ? STATUS_LABELS[status] : "Wszystkie"}
          </button>
        ))}
      </div>
      <QueryFeedback
        loading={query.isLoading}
        error={query.isError}
        errorMessage="Nie udało się pobrać dokumentów."
        onRetry={query.refetch}
      >
        {documents.length === 0 ? (
          <div className="py-8 text-center text-sm text-gray-400">
            <p>
              {statusFilter
                ? "Brak dokumentów o wybranym statusie."
                : "Brak dokumentów. Wybierz plik powyżej lub zrób zdjęcie."}
            </p>
            {statusFilter && (
              <button
                type="button"
                className="btn-secondary mt-3"
                onClick={() => setStatusFilter(undefined)}
              >
                Pokaż wszystkie dokumenty
              </button>
            )}
          </div>
        ) : (
          <ul className="space-y-2">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center gap-2 p-3 bg-gray-900 rounded-lg"
              >
                <button
                  type="button"
                  aria-label={`Otwórz dokument: ${doc.original_name}`}
                  onClick={() => setViewingId(doc.id)}
                  className="min-w-0 flex-1 rounded-lg p-2 text-left hover:bg-gray-800"
                >
                  <span className="block truncate text-sm font-medium text-gray-200">
                    {doc.original_name}
                  </span>
                  <span className="block text-xs text-gray-400">
                    {formatFileSize(doc.size_bytes)} ·{" "}
                    {new Date(doc.created_at).toLocaleDateString("pl-PL")}
                  </span>
                  {doc.status === "pending" && doc.next_attempt_at && (
                    <span className="block text-xs text-yellow-300">
                      Ponowna próba od{" "}
                      {new Date(doc.next_attempt_at).toLocaleString("pl-PL")}{" "}
                      (wykonano prób: {doc.attempt_count}).
                    </span>
                  )}
                  {doc.status === "error" && (
                    <span className="block text-xs text-red-300">
                      Przetwarzanie zakończone błędem. Automatyczne próby
                      zakończone.
                    </span>
                  )}
                </button>
                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${STATUS_COLORS[doc.status]}`}
                >
                  {STATUS_LABELS[doc.status]}
                </span>
                <button
                  type="button"
                  aria-label={`Usuń dokument: ${doc.original_name}`}
                  disabled={deleteDoc.isPending}
                  onClick={() => {
                    if (
                      window.confirm(`Usunąć dokument „${doc.original_name}”?`)
                    )
                      deleteDoc.mutate(doc.id);
                  }}
                  className="min-h-11 px-2 text-sm text-red-300 rounded-lg hover:bg-gray-800 disabled:opacity-50"
                >
                  Usuń
                </button>
              </li>
            ))}
          </ul>
        )}
      </QueryFeedback>
      {deleteDoc.isError && (
        <p role="alert" className="mt-3 text-sm text-red-300">
          Nie udało się usunąć dokumentu. Spróbuj ponownie.
        </p>
      )}
      {viewingDoc && (
        <DocumentViewer
          document={viewingDoc}
          onClose={() => setViewingId(null)}
        />
      )}
    </div>
  );
}
