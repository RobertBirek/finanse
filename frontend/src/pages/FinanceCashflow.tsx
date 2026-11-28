import { useState } from "react";
import { Link } from "react-router-dom";
import {
  canConfirmSuggestion,
  cashflowStatusLabel,
  useAccounts,
  useCategories,
  useCashflowForecast,
  useConditionalRecurringObligations,
  useScheduledFinanceItems,
  type CashflowSuggestion,
  type ScheduledFinanceItem,
} from "../api/finance";
import { formatPLN } from "../lib/format";
import { formatCalendarDate, localTodayIso } from "../lib/date";
import { CashflowForecast } from "../components/finance/CashflowForecast";
import { CashflowSettingsForm } from "../components/finance/CashflowSettingsForm";
import { ConfirmScheduledItemDialog } from "../components/finance/ConfirmScheduledItemDialog";
import { ScheduledItemForm } from "../components/finance/ScheduledItemForm";
import { ScheduledItemsList } from "../components/finance/ScheduledItemsList";
import { ConditionalRecurringObligations } from "../components/finance/ConditionalRecurringObligations";
import { QueryFeedback } from "../components/QueryFeedback";
import { PageHeader } from "../components/PageHeader";

export function FinanceCashflow({
  configure = true,
  settingsSection = "all",
}: {
  configure?: boolean;
  settingsSection?: "all" | "schedules" | "forecast";
}) {
  const accounts = useAccounts();
  const categories = useCategories();
  const items = useScheduledFinanceItems();
  const forecast = useCashflowForecast();
  const conditionalObligations = useConditionalRecurringObligations();

  const [editingItem, setEditingItem] = useState<ScheduledFinanceItem | null>(
    null,
  );
  const [suggestionForDialog, setSuggestionForDialog] =
    useState<CashflowSuggestion | null>(null);

  const todayIso = localTodayIso();
  const allItems = items.data ?? [];
  const suggestions = forecast.data?.suggestions ?? [];
  const eligibleItems = new Set(
    allItems
      .filter((item) => {
        const account = accounts.data?.find(({ id }) => id === item.account_id);
        const category = categories.data?.find(
          ({ id }) => id === item.category_id,
        );
        return (
          item.is_active &&
          item.currency === "PLN" &&
          account?.is_active &&
          account.is_budget_account &&
          account.currency === item.currency &&
          category?.is_active &&
          category.type === item.type
        );
      })
      .map(({ id }) => id),
  );
  const confirmable = suggestions.filter(
    (suggestion) =>
      suggestion.source !== "financial_document" &&
      canConfirmSuggestion(suggestion, todayIso) &&
      eligibleItems.has(suggestion.scheduled_item_id ?? ""),
  );
  const otherSuggestions = suggestions.filter(
    (suggestion) =>
      suggestion.status !== "matched_actual" &&
      !confirmable.includes(suggestion),
  );
  const itemForDialog =
    suggestionForDialog && suggestionForDialog.source !== "financial_document"
      ? (allItems.find(
          (item) => item.id === suggestionForDialog.scheduled_item_id,
        ) ?? null)
      : null;

  return (
    <div className="page-workspace">
      <PageHeader
        title={
          configure
            ? settingsSection === "forecast"
              ? "Parametry prognozy"
              : settingsSection === "schedules"
                ? "Harmonogramy"
                : "Płynność"
            : "Płynność"
        }
      />

      {!configure || settingsSection === "all" ? (
        <CashflowForecast
          forecast={forecast.data}
          loading={forecast.isLoading}
          error={forecast.isError}
        />
      ) : null}

      {configure && settingsSection !== "schedules" ? (
        <CashflowSettingsForm />
      ) : null}

      {settingsSection !== "forecast" ? (
        <section className="mb-6">
          <h2 className="mb-4 text-lg font-semibold text-white">
            Zaplanowane pozycje
          </h2>
          {configure ? (
            <ScheduledItemForm
              key={editingItem?.id ?? "create"}
              mode={editingItem ? "edit" : "create"}
              accounts={accounts.data ?? []}
              categories={categories.data ?? []}
              initialItem={editingItem ?? undefined}
              onCancel={editingItem ? () => setEditingItem(null) : undefined}
              onSuccess={() => setEditingItem(null)}
            />
          ) : null}
          <ScheduledItemsList
            items={allItems}
            suggestions={suggestions}
            loading={items.isLoading}
            error={items.isError}
            onEdit={configure ? setEditingItem : undefined}
          />
        </section>
      ) : null}
      {configure && settingsSection !== "forecast" ? (
        <ConditionalRecurringObligations
          accounts={accounts.data ?? []}
          items={conditionalObligations.data ?? []}
          loading={conditionalObligations.isLoading}
        />
      ) : null}

      {!configure || settingsSection === "all" ? (
        <section>
          <h2 className="mb-4 text-lg font-semibold text-white">
            Do potwierdzenia
          </h2>
          <QueryFeedback
            loading={
              forecast.isLoading ||
              items.isLoading ||
              accounts.isLoading ||
              categories.isLoading
            }
            error={
              forecast.isError ||
              items.isError ||
              accounts.isError ||
              categories.isError
            }
            errorMessage="Nie udało się pobrać pozycji do potwierdzenia."
            onRetry={() => {
              if (forecast.isError) void forecast.refetch();
              if (items.isError) void items.refetch();
              if (accounts.isError) void accounts.refetch();
              if (categories.isError) void categories.refetch();
            }}
          >
            {confirmable.length === 0 ? (
              <p className="card text-sm text-gray-500">
                Brak pozycji wymagających potwierdzenia.
              </p>
            ) : (
              <ul className="space-y-2">
                {confirmable.map((suggestion) => (
                  <li
                    key={suggestion.source_key}
                    className="card flex flex-wrap items-center justify-between gap-3 p-4"
                  >
                    <ForecastSuggestionDetails suggestion={suggestion} />
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => setSuggestionForDialog(suggestion)}
                    >
                      Potwierdź
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </QueryFeedback>
        </section>
      ) : null}
      {(!configure || settingsSection === "all") &&
      !forecast.isLoading &&
      !forecast.isError &&
      otherSuggestions.length ? (
        <section className="mt-6">
          <h2 className="mb-4 text-lg font-semibold text-white">
            Pozostałe pozycje prognozy
          </h2>
          <ul className="space-y-2">
            {otherSuggestions.map((suggestion) => (
              <li
                key={suggestion.source_key}
                className="card flex flex-wrap items-center justify-between gap-3 p-4"
              >
                <ForecastSuggestionDetails suggestion={suggestion} />
                {suggestion.financial_document_id ? (
                  <Link
                    className="btn-secondary"
                    to={`/finances/documents?bill=${suggestion.financial_document_id}`}
                  >
                    Otwórz dokument
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {suggestionForDialog && itemForDialog ? (
        <ConfirmScheduledItemDialog
          suggestion={suggestionForDialog}
          item={itemForDialog}
          onClose={() => setSuggestionForDialog(null)}
        />
      ) : null}
    </div>
  );
}

function ForecastSuggestionDetails({
  suggestion,
}: {
  suggestion: CashflowSuggestion;
}) {
  return (
    <div className="min-w-0">
      <p className="break-words text-sm font-medium text-white">
        {suggestion.name}
      </p>
      <p className="mt-0.5 text-xs text-gray-500">
        {suggestion.due_date
          ? formatCalendarDate(suggestion.due_date)
          : "Brak terminu"}
        {" · "}
        {cashflowStatusLabel(suggestion.status)}
        {suggestion.amount_pln != null
          ? ` · ${formatPLN(suggestion.amount_pln)} PLN`
          : suggestion.amount_minor != null
            ? ` · ${(suggestion.amount_minor / 100).toFixed(2)} ${suggestion.currency}`
            : ""}
      </p>
    </div>
  );
}
