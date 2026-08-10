import { useState, useRef, useEffect } from "react";
import {
  useConversations,
  useMessages,
  useSendMessage,
} from "../api/advisor";

export function Advisor() {
  const [input, setInput] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: conversations } = useConversations();
  const { data: apiMessages } = useMessages(activeId);
  const sendMessage = useSendMessage();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
      }
    );
  };

  const handleNewConversation = () => {
    setActiveId(null);
  };

  const messages = apiMessages || [];

  return (
    <div className="flex h-[calc(100vh-64px)] -m-6">
      {/* Sidebar */}
      <div className="hidden lg:flex flex-col w-64 bg-gray-900 border-r border-gray-800">
        <div className="p-4 border-b border-gray-800">
          <button
            onClick={handleNewConversation}
            className="btn-primary w-full text-sm"
          >
            + Nowa rozmowa
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations?.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setActiveId(conv.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors truncate ${
                conv.id === activeId
                  ? "bg-advisor-500/20 text-advisor-400"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
              }`}
            >
              {conv.title}
            </button>
          ))}
          {conversations?.length === 0 && (
            <p className="text-gray-600 text-sm px-3 py-4 text-center">
              Brak rozmów
            </p>
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-800">
          <h2 className="text-sm font-medium text-gray-300">
            {activeId
              ? conversations?.find((c) => c.id === activeId)?.title || "Rozmowa"
              : "Nowa rozmowa"}
          </h2>
          <p className="text-xs text-gray-500">
            Osobisty asystent AI
          </p>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 && !sendMessage.isPending && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-14 h-14 rounded-xl bg-advisor-500 flex items-center justify-center mb-4">
                <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">Witaj w Personal Advisor</h3>
              <p className="text-gray-400 text-sm max-w-md mb-6">
                Twój osobisty asystent do zarządzania czasem, pieniędzmi i projektami.
                Zadaj pytanie, a Doradca pomoże Ci podjąć dobrą decyzję.
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
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-xl px-4 py-3 text-sm ${
                  msg.role === "user"
                    ? "bg-advisor-500 text-white"
                    : "bg-gray-800 text-gray-200"
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
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

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-6 py-4 border-t border-gray-800">
          <div className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Zadaj pytanie Doradcy..."
              className="input flex-1"
              disabled={sendMessage.isPending}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || sendMessage.isPending}
              className="btn-primary"
            >
              {sendMessage.isPending ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
