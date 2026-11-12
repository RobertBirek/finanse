import { useMemo, useState } from "react";
import type { Category } from "../../api/finance";
import { categoryOptions } from "../../lib/categories";

export function CategoryPicker({
  id,
  label = "Kategoria",
  categories,
  hierarchyCategories = categories,
  value,
  onChange,
  type,
  includeInactive = false,
  excludedIds,
  retainSelectedOption = true,
}: {
  id: string;
  label?: string;
  categories: Category[];
  hierarchyCategories?: readonly Category[];
  value: string;
  onChange: (value: string) => void;
  type?: Category["type"];
  includeInactive?: boolean;
  excludedIds?: ReadonlySet<string>;
  retainSelectedOption?: boolean;
}) {
  const [query, setQuery] = useState("");
  const options = useMemo(() => {
    const selected = categories.find((category) => category.id === value);
    return categoryOptions(categories, hierarchyCategories).filter(
      (category) =>
        (retainSelectedOption && category.id === selected?.id) ||
        ((!type || category.type === type) &&
          !excludedIds?.has(category.id) &&
          (includeInactive || category.is_active !== false) &&
          category.label
            .toLocaleLowerCase("pl")
            .includes(query.toLocaleLowerCase("pl"))),
    );
  }, [
    categories,
    hierarchyCategories,
    includeInactive,
    query,
    type,
    value,
    excludedIds,
    retainSelectedOption,
  ]);
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-gray-400">
        {label}
      </label>
      <input
        className="input mb-2"
        aria-label={`Szukaj: ${label}`}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Szukaj w drzewie…"
      />
      <select
        id={id}
        className="input"
        value={options.some((option) => option.id === value) ? value : ""}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Wybierz kategorię</option>
        {options.map((category) => (
          <option key={category.id} value={category.id}>
            {category.label}
            {category.is_active === false ? " (archiwalna)" : ""}
          </option>
        ))}
      </select>
      {!options.length ? (
        <p role="status" className="mt-1 text-xs text-gray-400">
          Brak pasujących kategorii
        </p>
      ) : null}
    </div>
  );
}
