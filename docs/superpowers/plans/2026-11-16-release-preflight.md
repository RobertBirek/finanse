# Release Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mały readonly preflight rozróżniający brak rollout/app-only/migrację i blokujący niepewne wejścia przed zmianami.

**Architecture:** Czysta polityka podejmuje decyzję na podstawie typowanych faktów.
Osobny CLI zbiera fakty przez zamknięty zbiór odczytów Git/Compose/PG i emituje
zredagowany raport. Nie wykonuje wdrożenia i nie zastępuje istniejących bramek.

**Tech Stack:** Python3.12+, stdlib, pytest, Git, Docker Compose; bez nowych zależności.

**Spec:** `docs/superpowers/specs/2026-11-16-release-preflight-design.md`.
Użytkownik zatwierdził plan i Native 2026-11-17, następnie samodzielny dobór środowiska.

## Global Constraints

- Tylko dokumentacja w sesji planowania; wykonanie wymaga osobnego zatwierdzenia.
- V1 nigdy nie tworzy/startuje/zatrzymuje/usuwa kontenerów, nie zmienia DB lub metadata.
- Wyłącznie `--check`; JSON stdout z `report_version=1`, `authorized=false`,
  `production_ready=false`; exit0 klasyfikacja, exit2 blocked.
- Kandydat i każda rewizja usługi to pełne40znakowe SHA; obraz `sha256:`+64hex.
- Każdy subprocess timeout10s, kontrolowane argv, bez raw output/sekretów i assertguard.
- Zewnętrzna obserwacja nie jest blokadą TOCTOU; wymagana ponowna kontrola pod deploylock.
- V1 obsługuje tylko liniowy graf migracji z jednym head; bez import/exec migracji.
- Bez zmian `prepare_release.py`, `verify_release.py`, historycznego `release_policy.py`,
  modeli aplikacji, zależności, migracji, workflow CI lub istniejących fixtureDB.
- Bez push/deploy, prawdziwego Docker/DB lub odczytów produkcyjnych w implementacji.

## Review Focus

- Różne runtime SHA backend/workera/frontendu i nowszy docs git_tip: żadna usługa
  nie może zostać pominięta przez porównanie jednego wspólnego commita — Task1.
- Rename pliku testowego do runtime i nieznana ścieżka nie mogą dać no_rollout — Task1.
- Rollback aplikacji po już wykonanej migracji nie może ponowić backfillu — Task1.
- Obcy projekt/PG/imageID lub sekretny stderr nie mogą przejść lub wyciec — Task2.
- Sukces `--check`, stary raport lub `python -O` nie są zgodą na mutację — Tasks2–3.

## Pliki i odpowiedzialności

- Create `ops/release_preflight_policy.py`: typy, walidacja, klasyfikacja ścieżek/grafu.
- Create `ops/release_preflight.py`: parser, readonly obserwacja i raport/exit.
- Create `backend/tests/test_ops/test_release_preflight_policy.py`: czyste unit tests.
- Create `backend/tests/test_ops/test_release_preflight.py`: Git/tmp_path/fake Docker/CLI.
- Modify `.opencode/command/deploy.md`, `docs/operations/backup-restore.md`:
  użycie nowej bramki, granice i brak implicit authorization.
- Modify CHANGELOG/TASKS/JOURNAL po wykonaniu. Spec/plan stanowią dokumentację projektu.

## Przygotowanie

- [ ] Potwierdzić izolację przez using-git-worktrees, czytać aktualne4docs.
  Obecna baza planu: main/worktree `b5c212a`, runtime45bcf88/schemaefaf.
- [ ] Jawny istniejący ADVISOR_DEV_PYTHON i projectpreflight; nie aktualizować sharedvenv.
  Baseline `/lint`, `/typecheck`, `/test`; ten ostatni to offlinecollection+Vitest.
- [ ] Utrzymać ledger planu w jego własnym ignorowanym workspace, bez produkcyjnych danych.

### Task 1: Czysta decyzja i graf migracji

**Files:** create policy i jego testy wskazane powyżej.

