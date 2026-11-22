const reasons: Record<string, string> = {
  account_unresolved: "Nie udało się jednoznacznie ustalić rachunku.",
  opening_gap: "Saldo otwarcia nie zgadza się z księgą lub jest niedostępne.",
  source_validation_blocked: "Odczyt lub kontrola wyciągu wymaga sprawdzenia.",
  card_statement_review: "Wyciąg karty kredytowej wymaga uzgodnienia cyklu.",
  import_archived: "Import został zarchiwizowany.",
  settings_changed: "Ustawienia zmieniły się po zleceniu księgowania.",
  too_many_rows: "Wyciąg przekracza limit automatycznego księgowania.",
  processing_failed: "Nie udało się przetworzyć zlecenia.",
  source_integrity_failed: "Nie udało się potwierdzić zgodności oryginału.",
  movement_unclear: "Rodzaj operacji wymaga sprawdzenia.",
  not_postable: "Bank nie zaksięgował tej pozycji albo jej kwota wynosi zero.",
  fee_review: "Operacja zawiera opłatę bankową.",
  possible_duplicate: "Możliwy duplikat.",
  manual_decision: "Ta pozycja ma już zapisaną decyzję ręczną.",
  category_unavailable: "Brak aktywnej kategorii dla tego typu operacji.",
  fx_review: "Operacja w obcej walucie wymaga sprawdzenia kursu.",
};

export function importAutoPostReason(code: string): string {
  return reasons[code] ?? "Kontrole importu wymagają ręcznego sprawdzenia.";
}
