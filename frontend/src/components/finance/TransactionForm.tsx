import { useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import {
  buildTransactionPostings,
  parsePlnToGrosze,
  useAccounts,
  useCategories,
  useCreateExchange,
  useCreateExpenseRefund,
  useCreateTransaction,
} from "../../api/finance";
import { localTodayIso } from "../../lib/date";
import { QueryFeedback } from "../QueryFeedback";
import { CategoryPicker } from "./CategoryPicker";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

type TransactionType =
  "income" | "expense" | "expense_refund" | "transfer" | "exchange";

type TransactionFormProps = {
  onSuccess?: () => void;
  initialType?: TransactionType;
};

const DEFAULT_TYPE: TransactionType = "expense";

export function TransactionForm({
  onSuccess,
  initialType = DEFAULT_TYPE,
}: TransactionFormProps) {
  const accountsQuery = useAccounts();
  const categoriesQuery = useCategories();
  const create = useCreateTransaction();
  const exchange = useCreateExchange();
  const refund = useCreateExpenseRefund();

  const [type, setType] = useState<TransactionType>(initialType);
  const [accountId, setAccountId] = useState("");
  const [toAccountId, setToAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [fxRate, setFxRate] = useState("");
  const [date, setDate] = useState(localTodayIso());
  const [purchaseDate, setPurchaseDate] = useState(localTodayIso());
  const [sameDate, setSameDate] = useState(true);
  const [description, setDescription] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const accounts = accountsQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];

  const activePlnAccounts = accounts.filter(
    (account) => account.is_active !== false && account.currency === "PLN",
  );
  const activeAccounts = accounts.filter(
    (account) => account.is_active !== false,
  );
  const filteredCategories = categories.filter(
    (category) =>
      category.is_active !== false &&
      category.type === (type === "expense_refund" ? "expense" : type),
  );

  const errorMessage =
    apiErrorDetail(create.error) ??
    apiErrorDetail(exchange.error) ??
    apiErrorDetail(refund.error);

  const sourceAccount = accounts.find((account) => account.id === accountId);
  const amountCurrency =
    type === "exchange" ? (sourceAccount?.currency ?? "PLN") : "PLN";

  function resetForm() {
    setType(DEFAULT_TYPE);
    setAccountId("");
    setToAccountId("");
    setCategoryId("");
    setFxRate("");
    setAmount("");
    setDate(localTodayIso());
    setPurchaseDate(localTodayIso());
    setSameDate(true);
    setDescription("");
    setValidationError(null);
  }

  function handleTypeChange(nextType: TransactionType) {
    setType(nextType);
    setCategoryId("");
    setToAccountId("");
    setFxRate("");
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
    if (type === "exchange") {
      if (!accountId || !toAccountId) {
        setValidationError("Wybierz konto źródłowe i docelowe.");
        return;
      }
      const from = accounts.find((account) => account.id === accountId);
      const to = accounts.find((account) => account.id === toAccountId);
      if (
        !from ||
        !to ||
        from.id === to.id ||
        (from.currency === "PLN") === (to.currency === "PLN")
      ) {
        setValidationError(
          "Przewalutowanie wymaga jednego konta w PLN i drugiego w obcej walucie.",
        );
        return;
      }

      let fxRateValue: number | undefined;
      const fxRateRaw = fxRate.trim();
      if (fxRateRaw) {
        const parsed = Number(fxRateRaw.replace(",", "."));
        if (!Number.isFinite(parsed) || parsed <= 0) {
          setValidationError("Podaj poprawny kurs.");
          return;
        }
        fxRateValue = parsed;
      }

      setValidationError(null);
      exchange.mutate(
        {
          from_account_id: accountId,
          to_account_id: toAccountId,
          from_amount: amountGrosze,
          ...(fxRateValue !== undefined ? { fx_rate: fxRateValue } : {}),
          transaction_date: date,
          description: description.trim(),
        },
        {
          onSuccess: () => {
            resetForm();
            onSuccess?.();
          },
        },
      );
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

    if (type === "expense_refund") {
      if (!date) {
        setValidationError("Podaj datę zwrotu.");
        return;
      }
      refund.mutate(
        {
          account_id: accountId,
          category_id: categoryId,
          amount_minor: amountGrosze,
          transaction_date: date,
          description: description.trim(),
        },
        {
          onSuccess: () => {
            resetForm();
            onSuccess?.();
          },
        },
      );
      return;
    }

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
        ...(type === "expense"
          ? {
              purchase_date: purchaseDate,
              booking_date: sameDate ? purchaseDate : date,
            }
          : { transaction_date: date }),
        postings,
      },
      {
        onSuccess: () => {
          resetForm();
          onSuccess?.();
        },
      },
    );
  }

  if (accountsQuery.isLoading || categoriesQuery.isLoading) {
    return (
      <div className="mb-6">
        <QueryFeedback
          loading
          errorMessage="Nie udało się pobrać danych formularza."
        >
          {null}
        </QueryFeedback>
      </div>
    );
  }

  if (accountsQuery.isError || categoriesQuery.isError) {
    return (
      <div className="card mb-6" role="alert">
        <p>Nie udało się pobrać danych do formularza transakcji.</p>
        <button
          type="button"
          className="btn-secondary mt-3"
          onClick={() => {
            void accountsQuery.refetch();
            void categoriesQuery.refetch();
          }}
        >
          Ponów pobranie danych formularza
        </button>
      </div>
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
            <option value="expense_refund">Zwrot wydatku</option>
            <option value="income">Przychód</option>
            <option value="transfer">Transfer</option>
            <option value="exchange">Przewalutowanie</option>
          </select>
        </div>
        <div>
          <label htmlFor="tx-date" className="mb-1 block text-sm text-gray-400">
            {type === "expense" ? "Data księgowania" : "Data operacji"}
          </label>
          <input
            id="tx-date"
            type="date"
            className="input"
            value={type === "expense" && sameDate ? purchaseDate : date}
            disabled={type === "expense" && sameDate}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>
        {type === "expense" ? (
          <>
            <label className="block text-sm text-gray-400">
              Data zakupu
              <input
                className="input mt-1"
                type="date"
                required
                value={purchaseDate}
                onChange={(event) => setPurchaseDate(event.target.value)}
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={sameDate}
                onChange={(event) => {
                  setSameDate(event.target.checked);
                  if (!event.target.checked) setDate(purchaseDate);
                }}
              />
              Księgowanie w dniu zakupu
            </label>
          </>
        ) : null}
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
        ) : type === "exchange" ? (
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
                {activeAccounts.map((account) => (
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
                {activeAccounts
                  .filter((account) => account.id !== accountId)
                  .map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="tx-fx-rate"
                className="mb-1 block text-sm text-gray-400"
              >
                Kurs (opcjonalnie)
              </label>
              <input
                id="tx-fx-rate"
                className="input"
                value={fxRate}
                onChange={(event) => setFxRate(event.target.value)}
                placeholder="np. 4,30"
              />
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
            <CategoryPicker
              id="tx-category"
              categories={filteredCategories}
              hierarchyCategories={categories}
              value={categoryId}
              onChange={setCategoryId}
              type={type === "expense_refund" ? "expense" : type}
            />
          </>
        )}
        <div>
          <label
            htmlFor="tx-amount"
            className="mb-1 block text-sm text-gray-400"
          >
            Kwota ({amountCurrency})
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
      {type === "expense_refund" ? (
        <p className="mt-3 text-sm text-gray-400">
          Zwrot zwiększa saldo konta i pomniejsza wydatki kategorii. Nie jest
          przychodem.
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
          disabled={create.isPending || exchange.isPending || refund.isPending}
        >
          Zapisz transakcję
        </button>
      </div>
    </form>
  );
}
