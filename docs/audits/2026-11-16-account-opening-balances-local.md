# Bilans otwarcia kont — odbiór lokalny

Status: **lokalnie zweryfikowane**. Nie jest to zgoda ani raport wdrożenia.

## Zakres

Użytkownik zatwierdził BO każdego konta, kwoty dodatnie/ujemne/zerowe, datę oraz
edycję wyłącznie bez innych transakcji (również oczekujących). Polecił BO=0 dla
istniejących kont; oznacza to nowy zerowy BO, nie wyzerowanie ich rzeczywistych sald.

Nie wykonano migracji produkcyjnej, backfillu danych użytkownika, merge/push ani deployu.
Trwały prywatny klon certyfikacyjny i inne worktree pozostają nietknięte.

## Implementacja

- `AccountOpeningBalance`: jeden owner-safe rekord na konto, data i wersja,
  opcjonalny unikalny odnośnik do dedykowanej transakcji.
- BO=0 nie tworzy fikcyjnych transakcji/postings. Kwota nonzero wynika wyłącznie
  z księgi: dokładnie dwie nogi, debit+ / credit− = 0, dodatnie kwoty bezwzględne.
  Dodatnie saldo konta zgodnie z projektem daje credit, ujemne debit.
- Przeciwwagą jest ukryta chroniona kategoria transfer, nie dodatkowe konto.
  BO nie trafia do przychodów, wydatków lub wykorzystania budżetów; saldo,
  zadłużenie karty i początek prognozy uwzględniają księgę.
- PLN: kurs1. Nonzero EUR/USD: jawny kurs manualny, do6miejsc, Decimal/HALF_EVEN.
  Kwoty wejściowe w groszach/centach, strict integer ±9007199254740991, bez utraty
  końcowego grosza w frontendowym parsowaniu.
- Utworzenie konta, warunków karty i BO jest atomowe. PUT BO używa owner/account
  locks, wersji, klucza idempotencji, trwałego receipt i audytu.
- Blokada historii nie opiera się na saldzie lub opisie: wyłącza jedynie rzeczywiście
  powiązaną transakcję BO. Pozostała transakcja, także pending lub kompensująca
  inną do salda0, blokuje edycję.
- Zwykła edycja/usuwanie, source spoofing i użycie technicznej kategorii są blokowane.
  Dokumenty, darowizny, raty, korekta dat i kategoryzacja odrzucają typ BO.
  Po review także oznaczenia/opis/tagi/projekt nie mogą zmieniać BO ani odtwarzać
  niedozwolonego receipt.
- UI: pola w nowym koncie, osobny edytor BO, przyczyna blokady, readonly BO na
  listach transakcji. Retry zachowuje key;409 wymaga odświeżenia i nowego
  potwierdzenia. Zmiana sesji blokuje stary handler/wynik.

## Migracja

`efaf78432563` po `2c77e935ee39`, wygenerowana przez Alembic w zatwierdzonej własnej
bazie. Usunięto niezwiązany drift indeksów harmonogramów z autogenerate.

Backfill INSERT SELECT obejmuje wszystkie konta, także nieaktywne/karty/EUR/USD:
rekord BO bez transakcji, data=`opened_at`, wersja1. Realny test18syntetycznych
kont sprawdza każdą starą tabelę/wiersz i zachowanie historycznych postings `[BO]`.
Downgrade odmawia utraty nonzero BO. Nie wykonywano downgrade na danych użytkownika.

Przed przyszłym wdrożeniem wymagane są osobno: zgoda na migrację/backfill,
świeży backup/restore, retencja i zgodne wydanie backend/frontend.
Po zapisaniu nonzero BO nie należy zakładać, że stara aplikacja potrafi je
bezpiecznie edytować; rollback wymaga własnej oceny zgodności, nie downgrade danych.

## Dowody

