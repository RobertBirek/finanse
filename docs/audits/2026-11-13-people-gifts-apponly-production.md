# Osoby i darowizny — zakończone wdrożenie app-only

## Wynik

**Wdrożone i zweryfikowane na `https://finanse.birek.online`.** Backend, worker
i frontend używają zatwierdzonych obrazów rewizji `e0e746e` (kod funkcjonalny
`79011bc`), schemat pozostaje `2c77e935ee39`. Status aktywnego wydania:
`verified-live`. W tym wdrożeniu NIE uruchomiono migracji ani korekty danych.

Scalenie i push aplikacji: main `6b6d4f9`; późniejszy zapis stanu rollbacku:
`5bad1b9`. Drzewa backend/frontend/ops obu i wydania są zgodne. Dokumentacja tego
odbioru jest osobnym commitem na main, nie nowym obrazem aplikacji.

## Zgoda i zakres

Po opisanych w poprzednim raporcie błędach operatora użytkownik zatwierdził nowy
sześciopunktowy plan: najpierw próba w izolacji, te same obrazy, świeży backup
i restore, app-only rollout, testy odczytowe i minimum 300 sekund obserwacji.
Dodatkowo polecił: **„zrób izolowany klon na stałe, nie kasuj go”**.

Nie zmieniano siedmiu historycznych darowizn, kategorii, dat, kwot, postingów lub
sald. Nie tworzono testowych osób/linków w produkcji, nie wykonywano importów,
konwersji income→transfer, etapu A2 ani pożyczek etapu B. Wcześniejsza addytywna
migracja pozostała; nowy operator nie zawiera funkcji ani polecenia migracji.

## Bramki przed przerwą techniczną

- Potwierdzono zgodność źródeł z dowodem backend 2468 PASS i frontend 677 PASS.
  Z wcześniejszego odbioru: pełny UI 201 PASS / 1 planowy skip, świeże 4 E2E,
  tsc/ESLint/build i mypy205 PASS, lint zmienionych app/tests PASS, packaging6 PASS.
- Ponowiono obowiązkowy offline import jako finalne non-root `10001:10001`,
  porównano rzeczywistą zawartość trzech immutable image IDs z zatwierdzonym Git
  i świeżym dist. Pełny Compose różni się wyłącznie obrazami/build aplikacji.
- Ten sam walidator kontraktu GET działa offline, na ASGI, na faktycznym klonie
  aplikacji oraz live. GET nie wymaga requestBody; anonymous401 i ownedGET200
  potwierdzono bez tworzenia produkcyjnych sesji lub danych testowych.
- Online świeży backup/restore na trwałym klonie: identyczne 81 tabel i uploads.
- Rzeczywista próba trzech aplikacji (uvicorn/arq/nginx + własny Redis) oraz
  rzeczywisty rollback do starych trzech obrazów przeszły przed maintenance.
  Wszystkie tymczasowe aplikacje współdzieliły tylko networkless namespace klonu.
  Klonowy nginx miał read-only overlay zmieniający wyłącznie hostname backendu
  na loopback; konfiguracja produkcji i zawartość obrazów nie były modyfikowane.
- Publisher wykonano na shadow filesystem z rzeczywistym raportem obserwacji.
  Końcowy zestaw: **12 testów operatora PASS**, w tym awaria final verifiera
  wymuszająca rollback przed ogłoszeniem sukcesu.

## Review i decyzje

Review `ses_e2b581fc6ffeCZx6O0i5B4kqwR`: 2 Critical i 4 Important. Zabezpieczono:
lokalny drain z ustalonym SHA256, backup i helper połączenia z zatwierdzonego Git
przygotowane przed maintenance, manifest wszystkich wykonywanych skryptów,
końcowy verifier wewnątrz transakcji wdrożenia, aktualne public_observation oraz
kontrolę StartedAt/RestartCount usług danych. Regresje security RED → GREEN;
realny publisher i artefakty sprawdzone ponownie. Brak odłożonych Minors.

Jawne rozstrzygnięcia:

1. Pełna próba online jest przed maintenance, a dodatkowy fresh frozen backup,
   restore i sandbox są po fence. To dwie bramki, nie zamiennik testów przed
   przerwą. Koszt: dłuższa, ograniczona przerwa, zamiast użycia nieświeżej kopii.
2. Wyłączenie dostawców w sandboxie powoduje wyłącznie w KLONIE zmianę trzech
   tabel polityk i dopisanie audit_events. Kontrolowana allowlista dotyczy tylko
   tych czterech tabel; pozostałe hashe i księga są identyczne. Stan przy samym
   restore sprawdzano ściśle dla wszystkich 81 tabel. Produkcyjne retention NIE
   ma tej allowlisty: wszystkie 81 tabel muszą być niezmienione przed ingress.
