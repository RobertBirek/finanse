import { useState, type SelectHTMLAttributes } from "react";
import type { Account, Category } from "../../api/finance";
import { SEARCH_FIELDS, TRANSACTION_TYPES } from "../../lib/transactionSearch";
import { categoryOptions } from "../../lib/categories";
import { retainFinancePeriod } from "./useFinancePeriod";

export function TransactionFilters({
  search,
  accounts,
  categories,
  onApply,
  onClear,
}: {
  search: URLSearchParams;
  accounts: Account[];
  categories: Category[];
  onApply: (next: URLSearchParams) => void;
  onClear: () => void;
}) {
  const activeFilters = SEARCH_FIELDS.filter(
    (field) => !["q", "size"].includes(field) && search.get(field),
  ).length;
  const accountId = search.get("account_id");
  const categoryId = search.get("category_id");
  const account = accounts.find((item) => item.id === accountId);
  const category = categoryOptions(categories).find(
    (item) => item.id === categoryId,
  );
  const chips = [
    search.get("q") && { field: "q", label: `Szukaj: ${search.get("q")}` },
    accountId && {
      field: "account_id",
      label: `Konto: ${
        account
          ? `${account.name}${account.is_active === false ? " (archiwalne)" : ""}`
          : "Wybrane konto — nazwa niedostępna"
      }`,
    },
    categoryId && {
      field: "category_id",
      label: `Kategoria: ${
        category
          ? `${category.label}${category.is_active === false ? " (archiwalna)" : ""}`
          : "Wybrana kategoria — nazwa niedostępna"
      }`,
    },
    search.get("include_descendants") === "true" && {
      field: "include_descendants",
      label: "Uwzględnij podkategorie",
    },
    search.get("budget_accounts_only") === "true" && {
      field: "budget_accounts_only",
      label: "Tylko konta budżetowe",
    },
    search.get("type") && {
      field: "type",
      label: `Typ: ${
        TRANSACTION_TYPES[
          search.get("type") as keyof typeof TRANSACTION_TYPES
        ] ?? search.get("type")
      }`,
    },
    search.get("date_basis") === "purchase" && {
      field: "date_basis",
      label: "Data zakupu",
    },
    search.get("date_from") && {
      field: "date_from",
      label: `Data od: ${search.get("date_from")}`,
    },
    search.get("date_to") && {
      field: "date_to",
      label: `Data do: ${search.get("date_to")}`,
    },
    search.get("currency") && {
      field: "currency",
      label: `Waluta: ${search.get("currency")}`,
    },
    search.get("min") && {
      field: "min",
      label: `Kwota od: ${search.get("min")} PLN`,
    },
    search.get("max") && {
      field: "max",
      label: `Kwota do: ${search.get("max")} PLN`,
    },
  ].filter((chip): chip is { field: string; label: string } => Boolean(chip));

  function removeFilter(field: string) {
    const next = new URLSearchParams(search);
    next.delete(field);
    if (field === "category_id") next.delete("include_descendants");
    next.delete("page");
    next.delete("detail");
    onApply(next);
  }

  return (
    <form
      className="card space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const next = retainFinancePeriod(search);
        for (const field of SEARCH_FIELDS) {
          const value = String(form.get(field) ?? "").trim();
          if (value) next.set(field, value);
        }
        onApply(next);
      }}
    >
      <h2 className="text-lg font-semibold text-white">Znajdź transakcję</h2>
      {chips.length > 0 && (
        <div
          aria-label="Aktywne filtry"
          className="flex flex-wrap gap-2 text-sm text-gray-200"
        >
          {chips.map((chip) => (
            <button
              key={chip.field}
              type="button"
              className="rounded-full border border-gray-600 px-3 py-1 hover:border-gray-400"
              aria-label={`Usuń filtr: ${chip.label}`}
              onClick={() => removeFilter(chip.field)}
            >
              {chip.label} ×
            </button>
          ))}
        </div>
      )}
      <label className="workspace-fields block text-sm text-gray-300">
        Szukaj po opisie, koncie lub kategorii
        <input
          name="q"
          type="search"
          maxLength={200}
          defaultValue={search.get("q") ?? ""}
          className="input w-full mt-1"
        />
      </label>
      <details>
        <summary className="cursor-pointer text-sm text-gray-300">
          Filtry szczegółowe
          {activeFilters ? ` (aktywne: ${activeFilters})` : ""}
        </summary>
        <div className="mt-4 grid max-w-5xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm text-gray-300">
            Konto
            <SearchSelect
              name="account_id"
              defaultValue={search.get("account_id") ?? ""}
              className="input w-full mt-1"
            >
              <option value="">Wszystkie konta</option>
              {search.get("account_id") &&
                !accounts?.some((a) => a.id === search.get("account_id")) && (
                  <option value={search.get("account_id")!}>
                    Wybrane konto — nazwa niedostępna
                  </option>
                )}
              {accounts?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                  {a.is_active === false ? " (archiwalne)" : ""}
                </option>
              ))}
            </SearchSelect>
          </label>
          <label className="text-sm text-gray-300">
            Kategoria
            <SearchSelect
              name="category_id"
              defaultValue={search.get("category_id") ?? ""}
              className="input w-full mt-1"
            >
              <option value="">Wszystkie kategorie</option>
              {search.get("category_id") &&
                !categories?.some(
                  (c) => c.id === search.get("category_id"),
                ) && (
                  <option value={search.get("category_id")!}>
                    Wybrana kategoria — nazwa niedostępna
                  </option>
                )}
              {categoryOptions(categories ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                  {c.is_active === false ? " (archiwalna)" : ""}
                </option>
              ))}
            </SearchSelect>
          </label>
          <label className="flex items-center gap-2 self-end pb-3 text-sm text-gray-300">
            <input
              name="include_descendants"
              type="checkbox"
              value="true"
              defaultChecked={search.get("include_descendants") === "true"}
            />
            Uwzględnij podkategorie
          </label>
          <label className="flex items-center gap-2 self-end pb-3 text-sm text-gray-300">
            <input
              name="budget_accounts_only"
              type="checkbox"
              value="true"
              defaultChecked={search.get("budget_accounts_only") === "true"}
            />
            Tylko konta budżetowe
          </label>
          <label className="text-sm text-gray-300">
            Typ
            <SearchSelect
              name="type"
              defaultValue={search.get("type") ?? ""}
              className="input w-full mt-1"
            >
              <option value="">Wszystkie typy</option>
              {Object.entries(TRANSACTION_TYPES).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SearchSelect>
          </label>
          <label className="text-sm text-gray-300">
            Podstawa daty
            <SearchSelect
              name="date_basis"
              defaultValue={
                search.get("date_basis") === "purchase" ? "purchase" : ""
              }
              className="input w-full mt-1"
            >
              <option value="">Data księgowania</option>
              <option value="purchase">Data zakupu</option>
            </SearchSelect>
          </label>
          <label className="text-sm text-gray-300">
            Data od
            <input
              type="date"
              name="date_from"
              defaultValue={search.get("date_from") ?? ""}
              className="input w-full min-w-0 mt-1"
            />
          </label>
          <label className="text-sm text-gray-300">
            Data do
            <input
              type="date"
              name="date_to"
              defaultValue={search.get("date_to") ?? ""}
              className="input w-full min-w-0 mt-1"
            />
          </label>
          <label className="text-sm text-gray-300">
            Waluta źródłowa
            <SearchSelect
              name="currency"
              defaultValue={search.get("currency") ?? ""}
              className="input w-full mt-1"
            >
              <option value="">Wszystkie waluty</option>
              {["PLN", "EUR", "USD"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </SearchSelect>
          </label>
          <label className="text-sm text-gray-300">
            Kwota od (PLN)
            <input
              name="min"
              inputMode="decimal"
              maxLength={18}
              defaultValue={search.get("min") ?? ""}
              aria-describedby="amount-filter-help"
              className="input w-full mt-1"
            />
          </label>
          <label className="text-sm text-gray-300">
            Kwota do (PLN)
            <input
              name="max"
              inputMode="decimal"
              maxLength={18}
              defaultValue={search.get("max") ?? ""}
              aria-describedby="amount-filter-help"
              className="input w-full mt-1"
            />
          </label>
          <label className="text-sm text-gray-300">
            Wyników na stronę
            <SearchSelect
              name="size"
              defaultValue={search.get("size") ?? "25"}
              className="input w-full mt-1"
            >
              {[25, 50, 100].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </SearchSelect>
          </label>
        </div>
        <p
          id="amount-filter-help"
          className="mt-3 max-w-[65ch] text-xs text-gray-400"
        >
          Kwoty to równowartości PLN bez znaku, dla pojedynczego zapisu na
          koncie — nie suma obu stron księgi. Daty obejmują oba wskazane dni.
          Wyszukiwanie obejmuje całą historię, także konta archiwalne.
        </p>
      </details>
      <div className="flex flex-wrap gap-3">
        <button className="btn-primary" type="submit">
          Zastosuj filtry
        </button>
        <button className="btn-secondary" type="button" onClick={onClear}>
          Wyczyść filtry
        </button>
      </div>
    </form>
  );
}

function SearchSelect({
  defaultValue,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const [value, setValue] = useState(String(defaultValue ?? ""));
  return (
    <select
      {...props}
      value={value}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}
