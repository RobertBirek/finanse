import { useState } from "react";
import {
  useInboxItems,
  useCreateInboxItem,
  useProcessInboxItem,
} from "../api/inbox";

const TARGET_LABELS: Record<string, string> = {
  task: "Zadanie",
  project: "Projekt",
  transaction: "Transakcja",
  reference: "Ref.",
  document: "Dokument",
  decision: "Decyzja",
};

export function Inbox() {
  const [filter, setFilter] = useState<"unprocessed" | "processed" | "all">("unprocessed");
  const [content, setContent] = useState("");

  const processed = filter === "processed" ? true : filter === "unprocessed" ? false : undefined;
  const { data: items, isLoading } = useInboxItems(
    processed !== undefined ? { processed } : undefined
  );
  const createItem = useCreateInboxItem();
  const processItem = useProcessInboxItem();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    createItem.mutate(
      { content: content.trim() },
      { onSuccess: () => setContent("") }
    );
  };

  const handleProcess = (id: string, target_type: string) => {
    processItem.mutate({ id, target_type: target_type as any });
  };

  const unprocessed = items?.filter((i) => !i.is_processed) || [];

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-white mb-6">Inbox</h1>

      {/* Capture input */}
      <div className="card mb-6">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            type="text"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Zapisz myśl, zadanie, notatkę... (Enter = zapisz)"
            className="input flex-1"
            autoFocus
          />
          <button
            type="submit"
            disabled={createItem.isPending || !content.trim()}
            className="btn-primary"
          >
            Zapisz
          </button>
        </form>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        {(["unprocessed", "processed", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              filter === f
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {f === "unprocessed" ? "Nieprzetworzone" : f === "processed" ? "Przetworzone" : "Wszystkie"}
          </button>
        ))}
      </div>

      {/* Items list */}
      <div className="space-y-3">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-6 h-6 border-2 border-advisor-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : items?.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-gray-500">Brak elementów</p>
            <p className="text-gray-600 text-sm mt-1">
              Zapisz coś w polu powyżej, aby zacząć
            </p>
          </div>
        ) : (
          items?.map((item) => (
            <div
              key={item.id}
              className={`card ${
                item.is_processed ? "opacity-60" : ""
              }`}
            >
              <p className="text-white text-sm mb-2">{item.content}</p>
              {item.agent_suggestion?.suggested_type && !item.is_processed && (
                <div className="mb-3 p-3 rounded-lg bg-advisor-500/10 border border-advisor-500/20">
                  <p className="text-xs text-advisor-400 font-medium mb-1">
                    Sugestia asystenta
                  </p>
                  <p className="text-sm text-gray-300">
                    {item.agent_suggestion.suggested_type === "task"
                      ? "Proponuję utworzyć zadanie"
                      : item.agent_suggestion.suggested_type === "transaction"
                        ? "Wygląda na transakcję"
                        : item.agent_suggestion.suggested_type === "project"
                          ? "Może to być projekt"
                          : `Sugestia: ${item.agent_suggestion.suggested_type}`}
                  </p>
                </div>
              )}
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  {new Date(item.created_at).toLocaleDateString("pl-PL", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                {!item.is_processed && (
                  <div className="flex gap-2">
                    {(["task", "project", "transaction", "reference"] as const).map(
                      (type) => (
                        <button
                          key={type}
                          onClick={() => handleProcess(item.id, type)}
                          disabled={processItem.isPending}
                          className="px-3 py-1 text-xs rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors disabled:opacity-50"
                        >
                          → {TARGET_LABELS[type]}
                        </button>
                      )
                    )}
                  </div>
                )}
                {item.is_processed && item.target_type && (
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">
                    {TARGET_LABELS[item.target_type] || item.target_type}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
