# Changelog

Wszystkie istotne zmiany w projekcie.

## [Verified] — 2026-10-24 — Aktualność przed importem Actual

- Kontrola tylko do odczytu:serwer Actual nie ma komunikatów po watermarku zatwierdzonego
  eksportu; ZIP/pin i produkcyjne konta,kategorie,mapowania oraz1601 pełnych zapisów
  transakcji/postingów są identyczne z baseline próby.
- Zakres nadal286 nowych operacji+1 zachowana source-absent. Wspólne operacje zgodne;
  poprzednie21 różnic opisów odtworzono jako efekt brakujących nazw zamkniętych kont
  w starym parserze. Obecnie0 różnic opisów,bez aktualizacji danych.
- Raport:docs/audits/2026-10-24-actual-current-preflight.md. Brak importu produkcyjnego;
  potrzebna osobna zgoda i świeży backup/restore przed ewentualnym wykonaniem.

## [d3c2c68] — 2026-10-24 — Wdrożona aplikacja, bez importu księgi

### Changed
- Po jawnej zgodzie scalono/push main i wdrożono backend/worker/frontendd3c2c68.
  Gate main:backend778/frontend194/E2E29+1skip,lint/types/build i GitHub CI PASS.
- Backupfa1551c7 i restore drill success/0. Zachowano hardening, dane/env/usługi danych;
  bez migracji, importu Actual/bankowego i resetu retry.
- Dwie wycofane próby opisano jawnie w raporcie: poprawiono uprawnienia wygenerowanej
  kopii kodu dla UID10001 i rozdzielono zmienną metrykę cron od niezmienności księgi.
  Końcowy HTTPS/health/assets/auth/browser375+1440 PASS; dane/pliki bez zmian.
- Raport:docs/audits/2026-10-24-release-d3c2c68.md; active metadata zaktualizowane,
  poprzednie obrazy i rollback do backend6811809/frontend8a7cda5 zachowane.

## [Unreleased] — 2026-10-24 — Jawne uzgodnienie zachowanej historii Actual

### Added
- Użytkownik zatwierdził uzgodnienie eksportu plus dokładnie jednej zachowanej
  lokalnej operacji z kontrolą ID i hasha. Zapisano projekt i plan actual-preserved-history.
  Manifest tylko identyfikuje zaakceptowany zapis; kwoty nadal z PostgreSQL.
- Plan zakłada osobny surowy raport, pełną kontrolę pozostałych różnic i próbę wyłącznie
  na kopii. Rozpoczęto zatwierdzone wykonanie natywne: moduł manifestu/fingerprintu/
  blokad i wkładu postingów przeszedł66 testów RED → GREEN (3266377).
  Backend tego modułu748 PASS (8 proxy deselected,2 znane warningi), frontend194 i lint/types PASS.
- Integracja CLI/niezmiennego ZIP/raportu raw_actual+augmented:30 nowych testów PASS,
  łącznie206 finansowych/kontraktowych PASS. Po końcowym review naprawiono kontrolę
  obecności pinu także w drugiej stronie transferu/dzieciach splitów i pomijanych
  przez rekonstrukcję wierszach. Regresje RED3 → GREEN, Ruff/mypy PASS.
- Próba na kopii z przypiętym manifestem PASS:286 nowych operacji,0 błędów;
  powtórzenie0 nowych/1085 pominiętych, identyczny raport i wiersze. Augmented zgodne
  dla16/16 kont,54/54 kategorii i9/9 grup; surowe różnice nadal jawne.
- Pełne fingerprinty1601 wcześniejszych transakcji/postingów niezmienione,2 zamknięte
  konta nieaktywne. Obie izolowane kopie zatrzymane. Raport:
  docs/audits/2026-10-24-actual-preserved-history-rehearsal.md.
  Końcowy backend778 PASS (8 proxy deselected,2 znane warningi), frontend194 i lint/types PASS.
  Brak zgody na import produkcyjny.

## [Unreleased] — 2026-10-24 — Historia zamkniętych kont Actual

### Fixed
- Parser uwzględnia wszystkie nietombstonowane konta, także zamknięte, w metadanych,
  walutach, nazwach transferów i saldach. Zamknięte konta są tworzone jako nieaktywne;
  import nie otwiera ponownie lokalnie zarchiwizowanych kont ani nie wymyśla dat zamknięcia.
- Jawny, wewnętrzny tryb importu historii Actual pozwala użyć nieaktywnego konta
  bez jego aktywacji. Zwykłe API i sam parametr source nadal nie omijają blokady;
  pozostałe walidacje księgi/własności pozostają włączone.
- Regresje RED → GREEN; 90 testów importera (w tym świeża sesja po rollbacku),
  110 testów z uzgodnieniami/kontraktami, backend682 PASS (8 proxy deselected,
  2 znane warningi), Ruff/mypy i ESLint/tsc/194 Vitest PASS. Review bez blokad.
- Próba na kopii: 16 kont, 0 błędów importu. Pozostała jedna różnica konta/kategorii/
  grupy, dokładnie odpowiadająca zachowanej operacji nieobecnej w eksporcie.
  require_reconciled wycofał całość; potwierdzono niezmienność1601 transakcji/postingów
  oraz metadanych kont i mapowań. Bez importu produkcyjnego i deployu.

## [Unreleased] — 2026-10-24 — Przyrostowe mapowanie Actual

### Fixed
- Po zgodzie użytkownika poprawiono rozpoznawanie nowych kont/kategorii przy
  kompletnych istniejących mapowaniach; brakujące historyczne referencje nadal blokują import.
- Regresje nowych encji, brakujących/błędnych mapowań, jednoznaczności postingów,
  rodzica kategorii, źródła bez grup i zachowania operacji nieobecnej w eksporcie:
  oraz nieużytych mapowań stale/unowned/wrong-model: RED → GREEN, 74 testy importera PASS.
  Walidacja wszystkich zapisanych referencji źródła odbywa się przed tworzeniem encji.
  Zachowano bezpieczne odtwarzanie brakującej grupy w częściowo zmapowanej historii legacy.
  Ruff/mypy i frontend ESLint/tsc/194 Vitest PASS;
  pełny backend666 PASS (8 proxy deselected, 2 znane ostrzeżenia), niezależny review bez blokad.

### Changed
- Ponowiona próba wyłącznie na kopii PA przeszła mapowanie, ale wymuszone uzgodnienie
  sald zatrzymało import: 7 transferów odwołuje się do 2 zamkniętych kont pomijanych
  przez parser. To osobna blokada; nie zmieniano jeszcze obsługi zamkniętych kont.
- Potwierdzono pełny rollback transakcji/postingów kopii i zatrzymano kontener próbny.
  Bez zapisu do produkcji, replacement, migracji ani wdrożenia.

## [Preflight] — 2026-10-23 — Aktualizacja z Actual

- Zweryfikowano lokalne źródło Actual: snapshot wymaga późniejszych komunikatów
  synchronizacji. Nie uruchomiono importu nieaktualnego snapshotu do księgi.
- Backup PA12055508 i izolowany restore drill success/0. Prywatne kopie źródła
  poza repozytorium; potrzebny kompletny zsynchronizowany eksport budżetu.
