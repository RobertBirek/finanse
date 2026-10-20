import { useState, type FormEvent } from "react";
import {
  useAccounts,
  useCategories,
  useCreateAccount,
  useCreateCategory,
  useDeleteAccount,
  useDeleteCategory,
  useUpdateAccount,
  useUpdateCategory,
  type Category,
} from "../api/finance";
import { AccountRow } from "../components/finance/AccountSettingsRow";
import { CategoryRow } from "../components/finance/CategorySettingsRow";
import {
  ACCOUNT_TYPES,
  apiErrorDetail,
} from "../components/finance/accountSettings";

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-8">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
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
