# Mały preflight wydania — projekt

## Cel i granica zgody

Użytkownik zaakceptował przygotowanie planu utrwalenia bezpiecznego preflightu:
sprawdzenie rewizji, schematu i obsługiwanych komend Compose, rozróżnienie migracji,
app-only oraz braku potrzeby deployu. Ta sesja tworzy dokumentację, nie implementację.
Implementacja, odczyty produkcyjne, push i wdrożenie wymagają kolejnych decyzji.

V1 jest **doradcą przed wdrożeniem**, nie automatycznym operatorem wydania.
Nie przenosimy całego prywatnego operatora z `/tmp` do repo.

## Dlaczego

Wydanie BO ujawniło dwa błędy operatora: porównanie tekstu CHECK po restore i
nieobsługiwaną flagę `compose create --no-deps`. Późniejsza poprawka samego testu
nie wymagała nowego wydania aplikacji. Mały wspólny preflight ma wcześnie
rozpoznać rodzaj pracy i odmówić zgadywania.

Istniejące `ops/prepare_release.py` nadal przygotowuje pakiet, a
`ops/verify_release.py` nadal poświadcza import gotowych obrazów jako nonroot.
Historyczny `ops/release_policy.py` ma konkretny kontrakt starego rollbacku;
nie uogólniamy ani nie osłabiamy go w tym zadaniu.

## Zachowanie

CLI `ops/release_preflight.py --check` wykonuje tylko odczyty i zwraca jeden raport
JSON na stdout. Nie zapisuje plików ani metadanych. Kod0 oznacza kompletną
klasyfikację, **nie zgodę na deploy**. Kod2 oznacza `blocked`, także po timeout/error.
Raport ma `report_version=1`, `authorized=false`, `production_ready=false`,
pełny `candidate`, obserwowane rewizje/ID usług, bieżącą i docelową rewizję schematu,
`action`, uporządkowane `pending_migrations`, stabilne `reason_codes`
i `required_gates`. Nie ma opcji apply, repair, migrate lub automatycznego fallbacku.
Przy błędnych/niezebranych facts pola rewizji i schematu mają wartość null,
nie echo niezweryfikowanego wejścia.

Akcje:

| Warunek | action |
|---|---|
| Brak istotnych zmian runtime dla każdej usługi, zmiany wyłącznie rozpoznane, schemat aktualny | `no_rollout` |
| Kod/build wejściowy wymaga wydania, schemat już na docelowej rewizji | `app_only` |
| Obecny schemat jest przodkiem jedynego docelowego head | `migration_then_app` |
| Niepewne dane, nieznany zakres lub niespójność | `blocked` |

Przypadek BO po rollbacku aplikacji na już zmigrowanym schemacie musi dać
`app_only`, z pustym `pending_migrations`. Nie proponować ponownego backfillu.
`no_rollout` nie oznacza poświadczenia sprawności/logowania aplikacji.
Klasyfikacja dotyczy **zmian źródeł i migracji**, nie zmian infrastruktury poza Git.
Każdy raport wymaga osobnej oceny zakresu zewnętrznej konfiguracji; nie
stwierdza, że zmieniony env/mount/ingress nie wymaga wydania. V1 nie certyfikuje
pełnej zgodności konfiguracji runtime. Ta granica musi być widoczna w CLI/docs.
Każdy raport dodatkowo zawiera `source_binding="operator_approved_inventory"`,
`content_provenance_verified=false`, `external_configuration_reviewed=false`.
V1 nie udaje kryptograficznej atestacji zawartości obrazu na podstawie OCI label.

## Weryfikacja źródeł

- Kandydat i rewizje backend/worker/frontend: istniejące pełne40znakowe SHA,
  nigdy ruchome `main`, `HEAD`, skróty lub `git_tip` zamiast rewizji usług.
- Bieżące dane usług pochodzą z rzeczywistego `docker inspect` dokładnych ID
  wskazanych przez pełny bieżący Compose. Porównać image IDs, OCI revisions,
  projekt/service labels i running state z `active-release.json`.
- CLI podaje jawnie repozytorium, projekt, active metadata, pełną uporządkowaną
  listę Compose, env-file i nazwę serwisu PostgreSQL. Nie ma ukrytych ścieżek
  `/opt/finanse` lub domyślnego celu produkcyjnego.
- Dla każdej usługi porównać jej runtime SHA z kandydatem; przodek jest wymagany.
  Inny projekt, retagowanie, brak obiektu Git, divergent/older candidate lub drift
  metadanych daje `blocked`, nie domyślną zgodę na rollback.
- Pliki kandydata i migracje czytać z przypiętych obiektów Git, nie dirty worktree.
  `git diff --name-only --no-renames -z` obejmuje także obie strony rename;
  odrzucić niezrozumiałe typy wpisów i zmiany symlinków, zamiast uznać je za testy.

