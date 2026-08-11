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
  storage_path: string;
  created_at: string;
  updated_at: string;
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

export function useDocuments(params?: { status?: string }) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: async () => {
      const { data } = await api.get<DocumentData[]>("/documents", { params });
      return data;
    },
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (docs?.some((d) => d.status === "processing" || d.status === "pending")) {
        return 3000;
      }
      return false;
    },
  });
}

export function useDocumentText(id: string) {
  return useQuery({
    queryKey: ["documents", id, "text"],
    queryFn: async () => {
      const { data } = await api.get<DocumentText>(`/documents/${id}/text`);
      return data;
    },
    enabled: !!id,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await api.post<DocumentUploadResponse>("/documents/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
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
  pending: "bg-gray-600 text-gray-200",
  processing: "bg-yellow-600 text-yellow-100",
  done: "bg-green-600 text-green-100",
  error: "bg-red-600 text-red-100",
};
