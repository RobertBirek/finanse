import type { Category } from "../api/finance";

export function categoryPath(
  id: string,
  categories: readonly Category[],
): string {
  const byId = new Map(categories.map((category) => [category.id, category]));
  const parts: string[] = [];
  const seen = new Set<string>();
  let current = byId.get(id);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    parts.unshift(current.name);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return parts.join(" → ");
}

export function eligibleCategoryParents(
  id: string,
  categories: readonly Category[],
): Category[] {
  const blocked = new Set([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const category of categories)
      if (
        category.parent_id &&
        blocked.has(category.parent_id) &&
        !blocked.has(category.id)
      ) {
        blocked.add(category.id);
        changed = true;
      }
  }
  return categories.filter((category) => !blocked.has(category.id));
}
