import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

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
}

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
};
export type DocumentUploadCapabilities = {
  max_file_bytes: number;
  accepted_mime_types: string[];
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
      if (
        docs?.some((d) => d.status === "processing" || d.status === "pending")
      ) {
        return 3000;
      }
      return false;
    },
  });
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
    onSuccess: () => {
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
  });
}

export function usePrepareDocumentReview() {
  const queryClient = useQueryClient();
  return useMutation({
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
    onSuccess: (review) =>
      queryClient.setQueryData(
        ["documents", review.document_id, "review"],
        review,
      ),
  });
}

export function useRetryDocumentOcr() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ documentId }: { documentId: string }) =>
      (
        await api.post(`/documents/${documentId}/retry-ocr`, undefined, {
          headers: mutationHeaders(),
        })
      ).data,
    onSuccess: (_result, { documentId }) => {
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
