import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import {
  captureProcessingActor,
  isProcessingActorCurrent,
  useDocumentProcessingStore,
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
  attempt_count: number;
  next_attempt_at: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
  processing_method: "legacy_ocr" | "vision";
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

export function useDocuments(params?: { status?: string }) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: async () => {
      const { data } = await api.get<DocumentData[]>("/documents", { params });
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

export function isDocumentWorkActive(document: DocumentData): boolean {
  return getDocumentOperations(document).some(isActiveOperation);
}

export function useDocumentText(id: string, enabled = true) {
  return useQuery({
    queryKey: ["documents", id, "text"],
    queryFn: async () => {
      const { data } = await api.get<DocumentText>(`/documents/${id}/text`);
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
  return useQuery({
    queryKey: ["documents", id, "review"],
    enabled: !!id,
    retry: false,
    queryFn: async () =>
      (await api.get<DocumentReview>(`/documents/${id}/review`)).data,
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
        useDocumentProcessingStore
          .getState()
          .register(actor, {
            key: `review:${review.id}`,
            operationId: `review:${review.id}`,
            documentId: review.document_id,
            kind: "ai",
            source: "review",
          });
      }
      queryClient.setQueryData(
        ["documents", review.document_id, "review"],
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
      useDocumentProcessingStore
        .getState()
        .register(actor, {
          key: `review:${review.id}`,
          operationId: `review:${review.id}`,
          documentId: review.document_id,
          kind: "ai",
          source: "review",
        });
      queryClient.setQueryData(
        ["documents", review.document_id, "review"],
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
  return useQuery({
    queryKey: ["documents", id, "preview"],
    enabled: !!id,
    queryFn: async () =>
      (
        await api.get<Blob>(`/documents/${id}/preview`, {
          responseType: "blob",
        })
      ).data,
  });
}

export function useDocumentOriginal(id: string | null) {
  return useQuery({
    queryKey: ["documents", id, "original"],
    enabled: !!id,
    queryFn: async () =>
      (
        await api.get<Blob>(`/documents/${id}/original`, {
          responseType: "blob",
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
