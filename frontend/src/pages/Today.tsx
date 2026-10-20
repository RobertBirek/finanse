import { useState } from "react";
import { useAuthStore } from "../stores/authStore";
import {
  useTasks,
  useCreateTask,
  useUpdateTask,
  useTimeBlocks,
} from "../api/work";
import { useFinancialSummary } from "../api/finance";
import { QueryFeedback } from "../components/QueryFeedback";
import { formatPLN } from "../lib/format";
import { formatLocalTime, localDayRange, useLocalNow } from "../lib/date";

export function Today() {
  const user = useAuthStore((s) => s.user);
  const now = useLocalNow();
  const range = localDayRange(now);
  const tasks = useTasks({ status: "todo,in_progress" });
  const blocks = useTimeBlocks(range);
  const summary = useFinancialSummary({
    month: now.getMonth() + 1,
    year: now.getFullYear(),
  });
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const [newTitle, setNewTitle] = useState("");
  const activeTasks =
    tasks.data?.filter(
      (t) => t.status !== "done" && t.status !== "cancelled",
    ) ?? [];
  const todayBlocks = (blocks.data ?? []).filter(
    (b) =>
      new Date(b.end_time) > new Date(range.start_time) &&
      new Date(b.start_time) <= new Date(range.end_time),
  );
  const greet =
    now.getHours() < 10
      ? "Dzień dobry"
      : now.getHours() < 18
        ? "Witaj"
        : "Dobry wieczór";

  function handleQuickAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!newTitle.trim()) return;
    createTask.mutate(
      { title: newTitle.trim() },
      { onSuccess: () => setNewTitle("") },
    );
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-white mb-6">
        {greet}
        {user?.display_name ? `, ${user.display_name}` : ""}
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="card">
          <p className="text-sm text-gray-400">Aktywne zadania</p>
          <p className="text-2xl font-bold text-white mt-1">
            {tasks.isLoading || tasks.isError ? "—" : activeTasks.length}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Bloki czasowe</p>
          <p className="text-2xl font-bold text-white mt-1">
            {blocks.isLoading || blocks.isError ? "—" : todayBlocks.length}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">
            Wynik miesiąca ({now.getMonth() + 1}.{now.getFullYear()})
          </p>
          <QueryFeedback
            loading={summary.isLoading}
            error={summary.isError}
            errorMessage="Nie udało się pobrać wyniku miesiąca."
            onRetry={summary.refetch}
          >
            {summary.data ? (
              <p
                className={`text-2xl font-bold mt-1 ${summary.data.net_total_pln >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatPLN(summary.data.net_total_pln)} PLN
              </p>
            ) : (
              <p className="text-gray-400">Brak podsumowania.</p>
            )}
          </QueryFeedback>
        </div>
      </div>
      <div className="card mb-6">
        <form onSubmit={handleQuickAdd} className="flex flex-wrap gap-3">
          <label htmlFor="quick-task-title" className="sr-only">
            Tytuł szybkiego zadania
          </label>
          <input
            id="quick-task-title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Dodaj szybkie zadanie…"
            className="input min-w-0 flex-1"
            maxLength={500}
          />
          <button
            type="submit"
            disabled={createTask.isPending || !newTitle.trim()}
            className="btn-primary"
          >
            {createTask.isPending ? "Dodawanie…" : "Dodaj"}
          </button>
        </form>
        {createTask.isError && (
          <p role="alert" className="mt-3 text-sm text-red-300">
            Nie udało się dodać zadania. Treść pozostała w polu — spróbuj
            ponownie.
          </p>
        )}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Zadania</h2>
          <QueryFeedback
            loading={tasks.isLoading}
            error={tasks.isError}
            errorMessage="Nie udało się pobrać zadań."
            onRetry={tasks.refetch}
          >
            {activeTasks.length === 0 ? (
              <p className="py-8 text-gray-400">
                Brak aktywnych zadań. Dodaj zadanie powyżej lub przez Inbox.
              </p>
            ) : (
              <ul className="space-y-2">
                {activeTasks.map((task) => (
                  <li
                    key={task.id}
                    className="flex items-center gap-3 p-3 rounded-lg bg-gray-800/50"
                  >
                    <button
                      type="button"
                      aria-label={`Ukończ zadanie: ${task.title}`}
                      disabled={updateTask.isPending}
                      onClick={() =>
                        updateTask.mutate({ id: task.id, status: "done" })
                      }
                      className="min-h-11 min-w-11 flex items-center justify-center rounded-lg hover:bg-gray-700"
                    >
                      <span
                        aria-hidden="true"
                        className="w-5 h-5 rounded-full border-2 border-gray-400"
                      />
                    </button>
                    <span className="flex-1 min-w-0 break-words text-sm text-gray-200">
                      {task.title}
                    </span>
                    {(task.priority === "high" ||
                      task.priority === "urgent") && (
                      <span className="text-xs px-2 py-0.5 rounded-sm bg-red-900/50 text-red-300">
                        {task.priority === "urgent" ? "Pilne" : "Ważne"}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </QueryFeedback>
          {updateTask.isError && (
            <p role="alert" className="mt-3 text-sm text-red-300">
              Nie udało się ukończyć zadania. Spróbuj ponownie.
            </p>
          )}
        </section>
        <section className="card">
          <h2 className="text-lg font-semibold text-white mb-4">
            Dzisiejszy plan
          </h2>
          <QueryFeedback
            loading={blocks.isLoading}
            error={blocks.isError}
            errorMessage="Nie udało się pobrać planu dnia."
            onRetry={blocks.refetch}
          >
            {todayBlocks.length === 0 ? (
              <p className="py-8 text-gray-400">Brak zaplanowanych bloków.</p>
            ) : (
              <ul className="space-y-2">
                {todayBlocks.map((block) => (
                  <li
                    key={block.id}
                    className="p-3 rounded-lg bg-gray-800/50 flex items-center gap-3"
                  >
                    <div
                      aria-hidden="true"
                      className="w-1 h-10 bg-advisor-500 rounded-full shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white break-words">
                        {block.title}
                      </p>
                      <p className="text-xs text-gray-400">
                        {formatLocalTime(block.start_time)} –{" "}
                        {formatLocalTime(block.end_time)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </QueryFeedback>
        </section>
      </div>
    </div>
  );
}
