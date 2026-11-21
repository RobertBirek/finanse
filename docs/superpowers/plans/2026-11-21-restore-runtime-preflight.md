# Kontrola zgodności restore — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ujawnić niezgodność drzewa migracji z wybraną kopią i oczekiwanym headem, zanim operator rozpocznie próbę lub przełączy wydanie.

**Architecture:** Samodzielne odczytowe CLI z zaufanego checkoutu sprawdzi dwa przypięte manifesty i dokładne pliki runtime'u. Czysta funkcja wykorzysta istniejącą weryfikację grafu AST; raport nie jest pozwoleniem na wykonanie operacji.

**Tech Stack:** Python 3.12+, biblioteka standardowa, istniejący parser AST, pytest offline.

**Spec:** [Projekt kontroli restore](../specs/2026-11-21-restore-runtime-preflight-design.md).

## Global Constraints

- Tylko odczyt plików lokalnych, bez importowania kodu runtime'u, subprocesów,
  DB, Restic, Docker, sieci lub konfiguracji produkcji.
- Brak zmian checkera V2, allowlisty, receiptów, aktualizacji systemd/Make
  i mechanizmu publikacji. Włączenie do czynności operatora wymaga później
  osobnego przeglądu, przypięcia narzędzia i akceptacji instalacji.
- Dwa niezależne wywołania: `rehearsal` i `after_rollout`. Nie przyjmuj
  `latest` ani skrótu snapshotu. Nie uznawaj wybranego pliku manifestu za
  dowód jego pochodzenia bez wiązania spoza CLI.

## Review Focus

1. Nieznany schemat kopii przy poprawnym headzie (Task 1).
2. Rozgałęzienie lub zależności Alembic wymagające innego modelu grafu (Task 1).
3. Dokładnie te same rewizje, ale inne bajty migracji lub dodatkowy skrypt (Task 2).
4. Niejawna inna lokalizacja migracji lub plik pod symlinkiem (Task 2).
5. Niepowiązany, skrócony lub ruchomy snapshot oraz błędy z prywatną treścią (Task 2).

### Task 1: Czysta decyzja o zgodności

**Files:** `ops/restore_runtime_preflight.py`, `backend/tests/test_ops/test_restore_runtime_preflight.py`.

**Interfejs:** `check_lineage(sources: dict[str, str], snapshot_revision: str, expected_head: str) -> None`. Przy błędzie zgłasza `PreflightInputError` z bezpiecznym kodem. Consumes `parse_lineage` i `ordered_lineage` z `ops/release_preflight_policy.py`; bez zmian w tym module.

- [ ] Dodać przypadki: `a → b → c` akceptuje kopie `a` i `c` dla headu `c`;
  nieznane `z` przy headzie `c` daje `snapshot_revision_unknown`; oczekiwane
  `b` przy faktycznym `c` daje `runtime_head_mismatch`. Rozgałęzienie,
  duplikat, cykl i `depends_on` zachowują błędy istniejącego parsera.
- [ ] Uruchomić wskazany plik testów w odizolowanym trybie offline według
  `docs/development/testing.md` (bez fixture DB). Oczekiwany RED: brak funkcji/modułu.
- [ ] Zaimplementować funkcję: sprawdzić pełne i domknięte drzewo przez istniejący
  parser, porównać ostatnią rewizję z dokładnym headem i wymagać członkostwa
  rewizji kopii w tym grafie.
- [ ] Ponowić ten sam plik i `tests/test_ops/test_release_preflight_policy.py`.
  Oczekiwane GREEN obu plików; mały commit tylko po projektowych kontrolach.

### Task 2: Przypięte wejścia i raport odczytowy

**Files:** `ops/restore_runtime_preflight.py`, `backend/tests/test_ops/test_restore_runtime_preflight.py`, `docs/operations/backup-restore.md`.

**Interfejs:** `main(argv: list[str] | None = None) -> int`, opcje jawnie
wymagane: `--phase rehearsal|after_rollout`, `--candidate` (40 hex),
`--runtime-root`, `--runtime-manifest`, `--runtime-manifest-sha256`,
`--snapshot-id` (64 hex), `--snapshot-manifest`,
`--snapshot-manifest-sha256`, `--expected-head`. SHA-256 w małych hex.