| Kontrola | Wynik |
|---|---|
| Baseline backendu | 25 PASS; niepełny wcześniejszy foreground timeout niezaliczony |
| Baseline frontendu | 677 PASS |
| Nowe modele/migracja | RED→GREEN,3PASS, retencja i nonzero downgrade |
| Komendy/guardy/races/karta/prognoza | 22 focused PASS |
| Poprawka review, annotations | 3 RED→3 GREEN, service/API/replay; snapshot8tabel bez zmian |
| Regresja budżetu zapytań | GREEN: zachowane3SELECT dla1i12grup kont |
| Pełny frontend | 707 PASS,113plików |
| Pełny E2E | 205 PASS i1dotychczasowy expectedskip,375/1440 |
| Nowe browser BO | 4 PASS;4screenshoty obejrzane, brak overflow |
| Build | PASS; istniejące ostrzeżenie bundla ponad500kB |
| Pełny lint/typecheck | PASS po poprawce review; Ruff/ESLint i mypy215/tsc |
| Komenda `/test` na końcowym drzewie | PASS: kolekcja offline i707Vitest,65.13s |
| Pełny backend po review | 2632 PASS,0skip, wszystkie8grup od nowa, fingerprint zgodny |
| Cleanup | 4własne PG idle, stop exit0, usunięcie i brak kontenerów potwierdzone |

Browser używa produkcyjnego buildu i kontrolowanych fixtureAPI. Backendowe testy
ASGI i integralności działają osobno na rzeczywistym PostgreSQL. Nie utożsamiamy
tych dowodów z testami rzeczywistej zalogowanej produkcji.

## Nieudane próby i ich rozstrzygnięcie

1. Nowa projekcja EXISTS wymagała jawnej korelacji z BO, zamiast automatycznej
   korelacji także z zewnętrznym Posting. Poprawiono przed pierwszym backendowym commitem.
2. Cztery stare fixture przestały pasować do nowego schematu: historyczna migracja
   używała obecnego create_account na starym schemacie, trzy security fixtures
   zmieniały owner konta bez owner-safe BO. Zachowano wszystkie asercje i mocne FK;
   poprawiono wyłącznie syntetyczne przygotowanie. Potwierdzone4PASS po wcześniejszych RED.
3. Własne testowe tmpfs512MB zapełniło się WAL (base44.5MB, WAL400–432MB),
   nie danymi użytkownika. Ustawiono wyłącznie własnym PG max_wal64/min32/checkpoint30s.
   Zrestartowano wyłącznie dwa własne zakończone PG z syntetyczną, odtwarzalną zawartością.
4. Brakowało istniejącego obrazu testowego wymaganego przez CI proxy:
   przygotowano `python:3.12-alpine`, digest
   `sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89`.
   Ponowny proxy14PASS, bez zmiany testów lub bramek.
5. Jeden cleanup scratch migracji zastał chwilowo połączenie; później0aktywnych,
   sam test ponowiony PASS. Nie wyłączono ani nie osłabiono ownership/idle guard.
6. Summary wykonywało4zamiast3SELECT. Usunięto nieużywane pobieranie projekcji BO
   w summary, nie rozluźniono istniejącej asercji wydajnościowej. Izolowana kolekcja
   samych starych queries miała wcześniej setupERROR braku rejestracji User;
   z normalną rejestracją modeli wszystkie6targetedPASS.
7. Review potwierdził jedną ważną lukę annotations — naprawa opisana powyżej.
   Nie zlecano drugiego review; końcowy V3 po tej poprawce przeszedł2632/2632.

## Jedno niezależne review

Reviewer: `ses_e1a81f29cffeJA7Pr6SzD0fv8w`, readonly całego drzewa od `c960d9c`,
łącznie z plikami ostatniego zadania. Wynik:0Critical/1Important/0Minor.

Important annotations odtworzony3RED i poprawiony3GREEN bez drugiego review.
Reviewer jawnie odłożył ocenę końcowego pełnego backendu — agent wykonujący ma ją
  potwierdzić dowodami, nie traktować review jako zastępstwa testów. V3 spełnił
  tę bramkę:2632/2632PASS. Brak odłożonych Minors.

## Jawne decyzje wykonawcze i koszty

- Aktualna lokalna baza `origin/main=c960d9c` zamiast starego main593a232:
  finanse identyczne, aktualne devchecks. Koszt: nowe zasady runnera wymagają baseline.
- Własne syntetyczne PG używają fsync off dla szybkości fixture. Koszt: te testy
  nie są dowodem trwałości przy awarii serwera; nie zmieniono produkcyjnych ustawień.
- Inicjalizacja BO=0 to metadata bez oddzielnego audytu pieniężnego; nonzero init
  i każda edycja są audytowane. Koszt: brak osobnego eventu pustego BO przy tworzeniu.
- Istniejące typeguardy dokument/gift/loan/date/split zachowano zamiast dublowania.
  Koszt: przyszłe poszerzenie ich typów musi utrzymać regresje BO.
