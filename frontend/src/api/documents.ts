import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import {
  captureProcessingActor,
  isProcessingActorCurrent,
  useDocumentProcessingStore,
  type ProcessingActor,
} from "../stores/documentProcessingStore";
import {
  getDocumentOperations,
  isActiveOperation,
} from "../components/documents/documentProcessing";

export interface DocumentData {
  id: string;
  user_id: string;
  filename: string;
  original_name: string;
  mime_type: string;
  sha256_hash: string;
  size_bytes: number;
  status: "pending" | "processing" | "done" | "error";
  archived_at?: string | null;
  attempt_count: number;
  next_attempt_at: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
  processing_method: "legacy_ocr" | "vision" | "bank_import";
  review: ReviewSummary | null;
  has_extracted_text: boolean;
  local_ocr_state: string | null;
  local_ocr_job_id?: string | null;
  local_ocr_error_code?: string | null;
}

export type ReviewSummary = {
  revision_id: string;
  revision: number;
  input_method: "text" | "image";
  status: "pending" | "processing" | "ready" | "incomplete" | "error";
  error_code: string | null;
  warnings: (
    "unreadable" | "missing_required_fields" | "unsupported_document"
  )[];
  job_state: string | null;
  job_id?: string | null;
};

export type DocumentReview = {
  id: string;
  document_id: string;
  revision: number;
  status: "pending" | "processing" | "ready" | "incomplete" | "error";
  error_code: string | null;
  document_type:
    | "invoice"
    | "receipt"
    | "statement"
    | "loan_schedule"
    | "other"
    | "unsupported"
    | "multiple";
  fields: {
    supplier_name: string | null;
    supplier_tax_id: string | null;
    number: string | null;
    issue_date: string | null;
    sale_date: string | null;
    due_date: string | null;
    description: string | null;
    payee_iban: string | null;
    total: string | null;
    currency: "PLN" | "EUR" | "USD" | null;
  };
  provenance: Record<string, string>;
  parser_version: string | null;
  input_method: "text" | "image";
  warnings: (
    "unreadable" | "missing_required_fields" | "unsupported_document"
  )[];
};
export type DocumentUploadCapabilities = {
  max_file_bytes: number;
  accepted_mime_types: string[];
  automatic_image_vision: boolean;
  vision_provider_label: string | null;
  vision_notice: string | null;
};
const mutationHeaders = () => ({ "Idempotency-Key": crypto.randomUUID() });

export const documentQueryKey = (
  id: string | null,
  kind: string,
  actor: ProcessingActor,
) => ["documents", id, kind, actor.ownerId, actor.generation] as const;
function useDocumentActor(): ProcessingActor {
  const ownerId = useAuthStore((s) => s.user?.id ?? null);
  const generation = useDocumentProcessingStore((s) => s.generation);
  return { ownerId, generation };
}

export interface DocumentText {
  id: string;
  document_id: string;
  extracted_text: string;
  ocr_engine: string | null;
  extracted_at: string | null;
  created_at: string;
}

export interface DocumentUploadResponse {
  document: DocumentData;
  is_duplicate: boolean;
}

export function useDocuments(params?: { status?: string; archived?: boolean }) {
  const actor = useDocumentActor();
  return useQuery({
    queryKey: ["documents", "list", actor.ownerId, actor.generation, params],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<DocumentData[]>("/documents", {
        params,
        signal,
      });
      return data;
    },
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (docs?.some((document) => isDocumentWorkActive(document))) {
        return 3000;
      }
      return false;
    },
  });
}

export function useDocumentMetadata(id: string) {
  const actor = useDocumentActor();
  return useQuery({
    queryKey: documentQueryKey(id, "metadata", actor),
    enabled: !!id,
    queryFn: async ({ signal }) =>
      (await api.get<DocumentData>(`/documents/${id}`, { signal })).data,
  });
}