- Dostarczony świeży eksport zweryfikowany; próba na izolowanej kopii PA zatrzymana
  na mapowaniach legacy (nowe encje źródłowe). Backup/restore bc2a3f05 PASS.
  Brak importu produkcyjnego; dalszy krok wymaga poprawki importera i ponownej próby.

## [Verified] — 2026-10-23 — Testy aplikacji po wdrożeniu UI

- Produkcyjny smoke na320/375/768/1440px PASS: logowanie anonimowe, brak overflow/
  błędów JS, lokalne fonty i ochrona API. Bez mutacji danych.
- E2E na pakiecie produkcyjnym29 PASS +1mobile-only skip; Vitest194 PASS,
  ESLint/tsc PASS. Raport: docs/audits/2026-10-23-webapp-test.md.
- Nie testowano operacji na zalogowanym koncie produkcyjnym (brak sesji).

## [8a7cda5] — 2026-10-23 — UI/UX wdrożone

### Changed
- Wdrożono wyłącznie frontend8a7cda5; backend/worker nadal6811809.
  Backup/restore cfc7102f, HTTPS/health, hashe JS/CSS/fontów i logowanie PASS.
- Backend/worker/Stirling/PostgreSQL/Redis bez restartu. Bez migracji i zmian danych.
  Smoke UI obejmuje anonimową stronę logowania; zalogowane widoki testowano na fixtures.

## [Unreleased] — 2026-10-23 — UI/UX pulpitu osobistego

### Release preparation
- `8a7cda5` scalono do main i wypchnięto. Przygotowano frontend-only image
  z przypiętym digestem, rollback do 6811809 i backup/restore cfc7102f PASS.
  Backend/worker i wcześniejszy refaktor finansów poza zakresem wydania.

### Fixed
- Na telefonie nazwy kont i kategorii nie konkurują z przyciskami działań;
  długie nazwy zawijają się. Przyciski wspólne i kontrolki kalendarza mają min. 44 px.
- Formularz transakcji i przegląd finansów pozwalają ponowić błędne odczyty;
  ładowanie ma tekst dostępny dla czytników ekranu.
- Mobilna agenda mieści puste dni w zwartych wierszach, bez ukrywania wpisów.

### Changed
- Dzisiaj pokazuje działania i chronologiczny plan przed statystykami także w DOM;
  bieżący blok oznaczony „Teraz”. Nowa granatowo-łupkowa paleta i lokalne fonty
  Barlow Semi Condensed / Source Sans 3 (licencje OFL w public/fonts).
- Audyt/screenshoty na danych syntetycznych, bez odczytów prywatnych danych ani deployu.
  Gate: backend642, frontend194, E2E29 PASS +1 celowe pominięcie testu mobile
  na desktopie; lint/types/build PASS. Axe na 8 widokach bez naruszeń wybranych
  reguł WCAG A/AA; review bez blokad. Bez wdrożenia.

## [Unreleased] — 2026-10-23 — Podział serwisu finansów

### Changed
- `finance.service` pozostaje publiczną fasadą; implementacje przeniesiono do
  modułów transactions, reporting, budgets i cashflow, daty do dates.
- Bez zmiany schematów/API, SQL, reguł księgi, zaokrągleń i blokad potwierdzeń.
  Wydzielono czyste obliczanie potomków kategorii z testem zachowania.
- Baseline finansów/integrity 207 PASS, kontrakty i jednostkowe FX 15 PASS;
  backend 642 PASS (8 proxy deselected), frontend 194 PASS, lint/types PASS.
  Niezależny review bez ustaleń blokujących. Brak migracji i deployu.

## [6811809] — 2026-10-23 — Wdrożona poprawka proporcji OCR

### Fixed
- Wdrożono zachowanie proporcji obrazów OCR i automatyczny dobór orientacji A4.
  Backup da7eb2d7 i restore drill PASS; HTTPS/health/assets i odrzucanie anonymous PASS.
- Zmieniono tylko obrazy backend/worker/frontend. Hardening zachowany;
  Stirling, PostgreSQL i Redis bez restartu. Bez migracji, zmian ACL i resetu retry.

## [Unreleased] — 2026-10-23 — Proporcje obrazów OCR

### Changed
- Rewizja 6811809 scalona do main i wypchnięta; pakiet produkcyjny oraz rollback
  przygotowane, backup/restore 23bcbccb PASS. Produkcja nadal działa na c765ea9.

### Fixed
- Konwersja PNG/JPEG przed OCR jawnie zachowuje proporcje i dobiera orientację
  strony A4 zamiast rozciągania obrazu. Oryginały, limity i retry pozostają bez zmian.
- Regresja multipart oraz rzeczywistej geometrii PDF odtworzyła wcześniejszy błąd.
  Staging OCR PASS: szerokie PNG/JPEG, pionowe PNG/JPEG i skan PDF, także polski
  tekst; geometria i niezmienność oryginałów potwierdzone. Poprawka niewdrożona.
- Gate: backend 636 PASS (8 proxy deselected), osobno staging OCR 1 PASS,
  frontend 194 PASS; Ruff/mypy/ESLint/tsc i diff check PASS.

## [c765ea9] — 2026-10-23 — Wdrożenie pakietu bezpieczeństwa dokumentów

### Changed
- Wdrożono backend, worker, frontend i przypięty Stirling non-root/read-only;
  zachowano cap-drop, no-new-privileges i limity zasobów.
- Zastosowano ACL uploads bez default inheritance, zmiany właścicieli i treści;
  migracja `c7f8c620460d` wykonana jawnie. Stirling wystartował przed workerem.
- Backup `e45cdc85` i izolowany restore drill PASS. HTTPS/health/zasoby 200,
  anonimowe dokumenty 401; obrazy, UID, mounty, logi i niezmienione data IDs sprawdzone.
- Pozostają: szerokie obrazy fillPage, walidacja worst-case sizing oraz komunikat
  Stirling o opcjonalnym katalogu szablonów na read-only root.
- Kontrola po wdrożeniu (12:31 CEST, ok. 9–11 min pracy): brak restartów/OOM
  i nowych błędów, kolejka OCR pusta, HTTPS/health poprawne. To krótka obserwacja
  bez obciążenia, nie test wydajności ani gwarancja długoterminowej stabilności.

## [Unreleased] — 2026-10-23 — Pakiet bezpieczeństwa dokumentów (niewdrożony)

> Historyczny zapis przygotowania; aktualny status wdrożenia znajduje się powyżej.

- Follow-up na osobnej gałęzi: derived Stirling z przypiętym modelem pol,
  hash-guarded patchem init i ścisłą walidacją uprawnień przeszedł rzeczywisty
  staging OCR PNG/JPEG/PDF dla skanów A4. Produkcyjne Compose i dane bez zmian.
- Finalny gate follow-up: 632 testy backendu, 8 proxy/ACL/OCR i 194 frontend PASS;
  lint/typecheck/build OK. Niezależny review i poprawki pokrycia zakończone.
- Dodano testy ACL/restore non-root na syntetycznych plikach. Wykryto osobno
  zniekształcanie szerokich obrazów przez domyślne fillPage; pozostaje w backlogu.
- Przygotowano projekt kompatybilnego runtime Stirling i stagingu uprawnień
  uploads; implementacja w toku na osobnej gałęzi. Dalszy staging ujawnił
  konflikt vendor chmod z wymaganą polityką uprawnień; runtime nie jest zatwierdzony.
