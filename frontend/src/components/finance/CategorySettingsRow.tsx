import { useState } from "react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { Category, CategoryUpdateInput } from "../../api/finance";
import { apiErrorDetail, isConflict } from "./accountSettings";

const CATEGORY_DELETE_CONFLICT_MESSAGE =
  "Kategoria ma zapisy — zdezaktywuj ją zamiast usuwać";

const CATEGORY_TYPE_LABEL: Record<Category["type"], string> = {
  income: "Przychód",
  expense: "Wydatek",
  transfer: "Transfer",
};

function collectDescendantIds(
  rootId: string,
  categories: Category[],
): Set<string> {
  const childrenByParent = new Map<string, string[]>();
  for (const category of categories) {
    if (category.parent_id === null) continue;
    const children = childrenByParent.get(category.parent_id) ?? [];
    children.push(category.id);
    childrenByParent.set(category.parent_id, children);
  }

  const descendants = new Set<string>();
  const stack = [rootId];
  while (stack.length > 0) {
    const current = stack.pop()!;
    for (const child of childrenByParent.get(current) ?? []) {
      if (descendants.has(child)) continue;
      descendants.add(child);
      stack.push(child);
    }
  }
  return descendants;
}

type CategoryRowProps = {
  category: Category;
  categories: Category[];
  updateMutation: UseMutationResult<
    Category,
    Error,
    CategoryUpdateInput & { id: string }
  >;
  deleteMutation: UseMutationResult<void, Error, string>;
  editing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
};

export function CategoryRow({
  category,
  categories,
  updateMutation,
  deleteMutation,
  editing,
  onStartEdit,
  onCancelEdit,
}: CategoryRowProps) {
  const [draftName, setDraftName] = useState(category.name);
  const [draftType, setDraftType] = useState<Category["type"]>(category.type);
  const [draftParentId, setDraftParentId] = useState(category.parent_id ?? "");

  const rowPending =
    (updateMutation.isPending &&
      updateMutation.variables?.id === category.id) ||
    (deleteMutation.isPending && deleteMutation.variables === category.id);

  const updateErrorForRow =
    updateMutation.variables?.id === category.id
      ? apiErrorDetail(updateMutation.error)
      : null;
  const deleteErrorForRow =
    deleteMutation.variables === category.id
      ? isConflict(deleteMutation.error)
        ? CATEGORY_DELETE_CONFLICT_MESSAGE
        : apiErrorDetail(deleteMutation.error)
      : null;

  const parentName =
    categories.find((candidate) => candidate.id === category.parent_id)?.name ??
    null;

  const excludedIds = collectDescendantIds(category.id, categories);
  excludedIds.add(category.id);
  const parentOptions = categories.filter(
    (candidate) => !excludedIds.has(candidate.id),
  );

  function startEdit() {
    setDraftName(category.name);
    setDraftType(category.type);
    setDraftParentId(category.parent_id ?? "");
    onStartEdit();
  }

  function save() {
    updateMutation.mutate(
      {
        id: category.id,
        name: draftName,
        type: draftType,
        parent_id: draftParentId || null,
      },
      { onSuccess: onCancelEdit },
    );
  }

  function toggle() {
    updateMutation.mutate({
      id: category.id,
      is_active: !category.is_active,
    });
  }

  function remove() {
    if (window.confirm(`Usunąć kategorię "${category.name}"?`)) {
      deleteMutation.mutate(category.id);
    }
  }

  return (
    <div
      className={`rounded-lg border border-gray-800 bg-gray-800/40 p-3 ${
        category.is_active ? "" : "opacity-60"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-white">
              {category.name}
            </p>
            {!category.is_active ? (
              <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
                nieaktywna
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            {CATEGORY_TYPE_LABEL[category.type]} · {parentName ?? "—"}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {editing ? (
            <>
              <button
                type="button"
                aria-label={`Zapisz kategorię ${category.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={rowPending}
                onClick={save}
              >
                Zapisz
              </button>
              <button
                type="button"
                aria-label={`Anuluj edycję kategorii ${category.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                onClick={onCancelEdit}
              >
                Anuluj
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                aria-label={`Edytuj kategorię ${category.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={rowPending}
                onClick={startEdit}
              >
                Edytuj
              </button>
              <button
                type="button"
                aria-label={`${
                  category.is_active ? "Dezaktywuj" : "Aktywuj"
                } kategorię ${category.name}`}
                className="btn-secondary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={rowPending}
                onClick={toggle}
              >
                {category.is_active ? "Dezaktywuj" : "Aktywuj"}
              </button>
              <button
                type="button"
                aria-label={`Usuń kategorię ${category.name}`}
                className="btn-danger px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={rowPending}
                onClick={remove}
              >
                Usuń
              </button>
            </>
          )}
        </div>
      </div>
      {editing ? (
        <div className="mt-3 space-y-3">
          <div>
            <label
              htmlFor="category-edit-name"
              className="mb-1 block text-xs text-gray-400"
            >
              Nazwa
            </label>
            <input
              id="category-edit-name"
              className="input"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label
                htmlFor="category-edit-type"
                className="mb-1 block text-xs text-gray-400"
              >
                Typ
              </label>
              <select
                id="category-edit-type"
                className="input"
                value={draftType}
                onChange={(event) =>
                  setDraftType(event.target.value as Category["type"])
                }
              >
                <option value="income">Przychód</option>
                <option value="expense">Wydatek</option>
                <option value="transfer">Transfer</option>
              </select>
            </div>
            <div>
              <label
                htmlFor="category-edit-parent"
                className="mb-1 block text-xs text-gray-400"
              >
                Kategoria nadrzędna
              </label>
              <select
                id="category-edit-parent"
                className="input"
                value={draftParentId}
                onChange={(event) => setDraftParentId(event.target.value)}
              >
                <option value="">brak</option>
                {parentOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      ) : null}
      {(updateErrorForRow ?? deleteErrorForRow) ? (
        <p className="mt-2 w-full text-xs text-red-400">
          {updateErrorForRow ?? deleteErrorForRow}
        </p>
      ) : null}
    </div>
  );
}
