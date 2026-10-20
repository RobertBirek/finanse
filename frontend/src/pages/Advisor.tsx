import { useState, useRef, useEffect } from "react";
import { Dialog } from "../components/Dialog";
import { QueryFeedback } from "../components/QueryFeedback";
import { isAxiosError } from "axios";
import {
  useConversations,
  useMessages,
  useSendMessage,
  useConfirmToolExecution,
  useDenyToolExecution,
  type Message,
} from "../api/advisor";

function ToolCallBanner({ message }: { message: Message }) {
  if (!message.tool_executions?.length) return null;
  const labels: Record<string, string> = {
    completed: "Wykonano",
    pending_confirmation: "Wymaga potwierdzenia",
    denied: "Odrzucono",
    failed: "Błąd",
  };
  return (
    <div className="my-2 space-y-2">
      {message.tool_executions.map((execution) => (
        <section
          key={execution.id}
          className="bg-gray-800/50 border border-gray-700 rounded-lg p-3 text-sm"
        >
          <p
            className={
              execution.status === "pending_confirmation"
                ? "text-amber-300"
                : "text-gray-300"
            }
          >
            {labels[execution.status] ?? "Status niedostępny"}
          </p>
          <details className="mt-2">
            <summary className="cursor-pointer text-gray-300">
              Szczegóły działania: {execution.tool_name}
            </summary>
            <pre className="mt-2 text-xs text-gray-300 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
              {JSON.stringify(
                execution.status === "pending_confirmation"
                  ? execution.arguments
                  : execution.result,
                null,
                2,
              )}
            </pre>
          </details>
          {execution.status === "pending_confirmation" && (
            <div className="flex flex-wrap gap-2 mt-3">
              <ToolExecutionActions
                executionId={execution.id}
                conversationId={message.conversation_id}
              />
            </div>
          )}
        </section>
      ))}
    </div>
  );
}

function mutationErrorMessage(error: unknown): string {
  if (isAxiosError(error) && typeof error.response?.data?.detail === "string") {
    return error.response.data.detail;
  }
  return "Nie udało się zmienić statusu narzędzia.";
}

function ToolExecutionActions({
  executionId,
  conversationId,
}: {
  executionId: string;
  conversationId: string;
}) {
  const confirm = useConfirmToolExecution();
  const deny = useDenyToolExecution();
  const isPending = confirm.isPending || deny.isPending;
  const error = confirm.error || deny.error;
  const variables = { executionId, conversationId };

  return (
    <>
      <button
        onClick={() => confirm.mutate(variables)}
        disabled={isPending}
        className="px-3 py-1 bg-green-800 hover:bg-green-900 disabled:opacity-50 text-white text-xs rounded-sm font-medium"
      >
        {confirm.isPending ? "..." : "Zatwierdź"}
      </button>
      <button
        onClick={() => deny.mutate(variables)}
        disabled={isPending}
        className="px-3 py-1 bg-red-600/50 hover:bg-red-500 disabled:opacity-50 text-red-200 text-xs rounded-sm"
      >
        {deny.isPending ? "..." : "Odrzuć"}
      </button>
      {error && (
        <p role="alert" className="basis-full text-xs text-red-300">
          {mutationErrorMessage(error)}
        </p>
      )}
    </>
  );
}