- Release `f256a10` wypchnięto do `main`; wdrożenie zatrzymane na stagingu:
  docelowy Stirling 2.14.3 nie uruchamia się z profilem read-only/non-root.
  Bez migracji produkcyjnej ani zmiany aktywnych usług.
- Po review objęto limitem Nginx 21 MiB obie ścieżki uploadu (z końcowym `/`
  i bez); regresja na rzeczywistym Nginx odtworzyła wcześniejsze odrzucenie 2 MiB.
- Walidacja PDF/PNG/JPEG w ograniczonym procesie potomnym (RAM, CPU, timeout,
  concurrency, limity stron/pikseli/klatek), środowisko bez sekretów aplikacji.
- Limity body przed multipart, spójny limit Nginx 21 MiB/plik 20 MiB,
  serializowana kontrola logicznych quota i rezerwy miejsca przed zapisem.
- Strumieniowe, ograniczone odpowiedzi OCR; nieoczekiwana kompresja odrzucana
  przed dekodowaniem. SHA-256 i oryginalne bajty zachowane.
- Retry błędów przejściowych przechowywane w PostgreSQL (3 próby, 30/120 s);
  błędy integralności/limitu/permanentne kończą przetwarzanie. Re-upload nie resetuje budżetu.
- Migracja `c7f8c620460d` dodaje metadata retry; przetestowano wyłącznie izolowaną bazę.
- UI pokazuje termin ponownej próby oraz odróżnia 413 od niedostępności 503/507.
- Dodano niewłączony profil hardeningu Compose i oddzielne kontenerowe testy w CI.
  Profil wymaga staging z docelowym obrazem Stirling; subprocess nie jest pełnym sandboxem.

## [Unreleased] — 2026-10-22

### Audit
- Po zgodzie na pakiet 1 przygotowano plan izolacji walidacji, limitów uploadu/OCR,
  storage admission i trwałego retry. Implementacja i deploy jeszcze nierozpoczęte.
- Przeprowadzono przekrojowy audyt rewizji `7cde5ac`: finanse, auth/AI,
  dokumenty/worker, frontend, CI i wybrane aspekty operacyjne.
- Raport: `docs/audits/2026-10-22-audit.md` — 14 ustaleń i 5 grup ryzyk,
  dowody, ograniczenia oraz kolejność proponowanych napraw. Bez zmian aplikacji.
- Potwierdzono CI tej rewizji: 582 backend, 189 Vitest i 18 Playwright PASS;
  produkcyjne obrazy pozostają starsze. Nie wykonano deployu ani migracji.

### Changed
- Zintegrowano zmiany z `genspark_ai_developer` z najnowszym `main` do
  wspólnej wersji `a115afc`; wdrożenie produkcyjne pozostaje poza zakresem.

### Fixed
- Upload dokumentów parsuje PDF-y i dekoduje PNG/JPEG przed storage w serwisie;
  odrzuca pliki uszkodzone i niezgodne z deklarowanym MIME przed zapisem.
- Worker weryfikuje SHA-256 oryginalnych bajtów przed OCR i przekazuje te same
  zweryfikowane bajty do parsera, aby nie odczytywać ponownie zmienionego pliku.
- Usunięto nadmiarowe puste linie EOF i poprawiono opis aktywnego workflow CI.

### Verified
- Backend: `381 passed, 182 skipped`; Ruff i mypy PASS.
- Frontend: Vitest `189 passed`; ESLint, TypeScript i build PASS.
- `git diff --check` PASS. Pominięto produkcyjne/operacyjne artefakty z
  nieśledzonego katalogu `webapp/` — nie należą do repozytorium.