**Interfaces:**
- `ReleaseFacts` frozen dataclass: `candidate: str`, `service_revisions: dict[str,str]`,
  `image_ids: dict[str,str]`,
  `changed_paths: dict[str,tuple[str,...]]` (backend/worker/frontend),
  `schema_heads: tuple[str,...]`, `lineage: dict[str,str|None]`,
  `compose_up_flags: frozenset[str]`, `ancestry_ok: bool`,
  `historical_migration_changed: bool`.
- `PreflightDecision` frozen dataclass: `action: Literal["no_rollout","app_only",
  "migration_then_app","blocked"]`, `pending_migrations: tuple[str,...]`,
  `reason_codes: tuple[str,...]`, `required_gates: tuple[str,...]`.
- `classify(facts: ReleaseFacts) -> PreflightDecision`.
- `parse_lineage(sources: dict[str,str]) -> dict[str,str|None]`: AST stałych Assign/
  AnnAssign; `PreflightInputError(code: str)` przy nieobsługiwanym/niespójnym grafie.
- `classify` waliduje typy i odpowiada blocked dla niepoprawnych facts; CLI mapuje
  parser exception do tego samego zredagowanego kontraktu.

- [ ] **Step1 — testy RED.** Dokładne nazwy i oczekiwania:
  - `test_docs_and_test_only_is_no_rollout`:3różneSHA, schema=head, wszystkie zmiany
    z allowlist → no_rollout, migrations(), brak wymagania nowego obrazu.
  - `test_backend_older_than_frontend_still_requires_app`:frontenddiffdocs,
    backenddiff`backend/app/main.py` →app_only mimo nowszego git_tip.
  - `test_other_service_only_paths_do_not_force_rollout`: backenddiff wyłącznie
    frontendruntime, frontenddiffdocs →no_rollout, gdy pozostałe fakty spójne.
  - `test_already_applied_head_never_repeats_migration`: pliknowejmigracji
    w diff, DB=head →app_only i migrations().
  - `test_missing_linear_revisions_are_ordered`: base→middle→head, DB=base →
    migration_then_app i ("middle","head").
  - `test_unknown_multihead_branch_cycle_and_duplicate_block`: każda wada →blocked.
  - `test_edit_or_delete_historical_migration_blocks`: existing versionsfile
    zmieniony/usunięty →blocked, odróżnić nowy append po już wykonanym head.
  - `test_lineage_ast_never_executes_source`: źródło zawierające wywołanie
    na poziomie modułu nie jest wykonywane; dynamiczne przypisanie revision blokuje.
  - `test_rename_test_to_runtime_and_unknown_paths_never_skip`: oldtest+newruntime
    →app_only; nieznanaścieżka →blocked.
  - `test_missing_compose_stage_flags_blocks_app_actions`: brak każdego z
    --no-start/--no-deps/--no-build →blocked, nie proponować create--no-deps.
  - `test_backend_dependencies_require_new_runtime_gate`: requirements.txt →
    required_gates zawiera rebuild_and_verify_runtime.
- [ ] **Step2 — potwierdzić RED.** Własny namespace bez sieci zgodnie z devchecks;
  `$ADVISOR_DEV_PYTHON -B -m pytest -q tests/test_ops/test_release_preflight_policy.py`.
  Expected: FAIL braku modułu/funkcji, nie połączenia DB.
- [ ] **Step3 — implementacja policy.** Allowlist i precedence dokładnie ze spec;
  kod2/blocked nie jest wyjątkiem procesu dla błędnych facts. AST nie uruchamia źródeł.
  Dla działań aplikacyjnych required_gates zawsze zawiera approval, CI/build,
  verify_release, backup_restore, fenced_retention, rollback_compatibility i runtime;
  migration action dodatkowo exact_migration_approval. Są to wymagania, nie status PASS.
  Każda akcja, także no_rollout, zawiera external_configuration_scope_review;
  narzędzie nie klasyfikuje zmian konfiguracji spoza Git.
  Czysta polityka scope per-service i blokadę historical_migration_changed bierze
  ze spec; brak udowodnionych faktów nie jest no_rollout.
