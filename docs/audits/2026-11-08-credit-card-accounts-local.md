# Typ konta karty i przegląd wielu kart — odbiór lokalny

Status: **odebrane lokalnie; bez wdrożenia**.

## Zakres i zgody

User zatwierdził: osobny typ „Karta kredytowa”, dodatkowe warunki przy tworzeniu
i edycji konta, zbiorcza lista kart z bieżącym stanem oraz działania „Wyciągi i raty”
i „Edytuj konto”. Po przejściu z Plan do Build: „ok, działaj”. Osobne potwierdzenie
dotyczy nowego efemerycznego PostgreSQL bez publikacji portów, danych produkcyjnych
lub używania istniejących baz, z usunięciem tylko własnego kontenera i wolumenu.

Plan: `docs/superpowers/plans/2026-11-08-credit-card-accounts.md`.
Base `775e875`; istniejący linked worktree `feat/financial-document-workflow`.
Commity: backend `0882d13`, frontend `25a69ad`. Bez merge, push, migracji produkcyjnej,
wdrożenia lub konfiguracji Velo. Dwa wcześniejsze raporty Velo/Q7 poza zmianą.

## Co zmieniono

- Nowy typ `credit_card`; zwykły `credit` nadal oznacza konto kredytowe, nie kartę.
- AccountCreate/Update przyjmuje `credit_card` z warunkami i expected_version.
  Konto i profil zapisują się razem, z blokadami mutacji/konta, audytem warunków
  i rollbackiem częściowej zmiany przy błędzie. Zmiana nazwy/koloru bez zmiany
  warunków nie wymaga przesłania profilu ani nie podbija jego wersji.
- W account response tylko małe warunki z wersją, bez historii wyciągów/rat.
  Pieniądze w groszach, APR jako dziesiętny string; waluta karty nadal PLN.
- `GET /api/finance/credit-cards`: właściciel i typ konta filtrowane w serwisie,
  wszystkie karty łącznie z oznaczonymi nieaktywnymi, dwa zapytania niezależnie
  od liczby kart, kwoty z księgi na dziś. Bez ładowania szczegółów dla każdej karty.
- Lista nie zawiera selektora zwykłych rachunków lub formularzy konfiguracji.
  Szczegóły rozliczeń pod `/settings/finances/cards/:accountId`; nieaktywne tylko
  do odczytu. Konfiguracja pod `/settings/finances/accounts?edit=:accountId`.
  Dawne `cards?account=` przekierowuje do właściwej karty.
- Wspólne pola warunków w create/edit, pojedynczy zapis HTTP, walidacja PLN/kwot/
  APR/dni i jawne błędy. Zachowane wpisy po błędzie, reset przy anulowaniu/wejściu;
  wersja pochodzi z momentu rozpoczęcia edycji. URL jest jedynym źródłem wyboru
  edytowanego konta, więc przejście między linkami nie zatrzymuje poprzedniej karty.
- Invalidacja cache przeglądu i szczegółów po zmianach kont i księgi.

## Migracja i retencja

`739144d5eaef` po `00a9ccb532b9` zmienia wyłącznie klasyfikację kont z istniejącym
profilem tego samego właściciela. Bez rozpoznawania karty po nazwie, tworzenia kont
lub zmiany sald. Downgrade przywraca klasyfikację `credit`, nie kasuje profili.
Autogenerate wykonano na własnej bazie; wycięto niezwiązany stary drift indeksów
harmonogramów. Nie zmieniano historycznych migracji ani produkcji.

Pełny Alembic upgrade/downgrade/reupgrade w odrębnej syntetycznej bazie we własnym
offline kontenerze PASS: wiersze wszystkich **62 tabel** zachowane poza zamierzoną
zmianą `accounts.type`, profile/księga bez zmian, zero niezbilansowanych transakcji,
zwykłe konto kredytowe o nazwie sugerującej kartę nadal `credit`.

## Testy i chronologia

- Baseline: **41 backend PASS**,156.50s, **555 frontend PASS**,46.50s.
- Start PostgreSQL najpierw trafił w okno restartu między tymczasowym serwerem
  inicjalizacji a docelowym serwerem. Żaden test nie ruszył w błędnym stanie;
  TCP readiness zamiast samego unix socket rozwiązało wyścig. Bez restartu danych
  innych środowisk lub łączenia się z nimi.
- Konto/profil:7RED i5ochronnychPASS → GREEN. Migracja1RED z niezmienionym typem
  → GREEN. Pierwszy GREEN ujawnił korelację SQL po dodaniu JOIN profilu; jawne
  correlate(Account) ją naprawiło. Serializacja APR ujednolicona do4miejsc.
  Focused konta/karty/waluta: **54 PASS**,200.84s, jeden znany passlib warning.
- Formularze5RED → **46 focused PASS**. Lista5RED → GREEN. Regresja URL edycji1RED
  → GREEN. Invalidacja przeglądu/szczegółów2RED → GREEN. Stary test konfiguracji
  zastąpiony testem przekierowania do konta, a konfiguracja ma odrębne nowe testy.