### Zatwierdzony inventory — jawny punkt zaufania

Moja propozycja po builder check: wymagane `--approved-inventory ABS` oraz osobno
`--inventory-sha256 HEX64`, dostarczone przez operatora z wcześniejszego,
niezależnie zatwierdzonego stanu. Preflight **nie wydaje** inventory ze swoich
obserwacji i nie adoptuje automatycznie active metadata jako pozwolenia.
To operacyjny snapshot oczekiwań, nie źródło danych aplikacji lub permit DB.
Koszt: ręczne przygotowanie/odbiór inventory pozostaje poza V1.

Ścisły JSON `version=1`, bez dodatkowych lub powtórzonych kluczy:
- `project: str`, `active_release_sha256: HEX64`;
- `compose_files: list[{path: absolute str, sha256: HEX64}]`, pełna kolejność;
- `env_file: {path: absolute str, sha256: HEX64}` (hash pliku, nigdy jego wartości);
- `services: {backend|worker|frontend: {container_id: HEX64,
  image_id: "sha256:"+HEX64, revision: SHA40}}`, dokładnie3usługi;
- `postgres: {service: str, container_id: HEX64, database: str, role: str}`.

Wszystkie pliki wejścia: regularne, bez symlinków. Inventory0600 i prywatny
parent0700, właściciel UID operatora lub root; walidacja digestu przed użyciem.
Istniejący `active-release.json` pozostaje niezmieniony i bez wymogu nowego formatu:
odczytać tylko `release_status=="verified-live"`, `service_revisions`,
`application_images[S].id` oraz `compose_override`. Te pola są obowiązkowe,
bez fallbacku do `revision`/`git_tip`; resztę historycznych pól ignorować,
ale zweryfikować digest całego pliku. Porównać inventory→active→obserwowane ID/label.
To proponowany kontrakt adaptera V1, nie potwierdzenie formatu aktualnego pliku
produkcyjnego. Jego zgodność trzeba zatwierdzić osobnym odczytem przed realnym użyciem;
brak pola daje blocked, nigdy automatyczną migrację metadanych.

Lista Compose/env/project/PGservice z CLI musi odpowiadać inventory;
`active.compose_override` jest **ostatnim** plikiem tej listy, z takim samym hashem.
Zmiana pliku/digestu lub podmiana kontenera blokuje. Nie wykonywać chmod lub
naprawy plików. Nie chronimy przed złośliwym rootem zmieniającym także zatwierdzony
hash/argv; zaufany operator i jego niezależna akceptacja to jawny model zagrożeń.
Wynik nie zastępuje dowodu zawartości z prepare/verify i kontroli artifact hashes.

Moja decyzja wykonawcza: zachowawcza klasyfikacja ścieżek. Jedyny allowlist
`no_rollout`: `docs/**`, `backend/tests/**`, `frontend/e2e/**` oraz
`frontend/src/**/*.test.ts` i `*.test.tsx`. Runtime: pozostałe `backend/**`,
`frontend/**` i root `.dockerignore`. Nieznane ścieżki, w tym zmiany `ops/**`
lub workflowów, wymagają ręcznej oceny i dają `blocked`. Koszt: czasem zbędna
ręczna kwalifikacja, zamiast fałszywego pominięcia wydania.
Zmiana backend/requirements nie daje zgody na reuse runtime: raport dodaje
`rebuild_and_verify_runtime` do wymaganych bramek.
Dla backend/workera istotny runtime to `backend/**`, dla frontendu `frontend/**`;
root `.dockerignore` jest wspólne. Porównania są per-service, a allowlist test/docs
stosuje się przed kwalifikacją runtime. Inny serwis nie wymusza niepotrzebnego
wydania wyłącznie dlatego, że jego SHA obejmuje starszy frontend lub backend.
Nieznane ścieżki blokują niezależnie od serwisu.

## Schemat i możliwości Compose

- Obserwacja PostgreSQL to wyłącznie stałe `SELECT version_num FROM alembic_version`
  z wymuszonym `default_transaction_read_only=on` i `statement_timeout=10000`.
  Użyć dokładnego inspectowanego ID serwisu PG właściwego projektu; żadnego klonu,
  adopcji bazy testowej lub dowolnego SQL z CLI/LLM.
- Kandydat: statyczny AST `revision` i `down_revision` z plików Git
  `backend/migrations/versions/*.py`; żadnego importu/exec migracji lub Alembic env.
- V1 obsługuje tylko kompletny liniowy graf z jednym head. Zero/wiele headów DB,
  branch/merge, cykl, brak rodzica, duplikat revision lub nieznany schemat → `blocked`.
  Nie hardkodować konkretnego head BO lub innych historycznych numerów.
