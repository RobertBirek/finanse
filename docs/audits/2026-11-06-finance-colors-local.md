# Kolory kont i kategorii — odbiór lokalny

## Zakres

Po prośbie o wybór kolorów kont/kategorii i użycie ich na dashboardzie/wykresach
użytkownik polecił „działaj”. Przyjęte i jawnie przedstawione ustawienia domyślne:
niezależny kolor konta, dziedziczenie najbliższego rodzica w kategorii, możliwość
nadpisania koloru podkategorii i powrotu do dziedziczenia. Bez zgody na wdrożenie.

## Implementacja

- `accounts.color` i `categories.color`: nullable VARCHAR(7), PostgreSQL jako źródło
  prawdy, API i DB dopuszczają wyłącznie `#RRGGBB`/NULL; API normalizuje HEX do uppercase.
  Ominięte pole PATCH pozostaje nietknięte, jawny NULL przywraca tryb automatyczny.
- Istniejące właścicielskie endpointy, serwisy i audyt obsługują zapis oraz odczyt;
  bez nowych uprawnień, grantów AI lub przepisywania księgi/import mappings.
- Ustawienia nowych i istniejących kont/kategorii: natywny wybór dowolnego koloru,
  nazwana paleta, podgląd HEX, reset. Zapis samego koloru wysyła tylko `color`, bez
  name/type/parent/currency/budgetflag; nie przycina też dawnych nazw kategorii.
- Dziedziczenie jest prezentacją, nie zapisem u potomków. Bez explicit koloru fallback
  zależy od stabilnego ID, nie nazwy lub pozycji na wykresie. Cykl/sierota nie zawiesza UI.
- Spójne akcenty kont, ostatnich transakcji i budżetu dashboardu oraz słupki/legendy
  raportów kategorii i budżetów. Kwoty/znaki/rollupy pochodzą z serwera; nie są sumowane
  ponownie. Długości słupków skaluje wartość bezwzględna, ujemne etykiety zachowują znak.
- Ostrzeżenia przekroczenia budżetu pozostają czerwone, a zbiorcza prognoza nie udaje
  serii jednego konta. Inicjały kont mają kontrastowy czarny/biały tekst, etykiety
  zachowują kontrast istniejącego motywu. Bez nowych bibliotek lub preferencji w plikach.

## Migracja i ochrona danych

`f3a9d17c2e4b` po `7b57f2f0bde6`: dwie nullable kolumny i dwa CHECK, bez backfillu
lub nadawania kolorów dotychczasowym rekordom. Stary runtime nie potrzebuje tych pól,
nowy backend wymaga migracji przed przełączeniem aplikacji.

W izolowanym, własnym schemacie lokalnego `finanse_test` wykonano pełny łańcuch
Alembic do7b57, dodano syntetyczne stare konto/kategorię/transakcję/postings, następnie
upgrade head. Wszystkie projekcje starych wierszy **56 tabel identyczne**; nowe kolory
NULL, schemahead zgodny. Empty downgrade/re-upgrade zachowuje stare dane. Po zapisaniu
koloru na dowolnym koncie lub kategorii downgrade odmawia przed DROP, blokując obie
tabele, aby nie usunąć preferencji w wyścigu z zapisem.

Nowa fixture odmawia niebezpiecznych URL przed engine/DDL; każdy test ma własny schemat
z przypiętym search_path i cleanup wyłącznie po udanym utworzeniu. Produkcji nie użyto
do testów, nie uruchomiono na niej migracji ani zmian kolorów.

## Przegląd i weryfikacja

- Jeden niezależny whole-feature review: **0 Critical / 1 Important / 0 Minor**,
  Declined to judge puste. Important: pierwotny downgrade usuwał zapisane kolory.
  Zweryfikowany i poprawiony testami:2RED→GREEN dla obu tabel, dodatkowo empty roundtrip.
- Testfixture guard:5RED→GREEN. Testy UI pokrywają zapis/reset/omitted/minimalPATCH,
  dziedziczenie, cykle, kontrast, zachowanie nazw i kwot oraz negative/zero-net rollupy.
- **1734 backend PASS**,8proxy wyłączonych projektowym markerem,10znanych ostrzeżeń
  deprecation, brak DBskip lub nieoczekiwanych pominięć.
- **507 frontend PASS**, ESLint/tsc/Ruff/mypy PASS; świeży production build PASS.
  Pozostało istniejące ostrzeżenie bundlera o chunk>500kB — nie jest błędem buildu.
- **145 E2E PASS +1 oczekiwany skip** na świeżym buildzie, desktop1440/mobile375,
  light/dark; zapis→nawigacja→reload→wykres→override/reset. Axe serious/critical0 dla
  pickera. Screenshoty desktop/mobile obejrzane, brak poziomego overflow.
- Pełny backend testował zamrożone źródła; SHA przed/po identyczne. Finalny verifier
  sprawdza bieżące bajty backend/frontend/testów i testowanego dist oraz proof migracji.

Dowody lokalne: `/tmp/opencode/finance-colors-20261106/` (logi, source/distfreeze,
`verify-final.py`, migrationproof i browser screenshots). Starsze przebiegi RED są
zachowane; nie są raportowane jako PASS. Ostateczny frontend build to `dist-frozen`.

## Przekazanie

Funkcja **gotowa lokalnie, NIE WDROŻONA**. Produkcyjne79kategorii i wcześniejsza
operacja porządkowania drzewa nie są ponawiane. Bez zmian auth, polityk AI, kont,
historii, sald lub postings; bez merge/push/deploy. Zachowany dotychczasowy branch,
worktree i niezwiązane dirty Velo/Q7. Wydanie wymaga osobnej zgody, backupu i próby
migracji na aktualnej kopii, spójnego backend/worker/frontend oraz zachowania
istniejących aktywnych kontraktów aplikacji; nie używać operatora reorganizacji drzewa.
