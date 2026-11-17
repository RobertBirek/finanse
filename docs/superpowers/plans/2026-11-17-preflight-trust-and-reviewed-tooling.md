# Preflight Trust And Reviewed Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Naprawić trzy potwierdzone braki preflightu i umożliwić klasyfikację wyłącznie dokładnie przejrzanych zmian jego narzędzi, bez osłabienia domyślnego blocked.

**Architecture:** Czysta polityka nadal klasyfikuje źródła i migracje; adapter konsumuje wyłącznie zatwierdzone narzędzia, snapshot konfiguracji i lokalny endpoint PG. Osobny launcher stdlib weryfikuje przypięty pakiet przed importem kodu checkera; osobny dowód review obejmuje dokładne zmiany tooling. To jeden zależny slice, nie nowy operator wdrożenia aplikacji.

**Tech Stack:** Python3.12+, stdlib, PyYAML6.0.3 w osobnym runtime narzędziowym, pytest; lokalne Git/Docker/Compose tylko po zatwierdzeniu ich plików.

**Spec:** `docs/superpowers/specs/2026-11-17-preflight-trust-and-reviewed-tooling-design.md` — użytkownik zatwierdził pełny projekt odpowiedzią „tak”.

## Global Constraints

- „Brak dowodu, niezgodność, nieobsługiwany format lub zakres nadal daje blocked/exit2.”
- „Nie tworzyć inventory z odczytów. Nie adoptować stanu, zmieniać historycznych rewizji/metadanych ani filtrować diffu, by uzyskać zielony wynik.”
- „Wyjście pozostaje authorized=false, production_ready=false oraz content_provenance_verified=false i external_configuration_reviewed=false.”
- „Brak apply/migrate/repair, buildów, restartów, operacji finansowych i wywołań AI.”
- „Nie dodawać kodu do siedmiu domen aplikacji ani zależności backendu/frontendu wyłącznie na potrzeby checkera.”
- „Środowisko jest jawnie zbudowane; nie dziedziczy konfiguracji Git, Dockera, pluginów Compose ani lokalizacji z HOME użytkownika.”
- „Nie wolno uprościć tego do ponownego sha256sum po renderze: taki zabieg sam nie dowodzi, jakie bajty Compose konsumował.”
- „Jeżeli obecna konfiguracja tego nie umożliwia, wynik to blocked z informacją, że wymagany jest osobny projekt dostępu; nie dodawać kanału z hasłem.”
- „Nie dodawać ogólnego allowlist dla ops/** lub .opencode/** i nie usuwać ich z porównania Git.”
- Każdy subprocess: timeout10s, brak stdin, shell=False, kontrolowane reason codes; PG statement_timeout10000, connect timeout5s.
- Nie odczytywać produkcji podczas implementacji/testów. Nie używać prawdziwego Docker/DB/AI ani lokalnych fixture baz; wyłącznie syntetyczne repo/pliki i atrapy.
- Zaufany administrator/root pozostaje granicą modelu zagrożeń, nie przeciwnikiem. Nie deklarować atomowej obserwacji całego środowiska ani kryptograficznego provenance obrazów.

## Review Focus

1. Compose YAML z !override/!reset, merge/aliasami i service.env_file: brak zmiany semantyki ścieżek i brak odczytu oryginalnego env — Task3, `test_compose_tags_aliases_and_relative_paths_keep_meaning`.
2. Aktualizacja kodu kandydata niezależna od instalowanego checkera: launcher nie importuje kandydata lub jego .pth — Task5, `test_candidate_import_and_pth_canaries_never_execute`.
3. Zmiana tylko jednego baseline usługi lub tylko docs po review: stary dowód nie autoryzuje nowej pary źródeł — Task4, `test_scope_proof_binds_every_service_and_exact_candidate`.
4. Różna tożsamość postgres OS user i roli DB: nie tworzyć map ani nie przechodzić na root/hasło — Task2, `test_pg_os_identity_and_database_role_are_distinct`.
5. Snapshot zawierający sekret przy timeout/cleanup failure: brak sekretu w raporcie i brak fałszywego sukcesu — Task3/6, `test_snapshot_cleanup_failure_redacts_and_blocks`.

---

## Stan wejściowy i granica tego planu

- Baza dokumentacji: lokalny `fbc83fc`; badany wcześniej kandydat `5c37246`, produkcja przy ostatnim odczycie `45bcf88`. Te numery to kontekst, nie stałe w implementacji.
- Obecne91testów preflightu PASS; trzy negatywne próby z review RED, nie naprawione.
- Przykłady dowodów: `/tmp/opencode/document-drafts-preflight-bct7kdzz/`. Przenieść sens regresji do testów repo; nie uzależniać ich od istnienia scratch.
- Nie zmieniać istniejącego inventory ani przyjmować jego SHA jako zgody na przyszły pakiet. Nowy kandydat i pakiet po implementacji będą wymagały oddzielnej akceptacji.
- Ten plan kończy się lokalnym odbiorem kodu i dokumentacji. Push/shared branch, pełne CI dokładnego kandydata, przygotowanie rzeczywistych artefaktów tooling, odczyty produkcyjne oraz rollout wymagają właściwych osobnych zgód.

## Mapa plików i decyzje wykonawcze

| Plik | Odpowiedzialność |
|---|---|
| `ops/release_preflight_policy.py` | Istniejące typy błędów, graf i czysta klasyfikacja; dodać jawne verified tooling facts. |
| `ops/release_preflight_trust.py` | Ścisłe schematy manifestów, FilePin, toolchain/runtime/PG, walidacja hashów i plików. |
| `ops/release_preflight_exec.py` | Zamknięty runner rzeczywistych komend i izolowany lokalny SELECT PG. |
| `ops/release_preflight_snapshot.py` | Walidacja YAML node graph, snapshot wejść, poprawka wyłącznie env_file, cleanup i wykrycie driftu. |
| `ops/release_preflight_review.py` | Weryfikacja dowodu review względem kompletnych zmian Git, bez wykonywania ich. |
| `ops/release_preflight.py` | Orkiestracja i bezpieczny raport V2; bez własnego zaufania do PATH lub kodu kandydata. |
| `ops/preflight_launcher.py` | Minimalny bootstrap stdlib: weryfikacja pakietu/runtime przed importami checkera. |
| `ops/prepare_preflight_bundle.py` | Przygotowanie lokalnego pakietu ze wskazanych źródeł; żadnych zgód/instalacji/produkcji. |
| `ops/preflight-requirements.txt` | Osobny pin `PyYAML==6.0.3`; nie zmieniać backend/requirements. |
| `backend/tests/test_ops/test_release_preflight_{trust,exec,snapshot,review,launcher}.py` | Nowe testy według granic modułów. |
| `backend/tests/test_ops/test_release_preflight.py` i `_policy.py` | Regresje CLI/policy i adaptacja istniejących91przypadków. |
| `.opencode/command/deploy.md`, `docs/operations/backup-restore.md` | Jawna procedura V2, bootstrap i ograniczenia; nie przemilczać wyniku blocked V1. |

Parser: użyć PyYAML6.0.3, wyłącznie czystych modułów Python, vendored do pakietu z jawnie podanego, istniejącego źródła dystrybucji; zachować licencję. Nie importować globalnego site-packages w checkerze. W obecnym zatwierdzonym środowisku deweloperskim wersja6.0.3 jest dostępna; backend uvicorn[standard] również wymaga PyYAML, ale to nie jest pin runtime narzędziowego. Nie instalować nic automatycznie; brak odpowiedniego źródła zatrzymuje pakowanie, a nie zmienia backend/CI. Testy parsera mogą korzystać z dostępnego PyYAML6.x; pakowanie rzeczywistego runtime wymaga dokładnego6.0.3.

Pakiet nie obejmuje pełnego operatora wydania, prepare_release/verify_release lub innych ops. Zamknięty `CHECKER_SOURCE_PATHS` to dokładnie dziewięć plików ops z tabeli powyżej, bez globów; dodatkowo kwalifikuje się wyłącznie `.opencode/command/deploy.md`. Nowe testy/docs są obsługiwane dotychczasową polityką. Zmiany workflowów/CI nadal blokują.

## Wspólny sposób weryfikacji

Tasks1–4 dostarczają niezależnie testowalne moduły i rozszerzenia czystej policy.
Nie przełączają jeszcze native CLI na niekompletny bootstrap. Dotychczasowe
testy CLI pozostają regresją V1; Task5 jednorazowo podłącza wszystkie nowe
interfejsy i usuwa stary runner. Nie raportować wcześniejszego bibliotecznego
GREEN jako naprawy CLI lub dopuszczenia go do środowiska rzeczywistego.

Użyć zatwierdzonego `ADVISOR_DEV_PYTHON`3.12+; obecnie:
`/tmp/opencode/backend-test-env-20261114/run-302e8d4cb8/venv/bin/python`.
Bez wyszukiwania zamiennika, instalacji lub zmiany środowiska bez zgody.

`offline_pytest PATH...` w krokach oznacza poniższą funkcję zdefiniowaną raz w shellu implementera; `$ROOT` jest bieżącym worktree. Nie przenosić jej do produkcyjnego checkera.

```bash
offline_pytest() {
  local h
  h="$(mktemp -d /tmp/opencode/preflight-tests.XXXXXXXX)"
  sudo -n -- unshare --net \
    setpriv --reuid "$(id -u)" --regid "$(id -g)" --init-groups --no-new-privs \
    env -i PATH=/usr/bin:/bin HOME="$h" \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    ENVIRONMENT=test PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    SECRET_KEY=synthetic-offline OPENAI_API_KEY= LLM_API_KEY= \
    TEST_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:9/finanse_test \
    DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:9/finanse_test \
    REDIS_URL=redis://127.0.0.1:9/0 \
    "$ADVISOR_DEV_PYTHON" -I -B -c \
    'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="pytest"; runpy.run_module("pytest",run_name="__main__")' \
    "$ROOT/backend" -q --basetemp="$h/pytest" "$@"
}
```

Przed każdym commitem uruchomić `/lint`, `/typecheck`, `/test` przez pełne istniejące bloki komend, bez modyfikacji ich znaczenia. Backend tego ostatniego to tylko kolekcja, osobne offline_pytest wykonuje testy ops. Ponadto z `$ROOT/backend`:

```bash
"$ADVISOR_DEV_PYTHON" -I -B -m ruff check ../ops/release_preflight*.py ../ops/preflight_launcher.py ../ops/prepare_preflight_bundle.py
MYPYPATH="$ROOT/ops" "$ADVISOR_DEV_PYTHON" -I -B -m mypy --explicit-package-bases ../ops/release_preflight*.py ../ops/preflight_launcher.py ../ops/prepare_preflight_bundle.py
```

W zadaniach wcześniejszych uwzględnić tylko już istniejące pliki, nigdy pustego globu. Oczekiwane PASS wszystkich kontroli i właściwego zestawu offline; brak któregokolwiek wyniku oznacza nieukończony odbiór. Nie wykonywać wszystkich backendowych test bodies ani fixture DB.

### Task 1: Ścisłe dowody zaufania i kontrakty danych

**Files:** Create `ops/release_preflight_trust.py`, `ops/preflight-requirements.txt`, `backend/tests/test_ops/test_release_preflight_trust.py`; reuse błędów z policy, bez zmiany jej decyzji.

**Interfaces:**
- Consumes: `PreflightInputError(code: str)` z istniejącej policy.
- Produces frozen dataclasses: `FilePin(path: Path, sha256: str, mode: int, uid: int)`, `PgEndpoint(container_id: str, image_id: str, uid: int, gid: int, env_executable: str, psql_executable: str, socket_directory: str, port: int, auth: Literal["peer", "trust"])`, `Toolchain(git: FilePin, docker: FilePin, compose: FilePin, postgres: PgEndpoint, limits: InputLimits)`.
- `InputLimits(max_file_bytes: int, max_yaml_nodes: int, max_yaml_depth: int, max_output_bytes: int)` to pozytywne wartości manifestu, nie nowe zaszyte limity produkcyjne.
- Produces `load_toolchain(path: Path, expected_sha256: str) -> Toolchain`, `verify_pinned_file(pin: FilePin, *, owner_uid: int = 0) -> bytes`, `read_private_json(path: Path, expected_sha256: str) -> dict[str, object]`.

Ścisły toolchain JSON version1: `version`, `executables` (git/docker/compose, każdy path/sha256/mode/uid), `postgres` (dokładnie pola PgEndpoint), `limits` (dokładnie pola InputLimits). uid plików narzędziowych musi być0 w produkcyjnym loaderze. Port1..65535, UID/GID nieujemne, mode bez setuid/setgid i zgodny z rzeczywistym plikiem; wszystkie liczbowe pola wymagają type(value) is int, nie bool. Nazwy PG nadal z inventory, nie w tym manifeście.

- [ ] **Step 1 — Write RED:** dodać `test_private_json_rejects_duplicates_extra_fields_and_bad_digest`, `test_binary_pin_rejects_group_write_symlink_and_untrusted_parent`, `test_toolchain_requires_explicit_pg_identity_and_input_limits`.

  Asercje: duplikat klucza, NaN, zły digest/owner/mode/symlink/niestabilna tożsamość pliku → `PreflightInputError`; brak limitu lub pola endpointu nie dostaje domyślnej wartości. Poprawny prywatny dokument daje niezmienny Toolchain.
- [ ] **Step 2 — Verify RED:** `offline_pytest "$ROOT/backend/tests/test_ops/test_release_preflight_trust.py"` → FAIL brak modułu/interfejsu, zapisać dowód.
- [ ] **Step 3 — Implement:** wskazane funkcje/typy; czytać bez follow symlinków, kontrolować stat/fstat i ponowne stat, digest i rozmiary, katalogi prywatne0700/pliki0600 dla dowodów. Systemowy symlink binarium rozwiązać do docelowej kanonicznej ścieżki przed akceptacją manifestu, nie podczas każdego fallbacku. Cała trasa do binarium musi być zaufana i bez zapisu dla grupy/innych.

  Pomocniki mają jawny owner_uid do unit testów; zewnętrzny loader nie ma opcji CLI/env obniżającej wymóg root dla binariów. Produkcyjny root policy i odmowa plików użytkownika muszą mieć osobny test. Pin PyYAML zapisać w osobnym pliku, bez instalacji.
- [ ] **Step 4 — Verify GREEN:** polecenie Step2 → PASS, plus istniejące testy policy → PASS; kanoniczne kontrole przed commitem.
- [ ] **Step 5 — Commit:** `feat: dodaj ścisłe dowody zaufania narzędzi preflight`.

### Task 2: Runner przypiętych binariów i jednoznaczny lokalny PG

**Files:** Create `ops/release_preflight_exec.py`, `backend/tests/test_ops/test_release_preflight_exec.py`. Przełączenie `ops/release_preflight.py:121-235,396-486` i fixture CLI należy do Task5.

**Interfaces:**
- Consumes: Toolchain/FilePin/PgEndpoint i walidatory Task1.
- Produces `ReadOnlyRunner(repository: Path, toolchain: Toolchain)` z `bind(compose_files: tuple[Path, ...], env_file: Path, project_directory: Path, project: str, inventory: dict[str, object]) -> None`, `run(argv: list[str]) -> str`, `schema_heads() -> tuple[str, ...]`.
- Logical argv runnera zaczyna się od dokładnie `git`, `docker` lub `compose`; po zamkniętej walidacji runner mapuje pierwszy token na konkretny FilePin, nie szuka PATH. `compose` to bezpośrednie przypięte binarium ComposeV2, nie odkrywany plugin.

- [ ] **Step 1 — Write RED:** `test_inherited_path_cannot_substitute_git_or_docker`, `test_compose_plugin_search_is_not_used`, `test_pg_endpoint_is_explicit_and_inherited_libpq_is_erased`, `test_pg_os_identity_and_database_role_are_distinct`, `test_mutating_and_arbitrary_sql_argv_are_rejected`.

  Asercje: fałszywe binaria we wcześniejszym PATH nie uruchamiają canary; wywołana jest ścieżka z pinu; brak shella lub dziedziczonego PGHOST/PGSERVICE. OS UID:GID np.999:999 nie jest rolą DB `synthetic_finance`; brak możliwości bezhasłowego połączenia → blocked, bez drugiego exec/zmiany usera/hasła.
- [ ] **Step 2 — Verify RED:** `offline_pytest "$ROOT/backend/tests/test_ops/test_release_preflight_exec.py"` → FAIL potwierdzające brak izolacji, a nie niepoprawny fake argv.
- [ ] **Step 3 — Implement:** odtworzyć zamkniętą whitelist w nowym runnerze, zachowując wszystkie dotychczasowe odczyty Git/inspect/config/ps/help. Nie podłączać nieukończonego CLI; usunięcie starego runnera jest częścią Task5. Docker używa jawnego lokalnego socketu, Compose stałego DOCKER_HOST i pustego prywatnego DOCKER_CONFIG/HOME; żadnych settings klienta użytkownika.

  SELECT budować jako argv, nie dynamiczny shell: przypięty docker `exec --user UID:GID ID`, zatwierdzony absolutny env, `-i`, `HOME=/nonexistent`, `PGPASSFILE=/dev/null`, `PGCONNECT_TIMEOUT=5`, `PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000 -c timezone=UTC`, zatwierdzony absolutny psql z `-X --no-password --host SOCKET --port PORT --username ROLE --dbname DB --set=ON_ERROR_STOP=1 --no-align --tuples-only --command` i jednym literalnym SQL.

  Porównać PG image ID z manifestem; rola/baza i kontener/projekt/service/running nadal z inventory. Konserwatywnie odrzucić każdy bind lub volume obejmujący katalog socketu; prywatny tmpfs kontenera jest dopuszczalny. Nie skanować obcych kontenerów ani nie wprowadzać nowych inspect do whitelisty. Nie czytać pg_hba ani wykonywać dodatkowych SQL.

  Użyć Popen z binarnymi pipe i selectors, wspólnym max_output_bytes dla stdout+stderr, monotonicznym deadline10s i start_new_session=True. Przy timeout/limicie zabić i zebrać własną grupę procesu; nie dekodować ani nie wypisywać raw błędu. Osobny SELECT ma także timeout serwera. Pin binarium sprawdzać przed wywołaniem i po nim; zmiana → blocked, brak reuse starego pozytywnego stat.

  Testy używają przypiętych fake tools i wewnętrznego DI walidatora plików. Nie dodawać CLI/env flagi wyłączającej produkcyjne kontrole właściciela, digestów lub PATH.
- [ ] **Step 4 — Verify GREEN:** Step2 oraz dotychczasowe testy odczytów/sekretów/timeout/-O → PASS. Dodatkowo test zwraca błąd przy podmienionym binarium po bind. Kanoniczne kontrole przed commitem.
- [ ] **Step 5 — Commit:** `fix: przypnij narzędzia i lokalny endpoint PG preflightu`.

### Task 3: Snapshot rzeczywiście konsumowanych Compose/env

**Files:** Create `ops/release_preflight_snapshot.py`, `backend/tests/test_ops/test_release_preflight_snapshot.py`. Włączenie do adaptera `_inventory`, `_observe` i orkiestracji należy do Task5.

**Interfaces:**
- Consumes: FilePin/InputLimits, ReadOnlyRunner.bind z Task2.
- Produces `capture_inputs(inventory: dict[str, object], *, inventory_pin: FilePin, active_pin: FilePin, scratch: Path, limits: InputLimits) -> InputSnapshot`. Digest inventory_pin pochodzi z zewnętrznej zgody, active_pin z zaakceptowanego inventory; nie tworzyć oczekiwań z właśnie odczytanych hashy.
- `InputSnapshot` jest context managerem z `compose_files: tuple[Path, ...]`, `env_file: Path`, `project_directory: Path`, `verify_originals() -> None`; jego exit usuwa wyłącznie własne pliki lub zgłasza `snapshot_cleanup_failed`.
- Produces `validate_compose_nodes(raw: bytes, *, source: Path, project_directory: Path, approved_env: Path, limits: InputLimits) -> tuple[EnvReference, ...]`, gdzie `EnvReference(start: int, end: int)` to zakresy znaków ScalarToken do zastąpienia, nie całe zakresy Node obejmujące anchor/tag.

- [ ] **Step 1 — Write RED:** `test_mutation_after_hash_never_changes_consumed_bytes`, `test_compose_tags_aliases_and_relative_paths_keep_meaning`, `test_external_include_extends_label_file_and_secret_file_block_before_render`, `test_cycle_duplicate_key_and_dynamic_env_file_block`, `test_snapshot_cleanup_failure_redacts_and_blocks`.

  Asercje: zmiana oryginału po capture nie zmienia bajtów otwieranych przez fake Compose; mimo snapshotu końcowy raport jest blocked jeśli oryginał pozostaje zmieniony. Canary sekretu nie trafia do żadnego wyniku lub wyjątku. Nieobsługiwane zależności blokują przed pierwszym uruchomieniem Compose.
- [ ] **Step 2 — Verify RED:** `offline_pytest "$ROOT/backend/tests/test_ops/test_release_preflight_snapshot.py"` → FAIL brak snapshotu/binding, zachować dowód z mutacją po hashu.
- [ ] **Step 3 — Implement:** odczytać każdy oryginał raz z deskryptora bez symlinków, zweryfikować zatwierdzony digest i zachować bajty. Używać `yaml.compose` z SafeLoader do node graph, nie unsafe constructors ani ponownego dumpowania całego YAML. Rozpoznawać wyłącznie standardowe bezpieczne tagi i !override/!reset; limitować nodes/depth/bytes, odrzucać cykle i duplikaty jawnych kluczy. Dla merge/aliasów wyznaczyć skuteczne mappingi z testem precedencji, bez gubienia współdzielonych zakresów źródła.

  Zablokować top-level include, service extends/label_file/credential_spec/provider/develop, build.ssh oraz configs/secrets z file. Dopuszczalne top-level keys to version/name/services/networks/volumes/configs/secrets i x-*; inne → unsupported_compose_input. Przypięcie wersji/digestu Compose nie upoważnia do nowych mechanizmów plikowych bez testu i zmiany walidatora. File-dependent paths muszą być literalne, nie interpolowane. Obsłużyć env_file string lub listę stringów wskazujących ten sam zatwierdzony env; formy mapowe nieobsługiwane → blocked.

  Zamknąć również zbiór service keys: image/build/container_name/restart/env_file/environment/labels/ports/expose/volumes/networks/network_mode/depends_on/healthcheck/command/entrypoint/working_dir/user/read_only/tmpfs/security_opt/cap_drop/cap_add/logging/deploy/stop_grace_period/stop_signal/init/profiles/hostname/domainname/extra_hosts/devices/ulimits/shm_size/privileged/configs/secrets/cpus/mem_limit/mem_reservation/pids_limit/oom_score_adj/stdin_open/tty/runtime/isolation/pid/ipc/uts/platform/pull_policy/scale oraz x-*. Inne → unsupported_compose_input. Build mapping dopuszcza tylko context/dockerfile/dockerfile_inline/args/target/cache_from/cache_to/additional_contexts/labels/network/extra_hosts/platforms/secrets/privileged/pull/no_cache/shm_size/ulimits/provenance/sbom i x-*. Config/secret definitions dopuszczają wyłącznie external/name/content/environment. Nie traktować nieznanego pola jako niegroźnego wyłącznie dlatego, że fake Compose je zignorował.

  Zachować oryginalną treść/kolejność/tagi i anchory, zastąpić tylko ScalarToken env_file na JSON-quoted bezwzględną ścieżkę snapshotu env. Node.start_mark może obejmować &anchor: skojarzyć go z jednoznacznym ScalarToken ze scanner yaml.scan, nie usuwać anchora/tagu wraz z wartością. Zastąpienia od końca, UTF-8, jednokrotne dla aliasowanych zakresów. Nie znać lokalizacji tokenu → blocked. Każde przekształcenie zapisać wyłącznie jako bezpieczne metadane techniczne w pamięci.

  Skopiowane Compose konsumować z `--project-directory` równym oryginalnemu katalogowi pierwszego Compose oraz z jawnym snapshot `--env-file`; zachowuje to względne ścieżki bind/build. Nie odczytywać tych bind/build źródeł. Wszystkie następne config/ps/help używają tego samego snapshotu, nigdy oryginalnego env lub Compose. Obsługę tych flag uwzględnić w whitelist runnera.

  Scratch istnieje, jest pusty, prywatny0700 i bez symlinków; utworzyć własny podkatalog, pliki0600, wyczyścić go w finally. Zły owner/mode, błąd create/delete/parse daje blocked. `verify_originals()` po obserwacjach obejmuje ponownie inventory, active metadata, Compose/env; nie aktualizuje oczekiwanego SHA.
- [ ] **Step 4 — Verify GREEN:** Step2 + Task1/2 tests → PASS. Fake Compose otwiera rzeczywiste snapshot files i potwierdza zachowane interpolacje, tags i project_directory; nie wystarczy mock wyjścia config. Kanoniczne kontrole przed commitem.
- [ ] **Step 5 — Commit:** `fix: wiąż odczyty Compose ze sprawdzonym snapshotem wejść`.

### Task 4: Dokładny dowód review zakresu tooling

**Files:** Create `ops/release_preflight_review.py`, `backend/tests/test_ops/test_release_preflight_review.py`; modify `ops/release_preflight_policy.py` i testy policy. Przełączenie adaptera `_source_facts` należy do Task5.

**Interfaces:**
- Consumes: read_private_json z Task1 i przypięty odczyt Git z Task2.
- Produces w czystym `release_preflight_policy.py` typy `SourceChange(service: str, path: str, before_mode: str | None, before_blob: str | None, after_mode: str | None, after_blob: str | None, after_sha256: str | None)` i `VerifiedToolingScope(proof_sha256: str, changes: tuple[SourceChange, ...])`. Moduł review importuje te typy z policy; policy nie importuje review/trust/exec, bez cyklu importów i I/O.
- Produces `verify_review_scope(path: Path, expected_sha256: str, *, candidate: str, service_revisions: dict[str, str], checker_bundle_sha256: str, actual_changes: tuple[SourceChange, ...], review_report: Path) -> VerifiedToolingScope`.
- Produces `collect_source_changes(runner: ReadOnlyRunner, *, candidate: str, service_revisions: dict[str, str]) -> tuple[SourceChange, ...]`; korzysta wyłącznie z zamkniętych odczytów Git, nie z Docker/DB. Repo i komendy Git są dostępne w runnerze przed bind Compose.
- Extend ReleaseFacts o `tooling_scope: VerifiedToolingScope | None = None` bez naruszenia istniejących pól. Pure policy korzysta wyłącznie z dokładnie dopasowanych entries, nie z bool reviewed=True.

Dowód version1 ma dokładnie `version`, `candidate`, `service_revisions`, `checker_bundle_sha256`, `review_report_sha256`, `review_result`, `changes`; review_result dokładnie `"accepted_no_open_critical_or_important"`. Każde changes to dokładnie pola SourceChange, jeden rekord per service/path w kompletnym unionie nieznanych źródeł. Brak/extra/duplikat blokuje. Treść raportu jest prywatnym, wskazanym plikiem o sprawdzonym hashu; operator akceptuje hash dowodu dopiero po rzeczywistym review. Tekstowe review_result samo nie daje zgody.

- [ ] **Step 1 — Write RED:** `test_unknown_ops_stays_blocked_without_scope`, `test_exact_reviewed_checker_paths_are_reported_not_filtered`, `test_scope_proof_binds_every_service_and_exact_candidate`, `test_foreign_ops_workflow_or_forged_blob_still_blocks`.

  Asercje: dowód dla3baseline i jednego kandydata nie pasuje po zmianie choć jednego SHA; zmiana tylko docs kandydata również wymaga nowego dopasowania. Nieprawidłowy lub pominięty stary/nowy blob/mode i nowy .github/workflow nadal blocked. Dodanie pliku ma null/null dla starej strony, usunięcie null/null dla nowej; symlinki nadal blokują.
- [ ] **Step 2 — Verify RED:** `offline_pytest "$ROOT/backend/tests/test_ops/test_release_preflight_review.py" "$ROOT/backend/tests/test_ops/test_release_preflight_policy.py"` → FAIL nowych oczekiwań, stare odmowy pozostają.
- [ ] **Step 3 — Implement:** ustalić zamknięte CHECKER_SOURCE_PATHS z mapy plików i jedną komendę deploy. Każdą nieznaną zmianę z pełnego diffu per-service porównać z dowodem, typem/mode Git i treścią nowego bloba. Nie zmieniać listy diff ani traktować tooling jak docs.

  Klasyfikacja zatwierdzonego tooling nie wymusza rollout aplikacji, ale dodaje required gate `approved_tooling_review`. Nie usuwa gates migracji/runtime/dependency/review konfiguracji. Brak dowodu zachowuje unknown_change_scope. Nie generować proof lub accepted report w checkerze.
- [ ] **Step 4 — Verify GREEN:** Step2 oraz regresje mixed-service/old-schema/historical migration → PASS. Zmienione narzędzia bez dowodu nadal exit2; z pełnym dowodem są nadal widoczne w raporcie. Kanoniczne kontrole przed commitem.
- [ ] **Step 5 — Commit:** `feat: weryfikuj dokładny zatwierdzony zakres narzędzi preflight`.

### Task 5: Bootstrap, lokalne pakowanie i CLI V2

**Files:** Create `ops/preflight_launcher.py`, `ops/prepare_preflight_bundle.py`, `backend/tests/test_ops/test_release_preflight_launcher.py`; modify `ops/release_preflight_trust.py`, adapter CLI/report i istniejące testy CLI.

**Interfaces:**
- Consumes: Task1 manifest helpers, Task2 runner, Task3 snapshot, Task4 proof.
- Produces `prepare_bundle(repository: Path, revision: str, git_pin: FilePin, python_runtime: Path, yaml_source: Path, output: Path) -> Path`; zwraca nowy `bundle-manifest.json`, bez zgody lub instalacji. Packager używa wyłącznie tego sprawdzonego absolutnego Git; nie ufa PATH także podczas przygotowania źródeł.
- Produces stdlib `verify_bundle(bundle_root: Path, expected_sha256: str, *, owner_uid: int = 0) -> dict[str, object]` i `main(argv: list[str] | None = None) -> int` launchera.
- Adapter: `main(argv: list[str] | None = None, *, bootstrap: BootstrapContext | None = None) -> int`. Dodać w trust frozen `BootstrapContext(bundle_sha256: str, toolchain_sha256: str, toolchain: Toolchain, review_scope_sha256: str | None, runtime_root: Path)`. Bez niego rzeczywisty CLI adaptera zwraca `checker_not_bootstrapped`, nie uruchamia narzędzi.

Bundle-manifest version1: `version`, `source_revision`, `runtime` (python_path/python_sha256/stdlib_root/stdlib_tree_sha256), `files` (dokładnie path/sha256/mode, relatywne bez traversal). Manifest nie obejmuje własnego hasha; „SHA pakietu” to SHA256 jego dokładnych bajtów, zatwierdzany poza pakietem. Zestaw files obejmuje cały launcher, checker, lock, vendor yaml/license; brak dodatkowych importowalnych plików/pyc. stdlib_tree_sha256 to SHA256 kanonicznego JSON uporządkowanych trójek(relative_path,sha256,mode) wszystkich .py/.pyc/.so pod stdlib_root z wyłączeniem site-packages; ensure_ascii=True, separators=(",",":"). Odrzucić symlinki i nieprzypięte ZIP/import paths. To hash treści, nie samo sys.version.

Toolchain, scope proof, review report i receipt leżą poza pakietem i kandydatem; nie włączać ich do manifestu powodując hash cycle. Receipt version1 ma `version`, `operator_reference`, `bundle_sha256`, `toolchain_sha256`, `review_scope_sha256` (nullable). Jest zapisem uzyskanej zgody, nie samodzielnym podpisem ani issuerem. Launcher dostaje artifact hashes osobno z zaakceptowanej instrukcji administratora i wymaga równości receiptu, manifestów i tych zewnętrznych pinów. Nie wyprowadza zgody z candidate files.

- [ ] **Step 1 — Write RED:** `test_bundle_digest_and_members_are_checked_before_import`, `test_candidate_import_and_pth_canaries_never_execute`, `test_launcher_requires_external_artifact_pins_not_receipt_claims`, `test_bundle_prepare_never_installs_approves_or_changes_existing_output`, `test_missing_bootstrap_never_calls_tools`.

  Asercje: canary w candidate module, .pth lub nadmiarowym pyc nie wykonuje się; zły hash/importlib origin/runtime/member/owner i obcy toolchain daje blocked przed checkerem. Brak prawidłowego6.0.3 yaml_source nie uruchamia pip. Istniejący output pozostaje identyczny.
- [ ] **Step 2 — Verify RED:** `offline_pytest "$ROOT/backend/tests/test_ops/test_release_preflight_launcher.py"` → FAIL brak interfejsów/bootstrapa, bez realnych narzędzi.
- [ ] **Step 3 — Implement:** przygotowanie pakietu tylko z przypiętych, istniejących obiektów Git i jawnego źródła PyYAML6.0.3; bez fetch/install lub przyjmowania dirty source. Sam packager nie jest zaufany przez to, że wygenerował hash — wynik podlega niezależnemu review/akceptacji.

  Launcher uruchamia się zatwierdzonym Pythonem `-I -S -B`, stdlib-only przed verify; nie może wykonać site/.pth. Zaufany supervisor/administrator zapewnia czyste środowisko już przy uruchomieniu interpretera, w tym brak LD_PRELOAD/LD_LIBRARY_PATH/PYTHON*; launcher nie może cofnąć kodu wykonanego przez loader przed startem Pythona. Po weryfikacji runtime, wszystkich members, receipt i zewnętrznych pinów wstawia wyłącznie verified code/vendor paths i importuje checker. Odrzuca niezgodny import origin. Brak CLI/env flagi testowej wyłączającej ochronę.

  CLI launchera wymaga `--bundle`, `--bundle-sha256`, `--toolchain`, `--toolchain-sha256`, `--approval`, oraz dotychczasowych jawnych target args i `--scratch-directory`; para `--review-scope`/`--review-scope-sha256` i `--review-report` jest opcjonalna, ale brak nadal blokuje unknown tooling. Nie ma domyślnego celu produkcyjnego. Receipty muszą być prywatne, bez duplikatów/extra.

  Tu podłączyć collect_source_changes, opcjonalny scope proof, ReadOnlyRunner i InputSnapshot do adaptera; usunąć starą implementację ToolRunner i bezpośrednie CLI używające PATH. Zachować walidację źródeł i decyzję o unknown scope przed wywołaniami Docker/DB. Snapshot służy dopiero do właściwych obserwacji.

  Report_version2 zachowuje istniejące pola nieautoryzacji i dodaje `checker_bundle_sha256`, `toolchain_sha256`, `review_scope_sha256`, `reviewed_tooling_changes` (bez sekretów). Przy błędzie nie echo niezaufanych wejść. Fakty tworzyć tylko po zakończeniu snapshot cleanup i verify_originals; nie drukować sukcesu przed finally.

  Testy bootstrap helpers mogą jawnie podać fixture owner_uid w procesie unit-test; zewnętrzny launcher zawsze używa0 dla zaufanego kodu/narzędzi. Pozytywne adapter tests wstrzykują zweryfikowany syntetyczny BootstrapContext, bez production CLI switch. Osobne testy dowodzą odmowy nie-root owner w zewnętrznym launcherze.
- [ ] **Step 4 — Verify GREEN:** Step2 i `offline_pytest "$ROOT/backend/tests/test_ops"/test_release_preflight*.py` → PASS; uruchomić też część launchera z `-O`. Realne fake tools mają exact argv journal; nie wystarczy przestawić assertów na stały success. Kanoniczne kontrole przed commitem.
- [ ] **Step 5 — Commit:** `feat: dodaj przypięty bootstrap i pakiet checkera preflight`.

### Task 6: Zintegrowany odbiór, procedura i jeden review całości

**Files:** Modify `.opencode/command/deploy.md`, `docs/operations/backup-restore.md`, `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`, testy CLI/policy; Create `docs/audits/2026-11-17-preflight-trust-local.md`.

**Interfaces:**
- Consumes: kompletny launcher/adapter/proof/snapshot z Task1–5.
- Produces: jawna procedura nowej wersji i raport odbioru kodu, nie inventory, approval receipt, production bundle ani deployment permit.

- [ ] **Step 1 — Write RED:** dodać `test_cli_v2_full_readonly_flow_and_all_gates`, `test_tooling_only_proof_never_restarts_or_relabels_apps`, `test_every_unknown_path_blocks_before_docker`, `test_timeout_mutation_cleanup_and_secret_canaries_do_not_emit_success`.

  Flow: synthetic Git per-service → exact tooling proof → private snapshot z prawdziwymi testowymi bajtami → fake Compose/inspect → jedno readonly exec PG → snapshot cleanup → report. Warianty no_rollout/app_only/migration_then_app muszą zachować pełne gates; po migracji i app rollback nigdy ponownego backfillu.
- [ ] **Step 2 — Verify RED:** uruchomić nowe testy przed poprawkami integracji; zapisać rzeczywisty brak flow/guard. Jeśli wszystkie od razu PASS, odnotować, że wcześniejsze zadania dostarczyły kontrakt; nie wymyślać regresji lub nie usuwać kodu tylko dla koloru.
- [ ] **Step 3 — Integrate/docs:** usunąć stare ścieżki odziedziczonego PATH i surowych Compose/env. Procedura prowadzi przez oddzielny odbiór dokładnego checkera/toolchain/scope, potem launcher, nigdy przez „zmień metadata/diff, by V1 przeszedł”. Stary raport blocked pozostaje ważnym dowodem; nowy sukces wymaga nowej zaakceptowanej wersji.

  Dokumentacja zawiera ograniczenia YAML/env_file/PG auth, prywatny scratch i ryzyko sekretów, brak atomowości całego serwera, brak issuerów, osobne przygotowanie tooling i niezmienione bramki aplikacyjne. Nowa procedura nie pozwala jej użyć na produkcji przed pełnym odbiorem i zgodami. Nie wpisywać rzeczywistych manifestów/env/danych produkcyjnych do dokumentacji.
- [ ] **Step 4 — Verify GREEN:** `offline_pytest "$ROOT/backend/tests/test_ops"/test_release_preflight*.py` → PASS, bez fixtures DB lub uruchamiania niepowiązanych operatorów. `/lint`, `/typecheck`, `/test`, dodatkowy Ruff/mypy wszystkich nowych ops oraz `git diff --check` → PASS. Raport oddziela wykonane offline tests, backend collection i Vitest; trzy pierwotne braki mają konkretne RED→GREEN.
- [ ] **Step 5 — One fresh whole-slice review:** review pełnego zakresu od bazy planu, wraz z pięcioma Review Focus i wszystkimi ledger rulings. Critical/Important naprawić w jednej uzasadnionej rundzie RED→GREEN; Minor odnotować. Nie uruchamiać odbioru produkcji jako „testu” zamiast review.
- [ ] **Step 6 — Commit and handoff:** `feat: zakończ lokalny odbiór bezpiecznego preflightu` lub osobne małe fix/docs commity po wymaganych kontrolach. Raport podaje exact SHA i nierozwiązane gates. Bez automatycznego push/publish/merge albo realnych artefaktów zgody.

## Poza lokalnym ukończeniem — nie wykonywać z rozpędu

Po lokalnym odbiorze i zgodzie na publikację potrzebne jest pełne CI dokładnego SHA, niezależny odbiór konkretnego pakietu/runtime/toolchain i dowodu review oraz ich akceptacja przez administratora. Dopiero osobna zgoda na readonly real-environment acceptance pozwala użyć nowego launchera na produkcji. Zmiana stanu unieważnia raport; powtórzyć pod deploylock przed mutacją.

Następnie nadal obowiązują backup/restore, retencja, obrazy/nonroot, kompatybilny rollback, dokładna migracja i spójny rollout aplikacji. Nie są zadaniami tego planu. Żaden sukces lokalny nie oznacza naprawy lub wdrożenia samych szkiców na produkcji.

## Self-review planu

- Pokrycie spec: trust/zgoda/runtime → Tasks1/5; PATH/PG → Task2; snapshot/sekrety/cleanup → Task3; dokładny tooling scope → Task4; procedura i odbiór → Task6.
- Interfejsy: ReadOnlyRunner konsumuje Toolchain; adapter bind dostaje wyłącznie InputSnapshot; source_facts tworzy SourceChange i VerifiedToolingScope dla ReleaseFacts; launcher konstruuje BootstrapContext dopiero po verify.
- Nie ma cyklu hashy: manifest pakietu wyklucza siebie i zewnętrzne dowody; proof wskazuje jego digest, ale nie jest member pakietu; receipt porównywany z zewnętrznymi pinami, nie sam ze sobą.
- W self-review poprawiono cykl importów (typy SourceChange/VerifiedToolingScope są w policy), brak project_directory i źródłowych pinów w interfejsie snapshotu oraz ryzyko usunięcia YAML anchora przy zastępowaniu całego Node. Zadania używają spójnych poprawionych sygnatur.
- Usunięto konflikt etapów: kompletne CLI przełączane jest w Task5, nie przez użycie brakujących jeszcze zależności w Task2/3. Każdy wcześniejszy moduł ma własny cykl testowy; V1 nigdy nie jest deklarowany bezpiecznym dzięki częściowej naprawie.
- Wszystkie pięć Review Focus ma konkretny test i właściciela. CLI/policy istniejące91przypadków pozostaje regresją, nie deklaracją wystarczalności.
- Zależności narzędziowe są odrębne; brak zmian backend/requirements i workflowów. Parser, bezpośredni Compose i lokalne bezhasłowe PG mogą nie obsłużyć rzeczywistego środowiska — jawny blocked, nigdy fallback.
- Nie zmieniono kodu, nie zainstalowano zależności i nie zatwierdzono przyszłych artefaktów. Implementacja czeka na przegląd planu oraz wybór Native/Subagent-driven.