export function Advisor() {
  const [input, setInput] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const conversationsQuery = useConversations();
  const messagesQuery = useMessages(activeId);
  const conversations = conversationsQuery.data;
  const apiMessages = messagesQuery.data;
  const sendMessage = useSendMessage();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({
      behavior: "auto",
      block: "end",
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [apiMessages, sendMessage.isPending]);

  const handleSend = () => {
    if (!input.trim() || sendMessage.isPending) return;
    sendMessage.mutate(
      { conversation_id: activeId, content: input.trim() },
      {
        onSuccess: (data) => {
          setInput("");
          if (!activeId) {
            setActiveId(data.conversation_id);
          }
        },
      },
    );
  };

  const handleNewConversation = () => {
    setActiveId(null);
    setHistoryOpen(false);
  };

  const messages = apiMessages || [];

  const history = (
    <>
      <div className="p-4 border-b border-gray-800">
        <button
          type="button"
          disabled={sendMessage.isPending}
          onClick={handleNewConversation}
          className="btn-primary w-full text-sm"
        >
          Nowa rozmowa
        </button>
      </div>
      <QueryFeedback
        loading={conversationsQuery.isLoading}
        error={conversationsQuery.isError}
        errorMessage="Nie udało się pobrać rozmów."
        onRetry={conversationsQuery.refetch}
      >
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations?.map((conv) => (
            <button
              type="button"
              key={conv.id}
              disabled={sendMessage.isPending}
              onClick={() => {
                setActiveId(conv.id);
                setHistoryOpen(false);
              }}
              aria-pressed={conv.id === activeId}
              className="min-h-11 w-full text-left px-3 py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800 break-words"
            >
              {conv.title}
            </button>
          ))}
          {conversations?.length === 0 && (
            <p className="text-gray-400 text-sm px-3 py-4">Brak rozmów.</p>
          )}
        </div>
      </QueryFeedback>
    </>
  );
  return (
    <div className="flex h-full min-h-0">
      <div className="hidden lg:flex shrink-0 flex-col w-56 bg-gray-900 border-r border-gray-800">
        {history}
      </div>
      {historyOpen && (
        <Dialog label="Rozmowy Doradcy" onClose={() => setHistoryOpen(false)}>
          <button
            type="button"
            className="btn-secondary mb-3"
            onClick={() => setHistoryOpen(false)}
          >
            Zamknij historię
          </button>
          {history}
        </Dialog>
      )}

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header */}
        <div className="flex flex-wrap gap-3 items-center justify-between px-4 py-3 border-b border-gray-800">
          <div>
            <h1 className="text-sm font-medium text-gray-300">
              {activeId
                ? conversations?.find((c) => c.id === activeId)?.title ||
                  "Rozmowa"
                : "Nowa rozmowa"}
            </h1>
            <p className="text-xs text-gray-400">Osobisty asystent AI</p>
          </div>
          <button
            type="button"
            className="btn-secondary lg:hidden"
            onClick={() => setHistoryOpen(true)}
          >
            Rozmowy
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
          <QueryFeedback
            loading={activeId !== null && messagesQuery.isLoading}
            error={messagesQuery.isError}
            errorMessage="Nie udało się pobrać wiadomości."
            onRetry={messagesQuery.refetch}
          >
            {messages.length === 0 && !sendMessage.isPending && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="w-14 h-14 rounded-xl bg-advisor-500 flex items-center justify-center mb-4">
                  <svg
                    className="w-7 h-7 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">
                  Witaj w Personal Advisor
                </h3>
                <p className="text-gray-400 text-sm max-w-md mb-6">
                  Twój osobisty asystent do zarządzania czasem, pieniędzmi i
                  projektami. Zadaj pytanie, a Doradca pomoże Ci podjąć dobrą
                  decyzję.
                </p>
                <div className="grid grid-cols-2 gap-2 max-w-md">
                  {[
                    "Pokaż moje dzisiejsze zadania",
                    "Jak wygląda mój budżet?",
                    "Podsumuj moje projekty",
                    "Co mam dzisiaj w kalendarzu?",
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => setInput(suggestion)}
                      className="text-left px-3 py-2 text-xs rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id}>
                <div
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-xl px-4 py-3 text-sm ${
                      msg.role === "user"
                        ? "bg-advisor-700 text-white"
                        : "bg-gray-800 text-gray-200"
                    }`}
                  >
                    <p className="whitespace-pre-wrap break-words">
                      {msg.content}
                    </p>
                  </div>
                </div>
                {msg.role === "assistant" &&
                  msg.tool_executions &&
                  msg.tool_executions.length > 0 && (
                    <ToolCallBanner message={msg} />
                  )}
              </div>
            ))}

            {sendMessage.isPending && (
              <div className="flex justify-start">
                <div className="bg-gray-800 rounded-xl px-4 py-3">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 rounded-full bg-gray-500 animate-bounce" />
                    <div className="w-2 h-2 rounded-full bg-gray-500 animate-bounce [animation-delay:0.1s]" />
                    <div className="w-2 h-2 rounded-full bg-gray-500 animate-bounce [animation-delay:0.2s]" />
                  </div>
                </div>
              </div>
            )}
          </QueryFeedback>
          {sendMessage.isError && (
            <p role="alert" className="text-sm text-red-300">
              Nie udało się wysłać wiadomości. Treść pozostała w polu — spróbuj
              ponownie.
            </p>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="shrink-0 px-4 py-3 border-t border-gray-800">
          <div className="flex gap-3">
            <label htmlFor="advisor-message" className="sr-only">
              Wiadomość do Doradcy
            </label>
            <input
              id="advisor-message"
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Zadaj pytanie Doradcy..."
              className="input min-w-0 flex-1"
              disabled={sendMessage.isPending}
            />
            <button
              aria-label={
                sendMessage.isPending
                  ? "Wysyłanie wiadomości"
                  : "Wyślij wiadomość"
              }
              onClick={handleSend}
              disabled={!input.trim() || sendMessage.isPending}
              className="btn-primary"
            >
              {sendMessage.isPending ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                  />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
