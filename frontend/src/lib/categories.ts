import type { Category } from "../api/finance";

export function categoryPath(
  id: string,
  categories: readonly Category[],
): string {
  const byId = new Map(categories.map((category) => [category.id, category]));
  return categoryNames(id, byId).join(" → ");
}

function categoryNames(
  id: string,
  byId: ReadonlyMap<string, Category>,
): string[] {
  const parts: string[] = [];
  const seen = new Set<string>();
  let current = byId.get(id);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    parts.unshift(current.name);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return parts;
}

const categoryCollator = new Intl.Collator("pl", { sensitivity: "base" });

/** Sort a copied list of choices using full ancestry, including unavailable parents. */
export function categoryOptions(
  categories: readonly Category[],
  hierarchy: readonly Category[] = categories,
): (Category & { label: string })[] {
  const byId = new Map(
    [...hierarchy, ...categories].map((category) => [category.id, category]),
  );
  return categories
    .map((category) => ({
      ...category,
      label: categoryNames(category.id, byId).join(" - "),
    }))
    .sort(
      (a, b) =>
        categoryCollator.compare(a.label, b.label) || a.id.localeCompare(b.id),
    );
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
