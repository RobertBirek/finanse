import { useMemo, useState } from "react";
import type { Category } from "../../api/finance";
import { categoryPath } from "../../lib/categories";

export function CategoryPicker({
  id,
  label = "Kategoria",
  categories,
  value,
  onChange,
  type,
  includeInactive = false,
  excludedIds,
}: {
  id: string;
  label?: string;
  categories: Category[];
  value: string;
  onChange: (value: string) => void;
  type?: Category["type"];
  includeInactive?: boolean;
  excludedIds?: ReadonlySet<string>;
}) {
  const [query, setQuery] = useState("");
  const options = useMemo(() => {
    const selected = categories.find((category) => category.id === value);
    return categories.filter(
      (category) =>
        category.id === selected?.id ||
        ((!type || category.type === type) &&
          !excludedIds?.has(category.id) &&
          (includeInactive || category.is_active !== false) &&
          categoryPath(category.id, categories)
            .toLocaleLowerCase("pl")
            .includes(query.toLocaleLowerCase("pl"))),
    );
  }, [categories, includeInactive, query, type, value, excludedIds]);
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
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Wybierz kategorię</option>
        {options.map((category) => (
          <option key={category.id} value={category.id}>
            {categoryPath(category.id, categories)}
            {category.is_active === false ? " (archiwalna)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
