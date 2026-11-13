# Osoby i darowizny — integracja i przerwane wdrożenie

**Aktualizacja:** po odrębnie zatwierdzonym planie app-only wdrożenie zakończono.
Aktualny stan opisuje `2026-11-13-people-gifts-apponly-production.md`.
Poniżej zachowano historyczny odbiór pierwotnej, przerwanej procedury.

## Stan końcowy

**Nowe wydanie NIE jest wdrożone.** Scalenie i push są zakończone. Produkcja działa
na poprzednich obrazach `db3a4b3`, po zweryfikowanym automatycznym rollbacku.
Addytywna migracja `3254a4781542 → 2c77e935ee39` została wykonana i pozostaje.
Metadane aktywnego wydania: `rollback-verified-live`. Nie wykonywano downgrade ani
odtwarzania produkcyjnej bazy. Kolejna próba wymaga zmienionego planu operatora.

## Zgoda i integracja

- Użytkownik: „scal, wypchaj na main i wdróż”, następnie „dokończ”.
- Zatwierdzony appcommit `e0e746e`, kod funkcjonalny `79011bc`.
- Main `6b6d4f9` został wypchnięty i porównany z remote. Trzy konflikty dokumentacji
  rozwiązano zachowaniem obu stron; drzewa backend/frontend/ops identyczne z appcommit.
- Zakres obejmuje osoby, metadane historii darowizn i spójny backend/worker/frontend.
  Bez korekty siedmiu historycznych wpływów, bez konwersji ich na transfery, bez B.

## Potwierdzone bramki

- Pełny backend: 2468 PASS na niezmienionym kodzie `79011bc`.
- Świeży frontend: 677 PASS / 110 plików; ESLint, tsc, build PASS.
- Świeży Playwright: 4 PASS, desktop/mobile. Pełny przebieg implementacyjny:
  201 PASS i 1 planowy skip. Zrzuty profilu osoby obejrzane dla 375 i 1440 px.
- Mypy: 205 plików PASS; lint zmienionych app/tests PASS. Pełny Ruff: 3 zastane
  DTZ007 w nietkniętych parserach. Dodatkowe wywołanie Ruff bezpośrednio na pliku
  migracji wykazało 5 stylistycznych naruszeń poza zakresem komendy `/lint`.
- Packaging proxy: 6 PASS / 11 deselected. Trzy wersjonowane obrazy offline,
  non-root import gate dla finalnych UID:GID `10001:10001` i dokładnych image IDs PASS.
- Pełny Compose zachowuje env, mounty, użytkowników, sieci i usługi danych; zmieniane
  tylko obrazy/build aplikacji. Zawartość emitowanego release'u oraz rzeczywistych
  trzech obrazów porównana z zatwierdzonym git i świeżym dist.

## Review i ograniczenia operatora

Review `ses_e2b83b9cfffeIDt7ycx8ngfJjG`: 0 Critical, 2 Important, 0 Minor.
Dodano bramkę integralności rzeczywistych artefaktów i kontrolę oczekiwanych metadanych
bezpośrednio przed atomowym rename: RED 2 → GREEN 2, dodatkowo 5 guard regressions PASS.

Publikacja metadanych opiera się na wspólnej advisory lock `finanse-deploy.lock`.
Nie jest kernelowym CAS przeciw procesowi root ignorującemu blokadę. Wszyscy
uprawnieni operatorzy muszą jej przestrzegać; koszt naruszenia to ryzyko nadpisania
metadanych przez pozaproceduralny proces. Nie deklarujemy silniejszej gwarancji.

## Trzy próby — bez ukrywania niepowodzeń

1. Po kopii, restore, migracji klonu i kontroli zgodności starych aplikacji ujawnił
   się błędny indent w osadzonym probe. Produkcyjna migracja nie ruszyła; automatyczny
   rollback starych obrazów/schema325/HTTPS200 potwierdzony. Dodano kompilowanie
   osadzonych skryptów, RED → GREEN. Rzeczywista próba na klonie dodatkowo wykryła
   niezgodność SELECT FOR SHARE z PostgreSQL READ ONLY. Probe kontekstu wyłącznie
   na klonie używa teraz SELECT/SET-only guard, rollback i porównanie hashy, bez DML.
