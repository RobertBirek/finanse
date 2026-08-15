import { useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import {
  buildTransactionPostings,
  parsePlnToGrosze,
  useAccounts,
  useCategories,
  useCreateTransaction,
} from "../../api/finance";
import { localTodayIso } from "../../lib/date";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

type TransactionType = "income" | "expense" | "transfer";

type TransactionFormProps = {
  onSuccess?: () => void;
};

const DEFAULT_TYPE: TransactionType = "expense";

export function TransactionForm({ onSuccess }: TransactionFormProps) {
  const accountsQuery = useAccounts();
  const categoriesQuery = useCategories();
  const create = useCreateTransaction();

  const [type, setType] = useState<TransactionType>(DEFAULT_TYPE);
  const [accountId, setAccountId] = useState("");
  const [toAccountId, setToAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(localTodayIso());
  const [description, setDescription] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const accounts = accountsQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];

  const activePlnAccounts = accounts.filter(
    (account) => account.is_active && account.currency === "PLN",
  );
  const filteredCategories = categories.filter(
    (category) => category.type === type,
  );

  const errorMessage = apiErrorDetail(create.error);

  function handleTypeChange(nextType: TransactionType) {
    setType(nextType);
    setCategoryId("");
    setToAccountId("");
    setValidationError(null);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const amountGrosze = parsePlnToGrosze(amount);
    if (amountGrosze === null) {
      setValidationError("Podaj kwotę większą od 0.");
      return;
    }
    if (description.trim().length === 0) {
      setValidationError("Podaj opis.");
      return;
    }
    if (type === "transfer") {
      if (!accountId || !toAccountId) {
        setValidationError("Wybierz konto źródłowe i docelowe.");
        return;
      }
    } else {
      if (!accountId) {
        setValidationError("Wybierz konto.");
        return;
      }
      if (!categoryId) {
        setValidationError("Wybierz kategorię.");
        return;
      }
    }

    setValidationError(null);

    const postings =
      type === "transfer"
        ? buildTransactionPostings({
            type: "transfer",
            fromAccountId: accountId,
            toAccountId,
            amountPlng: amountGrosze,
          })
        : buildTransactionPostings({
            type,
            accountId,
            categoryId,
            amountPlng: amountGrosze,
          });

    create.mutate(
      {
        type,
        description: description.trim(),
        date,
        postings,
      } as unknown as Parameters<typeof create.mutate>[0],
      {
        onSuccess: () => {
          setType(DEFAULT_TYPE);
          setAccountId("");
          setToAccountId("");
          setCategoryId("");
          setAmount("");
          setDate(localTodayIso());
          setDescription("");
          setValidationError(null);
          onSuccess?.();
        },
      },
    );
  }

  if (accountsQuery.isLoading || categoriesQuery.isLoading) {
    return (
      <div className="mb-6 flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
      </div>
    );
  }

  if (accountsQuery.isError || categoriesQuery.isError) {
    return (
      <p className="card mb-6 text-sm text-red-400">
        Nie udało się pobrać danych do formularza transakcji.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-4">
      <h3 className="mb-4 text-base font-semibold text-white">
        Nowa transakcja
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="tx-type" className="mb-1 block text-sm text-gray-400">
            Typ
          </label>
          <select
            id="tx-type"
            className="input"
            value={type}
            onChange={(event) =>
              handleTypeChange(event.target.value as TransactionType)
            }
          >
            <option value="expense">Wydatek</option>
            <option value="income">Przychód</option>
            <option value="transfer">Transfer</option>
          </select>
        </div>
        <div>
          <label htmlFor="tx-date" className="mb-1 block text-sm text-gray-400">
            Data
          </label>
          <input
            id="tx-date"
            type="date"
            className="input"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>
        {type === "transfer" ? (
          <>
            <div>
              <label
                htmlFor="tx-from-account"
                className="mb-1 block text-sm text-gray-400"
              >
                Z konta
              </label>
              <select
                id="tx-from-account"
                className="input"
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
              >
                <option value="">Wybierz konto</option>
                {activePlnAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="tx-to-account"
                className="mb-1 block text-sm text-gray-400"
              >
                Na konto
              </label>
              <select
                id="tx-to-account"
                className="input"
                value={toAccountId}
                onChange={(event) => setToAccountId(event.target.value)}
              >
                <option value="">Wybierz konto</option>
                {activePlnAccounts
                  .filter((account) => account.id !== accountId)
                  .map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
              </select>
            </div>
          </>
        ) : (
          <>
            <div>
              <label
                htmlFor="tx-account"
                className="mb-1 block text-sm text-gray-400"
              >
                Konto
              </label>
              <select
                id="tx-account"
                className="input"
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
              >
                <option value="">Wybierz konto</option>
                {activePlnAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="tx-category"
                className="mb-1 block text-sm text-gray-400"
              >
                Kategoria
              </label>
              <select
                id="tx-category"
                className="input"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
              >
                <option value="">Wybierz kategorię</option>
                {filteredCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
        <div>
          <label
            htmlFor="tx-amount"
            className="mb-1 block text-sm text-gray-400"
          >
            Kwota (PLN)
          </label>
          <input
            id="tx-amount"
            className="input"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="np. 1 234,56"
          />
        </div>
        <div className="sm:col-span-2">
          <label
            htmlFor="tx-description"
            className="mb-1 block text-sm text-gray-400"
          >
            Opis
          </label>
          <input
            id="tx-description"
            className="input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
      </div>
      {validationError ? (
        <p role="alert" className="mt-4 text-sm text-red-400">
          {validationError}
        </p>
      ) : null}
      {errorMessage ? (
        <p role="alert" className="mt-4 text-sm text-red-400">
          {errorMessage}
        </p>
      ) : null}
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          className="btn-primary"
          disabled={create.isPending}
        >
          Dodaj transakcję
        </button>
      </div>
    </form>
  );
}
