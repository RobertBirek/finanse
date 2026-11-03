import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useDocuments,
  useArchiveDocument,
  useRestoreDocument,
  documentArchiveError,
  formatFileSize,
  STATUS_LABELS,
  STATUS_COLORS,
} from "../api/documents";
import { DocumentViewer } from "./DocumentViewer";
import { DocumentReview } from "./documents/DocumentReview";
import { QueryFeedback } from "./QueryFeedback";
import { getDocumentStatus } from "./documents/documentStatus";
import { ProcessingPulse } from "./documents/ProcessingFeedback";
import { isDocumentWorkActive } from "../api/documents";
import { isProcessingActorCurrent } from "../stores/documentProcessingStore";

export function DocumentList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedReview = searchParams.get("review");
  const archived = searchParams.get("archived") === "true";
  const linkedReviewId =
    requestedReview &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      requestedReview,
    )
      ? requestedReview
      : null;
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  useEffect(() => {
    setViewingId(null);
    setReviewingId(linkedReviewId);
  }, [linkedReviewId]);
  const closeReview = () => {
    setReviewingId(null);
    if (searchParams.has("review")) {
      const next = new URLSearchParams(searchParams);
      next.delete("review");
      setSearchParams(next, { replace: true });
    }
  };
  const query = useDocuments({ status: statusFilter, archived });
  const archiveDoc = useArchiveDocument();
  const restoreDoc = useRestoreDocument();
  const [feedback, setFeedback] = useState<string | null>(null);
  const documents = query.data ?? [];
  // Resolve from current query data so a polling result also updates an open viewer.
  const viewingDoc = documents.find((doc) => doc.id === viewingId);

  return (
    <div>
      <div
        role="group"
        aria-label="Widoczność dokumentów"
        className="mb-3 flex gap-2"
      >
        {[false, true].map((value) => (
          <button
            key={String(value)}
            type="button"
            aria-pressed={archived === value}
            className={archived === value ? "btn-primary" : "btn-secondary"}
            onClick={() => {
              const next = new URLSearchParams(searchParams);
              next.delete("review");
              if (value) next.set("archived", "true");
              else next.delete("archived");
              setViewingId(null);
              setReviewingId(null);
              setStatusFilter(undefined);
              setSearchParams(next);
            }}
          >
            {value ? "Archiwum" : "Aktywne"}
          </button>
        ))}
      </div>
      {archived && (
        <p className="mb-3 text-sm text-gray-400">
          Archiwizacja ukrywa dokument na zwykłej liście. Pliki i powiązania
          finansowe pozostają zachowane.
        </p>
      )}
      {feedback && (
        <p
          role="status"
          className="mb-3 text-sm"
          style={{ color: "var(--ui-green)" }}
        >
          {feedback}
        </p>
      )}
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
                : archived
                  ? "Archiwum jest puste."
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
            {documents.map((doc) => {
              const reviewStatus = getDocumentStatus(doc);
              const statusColor =
                reviewStatus.tone === "danger"
                  ? "error"
                  : reviewStatus.tone === "success"
                    ? "done"
                    : reviewStatus.tone === "warning"
                      ? "processing"
                      : "pending";
              return (
                <li
                  key={doc.id}
                  className="flex items-center gap-2 p-3 bg-gray-900 rounded-lg"
                >
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      aria-label={`Otwórz dokument: ${doc.original_name}`}
                      aria-describedby={`document-meta-${doc.id}${doc.status === "pending" && doc.next_attempt_at ? ` document-pending-${doc.id}` : ""}${doc.status === "error" ? ` document-error-${doc.id}` : ""}`}
                      onClick={() => setViewingId(doc.id)}
                      className="min-h-11 w-full min-w-0 rounded-lg p-2 text-left hover:bg-gray-800"
                    >
                      <span className="block truncate text-sm font-medium text-gray-200">
                        {doc.original_name}
                      </span>
                    </button>
                    <span
                      id={`document-meta-${doc.id}`}
                      className="block text-xs text-gray-400"
                    >
                      {formatFileSize(doc.size_bytes)} ·{" "}
                      {new Date(doc.created_at).toLocaleDateString("pl-PL")}
                    </span>
                    {doc.status === "pending" && doc.next_attempt_at && (
                      <span
                        id={`document-pending-${doc.id}`}
                        className="block text-xs text-yellow-300"
                      >
                        Ponowna próba od{" "}
                        {new Date(doc.next_attempt_at).toLocaleString("pl-PL")}{" "}
                        (wykonano prób: {doc.attempt_count}).
                      </span>
                    )}
                    {doc.status === "error" && (
                      <span
                        id={`document-error-${doc.id}`}
                        className="block text-xs text-red-300"
                      >
                        Przetwarzanie zakończone błędem. Automatyczne próby
                        zakończone.
                      </span>
                    )}
                  </div>
                  <span
                    className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium shrink-0 ${STATUS_COLORS[statusColor]}`}
                  >
                    {isDocumentWorkActive(doc) && <ProcessingPulse />}
                    {reviewStatus.label}
                  </span>
                  <button
                    type="button"
                    aria-label={`${archived ? "Przywróć" : "Archiwizuj"} dokument: ${doc.original_name}`}
                    disabled={archiveDoc.isPending || restoreDoc.isPending}
                    onClick={() => {
                      if (
                        !archived &&
                        !window.confirm(
                          "Przenieść dokument do archiwum? Plik, historia odczytu i powiązania finansowe pozostaną zachowane.",
                        )
                      )
                        return;
                      const mutation = archived ? restoreDoc : archiveDoc;
                      mutation.mutate(
                        { documentId: doc.id },
                        {
                          onSuccess: (_result, _variables, actor) => {
                            if (!isProcessingActorCurrent(actor)) return;
                            setViewingId(null);
                            closeReview();
                            setFeedback(
                              archived
                                ? "Dokument przywrócony."
                                : "Dokument przeniesiony do archiwum.",
                            );
                          },
                        },
                      );
                    }}
                    className="min-h-11 px-2 text-sm text-red-300 rounded-lg hover:bg-gray-800 disabled:opacity-50"
                  >
                    {archived ? "Przywróć" : "Archiwizuj"}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </QueryFeedback>
      {(archiveDoc.isError || restoreDoc.isError) && (
        <p role="alert" className="mt-3 text-sm text-red-300">
          {documentArchiveError(archiveDoc.error ?? restoreDoc.error)}
        </p>
      )}
      {viewingDoc && (
        <DocumentViewer
          document={viewingDoc}
          onClose={() => setViewingId(null)}
          onReview={() => {
            setViewingId(null);
            setReviewingId(viewingDoc.id);
          }}
        />
      )}
      {reviewingId && (
        <DocumentReview
          key={reviewingId}
          documentId={reviewingId}
          onClose={closeReview}
        />
      )}
    </div>
  );
}
