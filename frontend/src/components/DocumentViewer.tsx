import { useDocumentText, DocumentData, STATUS_LABELS, STATUS_COLORS, formatFileSize } from "../api/documents";

interface Props {
  document: DocumentData;
  onClose: () => void;
}

export function DocumentViewer({ document: doc, onClose }: Props) {
  const { data: textData, isLoading: textLoading } = useDocumentText(doc.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col m-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <div>
            <h3 className="text-lg font-semibold text-white">{doc.original_name}</h3>
            <p className="text-sm text-gray-500">{formatFileSize(doc.size_bytes)} · {new Date(doc.created_at).toLocaleString("pl-PL")}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[doc.status]}`}>{STATUS_LABELS[doc.status]}</span>
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {doc.status === "pending" || doc.status === "processing" ? (
            <div className="text-center py-8">
              <svg className="w-8 h-8 mx-auto mb-3 animate-spin text-advisor-400" fill="none" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-gray-400">Dokument jest przetwarzany...</p>
            </div>
          ) : doc.status === "error" ? (
            <p className="text-red-400 text-center py-8">Błąd przetwarzania dokumentu.</p>
          ) : textLoading ? (
            <p className="text-gray-400">Ładowanie tekstu...</p>
          ) : textData ? (
            <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono bg-gray-950 p-4 rounded-lg">{textData.extracted_text}</pre>
          ) : (
            <p className="text-gray-500 text-center py-8">Brak wyekstrahowanego tekstu.</p>
          )}
        </div>
      </div>
    </div>
  );
}
