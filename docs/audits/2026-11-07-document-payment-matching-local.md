# Dopasowanie dokumentów i płatności 5A — lokalny odbiór

Data: 2026-11-07. Status: **lokalny odbiór PASS**, bez wdrożenia.
Zakres: spec i plan `docs/superpowers/{specs,plans}/2026-11-07-document-payment-matching*`.
Użytkownik zatwierdził zakres, następnie plan i native execution („tak, natywnie”),
oraz osobny tymczasowy PostgreSQL („ok”). Nie ma zgody na merge/push/deploy/migrację.

## Co zbudowano

- `BillCandidate.evidence` jest addytywnym, opcjonalnym kontraktem: opis, PLN,
  zakup/księgowanie ze źródłami, jawna para porównania dat i różnica dni, wskazówka
  pełnej nazwy sprzedawcy w opisie, zgodność planowanego konta i dwa odrębne okna dat.
- Brak metadanych nie udaje bankowej daty; obce metadane nie są dowodem. Bez kopiowania
  sale→purchase, żadnej zmiany źródłowych dat lub postings. Tokenizacja NFKC/casefold,
  bez fuzzy/aliasów i bez użycia technicznego prefiksu `[actual:…]` jako nazwy.
- GET zachowuje wszystkie wcześniejsze kwalifikacje/pojemności i kolejność legacy,
  kwota, następnie dodaje nazwę, odległość jawnej pary dat i deterministyczne IDs.
  Zakup może rozszerzyć widoczność; jednostronne legacy okno i jawne filtry txn.date
  nie są zawężane. Niedostępny dokument ma osobny reason, obcy nadal404.
- Dialog pokazuje kwoty pierwotne/wolne, daty/źródła i przyczyny, odróżnia loading,
  failure+retry, empty i niedostępność. Wybór/recurring acknowledgement są unieważniane
  po zmianie filtrów/strony/refetch, także przy identycznym JSON i przed rerenderem.
- Ręczna alokacja i jej payload niezmienione, receiptkey nadal od identycznego intent;
  409 wymaga nowej decyzji i ponownego wyboru. Brak autopost/autolink lub przełączenia
  pustej listy do tworzenia expense. Osobny stary tryb rejestracji pozostaje jawny.

## Środowisko i rzeczywiste dowody

- Linked worktree `finance-ui-redesign`, branch `feat/financial-document-workflow`;
  baza diffu69d53c3, Task1 commit8493abe. Istniejące zmiany Velo/Q7 niezwiązane ze scope.
- Własny `finanse-payment-matching-5a-20261107`: postgres16-alpine, networknone,
  tmpfsdata, portbindings `{}`. Testy w jego netnamespace przez localhost5432,
  `finanse_test`. Istniejących testDB na host5432/55432 nie używano i nie zmieniano.
- Stary współdzielony `/opt/finanse/backend/.venv` nie miał `openai.types.responses`;
  baseline14FAIL był błędem środowiska. Użyto istniejącego kompatybilnego
  `/tmp/opencode/financial-document-venv` (Python3.12.3/OpenAI2.54), bez instalowania
  lub zmieniania współdzielonych zależności. Nie wykonywano realnych AI/OCR/HTTPprovider.
- Slash commands nie mają callable API w harnessie i wskazują inny checkout;
  równoważne `/test`/`lint`/`typecheck` z cwd worktree realizuje zapisany
  `/tmp/opencode/payment-matching-5a/gate.sh`. Pełne logi w tym katalogu.
- Task1:27RED (brak helper/schema) →27GREEN; pełne1764backend,518frontend PASS.
- Task2:16RED/8existingPASS (w tym trzy błędy nowych fixtures: eagerpostings i różne
  konta loan poprawione w testach), potem49PASS z istniejącymi payments/concurrency/guards.
- Task3: nowa macierz UI RED, następnie35focusedPASS wraz z API/detail regresjami;
  409 stare mocks poprawione do prawidłowych endpointów i wymagania ponownego wyboru.
