import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export const aiSettingsPath = "/advisor/settings";
export const aiSettingsKey = ["advisor", "settings"] as const;

export interface AISettingsView {
  provider: "openai";
  model: string | null;
  server_model: string | null;
  active_model: string | null;
  credential_source: "custom" | "server" | "missing";
  custom_key_available: boolean;
  server_models: string[];
  instructions: string | null;
}

export interface PromptVersion {
  id: string;
  instructions: string | null;
  created_at: string;
}

export interface AIUsage {
  kind: "chat" | "test";
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

export function useAISettings() {
  return useQuery({
    queryKey: aiSettingsKey,
    queryFn: async () => (await api.get<AISettingsView>(aiSettingsPath)).data,
  });
}

export function useAIPrompts() {
  return useQuery({
    queryKey: [...aiSettingsKey, "prompts"],
    queryFn: async () =>
      (await api.get<PromptVersion[]>(`${aiSettingsPath}/prompts`)).data,
  });
}

export function useAIUsage(days: UsageDays) {
  return useQuery({
    queryKey: [...aiSettingsKey, "usage", days],
    queryFn: async () =>
      (
        await api.get<AIUsage[]>(`${aiSettingsPath}/usage`, {
          params: { days },
        })
      ).data,
  });
}

type SettingChange =
  | { kind: "model"; value: string | null }
  | { kind: "prompt"; value: string | null }
  | { kind: "removeCredential" };

export function useAISettingChange() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (change: SettingChange) => {
      if (change.kind === "model") {
        await api.put(`${aiSettingsPath}/model`, { model: change.value });
      } else if (change.kind === "prompt") {
        await api.post(`${aiSettingsPath}/prompts`, {
          instructions: change.value,
        });
      } else {
        await api.delete(`${aiSettingsPath}/credential`);
      }
    },
    onSuccess: async () =>
      client.invalidateQueries({ queryKey: aiSettingsKey }),
  });
}

export function useProbeAI() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (await api.post<ProbeResult>(`${aiSettingsPath}/test`)).data,
    onSuccess: async () =>
      client.invalidateQueries({ queryKey: [...aiSettingsKey, "usage"] }),
  });
}
