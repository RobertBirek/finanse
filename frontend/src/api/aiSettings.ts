import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export const aiSettingsPath = "/advisor/settings";
export const aiSettingsKey = ["advisor", "settings"] as const;
export type AIPurpose =
  "advisor" | "document_text" | "vision" | "receipt" | "categorization";

export function purposeParams(purpose: AIPurpose) {
  return { params: { purpose } };
}

export interface AISettingsView {
  provider: "openai";
  model: string | null;
  server_model: string | null;
  active_model: string | null;
  credential_source: "custom" | "server" | "missing";
  custom_key_available: boolean;
  server_models: string[];
  instructions: string | null;
  operational?: boolean;
}

export interface PromptVersion {
  id: string;
  instructions: string | null;
  created_at: string;
}

export interface AIUsage {
  kind: "chat" | "test" | "operation";
  model: string;
  requests: number;
  errors: number;
  average_duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  reports_with_tokens: number;
}

export type UsageDays = 7 | 30 | 90;

export interface ProbeResult {
  model: string;
  status: string;
  duration_ms: number;
}

export type BenchmarkVariant = { model: string; instructions: string | null };
export type BenchmarkResult = {
  suite_version: string;
  variants: {
    model: string;
    status: "ok" | "partial" | "failed";
    cases: {
      case_id: string;
      status: string;
      matches_expected: boolean | null;
      duration_ms: number;
      input_tokens: number | null;
      output_tokens: number | null;
    }[];
  }[];
};

export function useAIBenchmark() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (variants: [BenchmarkVariant, BenchmarkVariant]) =>
      (
        await api.post<BenchmarkResult>(`${aiSettingsPath}/benchmark`, {
          variants,
        })
      ).data,
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: [...aiSettingsKey, "advisor", "usage"],
      });
    },
  });
}

export function useAISettings(purpose: AIPurpose = "advisor") {
  return useQuery({
    queryKey: [...aiSettingsKey, purpose],
    queryFn: async () =>
      (await api.get<AISettingsView>(aiSettingsPath, purposeParams(purpose)))
        .data,
  });
}

export function useAIPrompts(purpose: AIPurpose) {
  return useQuery({
    queryKey: [...aiSettingsKey, purpose, "prompts"],
    queryFn: async () =>
      (
        await api.get<PromptVersion[]>(
          `${aiSettingsPath}/prompts`,
          purposeParams(purpose),
        )
      ).data,
  });
}

export function useAIUsage(days: UsageDays, purpose: AIPurpose) {
  return useQuery({
    queryKey: [...aiSettingsKey, purpose, "usage", days],
    queryFn: async () =>
      (
        await api.get<AIUsage[]>(`${aiSettingsPath}/usage`, {
          params: { days, purpose },
        })
      ).data,
  });
}

type SettingChange =
  | { kind: "model"; value: string | null }
  | { kind: "prompt"; value: string | null }
  | { kind: "removeCredential" };

export function useAISettingChange(purpose: AIPurpose) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (change: SettingChange) => {
      if (change.kind === "model") {
        await api.put(
          `${aiSettingsPath}/model`,
          { model: change.value },
          purposeParams(purpose),
        );
      } else if (change.kind === "prompt") {
        await api.post(
          `${aiSettingsPath}/prompts`,
          {
            instructions: change.value,
          },
          purposeParams(purpose),
        );
      } else {
        await api.delete(
          `${aiSettingsPath}/credential`,
          purposeParams(purpose),
        );
      }
    },
    onSuccess: async () =>
      client.invalidateQueries({ queryKey: [...aiSettingsKey, purpose] }),
  });
}

export function useProbeAI(purpose: AIPurpose) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (
        await api.post<ProbeResult>(
          `${aiSettingsPath}/test`,
          undefined,
          purposeParams(purpose),
        )
      ).data,
    onSuccess: async () =>
      client.invalidateQueries({
        queryKey: [...aiSettingsKey, purpose, "usage"],
      }),
  });
}