- [ ] **Step4 — GREEN i typy.** Ten sam pytest oraz Ruff/mypy nowych plików.
  Expected: wszystkie przypadki PASS, brak fake permits lub fixtureDB.
- [ ] **Step5 — commit** `feat: dodaj czystą klasyfikację preflight wydania`.

### Task 2: Readonly CLI i obserwacja

**Files:** create CLI i jego testy wskazane powyżej.

**Interfaces:**
- `ToolRunner.run(argv: list[str]) -> str`: zamknięta walidacja komend,
  subprocess shell=False/check=False/capture_output/timeout10s; błędy kontrolowane.
- `collect_facts(args: argparse.Namespace, runner: ToolRunner) -> ReleaseFacts`:
  pełne źródła Git, inspecty i schema; weryfikuje spójność active metadata.
- `build_report(facts: ReleaseFacts|None, decision: PreflightDecision) -> dict[str,object]`;
  `main(argv: list[str]|None = None) -> int`.
- CLI wymagane: --check, --repository ABS, --candidate FULL_SHA,
  --active-release ABS, --project NAME, powtarzane --compose-file ABS (min2, kolejność
  inventory, active override ostatni), --env-file ABS, --postgres-service NAME,
  --approved-inventory ABS, --inventory-sha256 HEX64.
  Servicebackend/worker/frontend stałe; PGwybranyjawnie. Brak domyślnych celów.
  Format inventory/version1, pola active metadata, uprawnienia i hashbinding
  dokładnie ze spec. Nie dodawać issuera lub nowego formatu active metadata.

- [ ] **Step1 — testy granicy RED.**
  - `test_check_cli_uses_only_read_allowlist`: uruchomić prawdziwy CLI na małym
    lokalnym Git i fake Dockerexe zapisującym argv; wynik0/3akcje bez żadnej mutacji.
  - `test_candidate_reads_git_not_dirty_worktree`: zmienić lokalną migrację po
    commicie, raport nadal wynika z dokładnego kandydata Git.
  - `test_git_modes_and_ancestry_are_checked`: zmiana testu w symlink lub gitlink,
    brak commit object i divergent/older candidate dają blocked.
  - `test_schema_read_targets_inspected_pg_id_readonly`: fakePG pod innym ID lub
    projektem blokuje przed exec; poprawny cel używa tylko literalnegoSELECT/PGOPTIONS.
  - `test_metadata_and_running_image_drift_blocks`: OCI/ID/project/service/running
    lub 2wyniki ps/inspect →exit2. Nigdy sam git_tip zamiast3revisionów.
  - `test_unapproved_or_changed_inventory_blocks_before_tools`: obcy digest,
    symlink, zły owner/mode/parent, brak/dodatkowe/powtórzone pola →exit2bezDocker.
  - `test_compose_role_and_target_are_inventory_bound`: zła kolejność/override/
    hash/envfile/PGdbrole blokują, także przy wiarygodnie wyglądających etykietach.
  - `test_no_apply_and_no_arbitrary_sql`: --apply/--sql/nierozpoznaneargv →exit2
    przed zewnętrznym subprocess; --help0 także bez subprocess.
  - `test_secrets_timeouts_and_invalid_json_are_redacted`: canary w env/config/
    stderr nie występuje w stdout/stderr/raporcie, także dla nonzero/timeout,
    duplicateJSONkeys lub niepełnegoinspectu.
  - `test_check_works_with_python_optimized`: rzeczywisty CLI -O z fake tools ma
    identyczne odmowy i authorized=false; żadne operacyjneasserty.
