import { useState } from "react";
import {
  importError,
  useImportCategories,
  useSaveStatementAutoPostSettings,
  useStatementAutoPostSettings,
  type StatementAutoPostSettings as Settings,
} from "../../../api/bankImports";

function SettingsForm({ initial }: { initial: Settings }) {
  const [draft, setDraft] = useState(initial);
  const categories = useImportCategories();
  const save = useSaveStatementAutoPostSettings();

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(draft);
      }}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={draft.enabled}
          disabled={save.isPending}
          onChange={(event) =>
            setDraft({ ...draft, enabled: event.target.checked })
          }
        />
        Księguj nowe wyciągi automatycznie
      </label>
      <p className="text-sm">
        Ta opcja dotyczy tylko nowo dodanych wyciągów. Kategorie poniżej
        obowiązują też przy jednorazowym księgowaniu z widoku wyciągu.
      </p>
      {(["expense", "income"] as const).map((kind) => {
        const field = `${kind}_category_id` as const;
        return (
          <label key={kind} className="block text-sm">
            {kind === "expense"
              ? "Kategoria dla rozpoznanych zakupów kartą"
              : "Kategoria dla rozpoznanych odsetek"}
            <select
              className="input mt-1 block w-full sm:w-auto"
              value={draft[field] ?? ""}
              disabled={
                categories.isPending || categories.isError || save.isPending
              }
              onChange={(event) =>
                setDraft({ ...draft, [field]: event.target.value || null })
              }
            >
              <option value="">Pozostaw te pozycje do sprawdzenia</option>
              {(categories.data ?? [])
                .filter(
                  (category) => category.is_active && category.type === kind,
                )
                .map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
            </select>
          </label>
        );
      })}
      {categories.isError ? (
        <p role="alert">Nie udało się pobrać kategorii.</p>
      ) : null}
      {save.isError ? <p role="alert">{importError(save.error)}</p> : null}
      <button type="submit" className="btn-secondary" disabled={save.isPending}>
        Zapisz ustawienia księgowania
      </button>
    </form>
  );
}

export function StatementAutoPostSettings() {
  const settings = useStatementAutoPostSettings();
  const current = settings.data;
  return (
    <section
      className="card mb-4 space-y-3"
      aria-label="Automatyczne księgowanie wyciągów"
    >
      <h2 className="text-xl">Automatyczne księgowanie</h2>
      {current ? (
        <SettingsForm
          key={`${current.enabled}:${current.expense_category_id}:${current.income_category_id}`}
          initial={current}
        />
      ) : settings.isError ? (
        <p role="alert">Nie udało się pobrać ustawień księgowania.</p>
      ) : (
        <p role="status">Ładowanie ustawień księgowania…</p>
      )}
    </section>
  );
}
