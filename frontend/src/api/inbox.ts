import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface InboxItem {
  id: string;
  user_id: string;
  content: string;
  source_type: string;
  target_type: string | null;
  target_id: string | null;
  is_processed: boolean;
  classified_by: string | null;
  agent_suggestion: { suggested_type?: string; confidence?: string } | null;
  created_at: string;
  updated_at: string;
}

export interface ProcessResponse {
  inbox_item: InboxItem;
  created_task: TaskBrief | null;
}

export type ProcessTargetType =
  "task" | "project" | "transaction" | "document" | "decision" | "reference";

export interface TaskBrief {
  id: string;
  title: string;
  status: string;
  priority: string;
}

export function useInboxItems(params?: { processed?: boolean }) {
  return useQuery({
    queryKey: ["inbox", "items", params],
    queryFn: async () => {
      const { data } = await api.get<InboxItem[]>("/inbox/items", {
        params: { is_processed: params?.processed },
      });
      return data;
    },
  });
}

export function useCreateInboxItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (item: { content: string; source_type?: string }) => {
      const { data } = await api.post<InboxItem>("/inbox/items", item);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inbox", "items"] });
    },
  });
}

export function useProcessInboxItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      target_type,
    }: {
      id: string;
      target_type: ProcessTargetType;
    }) => {
      const { data } = await api.post<ProcessResponse>(
        `/inbox/items/${id}/process`,
        {
          target_type,
        },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inbox", "items"] });
      queryClient.invalidateQueries({ queryKey: ["work", "tasks"] });
    },
  });
}
