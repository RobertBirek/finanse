# Actual Preserved History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uzgodnić Actual plus jedną przypiętą zachowaną operację bez zmiany księgi i wykonać wyłącznie próbę na kopii.

**Architecture:** Osobny moduł waliduje manifest i aktualny zapis w PostgreSQL oraz
wylicza wkład postingów. Importer zachowuje surowy raport, tworzy raport jawnie
rozszerzony o zatwierdzoną historię i nadal wymaga pełnego uzgodnienia przed commitem.

**Tech Stack:** Python 3.12+, Pydantic v2, SQLAlchemy async, PostgreSQL, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-actual-preserved-history-design.md`

## Global Constraints

- Dokładnie jedna istniejąca operacja Actual, z ID i hashem; kwoty wyłącznie z PostgreSQL.
- Bez aktualizacji/usuwania historii, korekt księgowych, tolerancji i dowolnego SQL przez LLM.
- Domyślne zachowanie importera bez manifestu nie zmienia się.
- Bez nowych zależności, migracji, deployu lub importu produkcyjnego.
- Rzeczywiste dane, manifest, hashe prywatnego eksportu i raport pozostają poza repozytorium.
- Testy integracyjne nie mogą działać równolegle na tej samej bazie finanse_test.

## Review Focus

1. Zmieniony zapis po zatwierdzeniu lub podmiana ZIP po hashowaniu muszą blokować zmianę danych użytych w próbie; pełne metadane/postingi są objęte pinem.
2. Operacja ponownie obecna w źródle nigdy nie zwiększa sald drugi raz.
3. Właściciel/source/mapowanie i obce lub brakujące referencje nie mogą przejść jako poprawne.
4. Równoległa zmiana zatwierdzonego zapisu musi czekać na koniec transakcji importera.
5. Dodatkowa niezatwierdzona różnica nadal blokuje commit; raport nie ukrywa surowej rozbieżności.

---

### Task 1: Pin i wkład zachowanej historii

**Files:**
- Create: `backend/app/finance/actual_history.py`
- Create: `backend/tests/test_finance/test_actual_history.py`

**Interfaces:**
- `PreservedHistoryManifest`: version=1, source_zip_sha256, user_id, transaction(actual_id, pa_id, snapshot_sha256); extra=forbid.
- `load_preserved_history(path: Path, archive_bytes: bytes, user_id: UUID) -> PreservedHistoryManifest`.
- `transaction_fingerprint(transaction: FinancialTransaction) -> str`.
- `validate_preserved_history(db: AsyncSession, user_id: UUID, manifest: PreservedHistoryManifest, source_actual_ids: set[str]) -> FinancialTransaction` (async; locks parent/postings, validates immutable pin).
- `add_preserved_history_balances(transaction: FinancialTransaction, account_map: dict[str, UUID], category_map: dict[str, UUID], group_map: dict[str, UUID], source_categories: list[CategoryDict], accounts: dict[str, SourceBalance], categories: dict[str, CategoryBalance], groups: dict[str, CategoryBalance]) -> tuple[dict[str, SourceBalance], dict[str, CategoryBalance], dict[str, CategoryBalance]]`; no mutation of inputs.

- [ ] Write negative tests for wrong ZIP/user/UUID/hash/source/mapping, missing/reappearing ID, unknown manifest fields, and changed metadata/postings.
- [ ] Run those tests and confirm missing implementation fails.
- [ ] Implement strict manifest, deterministic fingerprint and locked PostgreSQL validation. Preserve all original rows.
- [ ] Pin canonical encoding from the spec in tests: reordered ORM postings same hash, every mapped column changes hash, Unicode exact, UTC timestamps, six-decimal Numeric; no rounding away changed precision.
- [ ] Pin exact provenance equality (entity_type/actual_id/owner/entity_id) and the full transaction/transfer/split source ID union; reject duplicate source IDs before any writes.
- [ ] Write synthetic contribution tests using 37 minor units (not real data), including native foreign currency, PLN base category/group signs, missing references and unchanged input maps.
- [ ] Observe RED, implement additions with dataclasses.replace and inverse verified mappings; reject ambiguous/unmapped references and currency mismatch.
- [ ] Add two-session lock tests for pinned transaction/posting and referenced metadata; verify rejection or waiting, release by rollback. Acquire locks in the spec's fixed order under the user advisory lock, retain through commit/rollback.
- [ ] Run focused tests, Ruff and mypy; require PASS. Review and commit this independently testable module.

### Task 2: Importer, jawny raport i próba

**Files:**
- Modify: `backend/scripts/migrate_actual.py` (migrate/main/write_reconciliation_report).
- Create: `backend/tests/test_finance/test_actual_history_import.py`.
- Update: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`.

**Interfaces:**
- `migrate(..., preserved_history_manifest: Path | None = None) -> None`.
- `extract_sqlite(blob_path: Path, *, archive_bytes: bytes | None = None) -> Path`; with bytes only read one root db.sqlite from ZipFile(BytesIO), no reopening blob_path.
- CLI `--preserved-history-manifest PATH`, only with execute+require-reconciled and without replacement.
- Writer optional keyword-only `raw_actual: ReconciliationReport | None` and `preserved_history: dict[str, Any] | None`; no-manifest output unchanged.
- With manifest JSON envelope exactly: schema_version=1, source_basis, raw_actual, augmented, preserved_history(manifest, contributions). No-manifest output stays byte/schema compatible. ensure_reconciled consumes augmented; text labels both reports.

- [ ] Write integration fixture with one mapped Actual operation absent from synthetic export; without manifest strict import fails/rolls back, with manifest raw_actual remains false and augmented report becomes true.
- [ ] Run to RED; read ZIP once into immutable bytes, validate hash against those bytes and pass the same bytes to extraction. Implement mode/user checks, per-user advisory lock and locked pin verification before entity creation.
- [ ] Add TOCTOU regression swapping the path after hash verification: parsed data must still come from the originally approved bytes. Reject duplicate source IDs across all three parsed transaction paths.
- [ ] After ordinary map validation, derive augmented expectations from the pinned row; compute raw and augmented reports against the same PA snapshot. Run ensure_reconciled on the augmented report with unchanged import errors.
- [ ] Write tests for all invalid mode combinations, unchanged no-manifest behavior, wrong/stale pin, a reappearing source ID, and another unexplained difference. Verify no new account/mapping/transaction survives from a fresh session on failure.
- [ ] Write repeat-import test: existing transaction/postings unchanged and all new source IDs imported once, contributions applied once per report, not accumulated between runs.
- [ ] Run focused tests to GREEN; request independent review before the full gate.
- [ ] Run project test/lint/typecheck commands for backend and frontend; report deselected tests and warnings explicitly.
- [ ] Privately generate manifest only after verifying the existing approved snapshot; record source/code hashes. Run execute+require-reconciled only on the guarded isolated clone, retain raw/augmented report and compare all original ledger rows.
- [ ] Update docs, commit after gates; do not push/merge/deploy or run production execute. Return report for separate production decision.

## Self-review

Każdy punkt spec ma test lub krok powyżej. Wkład jest wyliczany z postingów, nie z
różnicy raportu; żaden błąd poza dokładnym pinem nie jest pomijany. Interfejsy modułu
i importera rozdzielają weryfikację od wyliczenia; domyślna ścieżka pozostaje bez zmian.
Builder-check uściślił niezmienny ZIP, provenance, kolejność blokad, kodowanie i envelope;
to techniczne wybory agenta, nie dodatkowa zgoda na dane lub produkcję.