Manifest runtime'u v1: `version`, `runtime_revision` (40 hex),
`runtime_root` (absolutny), `files` (lista dokładnych `{path, sha256}`) i
`scope` (dokładnie `candidate`, `phase`, `snapshot_id`,
`snapshot_manifest_sha256`, `expected_head`, zgodne z argumentami CLI).
Zmiana fazy lub celu wymaga osobnego przypiętego manifestu, nawet gdy bajty
runtime'u są te same.
Ścieżki względne wyłącznie `ops/restore-verify.sh`, `backend/alembic.ini`,
`backend/migrations/env.py`, `backend/.venv/bin/alembic` i komplet
`backend/migrations/versions/*.py` (tylko bezpośrednie pliki, bez innych
źródeł migracji). Jedyny ignorowany katalog to rzeczywisty, niebędący
symlinkiem `__pycache__`; bez odczytu bytecode. `alembic.ini`: sekcja
`[alembic]`, `script_location = migrations`, bez ustawień zmieniających
discovery, w tym `version_locations`, `recursive_version_locations` i
`sourceless`, również przez `[DEFAULT]`. Kopia ma dotychczasowy format
manifestu backupu, z wymaganym stringiem `alembic_revision`; pełny Restic ID
pochodzi z zewnętrznej zgody.

- [ ] Dodać testy CLI na plikach syntetycznych: `test_snapshot_head_compatibility_report`
  sprawdza obie fazy, pełny ID i wszystkie powiązania; `test_drift_blocks_even_with_same_revisions`
  zmienia bajty lub dodaje plik/nested source; `test_unsupported_restore_layout_blocks`
  obejmuje opcje discovery i symlinki katalogu, pliku oraz cache;
  `test_regular_pycache_is_ignored` chroni typowy istniejący runtime;
  `test_invalid_snapshot_binding_blocks`
  obejmuje `latest`, skrót lub zły digest; `test_input_failures_do_not_echo_contents`
  obejmuje duplikaty, brak pliku i marker prywatny w błędnym JSON.
- [ ] Uruchomić testy CLI offline; oczekiwany RED: brak obsługi wejść/raportu.
- [ ] Otwierać wyłącznie zwykłe pliki bez symlinków, pod zatwierdzonym absolutnym
  rootem i w ścieżkach bez `..`; odrzucać pliki/katalogi runtime'u zapisywalne
  dla grupy lub innych. W produkcji osobny nadzorca weryfikuje custody ścieżek
  jako root. Limity: 256 migracji, 1 MiB na plik (w tym wejściowe JSON),
  16 MiB łącznie odczytanych danych. Odrzucać duplikaty JSON/ścieżek, brak,
  nadmiar i drift. Parsować dokładnie bajty użyte do sprawdzenia hashy.
- [ ] Wywołać `check_lineage`. Na sukces (`0`) wypisać pojedynczy JSON:
  `version:1`, `compatible:true`, `authorized:false`, `phase`, `candidate`,
  `snapshot_id`, `snapshot_manifest_sha256`, `runtime_revision`,
  `runtime_manifest_sha256`, `snapshot_revision`, `expected_head`. Przy błędzie
  (`2`) tylko `version`, `compatible:false`, `authorized:false` i `reason_code`,
  bez surowych ścieżek, wyjątków ani zawartości danych.
- [ ] Opisać w runbooku obie fazy, dokładny snapshot i osobną kontrolę ścieżki
  systemd/Make oraz ograniczenia. Uruchomienie z czystego środowiska i
  jawnie przypiętego checkoutu narzędziowego; Python nie dodaje sprawdzanego
  runtime'u do ścieżki importów. Nie dopisywać, że narzędzie jest zainstalowane.
- [ ] Ponowić nowe i powiązane testy offline, `/lint`, `/typecheck`, `/test`
  zgodnie z projektem. Nie nazywać kolekcji testami backendu. Po niezależnym
  review zrobić mały lokalny commit. Wdrażanie i publikacja wymagają osobnej zgody.
