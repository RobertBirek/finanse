import {
  useDocumentText,
  type DocumentData,
  STATUS_COLORS,
  formatFileSize,
  isDocumentWorkActive,
} from "../api/documents";
import { Dialog } from "./Dialog";
import { DocumentIcon, DocumentTooltip } from "./documents/documentControls";
import { QueryFeedback } from "./QueryFeedback";
import { getDocumentStatus } from "./documents/documentStatus";

type Props = {
  document: DocumentData;
  onClose: () => void;
  onReview?: () => void;
};

export function DocumentViewer({ document: doc, onClose, onReview }: Props) {
  const text = useDocumentText(doc.id, !!doc.has_extracted_text);
  const status = getDocumentStatus(doc);
  const color =
    status.tone === "danger"
      ? "error"
      : status.tone === "success"
        ? "done"
        : status.tone === "warning"
          ? "processing"
          : "pending";
  return (
    <Dialog
      label={`Dokument: ${doc.original_name}`}
      onClose={onClose}
      panelClassName="w-full max-w-2xl rounded-xl border border-gray-700 bg-gray-900"
    >
      <header className="border-b border-gray-800 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold break-words text-white">
              {doc.original_name}
            </h2>
            <p className="mt-1 text-xs text-gray-400">
              {formatFileSize(doc.size_bytes)} ·{" "}
              {new Date(doc.created_at).toLocaleString("pl-PL")}
            </p>
          </div>
          <DocumentTooltip label="Zamknij">
            <button
              type="button"
              aria-label="Zamknij"
              onClick={onClose}
              className="document-icon-control"
            >
              <DocumentIcon name="close" />
            </button>
          </DocumentTooltip>
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <span
            className={`rounded-md px-2 py-1 text-xs ${STATUS_COLORS[color]}`}
          >
            {status.label}
          </span>
          {onReview && (
            <button
              type="button"
              onClick={onReview}
              className="btn-primary min-h-11"
            >
              Sprawdź dane
            </button>
          )}
        </div>
      </header>
      <section aria-label="Odczytany tekst" className="p-4">
        {isDocumentWorkActive(doc) ||
        (!doc.review &&
          (doc.status === "pending" || doc.status === "processing")) ? (
          <p role="status" className="py-8 text-center text-gray-300">
            Dokument jest przetwarzany…
          </p>
        ) : (
          <>
            {doc.status === "error" && (
              <p role="alert" className="mb-3 text-sm text-red-300">
                Ostatni odczyt zakończył się błędem. Oryginał jest zachowany.
                {onReview &&
                  doc.mime_type === "application/pdf" &&
                  !doc.archived_at &&
                  " W sekcji „Sprawdź dane” możesz ponowić lokalny OCR."}
              </p>
            )}
            {!doc.has_extracted_text ? (
              <p className="py-8 text-gray-400">
                Tekst OCR nie jest dostępny dla tego dokumentu.
              </p>
            ) : (
              <QueryFeedback
                loading={text.isLoading}
                error={text.isError}
                errorMessage="Nie udało się pobrać odczytanego tekstu."
                onRetry={text.refetch}
              >
                {text.data?.extracted_text.trim() ? (
                  <>
                    <h3 className="mb-2 text-sm font-medium text-gray-300">
                      Odczytany tekst
                    </h3>
                    <pre className="max-h-[56dvh] overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-gray-950 p-4 font-mono text-sm text-gray-300">
                      {text.data.extracted_text}
                    </pre>
                  </>
                ) : (
                  <p className="py-8 text-gray-400">
                    Nie znaleziono tekstu w dokumencie. Sprawdź, czy plik
                    zawiera czytelny tekst lub wyraźne zdjęcie.
                  </p>
                )}
              </QueryFeedback>
            )}
          </>
        )}
      </section>
    </Dialog>
  );
}