- Rewizje migracji: niepusty token `[A-Za-z0-9_-]{1,128}`, parent token albo None;
  dynamiczne wyrażenia i tuple rodziców są w V1 nieobsługiwane i blokują.
- Modyfikacja/usunięcie już istniejącego w runtime backend/workera pliku
  `migrations/versions/*.py` blokuje. Dopisanie nowego pliku jest inne:
  jeśli DB ma jego head po poprzedniej próbie, pending jest puste.
- `docker compose up --help` ma potwierdzić `--no-start`, `--no-deps`, `--no-build`
  przed akcją app-only/migration. Brak możliwości lub niejednoznaczny odczyt → blocked.
  Zalecany staging frontendu to `up --no-start --no-deps --no-build frontend`;
  preflight **nigdy go nie wykonuje**. Nie emitować automatycznego planu rollbacku.

## Granica subprocess i prywatności

Dozwolony jest wyłącznie zamknięty zbiór odczytów Git oraz Docker:
render `compose config --format json`, `compose ps --all --quiet SERVICE`,
`docker inspect ID`, `compose up --help` i powyższy dokładny odczyt PG.
Wynik config/inspect może zawierać sekrety: pozostaje w pamięci, nie trafia
do raportu, stderr, logów lub repo. Raport pokazuje tylko bezpieczny podzbiór.
JSON z duplikatami kluczy, niekompletne dane i niejednoznaczne wyniki są błędem.
Narzędzie nie dziedziczy ustawień Git zmieniających repo, nie używa globalnego
configu Git, external diff/textconv/hooków, shella dla dynamicznych argumentów
ani sieciowych operacji Git. Statyczny shell psql wewnątrz PG może jedynie użyć
istniejących `POSTGRES_USER`/`POSTGRES_DB` i literalnego SQL, bez wypisywania wartości.
Każde wywołanie ma timeout10s. Błędy operacyjne używają kontrolowanych reason codes,
bez raw stdout/stderr/wyjątków zawierających env. Walidacja argv przed subprocess.
Bez operacyjnych `assert`: zabezpieczenia muszą działać także pod Python `-O`.

Dokładny protokół PG (argv, nie dynamiczny shell hosta):
`docker exec --env "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000 -c timezone=UTC"
INSPECTED_PG_ID sh -c 'exec psql -X --no-password -U "$POSTGRES_USER" -d "$POSTGRES_DB" --set=ON_ERROR_STOP=1 --no-align --tuples-only --command="SELECT version_num FROM alembic_version"'`.
Przed exec potwierdzić w inspect ID/projekt/service/running oraz równość
`POSTGRES_USER`/`POSTGRES_DB` z inventory; env parsować jako mapę bez duplikatów.
Nie wypisywać tych wartości ani pozostałych env; odczyt nie przyjmuje SQL z CLI.

## Co pozostaje poza V1

Build, tworzenie/start/stop/remove kontenerów, maintenance, drain, backup/restore,
porównanie danych tabel i CHECK po restore, migracje, rollback, publikacja metadanych,
HTTP/ARQ smoke i obserwacja. Istniejąca procedura nadal wymaga ich osobnych dowodów
oraz zgody użytkownika. Preflight jest jedną bramką, nie ich zamiennikiem.

Moja decyzja: JSON to przejściowy raport operacyjny, nie nowe źródło prawdy aplikacji,
permit DB ani trwała zgoda. Zmiana źródeł/stanu po preflighcie unieważnia raport.
Raport jest atomową logiczną oceną z zebranych obserwacji, ale nie blokadą TOCTOU;
przed mutacją operator ponawia kontrole pod istniejącym deploylock.

## Odbiór

- Testy czystej klasyfikacji oraz CLI na syntetycznych repo i fake tools,
  bez kontaktu z rzeczywistym Docker/DB/produkcją.
- Rzeczywisty Git uruchamiany na własnym repo w tmp_path; kontrolowane fake Docker
  w prywatnym PATH umożliwia sprawdzenie całej granicy CLI i dziennika argv.
- Regresje: docs/test-only, mieszane rewizje usług, rename test→runtime,
  schemat już zmigrowany, nieznany schemat, brak capability, zmiana image ID,
  sekret w błędzie, optymalizowany Python i odmowa komend mutujących.
- `/lint`, `/typecheck`, `/test` według projektu; backend raportować jako kolekcję,
  a nowe i powiązane konkretne unit tests jako offline pytest. Brak pełnych fixture DB.
- Jeden świeży readonly review całego slice, poprawki Important/Critical przez TDD.
  Nie poświadczać realnego produkcyjnego preflightu na podstawie fake tools.
