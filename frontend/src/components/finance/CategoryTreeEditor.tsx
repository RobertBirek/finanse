import { useState, type ReactNode } from "react";
import {
  useDeleteCategory,
  useUpdateCategory,
  type Category,
} from "../../api/finance";
import { categoryPath, eligibleCategoryParents } from "../../lib/categories";
import { apiErrorDetail, isConflict } from "./accountSettings";

const DELETE_CONFLICT_MESSAGE =
  "Kategoria ma zapisy — zdezaktywuj ją zamiast usuwać";

const TYPE_LABEL: Record<Category["type"], string> = {
  income: "Przychód",
  expense: "Wydatek",
  transfer: "Transfer",
};

export function CategoryTreeEditor({
  categories,
  onAddChild,
}: {
  categories: Category[];
  onAddChild: (parentId: string) => void;
}) {
  const update = useUpdateCategory();
  const remove = useDeleteCategory();
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(categories.map((category) => category.id)),
  );
  const [editing, setEditing] = useState<string | null>(null);
  const [parentId, setParentId] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<Category["type"]>("expense");
  const byId = new Map(categories.map((category) => [category.id, category]));
  const childrenByParent = new Map<string, Category[]>();
  for (const category of categories) {
    if (!category.parent_id) continue;
    const children = childrenByParent.get(category.parent_id) ?? [];
    children.push(category);
    childrenByParent.set(category.parent_id, children);
  }

  function startEditing(category: Category) {
    setEditing(category.id);
    setParentId(category.parent_id ?? "");
    setName(category.name);
    setType(category.type);
  }

  function isPending(categoryId: string) {
    return (
      (update.isPending && update.variables?.id === categoryId) ||
      (remove.isPending && remove.variables === categoryId)
    );
  }

  function errorFor(categoryId: string) {
    if (update.variables?.id === categoryId)
      return apiErrorDetail(update.error);
    if (remove.variables === categoryId) {
      return isConflict(remove.error)
        ? DELETE_CONFLICT_MESSAGE
        : apiErrorDetail(remove.error);
    }
    return null;
  }

  const node = (
    category: Category,
    depth: number,
    ancestry: ReadonlySet<string>,
  ): ReactNode => {
    const children = (childrenByParent.get(category.id) ?? []).filter(
      (child) => !ancestry.has(child.id),
    );
    const open = expanded.has(category.id);
    const pending = isPending(category.id);
    const rowError = errorFor(category.id);
    const parentOptions = eligibleCategoryParents(
      category.id,
      categories,
    ).filter((candidate) => candidate.type === type);

    return (
      <li key={category.id} className="min-w-0">
        <div
          className="flex min-w-0 flex-col gap-2 border-b border-gray-800 py-2 sm:flex-row sm:items-center"
          style={{ paddingInlineStart: `${depth * 18}px` }}
        >
          <div className="flex min-w-0 flex-1 items-center gap-2">
            {children.length ? (
              <button
                type="button"
                className="min-h-11 min-w-11 text-gray-400"
                aria-expanded={open}
                aria-label={`${open ? "Zwiń" : "Rozwiń"} ${category.name}`}
                onClick={() =>
                  setExpanded((old) => {
                    const next = new Set(old);
                    if (open) next.delete(category.id);
                    else next.add(category.id);
                    return next;
                  })
                }
              >
                {open ? "⌄" : "›"}
              </button>
            ) : (
              <span className="inline-block w-11" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm font-medium text-white [overflow-wrap:anywhere]">
                {category.name}
              </p>
              <p className="text-xs text-gray-500">
                {TYPE_LABEL[category.type]}
                {!category.is_active ? " · archiwalna" : ""}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 sm:shrink-0">
            <button
              type="button"
              aria-label={`Dodaj podkategorię do ${category.name}`}
              className="btn-secondary px-2 py-1 text-xs"
              disabled={pending}
              onClick={() => onAddChild(category.id)}
            >
              Dodaj podkategorię
            </button>
            <button
              type="button"
              aria-label={`Edytuj kategorię ${category.name}`}
              className="btn-secondary px-2 py-1 text-xs"
              disabled={pending}
              onClick={() => startEditing(category)}
            >
              Edytuj
            </button>
            <button
              type="button"
              aria-label={`${category.is_active ? "Dezaktywuj" : "Aktywuj"} kategorię ${category.name}`}
              className="btn-secondary px-2 py-1 text-xs"
              disabled={pending}
              onClick={() =>
                update.mutate({
                  id: category.id,
                  is_active: !category.is_active,
                })
              }
            >
              {category.is_active ? "Archiwizuj" : "Przywróć"}
            </button>
            <button
              type="button"
              aria-label={`Usuń kategorię ${category.name}`}
              className="btn-danger px-2 py-1 text-xs"
              disabled={pending}
              onClick={() => {
                if (window.confirm(`Usunąć kategorię "${category.name}"?`)) {
                  remove.mutate(category.id);
                }
              }}
            >
              Usuń
            </button>
          </div>
        </div>
        {editing === category.id ? (
          <div className="grid gap-3 border-b border-gray-800 bg-gray-800/30 p-3 sm:grid-cols-3">
            <label className="text-sm text-gray-300">
              Nazwa
              <input
                className="input mt-1"
                value={name}
                disabled={pending}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="text-sm text-gray-300">
              Typ
              <select
                className="input mt-1"
                value={type}
                disabled={pending}
                onChange={(event) =>
                  setType(event.target.value as Category["type"])
                }
              >
                {Object.entries(TYPE_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-gray-300">
              Kategoria nadrzędna
              <select
                className="input mt-1"
                value={parentId}
                disabled={pending}
                onChange={(event) => setParentId(event.target.value)}
              >
                <option value="">Brak rodzica</option>
                {parentOptions.map((item) => (
                  <option key={item.id} value={item.id}>
                    {categoryPath(item.id, categories)}
                    {item.is_active ? "" : " (archiwalna)"}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2 sm:col-span-3">
              <button
                type="button"
                aria-label={`Zapisz kategorię ${category.name}`}
                className="btn-primary"
                disabled={pending || !name.trim()}
                onClick={() =>
                  update.mutate(
                    {
                      id: category.id,
                      name: name.trim(),
                      type,
                      parent_id: parentId || null,
                    },
                    { onSuccess: () => setEditing(null) },
                  )
                }
              >
                {pending ? "Zapisywanie…" : "Zapisz"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={pending}
                onClick={() => setEditing(null)}
              >
                Anuluj
              </button>
            </div>
          </div>
        ) : null}
        {rowError ? (
          <p className="py-2 text-xs text-red-400">{rowError}</p>
        ) : null}
        {open && children.length ? (
          <ul className="min-w-0" aria-label={`Podkategorie: ${category.name}`}>
            {children.map((child) =>
              node(child, depth + 1, new Set([...ancestry, category.id])),
            )}
          </ul>
        ) : null}
      </li>
    );
  };

  const roots = categories.filter(
    (category) => !category.parent_id || !byId.has(category.parent_id),
  );
  const reachable = new Set<string>();
  const markReachable = (categoryId: string, ancestry = new Set<string>()) => {
    if (ancestry.has(categoryId) || reachable.has(categoryId)) return;
    reachable.add(categoryId);
    const nextAncestry = new Set([...ancestry, categoryId]);
    for (const child of childrenByParent.get(categoryId) ?? []) {
      markReachable(child.id, nextAncestry);
    }
  };
  roots.forEach((root) => markReachable(root.id));
  const extraRoots: Category[] = [];
  for (const category of categories) {
    if (!reachable.has(category.id)) {
      extraRoots.push(category);
      markReachable(category.id);
    }
  }

  return (
    <div>
      <p className="mb-3 text-xs text-gray-500">
        Zmiana rodzica zmieni grupowanie również wcześniejszych raportów. Nie
        zmieni kwot ani transakcji.
      </p>
      <div className="mb-2 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary px-2 py-1 text-xs"
          onClick={() =>
            setExpanded(new Set(categories.map((category) => category.id)))
          }
        >
          Rozwiń wszystko
        </button>
        <button
          type="button"
          className="btn-secondary px-2 py-1 text-xs"
          onClick={() => setExpanded(new Set())}
        >
          Zwiń wszystko
        </button>
      </div>
      <ul aria-label="Drzewo kategorii" className="min-w-0">
        {roots.map((category) => node(category, 0, new Set()))}
        {extraRoots.map((category) => node(category, 0, new Set()))}
      </ul>
    </div>
  );
}
