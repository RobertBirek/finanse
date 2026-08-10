import { useParams } from "react-router-dom";
import { useProject, useTasks, useUpdateTask } from "../api/work";
import { useTransactions } from "../api/finance";

const statusLabels: Record<string, string> = {
  todo: "Do zrobienia",
  in_progress: "W trakcie",
  done: "Gotowe",
  blocked: "Zablokowane",
};
const priorityColors: Record<string, string> = {
  low: "text-gray-400",
  medium: "text-yellow-400",
  high: "text-orange-400",
  urgent: "text-red-400",
};

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: project, isLoading } = useProject(id || null);
  const { data: tasks } = useTasks({ project_id: id });
  const { data: transactions } = useTransactions({ limit: 10 });
  const updateTask = useUpdateTask();

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="w-6 h-6 border-2 border-advisor-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400">Projekt nie został znaleziony</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white mb-2">{project.name}</h1>
        {project.description && (
          <p className="text-gray-400">{project.description}</p>
        )}
        <div className="flex gap-4 mt-3">
          <span className="text-sm text-gray-500">
            Status:{" "}
            <span className="text-gray-300">
              {statusLabels[project.status] || project.status}
            </span>
          </span>
          {project.deadline && (
            <span className="text-sm text-gray-500">
              Termin:{" "}
              <span className="text-gray-300">
                {new Date(project.deadline).toLocaleDateString("pl-PL")}
              </span>
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tasks column */}
        <div className="lg:col-span-2">
          <h2 className="text-lg font-semibold text-white mb-4">Zadania</h2>
          <div className="space-y-2">
            {tasks?.length === 0 ? (
              <p className="text-gray-500 text-sm">Brak zadań w projekcie</p>
            ) : (
              tasks?.map((task) => (
                <div
                  key={task.id}
                  className="card flex items-start gap-3 group"
                >
                  <select
                    value={task.status}
                    onChange={(e) =>
                      updateTask.mutate({ id: task.id, status: e.target.value })
                    }
                    className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-advisor-500"
                  >
                    <option value="todo">Do zrobienia</option>
                    <option value="in_progress">W trakcie</option>
                    <option value="done">Gotowe</option>
                    <option value="blocked">Zablokowane</option>
                  </select>
                  <div className="flex-1">
                    <p
                      className={`text-sm ${
                        task.status === "done"
                          ? "text-gray-500 line-through"
                          : "text-gray-200"
                      }`}
                    >
                      {task.title}
                    </p>
                    {task.due_date && (
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(task.due_date).toLocaleDateString("pl-PL")}
                      </p>
                    )}
                  </div>
                  <span className={`text-xs ${priorityColors[task.priority] || "text-gray-400"}`}>
                    {task.priority.toUpperCase()}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Info column */}
        <div className="space-y-6">
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">
              Postęp
            </h3>
            {(() => {
              const done = tasks?.filter((t) => t.status === "done").length || 0;
              const total = tasks?.length || 0;
              const pct = total > 0 ? Math.round((done / total) * 100) : 0;
              return (
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-white font-bold">{pct}%</span>
                    <span className="text-sm text-gray-500">{done}/{total}</span>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-2">
                    <div
                      className="bg-advisor-500 h-2 rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })()}
          </div>

          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">
              Powiązane transakcje
            </h3>
            {transactions && transactions.length > 0 ? (
              <div className="space-y-2">
                {transactions
                  .filter((tx) => tx.project_id === id)
                  .slice(0, 5)
                  .map((tx) => (
                    <div key={tx.id} className="text-sm">
                      <p className="text-gray-300">{tx.description}</p>
                      <p className="text-xs text-gray-500">
                        {new Date(tx.transaction_date).toLocaleDateString("pl-PL")} — {tx.type}
                      </p>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">Brak</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
