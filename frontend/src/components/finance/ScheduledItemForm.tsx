import { useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import {
  parsePlnToGrosze,
  useCreateScheduledFinanceItem,
  useUpdateScheduledFinanceItem,
  type Account,
  type Category,
  type ScheduledFinanceItem,
  type ScheduledFinanceItemInput,
} from "../../api/finance";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

type ScheduledItemFormProps = {
  mode: "create" | "edit";
  accounts: Account[];
  categories: Category[];
  initialItem?: ScheduledFinanceItem;
  onCancel?: () => void;
  onSuccess?: () => void;
};

export function ScheduledItemForm({
  mode,
  accounts,
  categories,
  initialItem,
  onCancel,
  onSuccess,
}: ScheduledItemFormProps) {
  const createMutation = useCreateScheduledFinanceItem();
  const updateMutation = useUpdateScheduledFinanceItem();

  const [name, setName] = useState(initialItem?.name ?? "");
  const [type, setType] = useState<"income" | "expense">(
    initialItem?.type ?? "expense",
  );
  const [accountId, setAccountId] = useState(initialItem?.account_id ?? "");
  const [categoryId, setCategoryId] = useState(initialItem?.category_id ?? "");
  const [dueDay, setDueDay] = useState(initialItem?.due_day ?? 1);
  const [amountMethod, setAmountMethod] = useState<"fixed" | "last_actual">(
    initialItem?.amount_method ?? "fixed",
  );
  const [amount, setAmount] = useState(
    initialItem?.fixed_amount_pln != null
      ? (initialItem.fixed_amount_pln / 100).toFixed(2)
      : "",
  );

  const budgetAccounts = accounts.filter(
    (account) => account.is_budget_account && account.is_active,
  );
  const filteredCategories = categories.filter(
    (category) => category.type === type,
  );
  const selectedAccount = budgetAccounts.find(
    (account) => account.id === accountId,
  );

  const isPending =
    mode === "create" ? createMutation.isPending : updateMutation.isPending;
  const error = mode === "create" ? createMutation.error : updateMutation.error;
  const errorMessage = apiErrorDetail(error);

  const amountValid =
    amountMethod === "last_actual" || parsePlnToGrosze(amount) !== null;
  const canSubmit =
    name.trim().length > 0 && !!accountId && !!categoryId && amountValid;

  function handleTypeChange(nextType: "income" | "expense") {
    setType(nextType);
    if (!categories.some((c) => c.id === categoryId && c.type === nextType)) {
      setCategoryId("");
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const account = budgetAccounts.find((item) => item.id === accountId);
    const payload: ScheduledFinanceItemInput = {
      name: name.trim(),
      type,
      account_id: accountId,
      category_id: categoryId,
      currency: account?.currency ?? "PLN",
      due_day: dueDay,
      amount_method: amountMethod,
      fixed_amount_pln:
        amountMethod === "fixed" ? parsePlnToGrosze(amount) : null,
    };

    if (mode === "create") {
      createMutation.mutate(payload, { onSuccess });
    } else if (initialItem) {
      updateMutation.mutate({ id: initialItem.id, ...payload }, { onSuccess });
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card mb-4">
      <h3 className="mb-4 text-base font-semibold text-white">
        {mode === "create" ? "Nowa pozycja" : "Edytuj pozycję"}
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label
            htmlFor="item-name"
            className="mb-1 block text-sm text-gray-400"
          >
            Nazwa
          </label>
          <input
            id="item-name"
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div>
          <label
            htmlFor="item-type"
            className="mb-1 block text-sm text-gray-400"
          >
            Typ
          </label>
          <select
            id="item-type"
            className="input"
            value={type}
            disabled={mode === "edit"}
            onChange={(event) =>
              handleTypeChange(event.target.value as "income" | "expense")
            }
          >
            <option value="income">Przychód</option>
            <option value="expense">Wydatek</option>
          </select>
        </div>
        <div>
          <label
            htmlFor="item-account"
            className="mb-1 block text-sm text-gray-400"
          >
            Konto
          </label>
          <select
            id="item-account"
            className="input"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">Wybierz konto</option>
            {budgetAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor="item-currency"
            className="mb-1 block text-sm text-gray-400"
          >
            Waluta
          </label>
          <input
            id="item-currency"
            className="input opacity-60"
            value={selectedAccount?.currency ?? ""}
            disabled
          />
        </div>
        <div>
          <label
            htmlFor="item-category"
            className="mb-1 block text-sm text-gray-400"
          >
            Kategoria
          </label>
          <select
            id="item-category"
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
        <div>
          <label
            htmlFor="item-due-day"
            className="mb-1 block text-sm text-gray-400"
          >
            Dzień (1-28)
          </label>
          <input
            id="item-due-day"
            type="number"
            min={1}
            max={28}
            className="input"
            value={dueDay}
            onChange={(event) => setDueDay(Number(event.target.value))}
          />
        </div>
        <div>
          <label
            htmlFor="item-amount-method"
            className="mb-1 block text-sm text-gray-400"
          >
            Metoda kwoty
          </label>
          <select
            id="item-amount-method"
            className="input"
            value={amountMethod}
            onChange={(event) =>
              setAmountMethod(event.target.value as "fixed" | "last_actual")
            }
          >
            <option value="fixed">Stała kwota</option>
            <option value="last_actual">Ostatnia rzeczywista</option>
          </select>
        </div>
        {amountMethod === "fixed" ? (
          <div>
            <label
              htmlFor="item-amount"
              className="mb-1 block text-sm text-gray-400"
            >
              Kwota (PLN)
            </label>
            <input
              id="item-amount"
              className="input"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="np. 1 234,56"
            />
          </div>
        ) : null}
      </div>
      {errorMessage ? (
        <p className="mt-4 text-sm text-red-400">{errorMessage}</p>
      ) : null}
      <div className="mt-4 flex justify-end gap-2">
        {onCancel ? (
          <button
            type="button"
            className="btn-secondary"
            disabled={isPending}
            onClick={onCancel}
          >
            Anuluj
          </button>
        ) : null}
        <button
          type="submit"
          className="btn-primary"
          disabled={isPending || !canSubmit}
        >
          {mode === "create" ? "Dodaj pozycję" : "Zapisz zmiany"}
        </button>
      </div>
    </form>
  );
}
