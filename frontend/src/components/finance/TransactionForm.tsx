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
  type Transaction,
  type TransactionLedgerInput,
  type ManualFxTransactionInput,
  useTransactionFxQuote,
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
  /** Canonical PLN ledger loaded by the editor; special commands stay outside this form. */
  initialLedger?: Transaction;
  onLedgerSubmit?: (ledger: TransactionLedgerInput, changed: boolean) => void;
  editBusy?: boolean;
};

const DEFAULT_TYPE: TransactionType = "expense";

export function TransactionForm({
  onSuccess,
  initialType = DEFAULT_TYPE,
  initialLedger,
  onLedgerSubmit,
  editBusy = false,
}: TransactionFormProps) {
  const accountsQuery = useAccounts();
  const categoriesQuery = useCategories();
  const create = useCreateTransaction();
  const exchange = useCreateExchange();
  const refund = useCreateExpenseRefund();

  const initialAccount = initialLedger?.postings.find(
    (posting) =>
      posting.account_id &&
      (initialLedger.type !== "transfer" || posting.direction === "debit"),
  );
  const initialCategory = initialLedger?.postings.find(
    (posting) => posting.category_id,
  );
  const initialToAccount = initialLedger?.postings.find(
    (posting) =>
      posting.account_id && posting.account_id !== initialAccount?.account_id,
  );
  const initialDates = initialLedger?.date_metadata;
  const initialCanonical = !!initialLedger;
  const initialFx =
    initialAccount?.source_currency === "EUR" ||
    initialAccount?.source_currency === "USD";
  const minorToInput = (minor: number) => {
    const absolute = Math.abs(minor);
    return `${Math.trunc(absolute / 100)},${String(absolute % 100).padStart(2, "0")}`;
  };
  const [type, setType] = useState<TransactionType>(
    initialCanonical ? (initialLedger.type as TransactionType) : initialType,
  );
  const hasPurchaseDate =
    type === "expense" && (!initialLedger || !!initialDates);
  const [accountId, setAccountId] = useState(
    initialCanonical ? (initialAccount?.account_id ?? "") : "",
  );
  const [toAccountId, setToAccountId] = useState(
    initialLedger?.type === "transfer"
      ? (initialToAccount?.account_id ?? "")
      : "",
  );
  const [categoryId, setCategoryId] = useState(
    initialCanonical ? (initialCategory?.category_id ?? "") : "",
  );
  const [amount, setAmount] = useState(
    initialCanonical && initialAccount
      ? minorToInput(initialAccount.source_amount)
      : "",
  );
  const [fxRate, setFxRate] = useState("");
  const [manualRate, setManualRate] = useState<string | null>(
    initialFx ? String(initialAccount.fx_rate) : null,
  );
  const [date, setDate] = useState(
    initialDates?.booking_date ??
      initialLedger?.transaction_date ??
      localTodayIso(),
  );
  const [purchaseDate, setPurchaseDate] = useState(
    initialDates
      ? (initialDates.purchase_date ?? "")
      : (initialLedger?.transaction_date ?? localTodayIso()),
  );
  const [sameDate, setSameDate] = useState(
    (!initialDates || !!initialDates.purchase_date) &&
      (initialDates?.purchase_date ??
        initialLedger?.transaction_date ??
        localTodayIso()) ===
        (initialDates?.booking_date ??
          initialLedger?.transaction_date ??
          localTodayIso()),
  );
  const [description, setDescription] = useState(
    initialLedger?.description ?? "",
  );
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
  const allowsManualFx = type === "expense" || type === "income";
  const manualFxCurrency =
    allowsManualFx &&
    (sourceAccount?.currency === "EUR" || sourceAccount?.currency === "USD")
      ? sourceAccount.currency
      : null;
  const manualAccounts = allowsManualFx
    ? activeAccounts.filter(({ currency }) =>
        ["PLN", "EUR", "USD"].includes(currency),
      )
    : activePlnAccounts;
  const rateDay = type === "expense" && sameDate ? purchaseDate : date;
  const fxQuote = useTransactionFxQuote(
    onLedgerSubmit ? null : manualFxCurrency,
    rateDay,
  );
  const displayedRate = manualRate ?? fxQuote.data?.rate ?? "";
  const amountCurrency =
    type === "exchange"
      ? (sourceAccount?.currency ?? "PLN")
      : (manualFxCurrency ?? "PLN");

  function resetForm() {
    setType(DEFAULT_TYPE);
    setAccountId("");
    setToAccountId("");
    setCategoryId("");
    setFxRate("");
    setManualRate(null);
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
    setManualRate(null);
    setValidationError(null);
    if (
      (nextType === "transfer" || nextType === "expense_refund") &&
      sourceAccount?.currency !== "PLN"
    ) {
      setAccountId("");
      setAmount("");
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (editBusy) return;
    if (onLedgerSubmit && (type === "exchange" || type === "expense_refund"))
      return;

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
      if (!manualAccounts.some((account) => account.id === accountId)) {
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

    if ((type === "expense" || type === "income") && manualFxCurrency) {
      const rate = displayedRate.trim().replace(",", ".");
      if (
        !/^\d+(?:\.\d{1,6})?$/.test(rate) ||
        !(Number(rate) > 0 && Number(rate) < 1_000_000)
      ) {
        setValidationError(
          "Podaj kurs do PLN większy od zera (do 6 miejsc po przecinku).",
        );
        return;
      }
      const payload: ManualFxTransactionInput = {
        type,
        description: description.trim(),
        account_id: accountId,
        category_id: categoryId,
        currency: manualFxCurrency,
        amount_minor: amountGrosze,
        fx_rate: rate,
        ...(type === "expense"
          ? {
              purchase_date: purchaseDate || undefined,
              booking_date: sameDate && purchaseDate ? purchaseDate : date,
            }
          : { transaction_date: date }),
      };
      if (onLedgerSubmit) {
        onLedgerSubmit(
          { kind: "manual_fx", data: payload },
          accountId !== initialAccount?.account_id ||
            categoryId !== initialCategory?.category_id ||
            amountGrosze !== initialAccount?.source_amount ||
            Number(rate) !== initialAccount?.fx_rate ||
            payload.description !== initialLedger?.description ||
            (payload.booking_date
              ? payload.booking_date !== initialDates?.booking_date ||
                (payload.purchase_date ?? null) !==
                  (initialDates?.purchase_date ?? null)
              : date !== initialLedger?.transaction_date),
        );
        return;
      }
      create.mutate(
        {
          ...payload,
          ...(manualRate === null && fxQuote.data
            ? { fx_rate_source: "nbp" }
            : {}),
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

    const payload = {
      type,
      description: description.trim(),
      ...(hasPurchaseDate
        ? {
            purchase_date: purchaseDate || undefined,
            booking_date: sameDate && purchaseDate ? purchaseDate : date,
          }
        : { transaction_date: date }),
      postings,
      ...(initialLedger ? { is_pending: initialLedger.is_pending } : {}),
    };
    if (onLedgerSubmit) {
      const changed =
        !initialLedger ||
        type !== initialLedger.type ||
        description.trim() !== initialLedger.description ||
        accountId !== initialAccount?.account_id ||
        categoryId !== (initialCategory?.category_id ?? "") ||
        amountGrosze !== initialAccount?.source_amount ||
        (type === "transfer" && toAccountId !== initialToAccount?.account_id) ||
        (hasPurchaseDate &&
          (purchaseDate !== (initialDates?.purchase_date ?? "") ||
            (sameDate && purchaseDate ? purchaseDate : date) !==
              (initialDates?.booking_date ??
                initialLedger.transaction_date))) ||
        (!hasPurchaseDate && date !== initialLedger.transaction_date);
      onLedgerSubmit({ kind: "transaction", data: payload }, changed);
    } else {
      create.mutate(payload, {
        onSuccess: () => {
          resetForm();
          onSuccess?.();
        },
      });
    }
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
            disabled={initialFx || !!initialDates}
            onChange={(event) =>
              handleTypeChange(event.target.value as TransactionType)
            }
          >
            <option value="expense">Wydatek</option>
            {!onLedgerSubmit && (
              <option value="expense_refund">Zwrot wydatku</option>
            )}
            <option value="income">Przychód</option>
            <option value="transfer">Transfer</option>
            {!onLedgerSubmit && (
              <option value="exchange">Przewalutowanie</option>
            )}
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
            value={
              hasPurchaseDate && sameDate && purchaseDate ? purchaseDate : date
            }
            disabled={hasPurchaseDate && sameDate && !!purchaseDate}
            onChange={(event) => {
              setDate(event.target.value);
              if (!onLedgerSubmit) setManualRate(null);
            }}
          />
        </div>
        {hasPurchaseDate ? (
          <>
            <label className="block text-sm text-gray-400">
              Data zakupu
              <input
                className="input mt-1"
                type="date"
                required
                value={purchaseDate}
                onChange={(event) => {
                  setPurchaseDate(event.target.value);
                  if (sameDate && !onLedgerSubmit) setManualRate(null);
                }}
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={sameDate}
                onChange={(event) => {
                  setSameDate(event.target.checked);
                  if (!event.target.checked) setDate(purchaseDate);
                  if (!onLedgerSubmit) setManualRate(null);
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
                onChange={(event) => {
                  const next = manualAccounts.find(
                    (account) => account.id === event.target.value,
                  );
                  if (
                    sourceAccount &&
                    next?.currency !== sourceAccount.currency
                  ) {
                    setAmount("");
                    setFxRate("");
                    if (!onLedgerSubmit) setManualRate(null);
                  }
                  setAccountId(event.target.value);
                }}
              >
                <option value="">Wybierz konto</option>
                {manualAccounts
                  .filter(
                    (account) =>
                      !onLedgerSubmit ||
                      (initialFx
                        ? account.currency === initialAccount?.source_currency
                        : account.currency === "PLN"),
                  )
                  .map((account) => (
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
        {manualFxCurrency ? (
          <div>
            <label
              htmlFor="tx-manual-fx-rate"
              className="mb-1 block text-sm text-gray-400"
            >
              Kurs do PLN
            </label>
            <input
              id="tx-manual-fx-rate"
              className="input"
              inputMode="decimal"
              value={displayedRate}
              onChange={(event) => setManualRate(event.target.value)}
              aria-describedby="tx-manual-fx-help"
              placeholder="np. 4,25"
            />
            <p id="tx-manual-fx-help" className="mt-1 text-xs text-gray-400">
              {manualRate !== null
                ? `Kurs ręczny: ile PLN odpowiada 1 ${manualFxCurrency}?`
                : fxQuote.data
                  ? `Kurs NBP z ${fxQuote.data.effective_date} (PLN za 1 ${manualFxCurrency}).`
                  : fxQuote.isPending && rateDay
                    ? "Pobieram kurs NBP…"
                    : "Nie ma kursu NBP dla tej daty. Możesz wpisać kurs ręcznie."}
            </p>
            {manualRate !== null && fxQuote.data ? (
              <button
                type="button"
                className="btn-secondary mt-1"
                onClick={() => setManualRate(null)}
              >
                Użyj kursu NBP
              </button>
            ) : null}
          </div>
        ) : null}
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
          disabled={
            editBusy ||
            create.isPending ||
            exchange.isPending ||
            refund.isPending
          }
        >
          {onLedgerSubmit ? "Zapisz zmiany" : "Zapisz transakcję"}
        </button>
      </div>
    </form>
  );
}
