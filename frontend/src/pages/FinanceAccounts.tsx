import { useState, type FormEvent } from "react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import {
  useAccounts,
  useCategories,
  useCreateAccount,
  useCreateCategory,
  useDeleteAccount,
  useDeleteCategory,
  useUpdateAccount,
  useUpdateCategory,
  type Account,
  type AccountUpdateInput,
  type Category,
  type CategoryUpdateInput,
} from "../api/finance";

const ACCOUNT_DELETE_CONFLICT_MESSAGE =
  "Konto ma zapisy — zdezaktywuj je zamiast usuwać";
const CATEGORY_DELETE_CONFLICT_MESSAGE =
  "Kategoria ma zapisy — zdezaktywuj ją zamiast usuwać";

const ACCOUNT_TYPES = [
  { value: "checking", label: "Bieżące" },
  { value: "savings", label: "Oszczędnościowe" },
  { value: "cash", label: "Gotówka" },
  { value: "credit", label: "Kredytowe" },
  { value: "investment", label: "Inwestycyjne" },
] as const;

const CATEGORY_TYPE_LABEL: Record<Category["type"], string> = {
  income: "Przychód",
  expense: "Wydatek",
  transfer: "Transfer",
};

function accountTypeLabel(type: string): string {
  return ACCOUNT_TYPES.find((option) => option.value === type)?.label ?? type;
}

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

function isConflict(error: unknown): boolean {
  return (error as AxiosError)?.response?.status === 409;
}

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

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
    </div>
  );
}

type AccountRowProps = {
  account: Account;
  updateMutation: UseMutationResult<
    Account,
    Error,
    AccountUpdateInput & { id: string }
  >;
  deleteMutation: UseMutationResult<void, Error, string>;
  editing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
};

