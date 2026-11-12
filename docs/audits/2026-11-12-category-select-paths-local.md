# Jednolite selecty kategorii — odbiór lokalny

## Zatwierdzony zakres

Każdy finansowy wybór kategorii pokazuje pełną dostępną ścieżkę, np. `Dom - Gaz`
albo `Dom - Media - Prąd`, i jest sortowany rosnąco po całej ścieżce zgodnie
z polskim alfabetem, bez rozróżniania wielkości liter. Nazwy iID kategorii, dane
w bazie i obecne ograniczenia wyboru pozostają bez zmian.

Plan: `docs/superpowers/plans/2026-11-12-category-select-paths.md`.
BAZA:493bf48, existinglinkedworktree. Nie zmieniono backendu, API, migracji, zależności,
formatowania breadcrumbów poza selectami ani danych produkcyjnych.

## Implementacja i kompletność

- Jeden builder `categoryOptions(visible, hierarchy)` tworzy nowe kopie opcji
  z etykietą i sortuje je przez `Intl.Collator("pl", {sensitivity:"base"})`.
  Wspólna mapaID dla całej operacji; brak modyfikacji danych cache, bez zapętlenia
  dla brakujących/cyklicznych przodków. Dla równych etykiet deterministyczny IDtie-break.
- CategoryPicker: transakcje, splity, cykliczne, budżety, reguły, produkty paragonów
  i ustawienia kategoryzacji. Zachowane wyszukiwanie iretencja aktualnego wyboru.
- TransactionForm iScheduledItemForm przekazują pełną hierarchię obok prefiltrowanej
  listy dopuszczonych opcji. Aktywne dziecko archiwalnego rodzica zachowuje jego nazwę,
  bez dodawania rodzica do listy dopuszczonych wartości.
- Natywne selecty: TransactionFilters, DocumentReview, BillPaymentDialog,
  ImportGroupEditor (operacja iopłata), FinanceCreditCardDetails, FinanceAccounts
  (nowy rodzic), CategoryTreeEditor iCategorySettingsRow (edycja rodzica).
- Placeholdery iarchiwalne oznaczenia zachowane. Przenoszenie kategorii nadal nie
  dopuszcza self/descendant; dotychczasowe ograniczenia typu nie zostały zmienione.

## Dowody

- Baseline631PASS. Helper/pickerRED9FAIL/1PASS→GREEN12PASS.
- ConsumersRED9FAIL/94PASS; scheduledRED1FAIL/3PASS→117focusedPASS.
- Pełnyfrontend648PASS/107plików, ESLint/tsc/buildPASS. Build zachowuje istniejące
  ostrzeżenie o bundle>500kB. Backend nie był ponownie uruchamiany dla frontend-only.
- Jeden świeży review `ses_e303a1810ffeAMh6eWbvWSOrxi`:0Critical/Important/Minor,
  „Declined to judge”:puste. Reviewer potwierdził kompletność zidentyfikowanych selectów.
- Pierwszy Playwright:78PASS/2FAIL wyłącznie w nowym teście filtra. Snapshot pokazał
  poprawnie posortowane pełne etykiety; exactgetByLabel nie znajdował implicitlabel
  zawierającego opcje. Test poprawiony do roli combobox z nazwąKategoria, bez zmiany
  produktu. Pełny ponowny przebieg: **80PASS**, desktop/mobile,9dotkniętychspeców.
- Obejrzano screeny375/1440 formularza transakcji: etykiety pełne, wybranyID bez zmian,
  brak horizontaloverflow. Przeglądarka używa wyłącznie syntetycznego API.

## Stan integracji

Odbiór lokalny zakończony:648vitest/80E2E, lint/types/buildPASS, review bez uwag.
Żadnego merge/push/deploy ani mutacji
produkcji w tym zadaniu. Brak odłożonych uwagreview i odstępstw od zatwierdzonego zakresu.
Unrelateddirtydocs/audity pozostają poza commitem tej funkcji.
