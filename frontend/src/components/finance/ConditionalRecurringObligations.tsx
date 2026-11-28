import { useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import {
  parsePlnToGrosze,
  useCreateConditionalRecurringObligation,
  useDeleteConditionalRecurringObligation,
  useUpdateConditionalRecurringObligation,
  type Account,
  type ConditionalRecurringObligation,
  type ConditionalRecurringObligationInput,
} from "../../api/finance";

const currencies = ["USD", "EUR", "PLN"] as const;

function detail(error: unknown) {
  return (error as AxiosError<{ detail?: string }> | undefined)?.response?.data
    ?.detail;
}

export function ConditionalRecurringObligations({
  accounts,
  items,
  loading,
}: {
  accounts: Account[];
  items: ConditionalRecurringObligation[];
  loading: boolean;
}) {
  const create = useCreateConditionalRecurringObligation();
  const remove = useDeleteConditionalRecurringObligation();
  const update = useUpdateConditionalRecurringObligation();
  const [name, setName] = useState("");
  const [conditionKey, setConditionKey] = useState("");
  const [dueDay, setDueDay] = useState("1");
  const [primaryAccount, setPrimaryAccount] = useState("");
  const [primaryCurrency, setPrimaryCurrency] = useState<"USD" | "EUR" | "PLN">(
    "USD",
  );
  const [primaryAmount, setPrimaryAmount] = useState("");
  const [fallbackAccount, setFallbackAccount] = useState("");
  const [fallbackCurrency, setFallbackCurrency] = useState<
    "USD" | "EUR" | "PLN"
  >("PLN");
  const [fallbackAmount, setFallbackAmount] = useState("");
  const usable = accounts.filter(
    (account) => account.is_active && account.is_budget_account,
  );
  const valid =
    name.trim() &&
    conditionKey.trim() &&
    primaryAccount &&
    fallbackAccount &&
    primaryAccount !== fallbackAccount &&
    Number(dueDay) >= 1 &&
    Number(dueDay) <= 28 &&
    parsePlnToGrosze(primaryAmount) !== null;

  function submit(event: FormEvent) {
    event.preventDefault();
    const primary = parsePlnToGrosze(primaryAmount);
    const fallback = parsePlnToGrosze(fallbackAmount);
    if (!valid || primary === null) return;
    const input: ConditionalRecurringObligationInput = {
      name: name.trim(),
      condition_key: conditionKey.trim(),
      condition_state: "unknown",
      cadence: "monthly",
      due_month: null,
      due_day: Number(dueDay),
      primary_account_id: primaryAccount,
      primary_amount_minor: primary,
      primary_currency: primaryCurrency,
      fallback_account_id: fallbackAccount,
      fallback_amount_minor: fallback,
      fallback_currency: fallbackCurrency,
    };
    create.mutate(input, {
      onSuccess: () => {
        setName("");
        setConditionKey("");
        setPrimaryAmount("");
        setFallbackAmount("");
      },
    });
  }

  return (
    <section className="mb-6">
      <h2 className="mb-2 text-lg font-semibold text-white">
        Warunkowe zobowiązania walutowe
      </h2>
      <p className="mb-4 text-sm text-amber-300">
        To deklaracja bez księgowania. Kwoty walutowe blokują bezpieczny limit
        dzienny, dopóki nie ma jawnej wyceny.
      </p>
      <form onSubmit={submit} className="card mb-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-sm text-gray-400">
            Nazwa zobowiązania
            <input
              className="input mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="text-sm text-gray-400">
            Klucz warunku
            <input
              className="input mt-1"
              value={conditionKey}
              onChange={(e) => setConditionKey(e.target.value)}
              placeholder="np. account_eligible"
            />
          </label>
          <label className="text-sm text-gray-400">
            Dzień terminu (1–28)
            <input
              className="input mt-1"
              type="number"
              min="1"
              max="28"
              value={dueDay}
              onChange={(e) => setDueDay(e.target.value)}
            />
          </label>
          <div />
          <VariantFields
            label="Podstawowa"
            account={primaryAccount}
            currency={primaryCurrency}
            amount={primaryAmount}
            accounts={usable}
            onAccount={setPrimaryAccount}
            onCurrency={setPrimaryCurrency}
            onAmount={setPrimaryAmount}
          />
          <VariantFields
            label="Zapasowa"
            account={fallbackAccount}
            currency={fallbackCurrency}
            amount={fallbackAmount}
            accounts={usable}
            onAccount={setFallbackAccount}
            onCurrency={setFallbackCurrency}
            onAmount={setFallbackAmount}
            amountOptional
          />
        </div>
        {detail(create.error) ? (
          <p className="mt-3 text-sm text-red-400">{detail(create.error)}</p>
        ) : null}
        <button
          className="btn-primary mt-4"
          disabled={!valid || create.isPending}
        >
          Dodaj zobowiązanie
        </button>
      </form>
      {loading ? <p className="text-sm text-gray-500">Ładowanie…</p> : null}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-800 bg-gray-800/40 p-3"
          >
            <div>
              <p className="text-sm font-medium text-white">{item.name}</p>
              <p className="text-xs text-gray-500">
                warunek: {item.condition_key} · dzień {item.due_day} ·{" "}
                {item.condition_state === "unknown"
                  ? "nierozstrzygnięty"
                  : item.condition_state}
              </p>
            </div>
            <div className="text-right text-xs text-gray-400">
              <p>
                podstawowa: {(item.primary_amount_minor / 100).toFixed(2)}{" "}
                {item.primary_currency}
              </p>
              <p>
                zapasowa:{" "}
                {item.fallback_amount_minor == null
                  ? "kwota nieznana"
                  : `${(item.fallback_amount_minor / 100).toFixed(2)} ${item.fallback_currency}`}
              </p>
            </div>
            <label className="text-xs text-gray-400">
              Stan warunku
              <select
                className="input mt-1"
                value={item.condition_state}
                disabled={update.isPending}
                onChange={(event) =>
                  update.mutate({
                    id: item.id,
                    condition_state: event.target.value as
                      "unknown" | "satisfied" | "not_satisfied",
                  })
                }
              >
                <option value="unknown">Nierozstrzygnięty</option>
                <option value="satisfied">
                  Spełniony — wariant podstawowy
                </option>
                <option value="not_satisfied">
                  Niespełniony — wariant zapasowy
                </option>
              </select>
            </label>
            <button
              className="btn-danger px-3 py-1.5 text-sm"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(`Usunąć zobowiązanie "${item.name}"?`))
                  remove.mutate(item.id);
              }}
            >
              Usuń
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function VariantFields({
  label,
  account,
  currency,
  amount,
  accounts,
  onAccount,
  onCurrency,
  onAmount,
  amountOptional = false,
}: {
  label: string;
  account: string;
  currency: "USD" | "EUR" | "PLN";
  amount: string;
  accounts: Account[];
  onAccount: (value: string) => void;
  onCurrency: (value: "USD" | "EUR" | "PLN") => void;
  onAmount: (value: string) => void;
  amountOptional?: boolean;
}) {
  return (
    <fieldset className="rounded border border-gray-800 p-3">
      <legend className="px-1 text-sm text-gray-300">{label}</legend>
      <label className="block text-xs text-gray-400">
        Konto
        <select
          className="input mt-1"
          value={account}
          onChange={(e) => onAccount(e.target.value)}
        >
          <option value="">Wybierz konto</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.currency})
            </option>
          ))}
        </select>
      </label>
      <label className="mt-2 block text-xs text-gray-400">
        Waluta
        <select
          className="input mt-1"
          value={currency}
          onChange={(e) => onCurrency(e.target.value as "USD" | "EUR" | "PLN")}
        >
          {currencies.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <label className="mt-2 block text-xs text-gray-400">
        {amountOptional ? "Kwota (opcjonalna, jeśli nieznana)" : "Kwota"}
        <input
          className="input mt-1"
          value={amount}
          onChange={(e) => onAmount(e.target.value)}
        />
      </label>
    </fieldset>
  );
}