3. Publikacja metadanych to atomic rename z końcowym sprawdzeniem oczekiwanej
   wartości pod advisory flock. Wszyscy uprawnieni operatorzy muszą używać tej
   blokady; nie jest to kernelowy CAS przeciw niekooperującemu root.
4. Klon pozostaje na stałe zgodnie z poleceniem użytkownika; cleanup obejmuje tylko
   tymczasowe aplikacje sandbox i plaintext backup/raw/input. Koszt: utrzymywany
   wolumen z poufną kopią danych, bez otwartych portów i dostępu zewnętrznego.

## Pierwsza próba nowego operatora i naprawa

Pierwszy app-only rollout przeszedł runtime, GET/static/auth/worker i 29 kontroli
przez 300.97 sekundy z licznikami błędów równymi zero. Publisher błędnie sprawdzał
truthiness słownika `errors={backend:0,worker:0,frontend:0}`; test miał pustą listę.
Przed publikacją metadata nastąpił automatyczny, zweryfikowany rollback aplikacji.

Nie pominięto błędu: rzeczywisty receipt odtworzono w helperze i w całym publisherze
na shadow filesystem (RED2 → GREEN, pełne12 PASS). Teraz kontrolowany jest każdy
licznik i suma wartości. Zachowano dowody/backup pierwszej próby; ponowienie
wykonało nowy fence, backup/restore i nową obserwację, nie ręczne dopisanie sukcesu.

## Końcowy odbiór produkcyjny

- Cały operator zakończył się statusem 0:
  `PEOPLE_GIFTS_APPONLY_DEPLOYED_VERIFIED_LIVE_PASS`.
- Podmieniono tylko backend/worker/frontend. Finalne image IDs, rewizje, env,
  użytkownicy, mounty i sieci są zgodne z zatwierdzonym renderem.
- Przed otwarciem ingress zachowane wszystkie 81 tabel i uploads, ledger0.
  Brak migracji i produkcyjnych mutacji testowych.
- HTTPS200, health200, anonymous accounts/people401, OpenAPI GET, wszystkie bajty
  plików dist, browser375/1440 i worker readiness PASS.
- **29 kontroli / 304.07 sekundy; backend/worker/frontend: 0 błędów, 0 restartów.**
  Usługi danych mają niezmienione ID, image, mounty, StartedAt i RestartCount.
- Atomowe metadane `verified-live` zawierają aktualną obserwację rewizji e0e746e
  i schema2c. Final verifier wykonał się w transakcji oraz ponownie po zakończeniu.

Zweryfikowany, zaszyfrowany snapshot końcowy:
`5b32e0599ba03c4823ba27a17f7528b8d52b3db98d6c24fe351802aaa1cbb13f`.
Zachowano backupy, rollback `db3a4b3` i jego pełny override; bez retention/prune.
Plaintext backup/raw/input usunięte. Przy ewentualnym rollbacku zachować schema2c;
nie wykonywać downgrade lub produkcyjnego restore bez osobnej zgody.

## Trwały klon — NIE USUWAĆ

- Kontener: `finanse-people-gifts-certification-pg`.
- Wolumen: `finanse_people_gifts_certification_pgdata`, restart `unless-stopped`.
- Network `none`, brak publikowanych portów i podłączenia do sieci produkcyjnych.
- Zachowano cztery odtworzone bazy `certify_*`; każdy restore tworzył nową bazę,
  bez nadpisywania ani DROP poprzednich. Zawierają kopię danych produkcyjnych.
- Prywatny inventory i instrukcja poza /tmp:
  `/opt/finanse/webapp/clones/people-gifts-certification/`.
- Usunięcie kontenera, wolumenu lub tych baz wymaga osobnej zgody użytkownika.

## Dowody i pozostałe ograniczenia

Prywatny operator: `/tmp/opencode/people-gifts-apponly-e0e746e/`.
Trwała kopia dowodów: `/opt/finanse/webapp/releases/people-gifts-e0e746e/evidence-apponly/`.
Pierwotny nieudany operator i wcześniejsze rollbacki opisuje poprzedni raport;
nie są przedstawiane jako udane wdrożenia.

GitHubCI43410274033: frontend FAILED na npm audit7vulns (6 moderate/1 high), backend
CANCELLED. Manifesty zależności bez zmian względem poprzedniej produkcji. Pełny
Ruff nadal ma 3 zastane DTZ007; dodatkowe 5 stylistycznych diagnostyk wygenerowanej
migracji leży poza standardowym `/lint app/tests`. To nie jest globalnie zielone CI.
Naprawa zależności i lint wymagają osobnego planu; nie używano auditfix--force.
