import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface Conversation {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ToolExecution {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  status: string;
}

export interface DenyToolExecutionResult {
  status: "denied";
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: Array<{
    id: string;
    type: string;
    function: { name: string; arguments: string };
  }> | null;
  tool_executions?: ToolExecution[] | null;
  created_at: string;
}

export function hasPendingConfirmation(
  messages: Message[] | undefined,
): boolean {
  return (
    messages?.some((message) =>
      message.tool_executions?.some(
        (execution) => execution.status === "pending_confirmation",
      ),
    ) ?? false
  );
}

export function getMessagesRefetchInterval(
  messages: Message[] | undefined,
): 2000 | false {
  return hasPendingConfirmation(messages) ? 2000 : false;
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
  return useQuery<Message[]>({
    queryKey: ["advisor", "messages", conversationId],
    queryFn: async () => {
      const { data } = await api.get<Message[]>(
        `/advisor/conversations/${conversationId}/messages`,
      );
      return data;
    },
    enabled: !!conversationId,
    refetchInterval: (query) => getMessagesRefetchInterval(query.state.data),
    refetchIntervalInBackground: false,
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
      queryClient.invalidateQueries({
        queryKey: ["advisor", "messages", data.conversation_id],
      });
      queryClient.invalidateQueries({ queryKey: ["advisor", "conversations"] });
    },
  });
}

export interface ToolExecutionMutationVariables {
  executionId: string;
  conversationId: string;
}

function invalidateAdvisorConversation(
  queryClient: ReturnType<typeof useQueryClient>,
  conversationId: string,
) {
  queryClient.invalidateQueries({
    queryKey: ["advisor", "messages", conversationId],
    exact: true,
  });
  queryClient.invalidateQueries({
    queryKey: ["advisor", "conversations"],
    exact: true,
  });
}

export function useConfirmToolExecution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ executionId }: ToolExecutionMutationVariables) => {
      const { data } = await api.post<Message>(
        `/advisor/tool-executions/${executionId}/confirm`,
      );
      return data;
    },
    onSuccess: (_data, { conversationId }) => {
      invalidateAdvisorConversation(queryClient, conversationId);
    },
  });
}

export function useDenyToolExecution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ executionId }: ToolExecutionMutationVariables) => {
      const { data } = await api.post<DenyToolExecutionResult>(
        `/advisor/tool-executions/${executionId}/deny`,
      );
      return data;
    },
    onSuccess: (_data, { conversationId }) => {
      invalidateAdvisorConversation(queryClient, conversationId);
    },
  });
}