- Po poprawkach: backend `400 passed, 182 skipped`; Ruff i mypy PASS. Testy
  integracyjne są wykonywane w GitHub Actions na osobnym Postgresie.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie: [Semantic Versioning](https://semver.org/).

## Aktywacja CI i przenośny test migracji — 2026-10-21 (niewdrożone)

- Właściciel dodał `.github/workflows/ci.yml` na gałęzi PR #4. CI jest aktywne;
  opis wcześniejszej blokady poniżej przedstawia stan historyczny.
  Uprawnienia aplikacji GitHub nie zostały rozszerzone.
- Pierwszy przebieg: frontend przeszedł wszystkie kroki, backend miał 561 PASS
  i jeden błąd testu migracji sesji: sztywna ścieżka `.venv/bin/alembic`
  nie istnieje na runnerze GitHub. Ruff, mypy i połączenie testowej bazy przeszły.
- Test uruchamia teraz `sys.executable -m alembic`, z tego samego środowiska co
  pytest. Dodano regresję wyboru interpretera i przekazania testowej bazy
  zamiast domyślnego DATABASE_URL. Nie zmieniono migracji ani workflow właściciela.
- Lokalnie Ruff, mypy (53 moduły) oraz 5 testów modułu sesji PASS, w tym pełny
  cykl migracji na odizolowanym `finanse_test` (loopback, port 55432).
  Pełny przebieg GitHub Actions po poprawce jest weryfikowany w PR #4.
- Bez wdrożenia, migracji produkcyjnej i zmian danych produkcji. PR nadal draft.

## Tailwind 4 i weryfikacja gotowości CI — 2026-10-20 (niewdrożone)

### Migracja i testy
- Tailwind 3 zastąpiono Tailwind **4.3.3** i natywnym pluginem Vite.
  Usunięto stary plugin PostCSS, konfigurację PostCSS i zbędne bezpośrednie
  zależności autoprefixer/postcss. Plik JS z paletą marki ładowany jest jawnie
  przez `@config`; skanowanie klas ograniczono do źródeł i index.html.
- Zachowano dotychczasową paletę sRGB, style przycisków, placeholderów i granic.
  Zaktualizowano nazwy utility zaokrągleń i focus outline zgodnie z v4;
  gradient pozostaje w sRGB. Nie zmieniano logiki finansowej ani API.
- **npm audit całego drzewa, także dev: 0 zgłoszeń**. Tym samym zamknięto
  poprzednie 7 zgłoszeń w łańcuchu Tailwind 3, bez `audit fix --force`.
- **189 testów Vitest PASS**, ESLint, TypeScript, build i diff check PASS.
  **18 testów Playwright PASS** (wcześniej 12): dodano kontrolę skompilowanych
  kolorów/paddingów, nawigacji responsywnej, focus klawiatury oraz geometrii modala.
- Porównano 31 scenariuszy/zrzutów przed i po migracji w Chromium przy 375/1440 px:
  strony, formularz edycji, szczegóły transakcji i menu mobilne, bez overflow.
  Nie jest to deklaracja zgodności piksel w piksel: natywne pola daty różnią się
  o 2 px, a modal nie dziedziczy już dawnego przesunięcia 16 px z odstępów rodzica;
  test potwierdza pełny viewport, wycentrowanie, Escape i focus.
- CSS buildu wzrósł z ok. 28.84 kB (gzip 5.82) do 37.34 kB (gzip 7.26).
  Backend niezmieniony; nie powtarzano jego poprzednich 562 testów w tej iteracji.
- Tailwind 4 wymaga nowoczesnych przeglądarek: Safari 16.4+, Chrome 111+,
  Firefox 128+. Lokalnie sprawdzano Chromium; Safari/Firefox nie były testowane.

### CI nadal wymaga działania właściciela
- Odczyt GitHub API `user/installations` potwierdził, że instalacja
  `genspark-ai-developer` ma contents/administration/issues/pull_requests,
  lecz **nie ma uprawnienia workflows**. API wykazało zero workflow w repo.
  Nie próbowano obejścia ograniczenia ani samodzielnego rozszerzania uprawnień.
- Zaktualizowano dostarczany osobno szkic `ci.yml`: Python 3.12, PostgreSQL 16,
  Node 22, lint/typecheck/test/build/audit/Playwright, minimalne contents:read,
  bez sekretów produkcji i bez wdrożenia. Szkic odrzuca pominięte testy integracyjne.
  Sprawdzono strukturę YAML i składnię osadzonego Pythona, nie wykonanie na GitHub.
- Właściciel musi dodać szkic jako `.github/workflows/ci.yml` lub nadać aplikacji
  uprawnienie workflows:write. **CI nie jest aktywne**, PR pozostaje draft.
- Migracja ma wydzielony commit w istniejącym PR #4; nie tworzono fikcyjnego
  osobnego PR z tej samej gałęzi. Bez wdrożenia, migracji bazy i zmian danych produkcji.

## Domknięcie walidacji backendu — 2026-10-20 (niewdrożone)

### Poprawki i kontrakty
- PATCH kont: jawny `null` dla `name`, `type`, `is_active`, `is_budget_account`
  zwraca 422 przed odczytem/zapisem encji. Pominięte pola nie są aktualizowane;
  `closed_at=null` oraz wartości `false` pozostają poprawne.
- PATCH inbox: analogicznie chronione `content` i `is_processed`; nadal można
  wyczyścić `target_id`/`target_type`. Test integracyjny potwierdza brak częściowego
  zapisu, gdy poprawne i błędne pola znajdują się w jednym żądaniu.
- Naprawiono dodatkowo 500 dla poprawnego PATCH inbox: po UPDATE jawnie
  odczytywany jest serwerowy `updated_at`, bez asynchronicznego lazy-load
  podczas synchronicznej walidacji odpowiedzi.
- Starsze endpointy list transakcji, inbox, zadań i bloków czasu wymagają
  `limit >= 1`; zachowano górne granice 200/500, wartości domyślne i `offset=0`.
  Testy obejmują dolne/górne granice, domyślne limity i błędne parametry.
- Ekstrakcja LLM ma ścisły schemat: rzeczywiste boolean `detected`, typ
  income/expense, dodatnia całkowita kwota do granicy BIGINT (bez konwersji
  string/bool/float), PLN/EUR/USD, ograniczony niepusty opis, data YYYY-MM-DD
  lub null i opcjonalna kategoria. Dodatkowe pola są zabronione.
- Błędny/niepełny JSON jest traktowany jako brak rozpoznania. Brakujące kwoty,
  waluty i daty nie są zgadywane. Ponowna walidacja przed dostępem do bazy
  chroni również bezpośrednie wywołania tworzenia sugestii.
- Zachowano JSON mode dostawcy i limit tekstu OCR; klient jest zamykany w
  `finally`. Logi odrzuceń nie zawierają tekstu OCR ani odpowiedzi modelu.
- Kwoty sugestii są zapisywane i formatowane bez float, również na granicy
  BIGINT. Sugestia nadal nie jest zatwierdzoną transakcją. Odrzucenie sugestii
  nie cofa OCR, a ponowne przetworzenie nie duplikuje istniejącego inbox item.

### Weryfikacja
- **562 testy backendu PASS, bez pominięć** (137 więcej niż po poprzednim etapie).
  Wyłącznie odizolowany PostgreSQL `finanse_test`, `127.0.0.1:55432`.
- Ruff, mypy (53 moduły), `pip check` i `git diff --check`: PASS.
- Frontend bez zmian kodu: ponownie **189 testów PASS / 23 pliki**, ESLint,
  TypeScript i produkcyjny build PASS. Playwright nie był powtarzany w tej iteracji.
- Wywołania LLM/OCR w testach są mockowane; nie zużywano API ani danych produkcji.
- Brak migracji, aktualizacji zależności i wdrożenia w tej iteracji.
  Zgłoszenia Tailwind zamknięto w późniejszym etapie opisanym powyżej;
  blokada uprawnień CI pozostaje otwarta.

## Audyt i refaktor — 2026-10-20 (niewdrożone)

### Zakres i poprawki
- Przegląd repozytorium: sesje, CSRF/Origin, limity Redis, izolacja właściciela,
  księga finansowa i raportowanie, zatwierdzanie narzędzi AI, dokumenty/worker,
  frontend, zależności i skrypty operacyjne. To lokalny audyt kodu i regresji,
  nie test penetracyjny produkcji ani gwarancja braku wszystkich podatności.
- Naprawiono `TypeError`/500 dla dowodów CSRF spoza ASCII: jawne 403 przed
  odczytem sesji; trzy nowe testy regresyjne.
- Naprawiono renderowanie strukturalnych błędów API (np. tablicy `detail` z 422)
  i błędów sieciowych na ekranie kont; cztery nowe testy regresyjne.
- Wydzielono `finance/entities.py` i `finance/ledger_validation.py`, zachowując
  fasadę serwisu i kontrakty routerów/importera/AI. Serwis: 1251 → 983 linie.
- Wydzielono wiersze kont/kategorii i normalizację błędów do komponentów;
  `FinanceAccounts.tsx`: 819 → 318 linii.
- NBP: zamykanie klienta HTTP także przy błędzie/braku kursu, odrzucanie
  NaN/Infinity oraz Decimal/half-even zamiast mnożenia float. Regresja:
  `75 * 4.1` ma dawać 308 groszy, nie 307. Dziewięć nowych testów.
- Zaktualizowano React Router 7, Vite 7, Vitest 4, TypeScript ESLint 8
  i zgodne zależności przechodnie; dostosowano konfigurację i testy routera.
- Zaktualizowano FastAPI/Starlette/Pydantic, certifi/Mako i pytest/pytest-asyncio;
  ujednolicono deklaracje zależności, dodano brakujące arq i narzędzia dev.
  Określono zakres pętli fixture asyncio. Nie zmieniono współdzielonego venv.

### Końcowa weryfikacja lokalna
- Backend: **425 PASS, zero pominięć** na PostgreSQL `finanse_test`, loopback
  `127.0.0.1:55432`. Początkowe 177 pominięć wynikało z domyślnego portu 5432.
- Frontend: **189 PASS / 23 pliki**; Playwright: **12 PASS** (desktop/mobile).
  Testy przeglądarkowe używają produkcyjnego buildu i mocków API, nie produkcji
  ani pełnej integracji z zewnętrznymi dostawcami.
- Ruff, mypy (53 moduły), ESLint, TypeScript, build, `pip check`,
  `git diff --check` i kontrola składni skryptów Bash: PASS.
- Audyt npm `--omit=dev`: zero zgłoszeń. Zapytanie OSV dla pakietów faktycznie
  zainstalowanych w nowym, odizolowanym środowisku Python: zero zgłoszeń.
  Wyniki są migawką baz podatności z dnia audytu, nie certyfikatem bezpieczeństwa.

### Pozostałe ryzyka i ograniczenia
- **Historyczne: 7 zgłoszeń npm w narzędziach deweloperskich**
  (5 high, 2 moderate), łańcuch Tailwind 3 / braces / parser selektorów.
  Zamknięto je migracją do Tailwind 4 opisaną powyżej; pełny audyt npm: 0.
  Nadal nie należy udostępniać narzędzi developerskich publicznie ani budować
  niezaufanych źródeł z poświadczeniami/sekretami.
- Wskazane wtedy braki walidacji (`null` w kontach/inbox, dolne granice limitów
  starszych list i schemat ekstraktora LLM) zamknięto w kolejnym etapie
  „Domknięcie walidacji backendu” opisanym powyżej.
- Pozostają ostrzeżenia deprecacji Passlib i nazwy stałej HTTP 422.
- Nie wykonano live testów LLM/NBP/Stirling/Redis, restore drill ani zmian
  konfiguracji produkcyjnej. Historyczna blokada zapisu workflow GitHub Actions
  opisana w PR nadal obowiązuje; wyniki powyżej są lokalne, nie z CI.
- **Brak wdrożenia, migracji i zmian danych produkcyjnych.** Zmieniły się
  zależności runtime, więc przed ewentualnym wdrożeniem wymagany jest nowy,
  zweryfikowany obraz backendu i workera, a nie samo podmienienie źródeł.

## [Unreleased] — 2026-08-15

### Added
- **Automatyczne backupy produkcyjne**: systemd uruchamia `finanse-backup.timer`
  codziennie o 02:30 i `finanse-restore-verify.timer` w pierwszą niedzielę o
  04:30 (`Europe/Warsaw`, `Persistent=true`). Usługi dzielą 15-minutowy lock;
  rootowy wrapper jest instalowany poza repozytorium, a failure unit zapisuje
  zredagowane zdarzenia do journala.
- Restore wybiera snapshot wyłącznie przez `RESTORE_SNAPSHOT_ID`; legacy
  `snapshot=` jest fail-closed. Usługi i ręczne targety Makefile współdzielą
  lock, a usługi retry po 15 minutach, maksymalnie 3 starty w 3 godziny.
- **Cache Restic dla timerów**: unit i Make używają
  `/docker/finanse/data/restic-cache` (`root:root`, `0700`), zachowując
  `ProtectHome=true`. Produkcyjny restore drill uruchamia wyłącznie service z
  wrapperem; niskopoziomowy target Make jest wewnętrzny.
- **Security baseline wdrożony**: produkcja używa fail-fast konfiguracji,
  zamkniętej rejestracji, unieważnialnych sesji server-side, CSRF/Origin,
  limitów Redis i zredagowanego audytu bezpieczeństwa. Backup Restic do
  Contabo S3 obejmuje PostgreSQL i uploady; restore drill przeszedł kontrolę
  checksum, migracji i invariantów ledgeru.
- **Sesje serwerowe — zmiana niekompatybilna**: migracja unieważnia wszystkie
  historyczne ciasteczka przeglądarkowe JWT i po wdrożeniu wymusza ponowne logowanie.
  Publiczne uwierzytelnianie Bearer JWT zostało usunięte na rzecz ciasteczka
  `advisor_session`; audyt repozytorium nie wykazał zewnętrznych konsumentów.
- **Security baseline -- backup and restore verification**: versioned scripts
  `ops/backup.sh` and `ops/restore-verify.sh` create encrypted Restic snapshots
  of PostgreSQL and uploads, retain 7 daily/4 weekly/6 monthly snapshots, and
  perform a checksum-verified restore only to a loopback `_restore`/`_test`
  database. Operations documentation describes external credential setup, the
  monthly drill, RPO 24h and RTO 2h. The external Docker Makefile exposes
  `backup` and `restore-verify` targets.
- **Usuwanie i dezaktywacja kont i kategorii**: kolumna `categories.is_active`
  (migracja `1dbfe88dfb1b`), `DELETE /accounts/{id}` i `DELETE /categories/{id}`
  (204; brak/cudzy → 404; rekordy powiązane → 409 z sugestią dezaktywacji),
  dezaktywacja kategorii przez `PATCH /categories/{id}` (`is_active`).
  Usunięcie blokuje się przy istniejących postingach/pozycjach schedulera/
  budżetach/kategoriach-dzieciach; nieaktywne konta i kategorie są odrzucane
   przy tworzeniu transakcji, budżetów i pozycji schedulera.
- **Zarządzanie kontami i kategoriami**: strona `/finances/accounts` umożliwia
  tworzenie, edycję, aktywację/dezaktywację i bezpieczne usuwanie kont oraz
  kategorii. Dodano hooki TanStack Query dla tych operacji, link „Konta” w
  sidebarze i komunikaty o blokadzie usunięcia rekordów z historią.
- **Budżety w prognozie płynności**: prognoza zawiera podsumowanie budżetów
  bieżącego miesiąca (limit, wydano, pozostało) oraz ostrzeżenie, gdy pozostałe
  budżety przekraczają prognozowane saldo przed wypłatą.
- **Przewalutowanie (exchange)**: `POST /finance/transactions/exchange` z kursem
  NBP (automatycznym) lub ręcznym; zapisuje obie rzeczywiste kwoty i kurs jako
  transakcję `exchange` (PLN↔EUR/USD, suma zero zachowana). Formularz
  „Przewalutowanie" w `/finances/transactions`.
- **Edycja i usuwanie transakcji**: `DELETE /transactions/{id}` (kaskada postingów)
  oraz edycja inline opisu i daty w liście transakcji; usunięcie z potwierdzeniem.
- **Ręczne księgowanie transakcji**: formularz na `/finances/transactions` tworzy
  przychód, wydatek i transfer między kontami przez istniejący `POST
  /finance/transactions` (double-entry zachowany po stronie serwisu). Helper
  `buildTransactionPostings` koduje konwencję `balance = credit − debit`
  (przychód: konto `credit`/kategoria `debit`; wydatek: odwrotnie; transfer:
  źródło `debit`/cel `credit`). Kwoty w PLN.
- **Miesięczne budżety z limitami**: tabela `category_budgets` (limit `BIGINT > 0`
  per kategoria, unikalny na użytkownika i kategorię) z migracją
  `4340d1460982_category_budgets`. Endpointy `GET/POST /budgets`,
  `PATCH/DELETE /budgets/{id}` oraz `GET /budget-status` (wydane i pozostało,
  roll-up wydatków potomków dla kategorii-grup, kategorie z limitem i zerowymi
  wydatkami nadal widoczne). Strona `/finances/budgets` pokazuje limity, wydane,
  pozostało i pasek postępu z edycją inline, dodawaniem i usuwaniem.
- **Finanse — podstrony i zarządzanie płynnością**: rozdzielono widok finansów
  na realne trasy `/finances`, `/finances/transactions`, `/finances/cashflow`,
  `/finances/budgets` i `/finances/reports`; kontekstowy sidebar prowadzi do
  istniejących tras, a pozycje niezrealizowane pozostają oznaczone „Wkrótce".
- **Cashflow — formularze**: ustawienia dnia wypłaty, konta wpływu, horyzontu i
  tolerancji opóźnienia; CRUD miesięcznych pozycji przychodu/wydatku z metodą
  kwoty `fixed` lub `last_actual`, dezaktywacja oraz jawne usuwanie.
- **Cashflow — potwierdzanie sugestii**: endpoint
  `POST /cashflow/items/{item_id}/confirm` przelicza sugestię po stronie serwera
  i tworzy zbilansowaną transakcję wyłącznie przez serwis domeny finance;
  blokada wiersza chroni przed równoległym podwójnym księgowaniem.
- **Raporty z wyborem okresu**: `GET /summary` i `GET /category-summary`
  przyjmują `month`/`year` (z walidacją zakresu) i zwracają wartości wyłącznie
  wybranego miesiąca; domyślnie pozostaje bieżący miesiąc.
- Endpoint `DELETE /cashflow/items/{item_id}` do jawnego usunięcia własnej pozycji.

### Changed
- Frontend i npmplus komunikują się przez dedykowaną sieć
  `finanse_ingress`; backend jest wyłącznie na `internal`. Nginx normalizuje
  IP klienta przed przekazaniem do backendu.
- Operacyjne listy finansowe ukrywają nieaktywne konta i kategorie; strona
  `/finances/accounts` pozostaje bez zmian i nadal pokazuje pełną listę zarządzania.
- Potwierdzenie schedulera odrzuca pozycje nie-PLN (brak zweryfikowanego kursu),
  przyszłe, `overdue_uncertain`, `amount_unknown` i `matched_actual`; przyjmuje
  wyłącznie `due`/`overdue` z wyliczoną kwotą i ponownie waliduje powiązane konto
  i kategorię pod blokadą wiersza.
- Formularz schedulera ogranicza konta do aktywnych kont budżetowych w PLN.
- Wydzielono współdzielone komponenty finansowe (`formatPLN`, `SummaryCard`,
  `MonthPicker`, `CategorySpendTree`, `AccountTransactions`) oraz poprawiono
  znak transakcji per konto zgodnie z konwencją `balance = credit − debit`.

### Verified
- Automatyzacja na VPS: świeże `make test` przeszło (backend `198 passed, 125
  skipped`; frontend `129 passed`), a lint, typecheck i `git diff --check`
  przeszły. Oba timery są enabled. Ręczny backup utworzył `015211bb`; restore
  drill zakończył się sukcesem, nie pozostawił `finanse_restore` ani outputu,
  tylko pusty `root:root` `0700` parent. Statusy i journal nie zawierały
  sekretów. Wdrożenie nie spowodowało przerwy aplikacji webowej.
- Finalny proof po retry/lock hardening: backend `201 passed, 125 skipped`,
  frontend `129 passed`; lint, typecheck i `git diff --check` PASS. Legacy
  `snapshot=deadbeef` zakończył się kodem 2 przed runnerem/Restic. Backup
  utworzył `11fd2129`, a restore service zakończył się `status=0/SUCCESS`;
  parent restore pozostał pusty `root:root` `0700`, baza nie istnieje, journal
  nie zawiera sekretów.
- Cache proof: backend `201 passed, 125 skipped`, frontend `129 passed`; lint,
  typecheck i `git diff --check` PASS. Po instalacji cache `root:root` `0700`
  backup utworzył `a6e89e9d`, a restore service zwrócił `status=0/SUCCESS`.
  Bieżące okno journala nie zawiera `unable to open cache`; parent jest pusty,
  `finanse_restore` nie istnieje, a logi nie zawierają sekretów.
- Security baseline: backend `192 passed, 125 skipped`; integracyjne
  `125 passed`; frontend `129 passed`; Ruff, mypy, ESLint, TypeScript i build
  PASS. Snapshoty Contabo S3: `922d1aba` (przed migracją) i `63145774` (po
  migracji); pierwszy przeszedł rzeczywisty restore drill.
- Produkcja: migracja `c9d8e7f6a5b4` zastosowana, wszystkie usługi Up;
  health i frontend HTTP 200. Rejestracja zwraca 404, błędny login z zaufanym
  Origin 401, a bez Origin 403.
- Backup/restore static tests: `6 passed`; full backend unit suite:
  `132 passed, 109 skipped, 3 warnings`; Ruff and `bash -n` pass.
  ShellCheck is not installed. No Restic credentials, production backup,
  production restore, migration, or deploy was run.
- CRUD kont i kategorii: `make test` — backend `126 passed, 109 skipped` i
  frontend `106 passed`; `make test-integration` — `109 passed`; `make lint`,
  `make typecheck` i frontendowy production build PASS.
- Produkcja: migracja `1dbfe88dfb1b` zastosowana, backend/frontend/worker
  przebudowane i uruchomione; `https://finanse.birek.online/api/health` zwraca
  HTTP 200.
- Backend: `make lint` i `make typecheck` PASS. `make test`: `125 passed,
  79 skipped, 3 warnings`. `make test-integration` na izolowanej bazie:
  `79 passed, 125 deselected, 11 warnings`; migracja `4340d1460982` zastosowana,
  kontener testowy usunięty.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (`14 plików,
  63 passed`) i `npm run build` PASS.
- Naprawiono przekazywanie `transaction_date` (wcześniej `date`) w
  `useCreateTransaction` — wybrana data transakcji jest teraz zapisywana.
- Nie wykonano migracji produkcyjnej ani deployu dla ręcznego księgowania.

### Fixed
- Restore drill jawnie przekazuje bezpieczną nazwę bazy do `pg_restore`,
  izoluje środowisko Alembic i obsługuje zakodowany parametr `passfile`.
- **Ingress isolation**: final Task 7 rollout now has a documented dedicated
  `finanse_ingress` bridge (`172.24.0.0/24`), where only static npmplus
  `172.24.0.2` is trusted by the frontend. Backend remains internal-only.
- **Security baseline — limity za reverse proxy**: npmplus może przekazać łańcuch
  wyłącznie do frontendu, który normalizuje go modułem Nginx realip i wysyła do
  backendu pojedynczy adres. Backend akceptuje tylko jeden ścisły literal IP od
  aktualnie rozwiązanego kontenera `frontend`; łańcuch, whitespace lub bezpośredni
  peer wraca do adresu peera. Limity logowania, Advisora i uploadu są współdzielonymi
  zależnościami FastAPI. Backend usunięto z zewnętrznej sieci `proxy`; frontend
  pozostaje jedynym ingress do API.
- `PATCH /accounts/{id}` odświeża konto przed zwróceniem odpowiedzi
  (`db.refresh`), eliminując MissingGreenlet na `updated_at` po flush UPDATE
  (analogicznie do naprawionego wcześniej PATCH kategorii).
- Odwrócony znak transakcji per konto (`AccountTransactions`): przychód
  (income) z postingiem `credit` renderuje zielony „+", a wydatek (expense)
  z `debit` czerwony „−", zgodnie z konwencją `balance = credit − debit`.
- Formularz pozycji schedulera ogranicza wybór konta do aktywnych kont
  budżetowych w walucie PLN i blokuje walutę na „PLN", eliminując pozycje
  niemożliwe do potwierdzenia przez backend (non-PLN).
- Udokumentowano testem zakres invalidacji cashflow: w TanStack Query v5
  prefiks `["finance","accounts"]` obejmuje także transakcje per-konto
  (`["finance","accounts", id, "transactions", ...]`), więc centralna
  invalidacja po confirm/delete/create/update jest kompletna bez zmian.

### Added
- **Frontend — contextual sidebar**: jedna konfiguracja danych zasila desktopowy
  `IconRail`, menu kontekstowe i mobilny drawer; kontekst wybiera URL według
  najdłuższego pasującego prefiksu. Przyszłe moduły nie mają route'ów i są
  oznaczone jako „Wkrótce”.
- **Finanse — prognoza płynności cyklu wypłaty**: ustawienia dnia wypłaty,
  konta wpływu, horyzontu i tolerancji opóźnienia; miesięczne pozycje
  przychodu/wydatku powiązane z kontem budżetowym i kategorią.
- Migracja `8a6d0c1e2b3f` tworzy `finance_settings` i
  `scheduled_finance_items` z ograniczeniami dni, typów, metod kwot i własności
  relacji.
- Endpointy `cashflow/settings`, `cashflow/items` i `cashflow/forecast` oraz
  karta i lista prognozy na stronie Finanse.

### Changed
- Prognoza wykorzystuje wyłącznie salda kont budżetowych, kwotę stałą lub
  ostatnią zgodną transakcję, rozpoznaje rzeczywisty wpis w oknie trzech dni i
  nie dubluje go w projekcji. Po trzech dniach od terminu pozycja ma status
  `overdue_uncertain` i nie wpływa na saldo.
- Odczyt prognozy nie tworzy transakcji, postingów ani domyślnych ustawień;
  UI nie oferuje akcji księgowania.

### Verified
- Frontend: Vitest `12 passed`, ESLint, TypeScript typecheck i Vite production
  build przeszły. Testy routingu obejmują najdłuższy prefiks URL, active state,
  tooltip raila oraz zablokowane pozycje przyszłych modułów.
- Migracja izolowanej bazy `finanse_test` na `127.0.0.1:55432` doszła do
  `8a6d0c1e2b3f`; nie uruchomiono migracji produkcyjnej.
- `make VENV=/opt/finanse/backend/.venv/bin lint` i `typecheck`: PASS.
- `make VENV=/opt/finanse/backend/.venv/bin test`: backend `123 passed,
  47 skipped, 3 warnings`; frontend Vitest `7 passed`.
- `make VENV=/opt/finanse/backend/.venv/bin test-integration`: `47 passed,
  123 deselected, 11 warnings`; kontener testowy został usunięty.
- `npm run build` w `frontend`: PASS. Nie wykonano deployu.

### Fixed
- Domknięto historię tool calls Advisora dla kolejnych tur, walidację własności i walut transakcji w serwisie domenowym oraz oznaczenie sald `balance_pln` jako PLN.
- Fixture testowej bazy wiąże aplikacyjny session factory z izolowanym silnikiem per test.
- Import Actual rozpoznaje sobotnio-niedzielne HTTP 404 z NBP Table A, używa poprzedniego opublikowanego kursu z ograniczonego zakresu i zapisuje źródło `nbp_previous_business_day` zamiast odrzucać transakcję lub używać kursu 1.0.
- Reconciliation Actual wylicza oczekiwane salda kategorii bez `build_pa_postings`, raportuje agregaty grup kategorii i blokuje commit przy każdej różnicy grupy.
- Konta i kategorie importowane z Actual mają trwałe `source='actual'`; tryb zastąpienia odrzuca transakcję poza wskazanym blobem i każde ręczne użycie kandydata legacy.
- Preflight korekty legacy Actual rozpoznaje wyłącznie syntetyczny bilans otwarcia
  `source='actual'` z prefiksem `[BO] Bilans otwarcia`, dwiema przeciwnymi nogami
  tego samego konta i bez kategorii; każdy inny niepasujący rekord nadal blokuje korektę.

### Changed
- `DB_SCHEMA.md` opisuje rzeczywiste statusy `ToolExecution`.

### Added
- Testy pętli tool-calling Advisora: odpowiedź Level 0 po wykonaniu narzędzia, błędny JSON, nieznane narzędzie, błędy executora, limit iteracji oraz oczekiwanie na potwierdzenie Level 2.
- Testy potwierdzania mutacji: blokada ponownego confirm/deny, izolacja użytkownika, odrzucenie błędnego wyniku oraz rollback częściowej mutacji, gdy executor lub audit log zakończy się błędem.
- Izolowana baza PostgreSQL do testów integracyjnych na `127.0.0.1:55432`; fixture tworzy i usuwa schemat, a `make test-integration` sprząta kontener i sieć po zakończeniu.
- Flagi korekty `--replace-legacy-actual --backup-path`: wymagają `--execute --require-reconciled`, tworzą custom-format `pg_dump`, weryfikują go przez `pg_restore --list`, a dopiero potem otwierają transakcję zastąpienia.

### Changed
- **Doradca — bezpieczne mutacje finansowe**: `create_transaction` wymaga jawnego `account_name`, akceptuje wyłącznie dodatnie kwoty całkowite i odrzuca niezgodność waluty konta oraz walutę bez zweryfikowanego kursu FX.
- **Doradca — atomiczność potwierdzeń**: blokada wiersza chroni przed równoległym potwierdzeniem, a savepoint wycofuje częściowe zapisy executora i audit logu.
- **Frontend Advisora**: polling aktywnej rozmowy co 2 sekundy działa wyłącznie przy `pending_confirmation`; po rozstrzygnięciu polling się zatrzymuje.
- Poprawiono lokalne granice dnia i obsługę zmian czasu w harmonogramie, w tym offset DST zależny od konkretnej daty.
- Przywrócono lokalną semantykę daty transakcji (`7cc1973`): brak jawnej daty używa bieżącego dnia użytkownika zamiast daty UTC.
- Dodano konfigurację ESLint 8 z parserem TypeScript, regułami React Hooks/Refresh oraz środowiskiem browser/ES2022.

### Fixed
- Usunięto 7 błędów frontendowego lintowania.
- Spłacono backendowy dług Ruff i mypy: `ruff check app/ tests/` oraz `mypy app/` przechodzą.
- Poprawiono ochronę fixture testowej bazy: schemat można tworzyć i usuwać tylko w lokalnej bazie `finanse_test` na zatwierdzonym porcie; niedostępna baza powoduje pominięcie testów integracyjnych zamiast ingerencji w inną bazę.

### Verified
- Task 7 Actual reconciliation against isolated `finanse_test` on `127.0.0.1:55432`: migrations reached `e7a4b2c6d8f0`, and `--execute --require-reconciled` completed with exit code 0. No production PA database or Actual write API was used.
- `/tmp/actual_migration/reconciliation.json` has `is_reconciled=true`: all 15 account rows and all 46 category rows have zero difference; `Revolut USD` is `Actual 290`, `PA 290`, `diff 0`.
- The four formerly rejected USD expenses were imported using verified prior business-day rates and `fx_rate_source=nbp_previous_business_day`; the import wrote 800 transactions with 0 errors.
- Fresh quality gate in `actual-reconciliation`: Ruff, ESLint, mypy and TypeScript passed; backend pytest passed (`110 passed, 40 skipped, 5 warnings`); frontend Vitest passed (`6 tests`); Vite production build passed.
- Wdrożenie produkcyjne: obrazy backend/frontend zbudowane i uruchomione; `/api/health` oraz frontend zwracają HTTP 200.
- Smoke test produkcji: backend zgłasza `status=ok`, `environment=production`; kontenery backend/frontend działają.
- Historia sesji `f90a4d6..ab344ad` obejmuje 27 commitów; wcześniejszy zapis o 17 commitach był nieaktualny. Bieżący corrective docs commit nie należy do tego zakresu.
- Backend Ruff: PASS, bez błędów.
- Backend mypy: PASS, `46 source files`, bez błędów.
- Backend pytest: PASS, `89 passed, 23 skipped, 5 warnings`; testy zależne od niedostępnej lokalnie bazy zostały pominięte.
- Testy integracyjne z izolowanym PostgreSQL: PASS, `23 passed, 89 deselected, 11 warnings` w świeżonym uruchomieniu.
- Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (`1 test file, 4 tests`) oraz `npm run build` przeszły.
- Zmiany wyłącznie porządkowe w `backend/migrations/` przywrócono do `f90a4d6`; nie zmieniono schematu.
- Nie wykonano migracji produkcyjnej; deploy aplikacji wykonano po scaleniu do `main`.

### Known Limitations
- Backend i frontend korzystają w tym worktree z zależności poza repozytorium: backend z `/opt/finanse/backend/.venv`, frontend z lokalnego `node_modules`.
- Testy zgłaszają ostrzeżenia dotyczące domyślnego scope event loop w `pytest-asyncio`, deprecacji `crypt`/Argon2 i `datetime.utcnow` w zależnościach oraz `RuntimeWarning` w mocku NBP.
- Parser split transactions nie został zweryfikowany na rzeczywistych danych użytkownika.
- Brak SSE/streamingu dla zmian innych niż polling oczekujących potwierdzeń.

## [0.3.0] — 2026-08-12

### Added
- **Doradca Level 2 — narzędzia mutujące z potwierdzeniem użytkownika**
  - `create_task`, `create_time_block`, `create_transaction` w tool registry
  - Endpointy `POST /api/advisor/tool-executions/{id}/confirm` / `/deny`
  - Status `pending_confirmation` → `completed` / `denied` + audit log
  - Frontend: przyciski potwierdzenia/odrzucenia mutacji w czacie
- **Ekstrakcja danych finansowych z dokumentów (OpenAI/DeepSeek)**
  - `documents/extractor.py`: OCR text → structured JSON (type, amount w groszach, currency, category_suggestion)
  - Tworzy inbox item z sugerowaną transakcją → zatwierdzenie przez użytkownika w Inbox
- **Stirling PDF + OCR pipeline (dokończenie Iteracji 2)**
  - Worker async (Redis + ARQ), pipeline: upload → SHA-256 → Stirling → OCR → tekst
  - Frontend Dokumenty: upload, lista, podgląd plików
- **Rozbudowany kalendarz**: widok miesiąca, taski z due dates, filtrowanie po zakresie dat, kolorowane bloki czasowe
- **Finanse**: endpoint transakcji per konto, opening balances w migracji z Actual
- **Konfiguracja opencode pod projekt**
  - LSP: pyright (Python) + typescript-language-server (TS) — `lsp: true` + jawny override TS
  - MCP EXA: remote `https://mcp.exa.ai/mcp`, klucz przez `{env:EXA_API_KEY}` (bez sekretu w repo)
  - 7 komend: `/test`, `/lint`, `/typecheck`, `/migrate`, `/migration "opis"`, `/deploy`, `/docs`
  - Formatter: ruff (Python) + prettier (TS/JS/CSS/HTML/JSON) po zapisie
  - References (docs, infra), watcher ignore, permissions (lsp/webfetch/websearch/gh)
  - Skill `session-workflow` (inicjalizacja sesji + aktualizacja docs)
- **Narzędzia dev**: ruff 0.16.2 + mypy 2.3.0 w `backend/.venv`; config w `pyproject.toml`
  (ruff line-length 100, mypy `explicit_package_bases`, pytest `pythonpath`); Makefile naprawiony (jawne ścieżki `.venv/bin/`)

### Changed
- **Finanse — redesign strony**: uproszczona z 470 → 86 linii (widok sald, wybór konta, transakcje per konto)
- **Stirling OCR**: pipeline dwustopniowy — najpierw OCR dokumentu, potem ekstrakcja tekstu
- Frontend: lista kont z saldami, sekcja przychodów/wydatków

### Fixed
- **Statusy narzędzi Doradcy**: polling aktywnej rozmowy co 2 s tylko dla `pending_confirmation`, precyzyjne invalidacje po confirm/deny i obsługa błędów w bannerze
- **Payee resolution** w imporcie z Actual (fallback na kategorię)
- **Opening balances** poprawnie zapisywane przy migracji
- **Frontend nie ładował danych z API** — ostatecznie naprawione (wszystkie strony na TanStack Query)
- **Eager-loading tool_executions** w `get_conversation_messages` (ToolCallBanner po przeładowaniu)

## [0.2.0] — 2026-08-11

### Added
- **Import z Actual Budget**: skrypt CLI `scripts/migrate_actual.py`
  - Parser Actual SQLite (konta, kategorie, transakcje, transfery, splity)
  - Provider kursów NBP z cache (EUR, USD)
  - Double-entry invariant zachowany — 800 transakcji zaimportowanych (0 błędów)
  - Idempotentność przez `[actual:{uuid}]` prefix w description
  - Tryb `--dry-run` do walidacji przed zapisem
  - Raporty `migration_report.txt` + `migration_log.json`
- **22 testy** dla importu (unit + integracyjne)

### Changed
- Actual Budget dane zaimportowane do PA (15 kont, 46 kategorii, 800 transakcji)
- Backend ma dostępne narzędzia importu w `scripts/`

## [0.1.0] — 2026-08-10

### Added
- **Backend**: FastAPI + SQLAlchemy 2.x async + Alembic
  - 7 domen: identity, finance, work, inbox, advisor, documents, audit
  - Double-entry ledger: konta, kategorie, transakcje, postings (BIGINT)
  - Auth: Argon2id, JWT w HttpOnly Secure SameSite=Strict cookies
  - Policy engine dla Advisor (poziomy autonomii 0-4)
  - Audit log dla operacji mutujących
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS
  - TanStack Query + React Router v6 + Zustand
  - 9 stron: Login, Today, Inbox, Projects, ProjectDetail, Calendar, Finances, Advisor, Settings
  - Dark theme (gray-950), responsive layout
  - PWA-ready (manifest, theme-color)
- **Docker**: postgres:16, redis:7, backend, frontend (nginx+SPA), stirling-pdf
  - Wzorzec: kod w `/opt/finanse/`, infrastruktura w `/docker/finanse/`
  - Reverse proxy: npmplus (Nginx Proxy Manager fork)
- **Dokumentacja**: AGENTS.md, PRD.md, DB_SCHEMA.md, 9 ADR-ów
  - CHANGELOG.md, JOURNAL.md, TASKS.md
  - Agent OpenCode: `.opencode/agent/personal-advisor.md`
- **Testy**: 15 testów (11 unit + 4 integracyjne wymagające DB)
  - Double-entry invarianty, hashowanie haseł, tokeny, auth middleware

### Changed
- Actual przeniesiony z `finanse.birek.online` na `finanse.vps.birek.online`

### Verified
- E2E: rejestracja → logowanie → redirect /today → sesja cookie
- E2E: tworzenie konta → tworzenie transakcji (double-entry, suma=0)
- Frontend: wszystkie assety ładują się (302 KB JS + 21 KB CSS)
- Backend: health check, wszystkie endpointy auth i finance
