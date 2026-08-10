import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export function useConversations() {
  return useQuery({
    queryKey: ["advisor", "conversations"],
    queryFn: async () => {
      const { data } = await api.get<Conversation[]>("/advisor/conversations");
      return data;
    },
  });
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["advisor", "messages", conversationId],
    queryFn: async () => {
      const { data } = await api.get<Message[]>(
        `/advisor/conversations/${conversationId}/messages`
      );
      return data;
    },
    enabled: !!conversationId,
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      conversation_id,
      content,
    }: {
      conversation_id: string | null;
      content: string;
    }) => {
      const { data } = await api.post<Message>("/advisor/messages", {
        conversation_id,
        content,
      });
      return data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["advisor", "messages", data.conversation_id] });
      queryClient.invalidateQueries({ queryKey: ["advisor", "conversations"] });
    },
  });
}
