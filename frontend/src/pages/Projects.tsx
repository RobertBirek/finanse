import { useState } from "react";
import { Link } from "react-router-dom";
import { useProjects, useCreateProject } from "../api/work";

const statusLabels: Record<string, string> = {
  active: "Aktywny",
  on_hold: "Wstrzymany",
  completed: "Zakończony",
  archived: "Zarchiwizowany",
};

const statusColors: Record<string, string> = {
  active: "bg-green-900/50 text-green-400 border-green-800",
  on_hold: "bg-yellow-900/50 text-yellow-400 border-yellow-800",
  completed: "bg-blue-900/50 text-blue-400 border-blue-800",
  archived: "bg-gray-700 text-gray-400 border-gray-600",
};

export function Projects() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const params = statusFilter !== "all" ? { status: statusFilter } : undefined;
  const { data: projects, isLoading } = useProjects(params);
  const createProject = useCreateProject();

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    createProject.mutate(
      {
        name: name.trim(),
        description: description.trim() || undefined,
      },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          setShowCreate(false);
        },
      }
    );
  };

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Projekty</h1>
        <button onClick={() => setShowCreate(true)} className="btn-primary">
          + Nowy projekt
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {["all", "active", "on_hold", "completed"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              statusFilter === s
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {s === "all" ? "Wszystkie" : statusLabels[s] || s}
          </button>
        ))}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="card w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold text-white mb-4">Nowy projekt</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Nazwa</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Opis</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="input"
                  rows={3}
                />
              </div>
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="btn-secondary"
                >
                  Anuluj
                </button>
                <button
                  type="submit"
                  disabled={createProject.isPending || !name.trim()}
                  className="btn-primary"
                >
                  {createProject.isPending ? "Tworzenie..." : "Utwórz"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Projects grid */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="w-6 h-6 border-2 border-advisor-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : projects?.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-gray-500">Brak projektów</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {projects?.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="card hover:border-gray-700 transition-colors block"
            >
              <div className="flex items-start justify-between mb-3">
                <h3 className="text-white font-medium">{project.name}</h3>
                <span
                  className={`text-xs px-2 py-0.5 rounded border ${statusColors[project.status]}`}
                >
                  {statusLabels[project.status]}
                </span>
              </div>
              {project.description && (
                <p className="text-sm text-gray-400 line-clamp-2 mb-3">
                  {project.description}
                </p>
              )}
              {project.deadline && (
                <p className="text-xs text-gray-500">
                  Termin: {new Date(project.deadline).toLocaleDateString("pl-PL")}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