export function isDocumentWorkActive(document: DocumentData): boolean {
  return getDocumentOperations(document).some(isActiveOperation);
}

export function useDocumentText(id: string, enabled = true) {
  const actor = useDocumentActor();
  return useQuery({
    queryKey: documentQueryKey(id, "text", actor),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<DocumentText>(`/documents/${id}/text`, {
        signal,
      });
      return data;
    },
    enabled: !!id && enabled,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    onMutate: () => captureProcessingActor(),
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await api.post<DocumentUploadResponse>(
        "/documents/upload",
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
      return data;
    },
    onSuccess: (result, _file, actor) => {
      if (!isProcessingActorCurrent(actor)) return;
      const document = result.document;
      if (!result.is_duplicate && document.user_id === actor.ownerId) {
        const operation =
          getDocumentOperations(document).find(isActiveOperation);
        if (operation)
          useDocumentProcessingStore.getState().register(actor, {
            key: operation.id,
            operationId: operation.id.startsWith("upload:")
              ? undefined
              : operation.id,
            documentId: document.id,
            source: operation.source,
            kind: operation.kind,
          });
      }
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDocumentUploadCapabilities() {
  return useQuery({
    queryKey: ["documents", "upload-capabilities"],
    queryFn: async () =>
      (
        await api.get<DocumentUploadCapabilities>(
          "/documents/upload-capabilities",
        )
      ).data,
    staleTime: 60_000,
  });
}

export function useDocumentReview(id: string | null) {
  const actor = useDocumentActor();
  return useQuery({
    queryKey: documentQueryKey(id, "review", actor),
    enabled: !!id,
    retry: false,
    queryFn: async ({ signal }) =>
      (await api.get<DocumentReview>(`/documents/${id}/review`, { signal }))
        .data,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "processing" ? 3000 : false;
    },
  });
}

export function usePrepareDocumentReview() {
  const queryClient = useQueryClient();
  return useMutation({
    onMutate: () => captureProcessingActor(),
    mutationFn: async ({
      documentId,
      refresh,
    }: {
      documentId: string;
      refresh: boolean;
    }) =>
      (
        await api.post<DocumentReview>(
          `/documents/${documentId}/review/prepare`,
          undefined,
          { params: { refresh }, headers: mutationHeaders() },
        )
      ).data,
    onSuccess: (review, variables, actor) => {
      if (!isProcessingActorCurrent(actor)) return;
      if (
        variables.refresh ||
        review.status === "pending" ||
        review.status === "processing"
      ) {
        useDocumentProcessingStore.getState().register(actor, {
          key: `review:${review.id}`,
          operationId: `review:${review.id}`,
          documentId: review.document_id,
          kind: "ai",
          source: "review",
        });
      }
      queryClient.setQueryData(
        documentQueryKey(review.document_id, "review", actor),
        review,
      );
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function usePrepareDocumentVision() {
  const queryClient = useQueryClient();
  return useMutation({
    onMutate: () => captureProcessingActor(),
    mutationFn: async ({
      documentId,
      intentKey,
    }: {
      documentId: string;
      intentKey: string;
    }) =>
      (
        await api.post<DocumentReview>(
          `/documents/${documentId}/vision/prepare`,
          undefined,
          {
            headers: { "Idempotency-Key": intentKey },
          },
        )
      ).data,
    onSuccess: (review, _variables, actor) => {
      if (!isProcessingActorCurrent(actor)) return;
      useDocumentProcessingStore.getState().register(actor, {
        key: `review:${review.id}`,
        operationId: `review:${review.id}`,
        documentId: review.document_id,
        kind: "ai",
        source: "review",
      });
      queryClient.setQueryData(
        documentQueryKey(review.document_id, "review", actor),
        review,
      );
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useRetryDocumentOcr() {
  const queryClient = useQueryClient();
  return useMutation({
    onMutate: () => captureProcessingActor(),
    mutationFn: async ({
      documentId,
      intentKey,
    }: {
      documentId: string;
      intentKey: string;
    }) =>
      (
        await api.post<{ id: string; status: string; job_id?: string }>(
          `/documents/${documentId}/retry-ocr`,
          undefined,
          {
            headers: { "Idempotency-Key": intentKey },
          },
        )
      ).data,
    onSuccess: (result, { documentId, intentKey }, actor) => {
      if (!isProcessingActorCurrent(actor)) return;
      useDocumentProcessingStore.getState().register(actor, {
        key: result.job_id
          ? `ocr:${result.job_id}`
          : `legacy:${documentId}:${intentKey}`,
        operationId: result.job_id
          ? `ocr:${result.job_id}`
          : `legacy:${documentId}`,
        documentId,
        source: result.job_id ? "local_ocr" : "legacy_ocr",
        kind: "ocr",
      });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({
        queryKey: ["documents", documentId, "review"],
      });
    },
  });
}

export function useDocumentPreview(id: string | null) {
  const actor = useDocumentActor();
  return useQuery({
    queryKey: documentQueryKey(id, "preview", actor),
    enabled: !!id,
    queryFn: async ({ signal }) =>
      (
        await api.get<Blob>(`/documents/${id}/preview`, {
          responseType: "blob",
          signal,
        })
      ).data,
  });
}

export function useDocumentOriginal(id: string | null) {
  const actor = useDocumentActor();
  return useQuery({
    queryKey: documentQueryKey(id, "original", actor),
    enabled: !!id,
    queryFn: async ({ signal }) =>
      (
        await api.get<Blob>(`/documents/${id}/original`, {
          responseType: "blob",
          signal,
        })
      ).data,
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/documents/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

function useDocumentArchiveMutation(archived: boolean) {
  const client = useQueryClient();
  return useMutation({
    onMutate: () => captureProcessingActor(),
    mutationFn: async ({ documentId }: { documentId: string }) =>
      (
        await api.post<DocumentData>(
          `/documents/${documentId}/${archived ? "archive" : "restore"}`,
        )
      ).data,
    onSuccess: async (document, _variables, actor) => {
      if (
        !isProcessingActorCurrent(actor) ||
        document.user_id !== actor.ownerId
      )
        return;
      const tracker = useDocumentProcessingStore.getState();
      if (archived) tracker.clearDocumentFeedback(actor, document.id);
      else tracker.restoreDocumentFeedback(actor, document.id);
      await client.cancelQueries({ queryKey: ["documents"] });
      if (!isProcessingActorCurrent(actor)) return;
      client.setQueryData(
        documentQueryKey(document.id, "metadata", actor),
        document,
      );
      await client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
export function useArchiveDocument() {
  return useDocumentArchiveMutation(true);
}
export function useRestoreDocument() {
  return useDocumentArchiveMutation(false);
}

export function documentArchiveError(error: unknown): string {
  const response = (
    error as {
      response?: { status?: number; data?: { code?: string; detail?: string } };
    }
  )?.response;
  const code = response?.data?.code ?? response?.data?.detail;
  if (code === "document_processing_active")
    return "Dokument jest przetwarzany. Poczekaj na zakończenie odczytu AI/OCR.";
  if (code === "document_archived")
    return "Dokument jest w archiwum. Przywróć go przed nowym odczytem.";
  if (response?.status === 404)
    return "Dokument nie jest już dostępny. Odśwież listę.";
  return "Nie udało się zmienić archiwizacji dokumentu. Sprawdź połączenie i spróbuj ponownie.";
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const STATUS_LABELS: Record<string, string> = {
  pending: "Oczekuje",
  processing: "Przetwarzanie",
  done: "Gotowe",
  error: "Błąd",
};

export const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-800 text-gray-200",
  processing: "bg-yellow-900 text-yellow-100",
  done: "bg-green-900 text-green-100",
  error: "bg-red-900 text-red-100",
};
