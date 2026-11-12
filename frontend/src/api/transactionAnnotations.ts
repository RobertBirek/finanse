import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";

export interface TransactionAnnotations {
  display_description: string | null;
  original_description: string;
  note: string | null;
  tags: { id: string; name: string }[];
  project_id: string | null;
  project_name: string | null;
  version: number;
  context_snapshot: string;
  limits: {
    display_description: number;
    note: number;
    tag_name: number;
    tags: number;
  };
}

export interface TransactionAnnotationsInput {
  display_description: string | null;
  note: string | null;
  tags: string[];
  project_id: string | null;
  expected_version: number;
  expected_context_snapshot: string;
}

export function useTransactionAnnotations(id: string | null) {
  const session = useAuthStore((state) => state.sessionVersion);
  const user = useAuthStore((state) => state.user);
  return useQuery({
    queryKey: ["finance", "annotations", session, id],
    enabled: !!id && !!user,
    queryFn: async ({ signal }) =>
      (
        await api.get<TransactionAnnotations>(
          `/finance/transactions/${id}/annotations`,
          { signal },
        )
      ).data,
  });
}

export function useAnnotationTags(q: string) {
  const session = useAuthStore((state) => state.sessionVersion);
  const user = useAuthStore((state) => state.user);
  return useQuery({
    queryKey: ["finance", "annotation-tags", session, q],
    enabled: !!user,
    queryFn: async ({ signal }) =>
      (
        await api.get<{ id: string; name: string }[]>("/finance/tags", {
          params: { q },
          signal,
        })
      ).data,
  });
}

export function useUpdateTransactionAnnotations() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    onMutate: () => ({ session: useAuthStore.getState().sessionVersion }),
    mutationFn: async ({
      id,
      key,
      ...body
    }: TransactionAnnotationsInput & { id: string; key: string }) =>
      (
        await api.put<TransactionAnnotations>(
          `/finance/transactions/${id}/annotations`,
          body,
          { headers: { "Idempotency-Key": key } },
        )
      ).data,
    onSuccess: (_result, _input, context) => {
      if (context?.session !== useAuthStore.getState().sessionVersion) return;
      // A replay may return an older receipt. Refetch instead of installing it.
      for (const key of [
        "transactions",
        "accounts",
        "annotations",
        "annotation-tags",
      ])
        client.invalidateQueries({ queryKey: ["finance", key] });
    },
  });
}
