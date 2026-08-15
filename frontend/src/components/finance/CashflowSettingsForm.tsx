import { useEffect, useState, type FormEvent } from "react";
import type { AxiosError } from "axios";
import {
  useAccounts,
  useCashflowSettings,
  useUpdateCashflowSettings,
} from "../../api/finance";

function apiErrorDetail(error: unknown): string | null {
  if (!error) return null;
  return (
    (error as AxiosError<{ detail?: string }>)?.response?.data?.detail ?? null
  );
}

type SettingsFormState = {
  payday_day: number | "";
  payday_account_id: string | null;
  forecast_horizon_days: number | "";
  overdue_grace_days: number | "";
};

export function CashflowSettingsForm() {
  const settingsQuery = useCashflowSettings();
  const accountsQuery = useAccounts();
  const updateMutation = useUpdateCashflowSettings();

  const [form, setForm] = useState<SettingsFormState | null>(null);

  useEffect(() => {
    if (settingsQuery.data && form === null) {
      setForm({
        payday_day: settingsQuery.data.payday_day,
        payday_account_id: settingsQuery.data.payday_account_id,
        forecast_horizon_days: settingsQuery.data.forecast_horizon_days,
        overdue_grace_days: settingsQuery.data.overdue_grace_days,
      });
    }
  }, [settingsQuery.data, form]);

  if (settingsQuery.isLoading || accountsQuery.isLoading || form === null) {
    return (
      <div className="mb-6 flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
      </div>
    );
  }

  if (settingsQuery.isError || accountsQuery.isError) {
    return (
      <p className="card mb-6 text-sm text-red-400">
        Nie udało się pobrać ustawień płynności.
      </p>
    );
  }

  const budgetAccounts = (accountsQuery.data ?? []).filter(
    (account) => account.is_budget_account && account.is_active,
  );

  function setField<K extends keyof SettingsFormState>(
    key: K,
    value: SettingsFormState[K],
  ) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    updateMutation.mutate({
      payday_day: form.payday_day === "" ? undefined : form.payday_day,
      payday_account_id: form.payday_account_id,
      forecast_horizon_days:
        form.forecast_horizon_days === ""
          ? undefined
          : form.forecast_horizon_days,
      overdue_grace_days:
        form.overdue_grace_days === "" ? undefined : form.overdue_grace_days,
    });
  }

  const errorMessage = apiErrorDetail(updateMutation.error);

  return (
    <section className="card mb-6">
      <h2 className="mb-4 text-lg font-semibold text-white">
        Ustawienia płynności
      </h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="payday-day"
              className="mb-1 block text-sm text-gray-400"
            >
              Dzień wypłaty
            </label>
            <input
              id="payday-day"
              type="number"
              min={1}
              max={28}
              className="input"
              value={form.payday_day}
              onChange={(event) =>
                setField(
                  "payday_day",
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </div>
          <div>
            <label
              htmlFor="payday-account"
              className="mb-1 block text-sm text-gray-400"
            >
              Konto wypłaty
            </label>
            <select
              id="payday-account"
              className="input"
              value={form.payday_account_id ?? ""}
              onChange={(event) =>
                setField("payday_account_id", event.target.value || null)
              }
            >
              <option value="">Brak</option>
              {budgetAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="forecast-horizon"
              className="mb-1 block text-sm text-gray-400"
            >
              Horyzont prognozy (dni)
            </label>
            <input
              id="forecast-horizon"
              type="number"
              min={1}
              max={90}
              className="input"
              value={form.forecast_horizon_days}
              onChange={(event) =>
                setField(
                  "forecast_horizon_days",
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </div>
          <div>
            <label
              htmlFor="overdue-grace"
              className="mb-1 block text-sm text-gray-400"
            >
              Tolerancja opóźnienia (dni)
            </label>
            <input
              id="overdue-grace"
              type="number"
              min={0}
              max={14}
              className="input"
              value={form.overdue_grace_days}
              onChange={(event) =>
                setField(
                  "overdue_grace_days",
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </div>
        </div>
        {errorMessage ? (
          <p className="text-sm text-red-400">{errorMessage}</p>
        ) : null}
        <button
          type="submit"
          className="btn-primary"
          disabled={updateMutation.isPending}
        >
          Zapisz ustawienia
        </button>
      </form>
    </section>
  );
}