- Final gate: **1788backend PASS**,10proxy deselected,10znanychwarnings,2993.13s;
  **540frontend PASS** (86plików), Ruff/mypy/ESLint/tsc PASS. Bez integration skips.
  Frozenbackend SHA sprawdzony po gate; podczas pełnego runu kod backendu niezmieniany.
- Build PASS (znane ostrzeżenie głównego chunku>500kB). Focused financialdocuments
  **24E2E PASS**,375/1440 i desktop/mobile projects. Nowe E2E to acceptance firstPASS,
  nie deklarowane RED. Całościowe **153E2E PASS +1oczekiwany skip**,5.5min.
- Pierwszy dispatch review zakończył się „usage limit reached”, nie reviewPASS.
  Wznowiony jeden świeży read-only reviewer: `ses_e4a244217ffec2upN42pzty0O6` — **PASS**,
  brak Critical/Important/Minor, bez rundy poprawek. Przejrzano aktualny diff i nowe
  niecommitowane pliki, nie tylko8493abe; kod nie zmienił się podczas przeglądu.
- Dodatkowy końcowy frontend run:539PASS/1FAIL w istniejącym `DocumentList.test.tsx`,
  `opens a toast-linked review even when the document is outside the current list page`:
  oczekiwanie na element wyprzedziło asynchroniczne ustawienie wartości sprzedawcy.
  Bez zmiany kodu izolowany rerun1PASS, pełny rerun**540PASS**46.25s. Zapisane jako
  niestabilność starego testu; nie ukrywać pierwszego wyniku ani naprawiać innego zakresu.

## Jawne decyzje wykonawcze

1. Kompatybilny istniejący venv zamiast aktualizacji starego sharedvenv. Ryzyko:
   odtworzenie środowiska; wersje i polecenia zapisane, produkcja bez zmian.
2. Pełny backend run kosztuje około50min: po focused Task2 zamrożono jego kod,
   pełny run wykonano równolegle z frontendem. Commity Task2/3 dopiero po bramce.
   Ryzyko późniejszego wykrycia integracyjnych regresji: pokryte finalgate/review.
3. Macierz freshness wydzielona do `BillPaymentDialog.matching.test.tsx`, zamiast
   powiększać stary plik. Ryzyko pominięcia przez runner: pełneVitest ją wykonało.

### Granice niezależnego review — rozstrzygnięte przez wykonawcę

- Reviewer nie uruchamiał testów/E2E; wykonawca odczytał rzeczywiste zakończone logi
  i sprawdził manifesty źródeł. Ryzyko niewłaściwego pakietu ograniczają zapisaneSHA.
- Nie badano liveDB/HTTP/produkcji/providerów/migracji w read-only review; brak takich
  działań i brak obietnicy gotowości produkcyjnego wydania. Ryzyko livecompatibility
  pozostaje do osobnej bramki wdrożenia.
- Niezmienione mutatory nie przechodziły kolejnego review wewnętrznego; regresje
  owner/capacity/receipt/concurrency/audit/unlink przeszły focused i full suite.
  Ryzyko latentnego starego błędu nie jest rozszerzane nową ścieżką zapisu.
- Velo/Q7 nie należą do tej zmiany, pozostają niestage'owane; ryzyko zmieszania
  zakresów ogranicza staging konkretnych ścieżek.
- FX/refunds/loans/autolink/payee/history są świadomymi non-goals, nie brakami 5A;
  ryzyko odłożenia przyszłej funkcji, bez zmiany zasad księgowania.

Nie ma odłożonych uwag Minor z review. Ostrzeżenia zależności/chunku i niestabilny
stary test są ograniczeniami środowiska/odbioru, nie nowymi ukrytymi poprawkami.

## Granice odbioru

Nie wdrożono, nie scalono ani nie wypchnięto kodu. Bez migracji, backfillu, nowego
schematu, zapisów historii, realnych dokumentów/dostawców. Mutatory, modele i guards
niezmienione. Viewport mobile nie certyfikuje fizycznych Android/iPhone.
Wynik całościowego E2E i review zapisano powyżej. Własny kontener testDB zostaje
usunięty przy zamknięciu; istniejących kontenerów/testDB nie usuwać ani restartować.
