import type { CashflowForecast } from "../api/finance";

export function hasPaydayExclusions(forecast: CashflowForecast): boolean {
  return (
    forecast.has_excluded_obligations_before_payday ??
    forecast.has_excluded_obligations ??
    false
  );
}

export function forecastExclusionLabel(reason: string): string {
  const labels: Record<string, string> = {
    recurring_match_uncertain: "niejednoznaczne dopasowanie płatności",
    recurring_amount_unknown: "brak kwoty płatności cyklicznej",
    recurring_overdue_uncertain: "zaległa płatność cykliczna do sprawdzenia",
    missing_due_date: "brak terminu płatności",
    currency_without_pln_fx: "brak przeliczenia na PLN",
    missing_payment_account: "brak konta płatności",
    payment_account_not_active_budget_pln: "konto poza zakresem prognozy",
    coverage_unresolved: "nieustalone powiązanie z płatnością cykliczną",
    outside_horizon: "termin poza horyzontem",
    inactive_lifecycle: "dokument nieaktywny",
    payment_declaration_unknown: "nieustalony status płatności",
    payment_not_payable: "dokument niekwalifikujący się do prognozy",
  };
  return labels[reason] ?? "brak pełnych danych";
}
