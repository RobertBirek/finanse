# Jednolite ścieżki i sortowanie wyborów kategorii

Użytkownik zatwierdził w czacie: wszystkie finansowe selecty z kategoriami pokazują
pełną ścieżkę `Dom - Gaz`, także wiele poziomów, oraz sortują po niej rosnąco po polsku.
Nie zmieniać ID, danych, filtrów typów/aktywności, zachowania wybranej wartości,
reguł wyboru rodzica ani opcji pustych. Bez backendu, migracji lub wdrożenia.

## Global Constraints

- Istniejący linked worktree, BASE493bf48; zachować unrelated dirtydocs/audity.
- Wyłącznie frontend i dokumentacja. Pełna hierarchia musi być dostępna do budowy
  ścieżki, nawet gdy rodzic jest archiwalny albo nie jest dozwoloną opcją wyboru.
- Istniejące breadcrumbs/informacyjne etykiety poza selectami pozostają bez zmian.
- Nie mutować listy z cache TanStackQuery. Cykle/brak przodka nie mogą zawieszać UI.
- Placeholdery, archiwalne oznaczenia i wysyłane ID pozostają jak dotychczas.

## Review Focus

- Sortowanie pełnej ścieżki, nie nazwy liścia: odwrócona kolejność rodziców/liści,
  polskie litery, różne wielkości liter, identyczne nazwy pod różnymi rodzicami.
- Aktywne dziecko archiwalnego rodzica oraz prefiltrowane kategorie nadal mają
  całą dostępną ścieżkę. Wybrana opcja/ID nie zmienia się wskutek sortowania.
- Kompletność: CategoryPicker plus wszystkie natywne selecty i CardFormexpenseOptions,
  także CategoryTreeEditor i starszy CategorySettingsRow. Brak zmiany reguł rodziców.

### Task 1: Wspólny builder opcji i migracja wszystkich konsumentów

**Interfaces:** `categoryOptions(visible: readonly Category[], hierarchy = visible)`
zwraca nową tablicę `{...category, label: pełna ścieżka}` posortowaną przez
`Intl.Collator("pl", {sensitivity:"base"})`. Nazwa oryginalna iID zachowane.
`CategoryPicker` przyjmuje opcjonalny pełny kontekst hierarchii dla istniejących
prefiltrowanych list TransactionForm/ScheduledItemForm. Istniejąca logika retencji
wybranej opcji pozostaje bez zmian.

**Files:** lib/categories.ts/test; finance/CategoryPicker/test, TransactionFilters,
CategoryTreeEditor/test, CategorySettingsRow/test, TransactionForm, ScheduledItemForm;
documents/DocumentReview/test; bills/BillPaymentDialog/test; imports/ImportGroupEditor;
pages/FinanceAccounts/test, FinanceCreditCardDetails/test; nowe syntetyczne testy
kontraktu selectów i istniejące E2E kategorii/paragonów/reguł/importów/dokumentów.

- [x] Zweryfikować istniejącą izolację i czysty frontend; zapisać ledger.
- [x] RED: helper wielopoziomowy, polska kolejność, filtrowana lista z pełnym kontekstem,
  brak mutacji, cykl/brak przodka; picker ścieżka/sort/search/selected/archived.
  Expected: brak buildera lub stare niesortowane etykiety, nie błąd środowiska.
- [x] GREEN: minimalny wspólny builder, CategoryPicker i jego kontekst hierarchii.
- [x] RED: rzeczywiste selecty filtrów/dokumentów/bill/importów/karty/rodziców pokazują
  pełne ścieżki w porządku rosnącym i zachowują ograniczenia/ID. Expected: płaskie nazwy
  lub kolejność API. Mockować wyłącznie warstwę HTTP/API, nie renderer opcji.
- [x] GREEN: podłączyć builder we wszystkich miejscach; bez zmiany kont/walut/statusów.
- [x] /test wariantfrontend: pełny vitest, /lint ESLint, /typecheck tsc, frontendbuild.
  Expected:PASS; backend bez zmian, bez niebezpiecznej domyślnej bazy testowej.
- [x] Produkcyjny build + syntetyczne Playwright desktop/mobile dla nowych opcji i
  dotkniętych przepływów. Expected: ścieżki/sortowanie/ID, bez realnych API i overflow.
- [x] Jedno świeże review całości. Important/Critical: jeden TDDfixpass; Minor odnotować.
- [x] Zaktualizować CHANGELOG/TASKS/JOURNAL, commit jawnych plików funkcji po bramkach.
  Bez merge/push/deploy na podstawie zgody dotyczącej poprzedniej funkcji.

## Pre-flight

Jedno zadanie, bez współdzielonych interfejsów między zadaniami. Pełny kontekst
Category ma parent_id; DocumentReview zawężał typ do płaskich pól — przywrócić Category[].
Współdzielony CategoryPicker pokrywa także splity, recurring, budżety, reguły i receipt.
