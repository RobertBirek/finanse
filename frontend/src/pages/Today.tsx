import { useState } from "react";
import { useAuthStore } from "../stores/authStore";
import { useTasks, useCreateTask, useUpdateTask, useTimeBlocks } from "../api/work";
import { useFinancialSummary } from "../api/finance";

const todayStr = new Date().toISOString().split("T")[0];
const tomorrowStr = new Date(Date.now() + 86400000).toISOString().split("T")[0];

export function Today() {
  const user = useAuthStore((s) => s.user);
  // Fetch all active tasks: todo + in_progress
  const { data: tasks } = useTasks({ status: "todo,in_progress" });
  const { data: timeBlocks } = useTimeBlocks({
    start_time: todayStr,
    end_time: tomorrowStr,
  });
  const { data: summary } = useFinancialSummary();
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();

  const [newTitle, setNewTitle] = useState("");

  const handleQuickAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    createTask.mutate(
      { title: newTitle.trim() },
      { onSuccess: () => setNewTitle("") }
    );
  };

  const activeTasks = tasks?.filter((t) => t.status !== "done" && t.status !== "cancelled") || [];
  const todayBlocks = timeBlocks || [];

  const greet = () => {
    const h = new Date().getHours();
    if (h < 10) return "Dzień dobry";
    if (h < 18) return "Witaj";
    return "Dobry wieczór";
  };

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-white mb-6">
        {greet()}, {user?.display_name || "!"}
      </h1>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="card">
          <p className="text-sm text-gray-400">Aktywne zadania</p>
          <p className="text-2xl font-bold text-white mt-1">
            {activeTasks.length}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Bloki czasowe</p>
          <p className="text-2xl font-bold text-white mt-1">
            {todayBlocks.length}
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-400">Bilans ({summary?.month}.{summary?.year})</p>
          <p className={`text-2xl font-bold mt-1 ${(summary?.net_total_pln ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
            {(summary?.net_total_pln ?? 0) / 100} PLN
          </p>
        </div>
      </div>

      {/* Quick add */}
      <div className="card mb-6">
        <form onSubmit={handleQuickAdd} className="flex gap-3">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Dodaj szybkie zadanie..."
            className="input flex-1"
          />
          <button type="submit" disabled={createTask.isPending || !newTitle.trim()} className="btn-primary">
            Dodaj
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Tasks */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Zadania</h2>
          {activeTasks.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500">Brak zadań</p>
              <p className="text-gray-600 text-sm mt-1">
                Dodaj zadanie powyżej lub przez Inbox
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {activeTasks.map((task) => (
                <div
                  key={task.id}
                  className="flex items-center gap-3 p-3 rounded-lg bg-gray-800/50 hover:bg-gray-800 group"
                >
                  <button
                    onClick={() =>
                      updateTask.mutate({ id: task.id, status: "done" })
                    }
                    className="w-5 h-5 rounded-full border-2 border-gray-600 hover:border-advisor-500 flex-shrink-0 transition-colors"
                  />
                  <span className="flex-1 text-sm text-gray-200">{task.title}</span>
                  {task.source === "inbox" && (
                    <span className="text-xs px-2 py-0.5 rounded bg-advisor-900/50 text-advisor-400">
                      Inbox
                    </span>
                  )}
                  {task.priority === "high" || task.priority === "urgent" ? (
                    <span className="text-xs px-2 py-0.5 rounded bg-red-900/50 text-red-400">
                      {task.priority === "urgent" ? "Pilne" : "Ważne"}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Time blocks */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Dzisiejszy plan</h2>
          {todayBlocks.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500">Brak zaplanowanych bloków</p>
              <p className="text-gray-600 text-sm mt-1">
                Zaplanuj bloki w kalendarzu
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {todayBlocks.map((block) => (
                <div
                  key={block.id}
                  className="p-3 rounded-lg bg-gray-800/50 flex items-center gap-3"
                >
                  <div className="w-1 h-10 bg-advisor-500 rounded-full flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-white">{block.title}</p>
                    <p className="text-xs text-gray-400">
                      {block.start_time?.slice(11, 16)} – {block.end_time?.slice(11, 16)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
