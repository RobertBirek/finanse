import { useEffect, useId, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  isDocumentWorkActive,
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
import {
  getDocumentStatus,
  getFinanceDocumentStatus,
} from "./documents/documentStatus";
import { ProcessingPulse } from "./documents/ProcessingFeedback";
import { DocumentIcon, DocumentTooltip } from "./documents/documentControls";
import { isProcessingActorCurrent } from "../stores/documentProcessingStore";

const statusClass = {
  neutral: STATUS_COLORS.pending,
  warning: STATUS_COLORS.processing,
  success: STATUS_COLORS.done,
  danger: STATUS_COLORS.error,
};

function DocumentImportMenu({ documentId }: { documentId: string }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const actionsId = useId();

  return (
    <div
      className="relative"
      onBlur={(event) => {
        if (
          !(event.relatedTarget instanceof Node) ||
          !event.currentTarget.contains(event.relatedTarget)
        ) {
          setOpen(false);
        }
      }}
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        event.stopPropagation();
        setOpen(false);
        button.current?.focus();
      }}
    >
      <DocumentTooltip label={open ? undefined : "Więcej akcji"}>
        <button
          ref={button}
          type="button"
          aria-label="Więcej akcji"
          aria-expanded={open}
          aria-controls={actionsId}
          className="document-icon-control"
          onClick={() => setOpen(!open)}
        >
          <DocumentIcon name="more" />
        </button>
      </DocumentTooltip>
      <div
        id={actionsId}
        hidden={!open}
        className="absolute right-0 top-full z-10 w-max rounded-lg border border-gray-700 bg-gray-950 p-1 shadow-lg"
      >
        <Link
          to={`/finances/imports?document=${encodeURIComponent(documentId)}`}
          className="flex min-h-11 items-center rounded-md px-3 text-sm text-gray-200 hover:bg-gray-800"
        >
          Użyj do importu
        </Link>
      </div>
    </div>
  );
}

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
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="Widoczność dokumentów"
          className="flex gap-2"
        >
          {[false, true].map((value) => (
            <button
              key={String(value)}
              type="button"
              aria-pressed={archived === value}
              className={`min-h-11 ${archived === value ? "btn-primary" : "btn-secondary"}`}
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
        <label className="flex min-w-0 items-center gap-2 text-sm text-gray-300">
          Status
          <select
            aria-label="Status dokumentów"
            className="input min-h-11 min-w-0"
            value={statusFilter ?? ""}
            onChange={(event) => {
              setStatusFilter(event.target.value || undefined);
              setViewingId(null);
            }}
          >
            <option value="">Wszystkie</option>
            {Object.entries(STATUS_LABELS).map(([status, label]) => (
              <option key={status} value={status}>
                {label}
              </option>
            ))}
          </select>
        </label>
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
          <ul className="divide-y divide-gray-800 rounded-xl border border-gray-800 bg-gray-900">
            {documents.map((doc) => {
              const reading = getDocumentStatus(doc);
              const finance = getFinanceDocumentStatus(doc);
              const billId = doc.finance?.bill_id;
              const canReview =
                !archived && (!billId || doc.finance?.review === "draft");
              const canImport =
                !archived &&
                doc.status === "done" &&
                doc.mime_type === "application/pdf";
              const retryAt =
                doc.status === "pending" ? doc.next_attempt_at : null;
              const archiveLabel = archived
                ? "Przywróć dokument"
                : "Archiwizuj dokument";
              const hint =
                doc.status === "error"
                  ? "Odczyt nie powiódł się. Otwórz dokument, aby sprawdzić dostępne opcje."
                  : retryAt
                    ? `Ponowna próba od ${new Date(retryAt).toLocaleString("pl-PL")} (próby: ${doc.attempt_count}).`
                    : null;
              return (
                <li
                  key={doc.id}
                  className="grid min-w-0 gap-x-4 gap-y-1.5 px-3 py-2.5 lg:grid-cols-[minmax(0,1fr)_minmax(12rem,31%)_13.5rem] lg:items-center lg:px-4"
                >
                  <div className="flex min-w-0 items-start gap-2">
                    <span className="mt-2.5 rounded-lg bg-gray-800 p-1.5 text-gray-300">
                      <DocumentIcon
                        name={
                          doc.mime_type?.startsWith("image/") ? "image" : "file"
                        }
                      />
                    </span>
                    <div className="min-w-0 flex-1">
                      <button
                        type="button"
                        aria-label={`Otwórz dokument: ${doc.original_name}`}
                        aria-describedby={`document-meta-${doc.id}${hint ? ` document-hint-${doc.id}` : ""}`}
                        onClick={() => setViewingId(doc.id)}
                        className="block min-h-11 w-full min-w-0 rounded-md text-left hover:underline"
                      >
                        <span
                          className="block truncate text-sm font-semibold text-gray-100"
                          title={doc.original_name}
                        >
                          {doc.original_name}
                        </span>
                      </button>
                      <span
                        id={`document-meta-${doc.id}`}
                        className="block text-xs font-normal text-gray-400"
                      >
                        {formatFileSize(doc.size_bytes)} ·{" "}
                        {new Date(doc.created_at).toLocaleDateString("pl-PL")}
                      </span>
                      {hint && (
                        <p
                          id={`document-hint-${doc.id}`}
                          className={`mt-1 text-xs ${doc.status === "error" ? "text-red-300" : "text-amber-300"}`}
                        >
                          {hint}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5 pl-10 lg:pl-0">
                    <span
                      role="group"
                      aria-label="Odczyt"
                      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ${statusClass[reading.tone]}`}
                    >
                      {isDocumentWorkActive(doc) ? (
                        <ProcessingPulse />
                      ) : (
                        <DocumentIcon name="scan" />
                      )}
                      {reading.label}
                    </span>
                    <span
                      role="group"
                      aria-label="Finanse"
                      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ${statusClass[finance.tone]}`}
                    >
                      <DocumentIcon name="finance" />
                      {finance.label}
                    </span>
                  </div>
                  <div className="flex min-w-0 flex-wrap items-center justify-end gap-0.5">
                    {canReview && (
                      <button
                        type="button"
                        className="min-h-11 rounded-lg px-2 text-sm font-medium text-[var(--ui-blue)] hover:bg-[var(--ui-hover)] hover:underline"
                        onClick={() => setReviewingId(doc.id)}
                      >
                        {billId ? "Sprawdź szkic" : "Sprawdź dane"}
                      </button>
                    )}
                    {billId && (
                      <DocumentTooltip label="Otwórz w finansach">
                        <Link
                          aria-label="Otwórz w finansach"
                          className="document-icon-control"
                          to={`/finances/documents?bill=${encodeURIComponent(billId)}`}
                        >
                          <DocumentIcon name="finance" />
                        </Link>
                      </DocumentTooltip>
                    )}
                    <DocumentTooltip label={archiveLabel}>
                      <button
                        type="button"
                        aria-label={`${archiveLabel}: ${doc.original_name}`}
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
                        className="document-icon-control"
                      >
                        <DocumentIcon name={archived ? "restore" : "archive"} />
                      </button>
                    </DocumentTooltip>
                    {canImport && <DocumentImportMenu documentId={doc.id} />}
                  </div>
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
