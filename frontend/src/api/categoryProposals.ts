import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { invalidateFinanceLedger } from "./finance";
import type { CategorizationContext, CategoryPart } from "./categorization";

const ROOT = "/finance/categorization";
export interface SuggestionSettingsData {
  version: number;
  enabled: boolean;
  effective_enabled: boolean;
  available: boolean;
  blocked_reason: string | null;
  server_epoch: number;
  configuration_fingerprint: string | null;
  daily_call_limit: number;
  max_description_chars: number;
  max_categories: number;
  review_page_size: number;
  privacy_text: string;
}
export interface SuggestionUsage {
  usage_date: string;
  limit: number;
  held: number;
  dispatched: number;
  known: number;
  unknown: number;
  released: number;
  remaining_slots: number;
  known_input_tokens: number | null;
  known_output_tokens: number | null;
  cost_status: "unpriced";
}
export interface ProposalDetail {
  id: string;
  version: number;
  status: string;
  transaction_id: string | null;
  description: string;
  amount_minor: number | null;
  currency: "PLN";
  decision: string;
  explanation: string;
  confidence: string;
  new_category: {
    name: string;
    parent_path: string | null;
    explanation: string;
  } | null;
  current_parts: CategoryPart[];
  target_path: string | null;
  eligible: boolean;
  blocked_reason: string | null;
  expires_at: string;
}
export interface ProposalPage {
  items: ProposalDetail[];
  next_cursor: string | null;
  page_size: number;
}
export interface ProposalPreview {
  proposal_id: string;
  expected_version: number;
  source_version: number;
  context_snapshot: string;
  preview_snapshot: string;
  amount_minor: number;
  currency: "PLN";
  before_parts: CategoryPart[];
  after_parts: CategoryPart[];
  target_path: string;
  explanation: string;
  confidence: string;
  expires_at: string;
}
export interface ProposalDecision {
  proposal_id: string;
  version: number;
  status: "approved" | "rejected";
  context?: CategorizationContext | null;
}
export interface SuggestionActivity {
  active_jobs: SuggestionJob[];
  recent_outcomes: SuggestionJob[];
  poll_after_ms: number;
}
export interface SuggestionJob {
  id: string;
  transaction_id: string;
  state: string;
  result_kind: string | null;
  reason_code: string | null;
  updated_at: string;
}
export interface SuggestionSettingsInput {
  session: number;
  key: string;
  expected_version: number;
  enabled: boolean;
  expected_server_epoch?: number;
  expected_configuration_fingerprint?: string | null;
  confirm_future_only?: true;
  confirm_data_export?: true;
}
export interface ProposalApplyInput {
  session: number;
  id: string;
  key: string;
  expected_version: number;
  preview_snapshot: string;
  confirmed: true;
}

function assertSession(session: number) {
  if (session !== useAuthStore.getState().sessionVersion)
    throw new Error("session_changed");
}
export function invalidateProposals(client: QueryClient) {
  client.invalidateQueries({ queryKey: ["finance", "proposals"] });
  client.invalidateQueries({ queryKey: ["finance", "suggestions"] });
}
export function useSuggestionSettings() {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "suggestions", session, "settings"],
    retry: false,
    queryFn: async ({ signal }) =>
      (
        await api.get<SuggestionSettingsData>(`${ROOT}/suggestions/settings`, {
          signal,
        })
      ).data,
  });
}
export function useChangeSuggestionSettings() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (input: SuggestionSettingsInput) => {
      const { session, key, ...body } = input;
      assertSession(session);
      return (
        await api.patch<SuggestionSettingsData>(
          `${ROOT}/suggestions/settings`,
          body,
          { headers: { "Idempotency-Key": key } },
        )
      ).data;
    },
    onSuccess: (_data, input) => {
      if (input.session === useAuthStore.getState().sessionVersion)
        invalidateProposals(client);
    },
  });
}
export function useSuggestionUsage(
  day = new Date().toISOString().slice(0, 10),
) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "suggestions", session, "usage", day],
    retry: false,
    queryFn: async ({ signal }) =>
      (
        await api.get<SuggestionUsage>(`${ROOT}/suggestions/usage`, {
          signal,
          params: { date: day },
        })
      ).data,
  });
}
export function useCategoryProposals(
  cursor: string | null = null,
  state = "pending",
) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "proposals", session, state, cursor],
    retry: false,
    queryFn: async ({ signal }) =>
      (
        await api.get<ProposalPage>(`${ROOT}/proposals`, {
          signal,
          params: { state, cursor: cursor ?? undefined },
        })
      ).data,
  });
}
export function useProposalDetail(id: string) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "proposals", session, "detail", id],
    retry: false,
    queryFn: async ({ signal }) =>
      (await api.get<ProposalDetail>(`${ROOT}/proposals/${id}`, { signal }))
        .data,
  });
}
export function usePreviewProposal() {
  return useMutation({
    retry: false,
    mutationFn: async (input: {
      session: number;
      id: string;
      version: number;
    }) => {
      assertSession(input.session);
      return (
        await api.post<ProposalPreview>(
          `${ROOT}/proposals/${input.id}/preview`,
          { expected_version: input.version },
        )
      ).data;
    },
  });
}
export function useApplyProposal() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationKey: ["finance", "proposals", "apply"],
    mutationFn: async (input: ProposalApplyInput) => {
      const { session, id, key, ...body } = input;
      assertSession(session);
      return (
        await api.post<ProposalDecision>(
          `${ROOT}/proposals/${id}/apply`,
          body,
          { headers: { "Idempotency-Key": key } },
        )
      ).data;
    },
    onSettled: (_data, _error, input) => {
      if (input.session === useAuthStore.getState().sessionVersion) {
        invalidateFinanceLedger(client);
        invalidateProposals(client);
      }
    },
  });
}
export function useRejectProposal() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (input: {
      session: number;
      id: string;
      key: string;
      expected_version: number;
    }) => {
      const { session, id, key, ...body } = input;
      assertSession(session);
      return (
        await api.post<ProposalDecision>(
          `${ROOT}/proposals/${id}/reject`,
          body,
          { headers: { "Idempotency-Key": key } },
        )
      ).data;
    },
    onSettled: (_data, _error, input) => {
      if (input.session === useAuthStore.getState().sessionVersion)
        invalidateProposals(client);
    },
  });
}
export function useSuggestionActivity() {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: ["finance", "suggestion-activity", session],
    retry: false,
    queryFn: async ({ signal }) => {
      const { data } = await api.get<SuggestionActivity>(
        `${ROOT}/suggestions/activity`,
        { signal },
      );
      if (
        !Array.isArray(data.active_jobs) ||
        !Array.isArray(data.recent_outcomes)
      )
        throw new Error("invalid_suggestion_activity");
      return { ...data, session };
    },
    refetchInterval: (q) =>
      q.state.data?.active_jobs.length ? q.state.data.poll_after_ms : false,
  });
}
