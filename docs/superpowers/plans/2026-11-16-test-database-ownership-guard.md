# Test Database Ownership Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przypadkowo uruchomiony lokalny pytest nie łączy się z istniejącą bazą i nie usuwa jej schematu tylko dlatego, że nazywa się `finanse_test`.

**Architecture:** Oddzielić walidację adresu od uprawnienia danego uruchomienia. Wszystkie cztery wejścia do lifecycle DB wymagają prywatnego, krótkotrwałego pozwolenia wydanego przy przygotowaniu nowego środowiska; przed DDL sprawdzają rzeczywistą tożsamość PostgreSQL. W pierwszym zakresie pozwolenie wydaje wyłącznie istniejący job CI dla swojego nowego ephemeral serwisu; brak lokalnego provisionera oznacza odmowę lokalnych testów mutujących, nie fallback.

**Tech Stack:** Python 3.12+, pytest/pytest-asyncio, SQLAlchemy async, asyncpg, PostgreSQL 16, istniejący GitHub Actions. Bez nowych zależności i zmian aplikacji.

**Spec:** [Kontrakt i granice](#kontrakt-i-granice) w tym dokumencie. Zatwierdzony do lokalnej implementacji Native/offline; bez zgody na rzeczywistą DB, publikację i CI.

## Execution ledger — lokalna implementacja

- [x] Istniejący izolowany worktree, nowa gałąź `fix/test-database-ownership-guard`
  od main `c960d9c`, preflight wybranego Pythona PASS.
- [x] Task1:53 RED →53 GREEN; lint/mypy helpera i testu PASS, commit `e70ec0b`.
- [x] Task2:23 RED dla wejść lifecycle i workflow → GREEN; dodatkowe próby obcego
  URL i odmowy Alembic. Końcowa zatwierdzona selekcja offline176 PASS,
  Ruff app/tests/ci_tools PASS, mypy9 zmienionych plików PASS; commit `d3d09ba`.
- [x] Task3: dokumentacja, kontrola dokładnie15 plików i jeden readonly review.
  Review nie zgłosił Critical/Important; zgłoszoną uwagę o umask potraktowano jako
  błąd niezawodności jawnego kontraktu0600 i poprawiono w jednej rundzie.
- [x] Final: `test_permit_mode_is_0600_even_with_restrictive_umask`
  RED(mode000)→GREEN(mode0600), jawny fchmod po otwarciu pliku; commit `abffa64`.
  Końcowo177 testów offline PASS, pełny Ruff i mypy9 plików PASS.
- Walidacja131.56/180s; mypy `--follow-imports=silent --ignore-missing-imports`,
  bez nowych stubów/zależności. Jawna uwaga mypy o istniejącym nietypowanym body.
  Zastane ostrzeżenie passlib/crypt DeprecationWarning, nie usuwane poza zakresem.
- Ruling: osobny ledger pod `/tmp/opencode/test-db-ownership-impl-20261116/run-01/`
  zamiast dodatkowego śledzonego pliku — zachowanie limitu15; koszt: ledger nie
  podróżuje z PR, więc istotne decyzje i wyniki zapisujemy też w tym planie.
- Lokalny pytest procesu nadrzędnego odrzuca realne socket.connect przez audit hook.
  SQLAlchemy/asyncpg/subprocess w próbach lifecycle są kontrolowanymi atrapami.
  Bez rzeczywistego DDL/DB/Docker/push/CI/merge/deploy.
- Final Ruling: manipulacje tego samego UID/admina PG i TOCTOU między osobnymi
  połączeniami pozostają poza modelem — ochrona pomyłek zaufanego runnera;
  koszt błędnego zastosowania: guard nie izoluje złośliwego administratora.
- Final Ruling: pozytywna ścieżka na prawdziwym PostgreSQL nie jest zweryfikowana
  offline — wymaga zatwierdzonego standardowego CI przed merge;
  koszt pomylenia dowodów: można przeoczyć problem rzeczywistego drivera/SQL/runtime.
- Final Ruling: reviewer nie oceniał finalizowanych wpisów dokumentacji —
  autor sprawdza linki, zakres i zgodność z realnymi wynikami bez drugiego review;
  koszt: brak niezależnej oceny końcowej prozy.
- Brak odłożonych uwag tego review. Publikacja i standardowe CI wymagają osobnej zgody.

## Stan wyjściowy i inwentaryzacja

Baza: main `c960d9c52a3b29bd20d3fcfbd6453cc33246425c`; lokalny `81f6bdb` ma identyczne drzewo. PR #9 i main CI43858583429: 11/11 jobów PASS. To nie dowód bezpieczeństwa dowolnej lokalnej DB.

| Wejście | Zastany mechanizm | Co zabezpieczamy |
|---|---|---|
| `tests/conftest.py:test_database` | localhost/port/nazwa; public create_all/drop_all | odmowa przed engine; identity przed setup i teardown |
| `tests/test_finance/category_tree_database.py:test_database` | własny UUID schematu, własna fixture | osobny guard przed engine i DDL/cleanup |
| `tests/test_finance/test_entity_colors.py:color_db_session` | własny UUID schematu, brak koniecznego markera integration | guard niezależny od markerów i globalnej fixture |
| `tests/migration_fixtures.py:owned_migration_database` | jawna flaga, rola task, nowa DB, kontrola owner/OID cleanup | uprawnienie i identity bazy nadrzędnej oraz powiązanie nowej DB |
| `tests/test_identity/test_sessions.py:run_alembic` | osobny proces używa TEST_DATABASE_URL | nie uruchamiać subprocess dla zmienionego/nieuprawnionego celu |

Pozostałe SQL testów (np. usuwanie kolumn dokumentów/kolorów) działa przez sesje tych fixture. Nie zmieniamy treści migracji. Inwentaryzacja jest statyczna, nie certyfikacją dowolnego SQL w repo.

Stary `owned_schema_pilot.py` dotyczy reuse/fingerprint/TRUNCATE i zostawia fallback do poprzedniego lifecycle, kiedy pilot nie jest włączony. Nie realizuje domyślnej odmowy; nie kopiować go ani jego hooków.

## Kontrakt i granice

1. **Domyślna odmowa.** Brak lub niepoprawne `ADVISOR_TEST_DB_PERMIT` oznacza błąd przed `create_async_engine`, `asyncpg.connect`, DDL i subprocess. Nie SKIP, nie domyślne pozwolenie na podstawie `CI=true`, `GITHUB_ACTIONS=true`, localhost lub nazwy DB.
2. **Unit i collect bez DB.** Testy bez fixture DB i kolekcja nie wymagają pozwolenia i nie wywołują jego generatora, nie łączą się z usługami. Dotychczasowe `is_safe_test_database_url` pozostaje tylko filtrem adresów dla istniejących importerów helpera; nie nazywać go dowodem własności.
3. **Cel ścisły.** PostgreSQL+asyncpg, host `127.0.0.1`/`localhost`, port5432/55432, baza `finanse_test`, brak URL query, rola `bank_import_task_[0-9a-f]+`. Zgodność z pozwoleniem obejmuje driver/host/port/database/role. Hasła nie trafiają do pozwolenia, repr lub komunikatów.
4. **Pozwolenie jest artefaktem uruchomienia, nie źródłem danych aplikacji.** Absolutny prywatny plik JSON w katalogu danego joba: zwykły plik bez symlinków, owner=euid, brak uprawnień group/other, rozmiar maks.16KiB, jawny version/purpose i ścisły zestaw pól. `ADVISOR_TEST_DB_PERMIT` wskazuje ten plik; helper nigdy nie szuka go w `.env`, PATH lub produkcyjnej konfiguracji.
5. **Pola:** `version=1`, `purpose=advisor-test-db-lifecycle`, `issuer=github-ephemeral-postgres`, `target` (bez hasła), `db_oid`, `system_identifier` (string), `db_owner`, losowy `nonce`32hex, `run_id`, `run_attempt`, `job=backend_tests`, `group`, `commit`40hex. Run/attempt/group/commit wiążemy z bieżącym jobem, a nie tylko z dowolnym plikiem z przeszłości. Nie dodawać pola „reuse”.
6. **Issuer tylko po provisioningu.** CI zachowuje własny nowy serwis `postgres:16-alpine`, istniejący użytkownik `bank_import_task_c1`, nazwę i porty. Po dotychczasowych kontrolach roli/nazwy sprawdza pusty public (także sequences/views/routines, nie tylko pg_tables), pobiera OID/owner/system_identifier i zapisuje nonce jako komentarz bazy. Nie adoptuje istniejącej lokalnej/produkcyjnej bazy. Dokładny SQL i publikacja poniżej:
   - Nazwa celu jest stała: `"finanse_test"`, nigdy identyfikator z URL. Uzyskać literal przez parametryzowane `SELECT quote_literal($1::text)` z nonce, następnie zbudować wyłącznie `COMMENT ON DATABASE "finanse_test" IS <server-quoted-literal>`. Nie używać `$1` bezpośrednio jako argumentu polecenia utility COMMENT ani własnego escaping stringów. Zatwierdzić zapis komentarza przed publikacją pozwolenia.
   - Nonce jest znacznikiem tożsamości, nie sekretem uwierzytelniającym: komentarze PostgreSQL są publicznie odczytywalne. Prywatny plik i zaufany provisioning wiążą intencję uruchomienia; nie opierać bezpieczeństwa na tajności komentarza.
   - Workflow tworzy unikatowy katalog joba `0700` przez mktemp pod `$RUNNER_TEMP`. Issuer wymaga jego własności/prywatności i odmawia, jeśli docelowy plik już istnieje (także symlink), jeszcze przed DB I/O.
   - Publikacja dokładnie raz: tymczasowy plik `0600` otwarty przez `O_CREAT|O_EXCL|O_NOFOLLOW`, kompletny zapis/flush/fsync, następnie atomowy hard-link do docelowej nazwy bez zastępowania (`link`, nie replace/rename nad istniejącym plikiem). Odmowa także przy wyścigu o docelową nazwę. Usuwać wyłącznie własny plik tymczasowy. Ścieżkę finalną eksportować dopiero po sukcesie; nigdy użyć starszego pliku jako fallbacku.
7. **Fakty PostgreSQL.** SELECT z ustalonym zapytaniem sprawdza current_database/current_user/owner/OID/system_identifier oraz komentarz nonce. Brak uprawnień do odczytu oznacza odmowę, nie słabszy wariant. Przed setup i przed cleanup identity sprawdzamy na połączeniu, na którym ma nastąpić DDL; przy zmianie tożsamości nie wykonujemy cleanup.
8. **Utrzymanie sesji.** Przy odmowie/błędzie zawsze zwolnić własne połączenia/engine i odtworzyć app engine/session factory. Nie wykonywać drop po nieudanym setup. Brak pozwolenia nie może trafić do istniejącej obsługi „DB niedostępna → skip”; zachować osobny błąd `DatabaseSafetyError`.
9. **Migracje.** Utrzymać istniejące `BANK_IMPORT_MIGRATIONS_ALLOWED` i kontrolę roli, UUID nowej scratch DB i owner/OID. Pozwolenie dotyczy nadrzędnej finanse_test; child identity to nazwany nowy obiekt z zapamiętanym OID i tym samym cluster/system_identifier/role. Przed CREATE i DROP sprawdzić parent; przed migracją i usunięciem sprawdzić także child. `MigrationDatabase` przechowuje immutable child identity. Jego `migrate()` weryfikuje ją przez zachowane połączenie tylko do odczytu **bezpośrednio przed każdym** `asyncio.create_subprocess_exec`, nie tylko przy wejściu do fixture. Podmieniony cel/URL/OID/cluster oznacza odmowę przed spawn. Przy cleanup kontrola parent jest ponawiana bezpośrednio przed DROP DATABASE, a istniejąca kontrola child OID/owner/aktywnych połączeń pozostaje. Nie używać parent pozwolenia do dowolnej DB podmienionej w URL.
10. **Sesje/Alembic.** `run_alembic` staje się async; przed subprocess weryfikuje cel i server identity przez krótkie połączenie tylko do odczytu, zamknięte przed startem procesu. Aktualne 6 wywołań w tym pliku dostają await. Sam marker integration lub wcześniejszy sukces fixture nie jest pozwoleniem na inny URL.
11. **Prawa i wyścigi.** Pozwolenie chroni przed pomyłką operatora i przypadkowym wybraniem wspólnej DB. Nie jest sandboxem wobec złośliwego procesu tego samego UID lub administratora PostgreSQL, który może podmienić bazę między połączeniami; jawnie nie obiecujemy kryptograficznego uwierzytelnienia lokalnego operatora.
12. **Seryjność.** Zachować obecny zakaz xdist runnera. Guard odrzuca `PYTEST_XDIST_WORKER`; nie dodaje globalnego locka lub optymalizacji reuse. Każdy job CI ma własny klaster, więc nie współdzieli lifecycle z innym jobem.

### Świadomy efekt dla lokalnego developera

Zwykłe lokalne `pytest` wymagające DB przestaje działać z historycznym fallbackiem. `/test` nadal robi kolekcję offline, a jednostkowe testy offline działają bez pozwolenia. W tym etapie **nie dodajemy automatycznego sposobu odblokowania lokalnego DDL**.

Lokalny provisioner nowej syntetycznej DB/netns i jego rzeczywisty pilot to osobny zakres, jeżeli potrzebny. Nie wolno tworzyć pliku pozwolenia z parametrów istniejącej bazy, żeby „naprawić” błąd gate. Implementacja guardów może być zweryfikowana offline, a zgodność pozytywnej ścieżki potwierdzona później zatwierdzonym standardowym CI na nowych serwisach.

## File structure

| Plik | Odpowiedzialność |
|---|---|
| `backend/tests/database_safety.py` (nowy) | pozwolenie, pure validation, ustalone adaptery identity, issuer CI |
| `backend/tests/test_database_safety.py` (nowy) | pure i fake-I/O regresje wszystkich bramek |
| `backend/tests/conftest.py` | wpięcie lifecycle globalnej fixture |
| `backend/tests/test_test_database.py` | wyjaśnienie legacy fallback != zgoda; testy istniejących kontraktów |
| `backend/tests/migration_fixtures.py` | parent/child guard migracji, bez usuwania istniejących zabezpieczeń |
| `backend/tests/test_identity/test_sessions.py` | async guard przed osobnym Alembic i test helpera |
| `backend/tests/test_finance/category_tree_database.py` | gate override kategorii |
| `backend/tests/test_finance/test_entity_colors.py` | gate niezależnej fixture kolorów |
| `.github/workflows/ci.yml` | pozwolenie tylko dla już utworzonego serwisu danego joba |
| `backend/tests/test_ci_tools/workflow_assertions.py` | kontrakt permit/preflight/porządku kroków bez obniżania istniejących wymagań |
| `docs/development/testing.md` | odmowy, granice i bezpieczny workflow lokalny |

11 plików funkcjonalnych/operacyjnych + ten plan i 3 wpisy sesji = **maksymalnie15 plików** przyszłego PR. Jeśli inwentaryzacja implementacji wykaże dodatkowe wejścia lub potrzebę szerszej zmiany, zatrzymać się i przedstawić zmianę zakresu.

## Global Constraints

- Etap planowania był wyłącznie dokumentacyjny; późniejsza zgoda obejmuje implementację i testy offline, nie DB/Docker/push/CI.
- Implementacja dopiero po zatwierdzeniu: od aktualnego main w izolowanym worktree, zachować wszystkie stare zmiany.
- Bez zmian backend/app, danych użytkownika, modeli/migracji, frontendu, obrazów produkcyjnych i infra.
- Bez reuse/TRUNCATE, przyspieszania suite, xdist, zmiany liczby grup lub timeoutów obecnego CI.
- Lokalna walidacja: wyłącznie offline, budżet proponowany180s łącznie, jawny zgodny Python, bez instalacji/retry po timeout. Przed implementacją preflight metadanych.
- Operacje tworzące/usuwające schemat istnieją w kodzie fixture, ale w lokalnej walidacji używają wyłącznie doubles. Ta zgoda nie uprawnia do rzeczywistego DROP/TRUNCATE/migracji.
- Push/draft PR i standardowe CI wymagają osobnej zgody. Standardowe CI wtedy może użyć tylko nowego serwisu tego joba. Merge i deploy poza zakresem.

## Review Focus

1. Override fixture i test bez markera integration: żadna niezależna ścieżka nie może ominąć bramki; Task2 `test_all_lifecycle_entries_refuse_before_io`.
2. Brak/stary/obcy permit, query override DSN, rola lub cluster mismatch: odmowa bez DDL i bez sekretów; Task1 tabela przypadków.
3. Cleanup po wyjątku/setup częściowym/zmianie identity: nigdy drop obcego celu, zawsze zwolnienie zasobów i restore app; Task2 testy generatorów.
4. Child DB migracji i subprocess Alembic: parent pozwolenie nie zatwierdza nowego obcego URL; Task2 `test_migration_and_alembic_targets_are_bound`.
5. Kolekcja/unit nie kontaktuje się z DB, a CI nie dostaje implicit allowlist po CI=true; Task1 i Task3 próby z zakazanymi engine/connect.

---

### Task 1: Kontrakt pozwolenia i weryfikacja identity

**Files:** create helper i `test_database_safety.py`; bez wpinania do fixture w pierwszym kroku.

**Interfaces:**
- `DatabaseSafetyError(ValueError)` — komunikat bez DSN/hasła/nonce.
- `@dataclass(frozen=True) DatabasePermit` — pola kontraktu; bez credentiali, nonce repr=False.
- `load_permit(url: str, environ: Mapping[str,str]) -> DatabasePermit` — tylko lokalny odczyt private permit i pure validation, bez DB.
- `check_identity(permit: DatabasePermit, observed: Mapping[str,object]) -> None`.
- `verify_sqlalchemy(connection: AsyncConnection, permit: DatabasePermit) -> None`;
  `verify_asyncpg(connection: asyncpg.Connection, permit: DatabasePermit) -> None`.
- `verify_target(url: str, permit: DatabasePermit) -> None` — async, bounded readonly probe dla Alembic, zawsze zamyka własne połączenie.
- `issue_ci_permit(url: str, path: Path, environ: Mapping[str,str]) -> None` — async, tylko przygotowany ephemeral job; fixed SQL, kończy odczyty/komentarz przed publikacją pliku.

- [ ] **1. RED testy pure.** Brak env/relative path/symlink/FIFO/public permissions/zły owner/za duży lub niepoprawny JSON/obce pola odrzucane. DSN prod/remote/socket/query, obca rola, inny run/attempt/group/commit/nonce odrzucane; prawidłowe literalne fake dane przechodzą. Samo CI=true/GITHUB_ACTIONS=true bez pliku nie wystarcza.
- [ ] **2. Uruchomić RED offline.** `"$P" -I -B -m pytest -q -p no:cacheprovider tests/test_database_safety.py`; oczekiwane braki helpera, bez integracyjnych markerów lub usług.
- [ ] **3. Implementacja pure i adapterów.** Fixed identity query bez arbitralnego SQL, porównanie faktycznych pól, prywatne odczyty przez deskryptor; brak fallbacku na słabsze identity. Probe connect5s, command_timeout5s. Nie interpolować niezaufanych identyfikatorów do SQL.
- [ ] **4. Testy fake-I/O.** Zmieniaj każde pole identity osobno — DatabaseSafetyError i zero DDL; prawidłowe przechodzi. Fake issuer odmawia niepustego public/złej roli/braku GitHub context; błędy SQL/comment/write nie publikują pozwolenia. Hasło i nonce nie pojawiają się w błędzie/repr. Monkeypatch connect/engine na forbidden przy próbach bez pozwolenia. Dodatkowe nazwane kontrakty:
  - `test_comment_uses_fixed_database_and_server_quoted_nonce`: fake adapter otrzymuje nonce jako parametr SELECT quote_literal; COMMENT ma stały identyfikator i literal zwrócony przez serwer, nigdy utility placeholder `$1`. Po błędzie SQL brak pozwolenia.
  - `test_issuer_refuses_existing_destination_before_io`: istniejący plik lub symlink pozostaje byte-for-byte bez zmian, licznik DB I/O=0.
  - `test_permit_publish_is_complete_and_no_clobber`: błąd przed link nie ujawnia finalnego permitu; pojawienie się pliku docelowego przed link powoduje odmowę, nie zastąpienie; sukces daje kompletny plik0600 w prywatnym katalogu.
- [ ] **5. GREEN/lint/types i lokalny commit** tylko helper/test. Brak pozytywnej próby na prawdziwym PostgreSQL.

### Task 2: Wszystkie lifecycle entries i istniejący ephemeral CI

**Files:** 6 istniejących plików fixture/testów z tabeli; workflow i workflow_assertions; rozszerzenie `test_database_safety.py`.

**Interfaces:** używa niezmienionych API Task1. Scratch migracji ma dodatkowy immutable record `name, oid, role, system_identifier` powstały po CREATE, nie z env. Zachować `MigrationDatabase` jako istniejący interfejs dla testów konsumentów.

- [ ] **1. RED odmów wszystkich wejść.** Parametryzowane uruchomienie prawdziwych `__wrapped__` generatorów global/category/colors/migration oraz Alembic helpera z silnikami/connect/subprocess zabronionymi: bez permit każde kończy się błędem i liczniki I/O pozostają0. Kolory testować bez markera integration. Dla nie-DB przypadku globalna fixture yield None bez odczytu permit.
- [ ] **2. RED lifecycle fake.** Poprawny permit + fake DB: identity przed create/drop; po przerwaniu test body cleanup tylko dla własnego setup. Identity mismatch przy cleanup → zero drop; setup failure → zero drop; dispose/restore app także po wyjątku. Dotyczy wszystkich trzech engine fixture, nie tylko globalnej.
- [ ] **3. Wpięcie guardów i async Alembic.** Zachować istniejący krótki filtr unsafe URL przed nową bramką w kolorach (kompatybilność testu unsafe target). W globalnej fixture dodać bramkę zanim zaimportuje app/database i utworzy engine. Przejść po wszystkich otwarciach/transakcjach setup/teardown, używając rzeczywistego connection do verify.
- [ ] **4. Migracje i child regression.** Parent identity przed CREATE/cleanup, child cluster/name/OID/role przed migracją i DROP. `test_migrate_rechecks_child_before_each_spawn`: pierwszy migrate z prawidłową identity wywołuje fake subprocess raz; zmiana identity przed drugim migrate powoduje odmowę, licznik spawn nadal1. `test_parent_rechecked_before_scratch_drop`: zmiana parent przy cleanup daje zero DROP i zasoby są zamknięte. Uaktualnić helper i test w sessions do await; nie zmieniać istoty testu migracji sesji.
- [ ] **5. CI issuer.** Zachować istniejący serwis i preflight; utworzyć nowy unikatowy katalog0700 pod `$RUNNER_TEMP`, dopiero po sukcesie issuera przekazać nową absolutną ścieżkę do runnera przez `$GITHUB_ENV`. Brak „reuse istniejącej ścieżki”. Przekazać jawnie group i zweryfikowany checkout SHA do issuer. Issuer odczytuje jedynie oczekiwany TEST_DATABASE_URL; nie kontaktuje się z DATABASE_URL/produkcją. Nie generować permit w jobie kolekcji.
- [ ] **6. GREEN offline i lokalny commit.** Testy bezpieczeństwa + obecne `test_test_database.py`, `test_entity_color_test_safety.py`, unit helpera Alembic i `test_ci_tools`. Ruff/mypy zmienionych plików. Nie uruchamiać reszty `test_sessions.py`, fixture integracyjnych lub workflow lokalnie.

### Task 3: Odbiór ograniczeń, dokumentacja i przekazanie

**Files:** `docs/development/testing.md`, plan i CHANGELOG/TASKS/JOURNAL.

- [ ] **1. Potwierdzić smoke bez DB.** Testy odmów z fake I/O, zachowanie unit/collect; nie wywoływać rzeczywistego collect całego repo poza zatwierdzonym budżetem ani integracyjnego pytest. Uczciwie raportować, że offline positive path używa doubles.
- [ ] **2. Kontrola zakresu.** Maksymalnie15 wskazanych plików, stare worktree/app/migrations/infra bez zmian; brak reuse/fallback/init istniejącej bazy lub zniesienia bramki dla CI=true.
- [ ] **3. Jeden readonly review bezpieczeństwa całości.** Sprawdzić pięć Review Focus, granicę zaufania issuera, adaptery child DB, zasoby i redakcję sekretów. Important/Critical poprawiać RED→GREEN, nie przez pomijanie testów.
- [ ] **4. Dokumentacja i commit lokalny.** Opisać nową odmowę lokalnej DB i ścieżkę unit/CI; lokalny provisioner nie jest jeszcze dostarczony. Nie deklarować „pełne testy lokalne PASS” ani „lokalny pilot zweryfikowany”.
- [ ] **5. Handoff.** Po osobnej zgodzie jeden push/draft PR i standardowe CI. Jeśli którekolwiek job/phase zostanie pominięte lub brak identity, odmowa odbioru bez automatycznego retry. Rzeczywisty nowy lokalny klaster wymaga oddzielnego planu i zgody, bez dostępu do istniejących baz. Merge/deploy osobno.

## Self-review i wykonanie

- Pokrycie: Task1 walidacja i adaptery; Task2 wszystkie odnalezione wejścia + CI; Task3 granice dowodu i publikacja.
- Współdzielone API i plik testowy wymagają kolejności, nie równoległych implementerów. Propozycja: Native i jeden świeży końcowy reviewer.
- Żadne pole pozwolenia samo nie dowodzi autoryzacji człowieka: issuer może działać tylko dla przygotowanego nowego joba. Lokalna walidacja nie wyda realnego pozwolenia i nie wykona DDL.
- Etap planowania nie publikował zmian. Po zatwierdzonej implementacji powstały
  tylko lokalne commity; następny krok to osobna zgoda na publikację i standardowe
  CI nowych ephemeral baz, nie użycie istniejących baz lub lokalnego pilota.
- Readonly review planu: trzy Important doprecyzowane w kontrakcie i testach —
  wykonalny bezpieczny SQL COMMENT, identity child przed każdym migrate/spawn oraz
  jednorazowa atomowa publikacja pozwolenia bez nadpisywania starego pliku.
  To review planu, nie wykonania; żadnej ścieżki nie zweryfikowano na realnej DB.
- Źródło składni/ograniczeń komentarzy: [PostgreSQL 16 COMMENT](https://www.postgresql.org/docs/16/sql-comment.html).