- Pełny frontend **568 PASS/93 pliki**,51.41s. ESLint najpierw wskazał dwa nieużyte
  destructured expected_version w fixture E2E; fixture teraz sprawdza wersje.
  Ponowne ESLint/tsc/build PASS. Istniejące ostrzeżenie o bundle ponad500kB jawne.
- Focused **12 E2E PASS**,34.3s: dwie karty, atomowy create/PATCH, odrębne limity,
  linki/back, stary URL, plany i wyciągi, mobile375/desktop1440, oba motywy,
  Axe i overflow. Obejrzano screenshoty przeglądu oraz edycji.
- Pełne E2E: **165 PASS + 1 oczekiwany skip**,5.8min, oba viewporty i wszystkie
  dotychczasowe moduły.
- Pełny backend: **1863 PASS**,14 standardowo wyłączonych proxy, zero runtime-skips,
  błędów i failures;3705.09s. Dziesięć znanych ostrzeżeń zależności. JUnit i osobna
  kolekcja potwierdzają pełne pokrycie; manifesty źródeł backend/frontend bez zmian.
  Jeden istniejący test OCR ma ID zawierające gzip MTIME z chwili kolekcji: pierwsze
  porównanie nazw wykryło tę różnicę. Znormalizowano wyłącznie cztery bajty timestampu
  w tym jednym ID, zachowując porównanie całej pozostałej treści i wszystkich1863
  przypadków. Nie zmieniono testu produktu ani nie pominięto przypadku.
- Oficjalny Ruff app/tests i nowa migracja oraz mypy152 PASS. Dodatkowy szeroki lint
  wszystkich starych migracji pokazał istniejące problemy stylu; nie naprawiano ich
  poza zakresem i nie deklarujemy takiego rozszerzonego gate jako zielonego.
- Końcowy niezależny review: `ses_e45620e54ffeXVNkWSyhxlNfP1` — **bez Critical,
  Important lub Minor**, bez żądanych zmian. Warunek pełnego backendu i E2E
  potwierdzony przez wykonawcę. Reviewer nie uruchamiał testów, migracji, Dockera lub HTTP; wyniki
  odczytuje i potwierdza wykonawca, bez zastępowania ich opinią reviewera.

## Decyzje i granice

- Wykonanie natywne, jeden końcowy review — mniejszy koszt niż osobny kontekst
  wykonawcy/reviewera dla każdego zadania; ryzyko późniejszego wykrycia regresji.
- Osobny `credit_card`, nie przemianowanie `credit` — chroni zwykłe kredyty;
  zewnętrzni odbiorcy typu konta muszą uwzględnić nową wartość.
- Istniejące style/tokeny i brak nowych zależności — spójność produktu, bez redesignu.
- Wspólny `save_config()` pozwala zapisać profil bez ładowania rozliczeń;
  dotychczasowy configure nadal zwraca pełne szczegóły, koszt: dodatkowy entrypoint.
- Niekompletne konto typu karty jest widoczne jako wymagające konfiguracji,
  z nieznanym limitem zamiast zera; koszt: nullable kwoty i configured w summary.
- Bankowe warunki, grace period, oprocentowanie planów i zasady księgowania pozostają
  bez zmian. Nie odtwarzamy historycznych rat ani nie konfigurujemy Velo po nazwie.
- Odłożone przez reviewera runtime/testy/środowiska: koordynator przyjmuje własne
  świeże dowody pełnych backend/frontend/E2E/CLI migracji. Koszt pomyłki: odbiór
  nieprzetestowanej regresji — dlatego bramkę zamknięto dopiero po wyniku.
- Dwa stare raporty Velo/Q7 świadomie wyłączone z review i commitów; to niezwiązana
  praca użytkownika. Koszt: te robocze zmiany nie są objęte niniejszym odbiorem.

## Zamknięcie

Po zielonych bramkach usunięto wyłącznie własny kontener PostgreSQL i jego anonimowy
wolumen, po porównaniu pełnego DockerID, nazwy, etykiety zadania, networknone,
braku opublikowanych portów i zapisanych mountów. Potwierdzony brak kontenera
i wolumenu; bez force, prune lub usuwania współdzielonych obrazów. Obie własne
bazy syntetyczne zniknęły wraz z tym kontenerem. Produkcja i inne bazy nietknięte.

Prywatne logi, build i zrzuty: `/tmp/opencode/credit-card-accounts-20261108/`.
Dowody: `acceptance-proof.json`, `backend-full.xml`, `backend-collection.log`,
`migration-roundtrip-proof.json`, `frontend-acceptance.json`, `cleanup-proof.json`,
`review.json` i manifesty testowanych źródeł. Brak odłożonych uwag Minor.

Następny krok wymaga osobnej zgody: merge/push, backup i produkcyjna migracja
`00a9ccb532b9 → 739144d5eaef`, spójny deploy backend/worker/frontend. Nie konfigurować
Velo automatycznie; obecny release produkcyjny020c229 pozostaje bez zmian.