2. Backup został zaszyfrowany, lecz jego wybór zakładał jeden snapshot w całej
   historii własnego prefiksu. Po pierwszej próbie były dwa. Rollback starej
   aplikacji potwierdzony, produkcyjna migracja nadal nie ruszyła. Naprawiono
   identyfikację: różnica dokładnych ID sprzed/po backupie pod tą samą blokadą,
   dokładnie jeden nowy własny snapshot. RED → GREEN i próba na rzeczywistych
   snapshotach PASS; łącznie 9 testów operatora PASS. Nie używa się „latest”.
3. Świeży backup, restore, migracja klonu, zgodność rollbacku i produkcyjna migracja
   przeszły. Zachowano wszystkie wiersze 79 starych tabel, poza oczekiwaną wersją
   Alembic; dwie nowe tabele są puste, księga ma 0 naruszeń. Po podmianie trzech
   aplikacji smoke test błędnie wymagał `requestBody` dla GET `/api/finance/people`.
   Błąd jest w operatorze (`rollout.py`, asercja po wyborze GET), nie jest dowodem
   błędu endpointu. Automatycznie przywrócono stare obrazy na nowym addytywnym
   schemacie, zgodnie z wcześniej sprawdzoną kompatybilnością.

Po trzech niepowodzeniach nie rozpoczęto czwartej próby. Nie ma końcowego PASS
nowego wydania, pięciominutowej obserwacji ani publikacji `verified-live` dla niego.

## Zweryfikowany stan bezpieczny

Świeża kontrola po ostatnim rollbacku: poprzednie trzy image IDs i działające
kontenery, HTTPS/health 200, anonymous accounts 401, ledger 0, obie nowe tabele puste.
Postgres/Redis/Stirling: identyczne ID, image, mounty, StartedAt i RestartCount.
Nie wykonano testowych osób, linków, transakcji, importów lub korekt danych użytkownika.

Własny izolowany klon zatrzymano po potwierdzeniu idle i usunięto bez force/prune.
Własne plaintext backup/raw/input oraz tymczasowy migration env usunięte.
Wersjonowane obrazy, rollback i zaszyfrowane snapshoty wszystkich prób zachowane.
Końcowy zweryfikowany snapshot:
`76e5f56cae5bdbe7b7737c07c57b2d14812b573b009769a688c6365a51ed2223`.

Prywatne dowody: `/tmp/opencode/people-gifts-deploy-e0e746e/`, w tym
`attempt-1`, `attempt-2`, `paused-runtime-proof.json`, retention/migration/rollback
proofs i logi. Pakiet obrazów: `/opt/finanse/webapp/releases/people-gifts-e0e746e/`.
Nie traktować jego istnienia jako dowodu aktywnego wdrożenia.

## CI oddzielnie

Run `43410274033` dla main `6b6d4f9`: frontend job `131834643831` FAILED na
`npm audit --audit-level=low` (7 podatności: 6 moderate, 1 high), advisories
GHSA-mrwp-f3q8-3g9p / follow-redirects i GHSA-g3hv-75wg-m249 / minimatch.
Backend był w toku przy odczycie. Manifesty zależności identyczne z poprzednią
produkcją; nie wykonano niezatwierdzonego upgrade ani auditfix--force. CI nie jest zielone.

## Proponowana kontynuacja — do decyzji użytkownika

Nie ponawiać odziedziczonego operatora migracyjnego. Przygotować krótki operator
**app-only na istniejącym schema2c**, z testem kontraktu GET/responses/auth bez body
wykonanym offline przed maintenance. Ponownie sprawdzić bramki obrazów i rollback,
zrobić świeży backup/restore obecnego schematu, wdrożyć te same zatwierdzone trzy
obrazy, wykonać read-only smoke i minimum 300 sekund obserwacji. Żadnej kolejnej
migracji, downgrade, historycznej korekty lub produkcyjnych mutacji testowych.
