import {
  useDocumentText,
  type DocumentData,
  STATUS_LABELS,
  STATUS_COLORS,
  formatFileSize,
} from "../api/documents";
import { Dialog } from "./Dialog";
import { QueryFeedback } from "./QueryFeedback";

type Props = { document: DocumentData; onClose: () => void };

export function DocumentViewer({ document: doc, onClose }: Props) {
  const text = useDocumentText(doc.id, doc.status === "done");
  return (
    <Dialog
      label={`Dokument: ${doc.original_name}`}
      onClose={onClose}
      panelClassName="w-full max-w-2xl rounded-xl border border-gray-700 bg-gray-900"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 p-4 border-b border-gray-800">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-white break-all">
            {doc.original_name}
          </h2>
          <p className="text-sm text-gray-400">
            {formatFileSize(doc.size_bytes)} ·{" "}
            {new Date(doc.created_at).toLocaleString("pl-PL")}
          </p>
        </div>
        <span
          className={`px-2 py-1 rounded-full text-xs ${STATUS_COLORS[doc.status]}`}
        >
          {STATUS_LABELS[doc.status]}
        </span>
        <button type="button" onClick={onClose} className="btn-secondary">
          Zamknij
        </button>
      </div>
      <div className="p-4">
        {doc.status === "pending" || doc.status === "processing" ? (
          <p role="status" className="py-8 text-center text-gray-300">
            Dokument jest przetwarzany…
          </p>
        ) : doc.status === "error" ? (
          <p role="alert" className="py-8 text-red-300">
            Nie udało się odczytać dokumentu. Oryginał pozostaje zachowany.
            Możesz ponownie przesłać ten sam plik, aby ponowić odczyt.
          </p>
        ) : (
          <QueryFeedback
            loading={text.isLoading}
            error={text.isError}
            errorMessage="Nie udało się pobrać odczytanego tekstu."
            onRetry={text.refetch}
          >
            {text.data?.extracted_text.trim() ? (
              <pre className="text-sm text-gray-300 whitespace-pre-wrap break-words font-mono bg-gray-950 p-4 rounded-lg">
                {text.data.extracted_text}
              </pre>
            ) : (
              <p className="py-8 text-gray-400">
                Nie znaleziono tekstu w dokumencie. Sprawdź, czy plik zawiera
                czytelny tekst lub wyraźne zdjęcie.
              </p>
            )}
          </QueryFeedback>
        )}
      </div>
    </Dialog>
  );
}