- [ ] **Step2 — RED** offlinepytest tego pliku; ExpectedFAIL nieobecnegoCLI.
- [ ] **Step3 — implementacja obserwacji.** Nie kopiować prywatnych secretów lub
  danych do fixture. Ograniczyć runner do jawnych odczytów ze spec; dla Git czyste
  env i GIT_CONFIG_NOSYSTEM=1/GIT_CONFIG_GLOBAL=/dev/null, bez inherited GIT_*,
  --no-ext-diff/--no-textconv, bez fetch. Zachować PATH tylko dla narzędzi operatora.
  Akceptować dopiero pojedyncze inspectowane kontenery właściwego projektu i usługi.
  CLI nie emituje poleceń mutujących ani raw configów; brak .env sourcing w Pythonie.
  Protokół stałego PGexec i walidacja env dokładnie ze spec. `ReleaseFacts` bez
  źródłowego CLI/metadata inventory nie może być automatycznie adoptowane.
  Report dodaje source_binding/operator_approved_inventory,
  content_provenance_verified=false i external_configuration_reviewed=false.
- [ ] **Step4 — GREEN** nowe dwa pliki oraz istniejące unit tests
  `test_release_policy.py` i `test_verify_release.py` na doubles (bez realDocker).
  Ruff/mypy nowych modułów i testów PASS; runtime source bez zmian.
- [ ] **Step5 — commit** `feat: dodaj readonly preflight Git Compose i schematu`.

### Task 3: Włączenie bramki do procedury i odbiór

**Files:** modify `.opencode/command/deploy.md`, `docs/operations/backup-restore.md`,
CHANGELOG/TASKS/JOURNAL. Bez zmiany workflow lub aplikacji.

**Consumes:** kontraktCLI i exit/report Task2.
**Produces:** udokumentowany ręczny etap preflight, nadal z osobnymi approval/
backup/restore/nonroot/retention/runtime/rollback gates.

- [ ] **Step1 — przykłady i instrukcje.** Udokumentować --check z jawnie podanym
  zestawem aktualnychCompose/env/PGservice oraz zatwierdzonym inventory i digestem;
  interpretację4akcji i przykłady
  BOjużzmigrowane oraz docs/test-only. Dodać zakaz traktowania exit0/staregoJSON
  jako zgody. Status produkcyjny/cookies nie jest poświadczany tym narzędziem.
- [ ] **Step2 — regresje użycia.** Istniejące testy CLI z Task2 uruchamiają
  dokładny udokumentowany zestaw argumentów na syntetycznych repo/fakeDocker.
  Expected0dla3rozpoznanychakcji,2dlablokady; zero komend mutujących w argvjournal.
- [ ] **Step3 — pełne devchecks.** `/lint`, `/typecheck`, `/test`; osobno konkretne
  unit tests Task2 przez bezsieciowy runner. Domyślny /test to wyłącznie
  kolekcjabackendu+pełnyVitest; raportować to poprawnie, bez deklaracji pełnegoDBsuite.
  Bez doinstalowywania zależności, sudo fallbacków lub prawdziwegoPG/Docker.
- [ ] **Step4 — jeden readonly review całości.** Przekazać spec, plan i ReviewFocus.
  Important/Critical odtworzyć RED i poprawić w jednym przebiegu; brak drugiego review.
- [ ] **Step5 — docs i commit** `docs: włącz preflight jako readonly bramkę wydania`.
  Publiczne wyniki bez sekretów; zachować dowody fake/externalboundary/sourcehashes.
  Nie deklarować realnego preflightu produkcyjnego lub gotowości do deployu.

## Self-review

- Trzy zadania mają spójne ReleaseFacts/Decision/CLI; Task1niezależny odI/O,
  Task2używa jego typu, Task3wyłączniepublikuje działającykontrakt.
- ReviewFocus przypisany testom; żadne obecne bramki wydania nie znikają.
- Wdrożenie i automatyczny rollback/backup/retention nie zostały przemycone do V1.
- Decyzje wykonawcze są propozycją autora, nie dawnym uzgodnieniem użytkownika.
- Builder check: doprecyzowano niezależnie zatwierdzony inventory, granicę
  poświadczenia OCI, stałe argv PG i tożsamość ostatniego override Compose.
- Sprawdzono pokrycie spec, kontrakty typów, rozmiar zadań i Review Focus.
  Format active metadata pozostaje proponowanym adapterem: osobna weryfikacja
  przed użyciem produkcyjnym, nie zadanie odczytu produkcji w implementacji.