- Nietknięta pusta kwota w nowym formularzu korzysta z serwerowego zero/today.
  Koszt: nie odróżniamy pustego wejścia od domyślnego0, zgodnie z wymaganiem.
- Parser draftu i edytor są osobnymi małymi modułami. Koszt: dodatkowe pliki;
  brak nowych zależności i brak zmiany pozostałego layoutu.
- Testowy helper przenosi wyłącznie zerowe BO razem z syntetycznym kontem, aby
  fixtures foreign-owner zachowały swoją intencję bez osłabiania FK.
  Koszt: utrzymanie helpera, nie legalizacja przenoszenia realnych kont.
- Pełny zestaw jest rozłączną unią8CIgrup na4własnych no-portPG. Koszt: brak
  pojedynczego serialnego porządku wszystkich testów. V2 reuse niektórych PASS
  po wyłącznie fixture fixach został zastąpiony V3: całość od nowa po zmianie aplikacji.
- Summary pomija nieużywaną projekcję BO przez `include_opening=False`.
  Koszt: dodatkowy keyword trybu odczytu; publiczne konta domyślnie zawierają BO.
- Końcowy review wykonano przed ostatnią kosztowną regresją, aby jego poprawkę
  objąć pełnym testem bez podwójnej pracy. Koszt: reviewer nie poświadcza końcowego PASS;
  jego jawnie odłożona ocena walidacji pozostaje obowiązkiem wykonawcy.
- Po V3 nie odtwarzamy baz tylko dla zmian dokumentacji. Źródłowy fingerprint
  i verifier potwierdzają aktualność wyniku, a końcowa komenda `/test` ponawia
  kolekcję i pełny frontend. Koszt: brak jednego serialnego przebiegu wszystkich
  ośmiu grup, którego kontrakt CI nie wymaga.

## Końcowy pełny backend

| Grupa CI | Testy PASS | Czas (s) |
|---|---:|---:|
| legacy | 84 | 511.35 |
| ordinary-1 | 406 | 964.08 |
| ordinary-2 | 451 | 865.74 |
| ordinary-3 | 500 | 705.96 |
| ordinary-4 | 376 | 1129.38 |
| ordinary-5 | 380 | 1102.91 |
| ordinary-6 | 421 | 929.99 |
| proxy | 14 | 32.24 |
| **Razem** | **2632** | grupy równoległe |

Istniejący verifier potwierdził pełną unię ID, trzy fazy każdego testu, JUnit
i brak skipów. Źródłowy SHA256 obejmuje aplikację, testy, migracje i ci_tools;
kontrola przed cleanup potwierdziła identyczne bajty. Manifest wskazuje commit
bazowy zadania `975e77f` oraz źródłowo przypięte, wówczas niezatwierdzone poprawki.
Wynik dotyczy dokładnie tej zawartości, nie samego starego commita.

## Archiwum i cleanup

Dowody sesji: `/tmp/opencode/account-opening-balances-20261116-evidence.tar.gz`
(SHA256 w pliku z końcówką `.sha256`). Archiwum zawiera wyniki RED/GREEN,
manifesty/JUnit/fazy wszystkich prób, fingerprinty, komendy, ledger, review patch,
screenshoty, raporty E2E i receipt cleanup. Lokalne archiwum nie jest publikacją.

Cleanup dotyczył wyłącznie czterech utworzonych w tej sesji kontenerów:
`0d1231df…`, `e7fefcd8…`, `d843d6d8…`, `fa77db32…`. Przed stopem sprawdzono pełne
ID, etykietę planu, networknone/noports/tmpfs i0obcych połączeń klientów.
Każdy zakończył się exit0, bez OOM; brak kontenera po usunięciu potwierdzono.
Nie używano force/prune ani nie usuwano obrazów/wolumenów innych zadań.

## Kroki odbioru

- [x] Końcowy pełny backend po poprawce review i źródłowy fingerprint.
- [x] Odnowione komendy lint/typecheck/test bieżącego worktree.
- [x] Cleanup tylko własnych testowych zasobów.
- [x] Końcowy lokalny commit i trwałe archiwum dowodów (ścieżka powyżej).
- [ ] Osobna decyzja użytkownika o integracji i wydaniu; dane istniejących kont
  na produkcji nie zostały zmienione przez tę sesję.