function AccountRow({
  account,
  updateMutation,
  deleteMutation,
  editing,
  onStartEdit,
  onCancelEdit,
}: AccountRowProps) {
  const [draftName, setDraftName] = useState(account.name);
  const [draftType, setDraftType] = useState(account.type);
  const [draftBudget, setDraftBudget] = useState(account.is_budget_account);

  const rowPending =
    (updateMutation.isPending && updateMutation.variables?.id === account.id) ||
    (deleteMutation.isPending && deleteMutation.variables === account.id);

  const updateErrorForRow =
    updateMutation.variables?.id === account.id
      ? apiErrorDetail(updateMutation.error)
      : null;
  const deleteErrorForRow =
    deleteMutation.variables === account.id
      ? isConflict(deleteMutation.error)
        ? ACCOUNT_DELETE_CONFLICT_MESSAGE
        : apiErrorDetail(deleteMutation.error)
      : null;

  function startEdit() {
    setDraftName(account.name);
    setDraftType(account.type);
    setDraftBudget(account.is_budget_account);
    onStartEdit();
  }

  function save() {
    updateMutation.mutate(
      {
        id: account.id,
        name: draftName,
        type: draftType,
        is_budget_account: draftBudget,
      },
      { onSuccess: onCancelEdit },
    );
  }

  function toggle() {
    updateMutation.mutate({ id: account.id, is_active: !account.is_active });
  }

  function remove() {
    if (window.confirm(`Usunąć konto "${account.name}"?`)) {
      deleteMutation.mutate(account.id);
    }
  }

  return (
    <div
      className={`rounded-lg border border-gray-800 bg-gray-800/40 p-3 ${
        account.is_active ? "" : "opacity-60"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-white">
              {account.name}
            </p>
            {account.is_budget_account ? (
              <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400">
                budżetowe
              </span>
            ) : null}
            {!account.is_active ? (
              <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
                nieaktywne
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            {accountTypeLabel(account.type)} · {account.currency}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {editing ? (
            <>
              <button
                type="button"
                aria-label={`Zapisz konto ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={rowPending}
                onClick={save}
              >
                Zapisz
              </button>
              <button
                type="button"
                aria-label={`Anuluj edycję konta ${account.name}`}
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
                aria-label={`Edytuj konto ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={rowPending}
                onClick={startEdit}
              >
                Edytuj
              </button>
              <button
                type="button"
                aria-label={`${
                  account.is_active ? "Dezaktywuj" : "Aktywuj"
                } konto ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={rowPending}
                onClick={toggle}
              >
                {account.is_active ? "Dezaktywuj" : "Aktywuj"}
              </button>
              <button
                type="button"
                aria-label={`Usuń konto ${account.name}`}
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
              htmlFor="account-edit-name"
              className="mb-1 block text-xs text-gray-400"
            >
              Nazwa
            </label>
            <input
              id="account-edit-name"
              className="input"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label
                htmlFor="account-edit-type"
                className="mb-1 block text-xs text-gray-400"
              >
                Typ
              </label>
              <select
                id="account-edit-type"
                className="input"
                value={draftType}
                onChange={(event) => setDraftType(event.target.value)}
              >
                {ACCOUNT_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 pb-2.5 text-sm text-gray-300">
              <input
                type="checkbox"
                id="account-edit-budget"
                checked={draftBudget}
                onChange={(event) => setDraftBudget(event.target.checked)}
              />
              Budżetowe
            </label>
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

function CategoryRow({
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

export function FinanceAccounts() {
  const accountsQuery = useAccounts();
  const categoriesQuery = useCategories();
  const createAccount = useCreateAccount();
  const updateAccount = useUpdateAccount();
  const deleteAccount = useDeleteAccount();
  const createCategory = useCreateCategory();
  const updateCategory = useUpdateCategory();
  const deleteCategory = useDeleteCategory();

  const [editingAccountId, setEditingAccountId] = useState<string | null>(null);
  const [editingCategoryId, setEditingCategoryId] = useState<string | null>(
    null,
  );

  const [accountName, setAccountName] = useState("");
  const [accountType, setAccountType] = useState("checking");
  const [accountCurrency, setAccountCurrency] = useState("PLN");
  const [accountBudget, setAccountBudget] = useState(true);

  const [categoryName, setCategoryName] = useState("");
  const [categoryType, setCategoryType] = useState<Category["type"]>("expense");
  const [categoryParentId, setCategoryParentId] = useState("");

  const accounts = accountsQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];

  const createAccountError = apiErrorDetail(createAccount.error);
  const createCategoryError = apiErrorDetail(createCategory.error);

  function handleCreateAccount(event: FormEvent) {
    event.preventDefault();
    createAccount.mutate(
      {
        name: accountName.trim(),
        type: accountType,
        currency: accountCurrency,
        ...(!accountBudget ? { is_budget_account: false } : {}),
      },
      {
        onSuccess: () => {
          setAccountName("");
          setAccountType("checking");
          setAccountCurrency("PLN");
          setAccountBudget(true);
        },
      },
    );
  }

  function handleCreateCategory(event: FormEvent) {
    event.preventDefault();
    createCategory.mutate(
      {
        name: categoryName.trim(),
        type: categoryType,
        ...(categoryParentId ? { parent_id: categoryParentId } : {}),
      },
      {
        onSuccess: () => {
          setCategoryName("");
          setCategoryType("expense");
          setCategoryParentId("");
        },
      },
    );
  }

  return (
    <div className="max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold text-white">Konta i kategorie</h1>

      <section className="card mb-4">
        <h2 className="mb-4 text-lg font-semibold text-white">Konta</h2>
        {accountsQuery.isLoading ? (
          <LoadingSpinner />
        ) : accountsQuery.isError ? (
          <p className="text-sm text-red-400">Nie udało się pobrać kont.</p>
        ) : accounts.length === 0 ? (
          <p className="py-4 text-sm text-gray-500">Brak kont.</p>
        ) : (
          <div className="space-y-2">
            {accounts.map((account) => (
              <AccountRow
                key={account.id}
                account={account}
                updateMutation={updateAccount}
                deleteMutation={deleteAccount}
                editing={editingAccountId === account.id}
                onStartEdit={() => {
                  setEditingAccountId(account.id);
                  setEditingCategoryId(null);
                }}
                onCancelEdit={() => setEditingAccountId(null)}
              />
            ))}
          </div>
        )}
      </section>

      <form
        aria-label="Nowe konto"
        onSubmit={handleCreateAccount}
        className="card mb-4"
      >
        <h2 className="mb-4 text-lg font-semibold text-white">Nowe konto</h2>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label
              htmlFor="account-form-name"
              className="mb-1 block text-sm text-gray-400"
            >
              Nazwa
            </label>
            <input
              id="account-form-name"
              className="input"
              value={accountName}
              onChange={(event) => setAccountName(event.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor="account-form-type"
              className="mb-1 block text-sm text-gray-400"
            >
              Typ
            </label>
            <select
              id="account-form-type"
              className="input"
              value={accountType}
              onChange={(event) => setAccountType(event.target.value)}
            >
              {ACCOUNT_TYPES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="account-form-currency"
              className="mb-1 block text-sm text-gray-400"
            >
              Waluta
            </label>
            <select
              id="account-form-currency"
              className="input"
              value={accountCurrency}
              onChange={(event) => setAccountCurrency(event.target.value)}
            >
              <option value="PLN">PLN</option>
              <option value="EUR">EUR</option>
              <option value="USD">USD</option>
            </select>
          </div>
          <label className="flex items-center gap-2 pb-2.5 text-sm text-gray-300">
            <input
              type="checkbox"
              id="account-form-budget"
              checked={accountBudget}
              onChange={(event) => setAccountBudget(event.target.checked)}
            />
            Konto budżetowe
          </label>
          <button
            type="submit"
            className="btn-primary"
            disabled={createAccount.isPending}
          >
            Dodaj konto
          </button>
        </div>
        {createAccountError ? (
          <p className="mt-4 text-sm text-red-400">{createAccountError}</p>
        ) : null}
      </form>

      <section className="card mb-4">
        <h2 className="mb-4 text-lg font-semibold text-white">Kategorie</h2>
        {categoriesQuery.isLoading ? (
          <LoadingSpinner />
        ) : categoriesQuery.isError ? (
          <p className="text-sm text-red-400">
            Nie udało się pobrać kategorii.
          </p>
        ) : categories.length === 0 ? (
          <p className="py-4 text-sm text-gray-500">Brak kategorii.</p>
        ) : (
          <div className="space-y-2">
            {categories.map((category) => (
              <CategoryRow
                key={category.id}
                category={category}
                categories={categories}
                updateMutation={updateCategory}
                deleteMutation={deleteCategory}
                editing={editingCategoryId === category.id}
                onStartEdit={() => {
                  setEditingCategoryId(category.id);
                  setEditingAccountId(null);
                }}
                onCancelEdit={() => setEditingCategoryId(null)}
              />
            ))}
          </div>
        )}
      </section>

      <form
        aria-label="Nowa kategoria"
        onSubmit={handleCreateCategory}
        className="card mb-4"
      >
        <h2 className="mb-4 text-lg font-semibold text-white">
          Nowa kategoria
        </h2>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label
              htmlFor="category-form-name"
              className="mb-1 block text-sm text-gray-400"
            >
              Nazwa
            </label>
            <input
              id="category-form-name"
              className="input"
              value={categoryName}
              onChange={(event) => setCategoryName(event.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor="category-form-type"
              className="mb-1 block text-sm text-gray-400"
            >
              Typ
            </label>
            <select
              id="category-form-type"
              className="input"
              value={categoryType}
              onChange={(event) =>
                setCategoryType(event.target.value as Category["type"])
              }
            >
              <option value="income">Przychód</option>
              <option value="expense">Wydatek</option>
              <option value="transfer">Transfer</option>
            </select>
          </div>
          <div>
            <label
              htmlFor="category-form-parent"
              className="mb-1 block text-sm text-gray-400"
            >
              Kategoria nadrzędna
            </label>
            <select
              id="category-form-parent"
              className="input"
              value={categoryParentId}
              onChange={(event) => setCategoryParentId(event.target.value)}
            >
              <option value="">brak</option>
              {categories.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="btn-primary"
            disabled={createCategory.isPending}
          >
            Dodaj kategorię
          </button>
        </div>
        {createCategoryError ? (
          <p className="mt-4 text-sm text-red-400">{createCategoryError}</p>
        ) : null}
      </form>
    </div>
  );
}
