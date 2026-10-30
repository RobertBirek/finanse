import { useState } from "react";
import { Link } from "react-router-dom";
import {
  canConfirmSuggestion,
  cashflowStatusLabel,
  useAccounts,
  useCategories,
  useCashflowForecast,
  useScheduledFinanceItems,
  type CashflowSuggestion,
  type ScheduledFinanceItem,
} from "../api/finance";
import { formatPLN } from "../lib/format";
import { localTodayIso } from "../lib/date";
import { CashflowForecast } from "../components/finance/CashflowForecast";
import { CashflowSettingsForm } from "../components/finance/CashflowSettingsForm";
import { ConfirmScheduledItemDialog } from "../components/finance/ConfirmScheduledItemDialog";
import { ScheduledItemForm } from "../components/finance/ScheduledItemForm";
import { ScheduledItemsList } from "../components/finance/ScheduledItemsList";
import { FinanceTabs } from "../components/finance/FinanceTabs";

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

  const [editingItem, setEditingItem] = useState<ScheduledFinanceItem | null>(
    null,
  );
  const [suggestionForDialog, setSuggestionForDialog] =
    useState<CashflowSuggestion | null>(null);

  const todayIso = localTodayIso();
  const allItems = items.data ?? [];
  const suggestions = forecast.data?.suggestions ?? [];
  const itemForDialog =
    suggestionForDialog && suggestionForDialog.source !== "financial_document"
      ? (allItems.find(
          (item) => item.id === suggestionForDialog.scheduled_item_id,
        ) ?? null)
      : null;

  return (
    <div className="max-w-5xl">
      <h1 className="mb-2 text-2xl font-bold text-white">
        {configure
          ? settingsSection === "forecast"
            ? "Parametry prognozy"
            : settingsSection === "schedules"
              ? "Harmonogramy"
              : "Płynność"
          : "Nadchodzące"}
      </h1>
      {!configure ? <FinanceTabs /> : null}

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

      {!configure || settingsSection === "all" ? (
        <section>
          <h2 className="mb-4 text-lg font-semibold text-white">
            Do potwierdzenia
          </h2>
          {suggestions.length === 0 ? (
            <p className="card text-sm text-gray-500">
              Brak pozycji wymagających potwierdzenia.
            </p>
          ) : (
            <div className="space-y-2">
              {suggestions.map((suggestion) => {
                const canConfirm = canConfirmSuggestion(suggestion, todayIso);
                return (
                  <div
                    key={suggestion.source_key}
                    className="card flex items-center justify-between gap-3 p-4"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-white">
                        {suggestion.name}
                      </p>
                      <p className="mt-0.5 text-xs text-gray-500">
                        {suggestion.due_date
                          ? new Date(suggestion.due_date).toLocaleDateString(
                              "pl-PL",
                            )
                          : "Brak terminu"}{" "}
                        · {cashflowStatusLabel(suggestion.status)}
                        {suggestion.amount_pln != null
                          ? ` · ${formatPLN(suggestion.amount_pln)} PLN`
                          : ""}
                      </p>
                    </div>
                    {suggestion.source === "financial_document" ? (
                      <Link
                        className="btn-primary"
                        to={`/finances/documents?bill=${suggestion.financial_document_id}`}
                      >
                        Otwórz dokument
                      </Link>
                    ) : (
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={!canConfirm}
                        onClick={() => setSuggestionForDialog(suggestion)}
                      >
                        Potwierdź
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
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
