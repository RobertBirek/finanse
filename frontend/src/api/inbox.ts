import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface InboxItem {
  id: string;
  content: string;
  is_processed: boolean;
  agent_suggestion: string | null;
  classified_type: string | null;
  classified_id: string | null;
  created_at: string;
}

export function useInboxItems(params?: { processed?: boolean }) {
  return useQuery({
    queryKey: ["inbox", "items", params],
    queryFn: async () => {
      const { data } = await api.get<InboxItem[]>("/inbox/items", { params });
      return data;
    },
  });
}

export function useCreateInboxItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (item: { content: string }) => {
      const { data } = await api.post<InboxItem>("/inbox/items", item);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inbox", "items"] });
    },
  });
}

export function useClassifyInboxItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      type,
    }: {
      id: string;
      type: "task" | "project" | "transaction" | "reference";
    }) => {
      const { data } = await api.post<InboxItem>(`/inbox/items/${id}/classify`, {
        classified_type: type,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inbox", "items"] });
    },
  });
}
