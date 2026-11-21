import { useState } from "react";
import { Link } from "react-router-dom";
import { QueryFeedback } from "../components/QueryFeedback";
import { PageHeader } from "../components/PageHeader";
import {
  useInboxItems,
  useCreateInboxItem,
  useProcessInboxItem,
  type ProcessTargetType,
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
  const [filter, setFilter] = useState<"unprocessed" | "processed" | "all">(
    "unprocessed",
  );
  const [content, setContent] = useState("");

  const processed =
    filter === "processed"
      ? true
      : filter === "unprocessed"
        ? false
        : undefined;
  const query = useInboxItems(
    processed !== undefined ? { processed } : undefined,
  );
  const items = query.data;
  const createItem = useCreateInboxItem();
  const processItem = useProcessInboxItem();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    createItem.mutate(
      { content: content.trim() },
      { onSuccess: () => setContent("") },
    );
  };

  const handleProcess = (id: string, target_type: ProcessTargetType) => {
    processItem.mutate({ id, target_type });
  };

  return (
    <div className="page-workspace">
      <PageHeader
        title="Inbox"
        description="Zapisz notatkę lub zadanie do późniejszego przejrzenia."
      />

      <div className="workspace-panels">
        <section className="card" aria-label="Nowy wpis">
          <form
            onSubmit={handleSubmit}
            className="workspace-fields flex gap-3 flex-wrap"
          >
            <label htmlFor="inbox-content" className="sr-only">
              Treść wpisu
            </label>
            <input
              id="inbox-content"
              type="text"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Zapisz myśl, zadanie, notatkę... (Enter = zapisz)"
              className="input min-w-0 flex-1"
            />
            <button
              type="submit"
              disabled={createItem.isPending || !content.trim()}
              className="btn-primary"
            >
              {createItem.isPending ? "Zapisywanie…" : "Zapisz"}
            </button>
          </form>

          {createItem.isError && (
            <p role="alert" className="mt-3 text-sm text-red-300">
              Nie udało się zapisać wpisu. Treść pozostała w polu.
            </p>
          )}
        </section>
        <section className="min-w-0" aria-label="Wpisy w Inboxie">
          {/* Filters */}
          <div className="flex flex-wrap gap-2 mb-4">
            {(["unprocessed", "processed", "all"] as const).map((f) => (
              <button
                key={f}
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
                className={`min-h-11 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  filter === f
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {f === "unprocessed"
                  ? "Nieprzetworzone"
                  : f === "processed"
                    ? "Przetworzone"
                    : "Wszystkie"}
              </button>
            ))}
          </div>

          {processItem.isError && (
            <p role="alert" className="mb-4 text-sm text-red-400">
              Nie udało się przetworzyć wpisu. Spróbuj ponownie; sprawdź, czy
              zadanie nie przekracza 500 znaków.
            </p>
          )}

          {/* Items list */}
          <div className="space-y-3">
            <QueryFeedback
              loading={query.isLoading}
              error={query.isError}
              errorMessage="Nie udało się pobrać wpisów."
              onRetry={query.refetch}
            >
              {items?.length === 0 ? (
                <div className="card text-center py-12">
                  <p className="text-gray-300">
                    {filter === "unprocessed"
                      ? "Nie ma wpisów do przejrzenia."
                      : filter === "processed"
                        ? "Brak przetworzonych wpisów."
                        : "Nie ma jeszcze żadnych wpisów."}
                  </p>
                  {filter === "all" ? (
                    <p className="mt-1 text-sm text-gray-400">
                      Dodaj notatkę w formularzu „Nowy wpis”.
                    </p>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary mt-3"
                      onClick={() => setFilter("all")}
                    >
                      Pokaż wszystkie wpisy
                    </button>
                  )}
                </div>
              ) : (
                items?.map((item) => (
                  <div
                    key={item.id}
                    className={`card ${item.is_processed ? "opacity-60" : ""}`}
                  >
                    <p className="text-white text-sm mb-2 [overflow-wrap:anywhere]">
                      {item.content}
                    </p>
                    {item.agent_suggestion?.suggested_type &&
                      !item.is_processed && (
                        <div className="mb-3 p-3 rounded-lg bg-advisor-500/10 border border-advisor-500/20">
                          <p className="text-xs text-advisor-400 font-medium mb-1">
                            Sugestia asystenta
                          </p>
                          <p className="text-sm text-gray-300">
                            {item.agent_suggestion.suggested_type === "task"
                              ? "Proponuję utworzyć zadanie"
                              : item.agent_suggestion.suggested_type ===
                                  "transaction"
                                ? "Wygląda na transakcję"
                                : item.agent_suggestion.suggested_type ===
                                    "project"
                                  ? "Może to być projekt"
                                  : `Sugestia: ${item.agent_suggestion.suggested_type}`}
                          </p>
                        </div>
                      )}
                    <div className="flex flex-wrap gap-3 items-center justify-between">
                      <span className="text-xs text-gray-500">
                        {new Date(item.created_at).toLocaleDateString("pl-PL", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                      {!item.is_processed && (
                        <div className="flex flex-wrap gap-2">
                          {(
                            [
                              "task",
                              "project",
                              "transaction",
                              "reference",
                            ] as const
                          ).map((type) => (
                            <button
                              key={type}
                              onClick={() => handleProcess(item.id, type)}
                              disabled={
                                processItem.isPending ||
                                type === "project" ||
                                type === "transaction"
                              }
                              title={
                                type === "project" || type === "transaction"
                                  ? "Konwersja będzie dostępna w kolejnej wersji"
                                  : undefined
                              }
                              className="px-3 py-1 text-xs rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors disabled:opacity-50"
                            >
                              → {TARGET_LABELS[type]}
                              {type === "project" || type === "transaction"
                                ? " — wkrótce"
                                : ""}
                            </button>
                          ))}
                        </div>
                      )}
                      {item.is_processed && item.target_type && (
                        <span className="text-xs px-2 py-0.5 rounded-sm bg-gray-800 text-gray-400">
                          {TARGET_LABELS[item.target_type] || item.target_type}
                        </span>
                      )}
                      {item.target_type === "document" && item.target_id && (
                        <Link
                          to="/documents"
                          className="text-xs text-advisor-400 hover:underline"
                        >
                          Otwórz dokument
                        </Link>
                      )}
                    </div>
                  </div>
                ))
              )}
            </QueryFeedback>
          </div>
        </section>
      </div>
    </div>
  );
}
