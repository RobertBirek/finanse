import { useState, useRef, useEffect } from "react";
import {
  useConversations,
  useMessages,
  useSendMessage,
} from "../api/advisor";

export function Advisor() {
  const { data: conversations } = useConversations();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [localMessages, setLocalMessages] = useState<
    { role: "user" | "assistant"; content: string; id: string }[]
  >([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sendMessage = useSendMessage();

  const { data: serverMessages } = useMessages(activeId);

  useEffect(() => {
    if (serverMessages) {
      setLocalMessages(
        serverMessages.map((m) => ({
          role: m.role,
          content: m.content,
          id: m.id,
        }))
      );
    }
  }, [serverMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = {
      role: "user" as const,
      content: input.trim(),
      id: `local-${Date.now()}`,
    };
    setLocalMessages((prev) => [...prev, userMsg]);
    setInput("");

    sendMessage.mutate(
      {
        conversationId: activeId,
        content: input.trim(),
      },
      {
        onSuccess: () => {
          setLocalMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: "Dziękuję za wiadomość. Analizuję dane... (funkcjonalność w przygotowaniu)",
              id: `local-${Date.now() + 1}`,
            },
          ]);
        },
        onError: () => {
          setLocalMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: "Przepraszam, wystąpił błąd połączenia z Doradcą.",
              id: `local-${Date.now() + 1}`,
            },
          ]);
        },
      }
    );
  };

  return (
    <div className="h-[calc(100vh-7rem)] flex gap-0 -m-6">
      {/* Conversations sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-gray-800 bg-gray-900/50 p-4 overflow-y-auto hidden lg:block">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">
          Rozmowy
        </h2>
        <div className="space-y-1">
          <button
            onClick={() => {
              setActiveId(null);
              setLocalMessages([]);
            }}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
              activeId === null
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50"
            }`}
          >
            + Nowa rozmowa
          </button>
          {conversations?.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setActiveId(conv.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                activeId === conv.id
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/50"
              }`}
            >
              {conv.title || "Rozmowa"}
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0 bg-gray-950">
        {/* Chat header */}
        <div className="px-6 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">
            {activeId
              ? conversations?.find((c) => c.id === activeId)?.title ||
                "Rozmowa"
              : "Doradca"}
          </h2>
          <p className="text-sm text-gray-500">
            Osobisty asystent AI do zarządzania finansami, czasem i projektami
          </p>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {localMessages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-center">
              <div>
                <div className="w-16 h-16 rounded-2xl bg-advisor-500/20 flex items-center justify-center mx-auto mb-4">
                  <svg
                    className="w-8 h-8 text-advisor-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
                    />
                  </svg>
                </div>
                <h3 className="text-white font-semibold mb-2">
                  Witaj w Personal Advisor
                </h3>
                <p className="text-gray-400 text-sm max-w-md">
                  Zapytaj mnie o swoje finanse, zaplanuj zadania, poproś o analizę
                  projektów lub poproś o radę dotyczącą zarządzania czasem.
                </p>
                <div className="grid grid-cols-2 gap-2 mt-6 max-w-sm mx-auto">
                  {[
                    "Pokaż moje dzisiejsze zadania",
                    "Jak wygląda mój budżet?",
                    "Podsumuj moje projekty",
                    "Co mam dzisiaj w kalendarzu?",
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => {
                        setInput(suggestion);
                      }}
                      className="text-xs p-2 rounded-lg bg-gray-800/50 text-gray-400 hover:text-gray-200 hover:bg-gray-800 text-left transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            localMessages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-advisor-500 text-white"
                      : "bg-gray-800 text-gray-100"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form
          onSubmit={handleSend}
          className="p-4 border-t border-gray-800 flex gap-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Napisz wiadomość..."
            className="input flex-1"
          />
          <button
            type="submit"
            disabled={sendMessage.isPending || !input.trim()}
            className="btn-primary px-5"
          >
            {sendMessage.isPending ? (
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
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
        </form>
      </div>
    </div>
  );
}
