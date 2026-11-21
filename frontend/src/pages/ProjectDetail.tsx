import { Link, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { useProject, useTasks, useUpdateTask } from "../api/work";
import { useTransactions } from "../api/finance";
import { PageHeader } from "../components/PageHeader";
import { QueryFeedback } from "../components/QueryFeedback";

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
  const query = useProject(id || null);
  const taskQuery = useTasks({ project_id: id });
  const transactionsQuery = useTransactions({ limit: 10 });
  const updateTask = useUpdateTask();
  const project = query.data;
  const tasks = taskQuery.data;
  const transactions = (transactionsQuery.data ?? []).filter(
    (tx) => tx.project_id === id,
  );
  const notFound =
    isAxiosError(query.error) && query.error.response?.status === 404;
  const back = (
    <Link className="underline" to="/projects">
      Wszystkie projekty
    </Link>
  );

  if (query.isLoading || query.isError || !project) {
    return (
      <div className="page-workspace">
        <PageHeader title="Szczegóły projektu" context={back} />
        <section className="card">
          <QueryFeedback
            loading={query.isLoading}
            error={query.isError && !notFound}
            errorMessage="Nie udało się pobrać projektu."
            onRetry={query.refetch}
          >
            <p>
              Nie znaleziono projektu. Wróć do listy i wybierz inny projekt.
            </p>
          </QueryFeedback>
        </section>
      </div>
    );
  }

  return (
    <div className="page-workspace">
      <PageHeader
        title={project.name}
        description={project.description}
        context={back}
      />
      <div className="mb-6 flex flex-wrap gap-4">
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
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tasks column */}
        <div className="lg:col-span-2">
          <h2 className="text-lg font-semibold text-white mb-4">Zadania</h2>
          <QueryFeedback
            loading={taskQuery.isLoading}
            error={taskQuery.isError}
            errorMessage="Nie udało się pobrać zadań projektu."
            onRetry={taskQuery.refetch}
          >
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
                      aria-label={`Status zadania: ${task.title}`}
                      disabled={updateTask.isPending}
                      value={task.status}
                      onChange={(e) =>
                        updateTask.mutate({
                          id: task.id,
                          status: e.target.value,
                        })
                      }
                      className="bg-gray-800 border border-gray-700 rounded-sm px-2 py-1 text-xs text-gray-300 focus:outline-hidden focus:border-advisor-500"
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
                    <span
                      className={`text-xs ${priorityColors[task.priority] || "text-gray-400"}`}
                    >
                      {task.priority.toUpperCase()}
                    </span>
                  </div>
                ))
              )}
            </div>
          </QueryFeedback>
          {updateTask.isError && (
            <p role="alert" className="mt-3 text-sm text-red-400">
              Nie udało się zmienić statusu zadania. Spróbuj ponownie.
            </p>
          )}
        </div>

        {/* Info column */}
        <div className="space-y-6">
          <div className="card">
            <h3 className="text-sm font-medium text-gray-400 mb-3">Postęp</h3>
            {(() => {
              if (!tasks)
                return (
                  <p className="text-sm text-gray-400">
                    Postęp pojawi się po pobraniu zadań.
                  </p>
                );
              const done = tasks.filter((t) => t.status === "done").length;
              const total = tasks?.length || 0;
              const pct = total > 0 ? Math.round((done / total) * 100) : 0;
              return (
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-white font-bold">{pct}%</span>
                    <span className="text-sm text-gray-500">
                      {done}/{total}
                    </span>
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
            <QueryFeedback
              loading={transactionsQuery.isLoading}
              error={transactionsQuery.isError}
              errorMessage="Nie udało się pobrać transakcji."
              onRetry={transactionsQuery.refetch}
            >
              {transactions.length > 0 ? (
                <div className="space-y-2">
                  {transactions.slice(0, 5).map((tx) => (
                    <div key={tx.id} className="text-sm">
                      <p className="text-gray-300">{tx.description}</p>
                      <p className="text-xs text-gray-500">
                        {new Date(tx.transaction_date).toLocaleDateString(
                          "pl-PL",
                        )}{" "}
                        — {tx.type}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  Brak powiązań wśród ostatnich transakcji.
                </p>
              )}
            </QueryFeedback>
          </div>
        </div>
      </div>
    </div>
  );
}
