import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";

export interface RuleSettings {
  version: number;
  uncategorized_category_id: string | null;
  rules_enabled: boolean;
  max_description_chars: number;
}
export interface CategorizationRule {
  id: string;
  version: number;
  state: "draft" | "active" | "paused" | "retired";
  display_description: string;
  normalized_description_exact: string;
  target_category_id: string;
  approved_version: number | null;
}
export interface RulePreview {
  preview_snapshot: string;
  grant: {
    display_description: string;
    normalized_description_exact: string;
    target_path: string;
    marker_id: string;
    scope: string;
  };
}
export function useCategorizationSettings() {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "rule-settings", session],
    queryFn: async ({ signal }) =>
      (
        await api.get<RuleSettings>("/finance/categorization/settings", {
          signal,
        })
      ).data,
  });
}
export function useCategorizationRules() {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "rules", session],
    queryFn: async ({ signal }) =>
      (
        await api.get<CategorizationRule[]>("/finance/categorization/rules", {
          signal,
        })
      ).data,
  });
}
export function useRuleCommand() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      session: number;
      method: "post" | "patch";
      path: string;
      body: object;
      key: string;
    }) => {
      if (input.session !== useAuthStore.getState().sessionVersion)
        throw new Error("session_changed");
      return (
        await api[input.method](
          "/finance/categorization" + input.path,
          input.body,
          { headers: { "Idempotency-Key": input.key } },
        )
      ).data;
    },
    onSuccess: (_data, _variables) => {
      if (_variables.session !== useAuthStore.getState().sessionVersion) return;
      client.invalidateQueries({ queryKey: ["finance", "rules"] });
      client.invalidateQueries({ queryKey: ["finance", "rule-settings"] });
    },
  });
}
export function useRulePreview() {
  return useMutation({
    mutationFn: async (input: {
      session: number;
      id: string;
      version: number;
    }) => {
      if (input.session !== useAuthStore.getState().sessionVersion)
        throw new Error("session_changed");
      return (
        await api.post<RulePreview>(
          `/finance/categorization/rules/${input.id}/preview`,
          { expected_version: input.version },
        )
      ).data;
    },
  });
}
export function useRuleEvents() {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "rule-events", session],
    retry: false,
    queryFn: async ({ signal }) => {
      const { data } = await api.get<{
        events: {
          id: string;
          transaction_id: string;
          status: string;
          reason_code: string | null;
        }[];
        poll_after_ms: number;
      }>("/finance/categorization/events", {
        signal,
        params: { status: "active" },
      });
      if (!Array.isArray(data.events)) throw new Error("invalid_rule_events");
      return { ...data, session };
    },
    refetchInterval: (query) =>
      query.state.data?.events.length ? query.state.data.poll_after_ms : false,
  });
}
