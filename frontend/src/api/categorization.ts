import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { invalidateFinanceLedger } from "./finance";

export interface CategoryPart {
  category_id: string;
  amount_minor: number;
}
export interface AssignmentOrigin {
  origin: "manual" | "approved_rule" | "approved_llm";
  version: number;
  rule_id?: string | null;
  rule_version?: number | null;
  display_description?: string | null;
  target_path?: string | null;
  proposal_item_id?: string | null;
}
export interface CategorizationContext {
  transaction_id: string;
  eligibility: {
    allowed: boolean;
    reason_code: string | null;
    message: string | null;
  };
  amount_minor: number | null;
  currency: string | null;
  parts: CategoryPart[];
  version: number;
  source: "manual" | null;
  context_snapshot: string;
  max_parts: number;
  assignment_origin?: AssignmentOrigin | null;
}
export interface CategoryPreview {
  expected_version: number;
  preview_snapshot: string;
  before_parts: CategoryPart[];
  after_parts: CategoryPart[];
  target_paths: Record<string, string>;
}
export function useCategorization(id: string) {
  const session = useAuthStore((state) => state.sessionVersion);
  return useQuery({
    queryKey: ["finance", "categorization", session, id],
    queryFn: async ({ signal }) =>
      (
        await api.get<CategorizationContext>(
          `/finance/transactions/${id}/categorization`,
          { signal },
        )
      ).data,
  });
}
export function usePreviewCategorization(id?: string) {
  return useMutation({
    mutationKey: ["finance", "categorization", id, "preview"],
    mutationFn: async (input: {
      id: string;
      expected_version: number;
      expected_context_snapshot: string;
      parts: CategoryPart[];
    }) => {
      const { id, ...data } = input;
      return (
        await api.post<CategoryPreview>(
          `/finance/transactions/${id}/categorization/preview`,
          data,
        )
      ).data;
    },
  });
}
export function useApplyCategorization(id?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["finance", "categorization", id, "apply"],
    onMutate: () => ({ session: useAuthStore.getState().sessionVersion }),
    mutationFn: async (input: {
      id: string;
      key: string;
      expected_version: number;
      expected_preview_snapshot: string;
      parts: CategoryPart[];
      confirmed: true;
    }) => {
      const { id, key, ...data } = input;
      return (
        await api.post<CategorizationContext>(
          `/finance/transactions/${id}/categorization/apply`,
          data,
          { headers: { "Idempotency-Key": key } },
        )
      ).data;
    },
    onSuccess: (_data, _variables, context) => {
      if (context?.session === useAuthStore.getState().sessionVersion) {
        invalidateFinanceLedger(queryClient);
        queryClient.invalidateQueries({
          queryKey: ["finance", "categorization"],
        });
        queryClient.invalidateQueries({ queryKey: ["finance", "bills"] });
        queryClient.invalidateQueries({ queryKey: ["finance", "proposals"] });
      }
    },
  });
}
