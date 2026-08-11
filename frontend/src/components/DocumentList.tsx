import { useState } from "react";
import { useDocuments, useDeleteDocument, DocumentData, formatFileSize, STATUS_LABELS, STATUS_COLORS } from "../api/documents";
import { DocumentViewer } from "./DocumentViewer";

export function DocumentList() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [viewingDoc, setViewingDoc] = useState<DocumentData | null>(null);
  const { data: documents, isLoading } = useDocuments(statusFilter ? { status: statusFilter } : undefined);
  const deleteDoc = useDeleteDocument();

  if (isLoading) return <p className="text-gray-400 text-sm">Ładowanie dokumentów...</p>;

  if (!documents || documents.length === 0) {
    return <p className="text-gray-500 text-sm py-8 text-center">Brak dokumentów. Upuść plik powyżej lub zrób zdjęcie.</p>;
  }

  return (
    <div>
      <div className="flex gap-2 mb-4 flex-wrap">
        {[undefined, "pending", "processing", "done", "error"].map((s) => (
          <button key={s ?? "all"} onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${statusFilter === s ? "bg-advisor-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}>
            {s ? STATUS_LABELS[s] : "Wszystkie"}
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {documents.map((doc) => (
          <div key={doc.id} className="flex items-center gap-4 p-3 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors cursor-pointer" onClick={() => setViewingDoc(doc)}>
            <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center flex-shrink-0">
              {doc.mime_type.startsWith("image/") ? (
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-200 truncate">{doc.original_name}</p>
              <p className="text-xs text-gray-500">{formatFileSize(doc.size_bytes)} · {new Date(doc.created_at).toLocaleDateString("pl-PL")}</p>
            </div>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${STATUS_COLORS[doc.status]}`}>
              {doc.status === "processing" && (
                <svg className="w-3 h-3 inline mr-1 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                  <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {STATUS_LABELS[doc.status]}
            </span>
            <button onClick={(e) => { e.stopPropagation(); if (confirm("Usunąć dokument?")) deleteDoc.mutate(doc.id); }}
              className="p-1 text-gray-600 hover:text-red-400 transition-colors flex-shrink-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        ))}
      </div>
      {viewingDoc && <DocumentViewer document={viewingDoc} onClose={() => setViewingDoc(null)} />}
    </div>
  );
}
