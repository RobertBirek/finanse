# Vision Amount Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this approved small change. Track steps below.

**Goal:** Give the vision model the canonical amount format already required by the backend, without weakening financial validation.

**Architecture:** Add a nullable, positive decimal-string pattern and description to `VisionFields.total`, and matching developer instructions. Retain `to_minor_units`, `ReviewFields`, safe error handling and human approval unchanged. Only synthetic tests; no provider requests or production changes.

**Tech Stack:** Python, Pydantic v2, OpenAI Responses strict JSON Schema, pytest/httpx MockTransport.

**Spec:** User-approved three-point chat scope: enforce format like `"1234.56"` in schema/instructions; retain positive/exact/bounded validation without guessing or rounding; synthetic tests. User approved local implementation, not deploy or another AI call. This document records that already approved scope, not a new project.

## Global Constraints

- No AI/OCR, upload, production DB writes, document edits, migrations, policy changes or deployment.
- Keep amounts as strings at the model boundary and exact integer minor units at the financial boundary; never floats or rounding.
- Preserve null for unknown/ambiguous totals, existing overflow limit, canonical values with zero/one/two fractional digits, and nonretryable safe rejection.
- Do not normalize malformed model output, invent values, or accept zero/negative totals.
- Preserve unrelated Velo/Q7 documentation changes and use the existing linked worktree.

## Review Focus

- Sub-unit amounts (`0.01`, `0.1`, `0.10`) remain accepted exactly; zero does not.
- Localized formatting, currency text, signs, whitespace, exponent notation and >2 fractional digits remain rejected, not silently repaired.
- The existing maximum exact amount is accepted; its next cent is rejected by existing financial validation.
- Null total stays null and produces an incomplete review, not a default or a retry.
- Provider payload, safe exception and logs do not expose private input or enable automatic retries.

## Task 1: Align the outbound amount contract and prove unchanged boundaries

**Files:**
- Modify: `backend/app/documents/vision_schemas.py` — pattern/description for model-facing total only.
- Modify: `backend/app/documents/vision_client.py` — developer instructions for formatting a legible unambiguous source total.
- Create: `backend/tests/test_documents/test_vision_amount_contract.py` — schema/request and adapter regression matrix.
- Update: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` — results and deployment caveats.

**Interfaces:** `VisionFields.total: str | None`, `extract_image_review(jpeg: bytes, *, config: VisionConfig) -> VisionExtraction`, and `to_minor_units(total: str) -> int` retain signatures. No frontend or DB contract changes.

- [x] Baseline: existing vision-client tests pass in the isolated test environment (28 PASS).
- [x] RED: add request assertions for nullable total pattern/description and developer instructions. Assert schema rejects noncanonical/zero strings and accepts canonical positive strings; current schema fails (27 failures, 39 existing-behavior passes).
- [x] Add adapter regressions: preserve valid strings and exact cents (`0.01` → 1, `0.10` → 10, `1234.56` → 123456, `90071992547409.91` → 9007199254740991); null stays incomplete; invalid strings/JSON numbers/overflow fail once without leaking input.
- [x] GREEN: add ASCII canonical positive decimal grammar (no sign/grouping, at most two fractional digits), nullable description and matching instructions; preserve all semantic validators. This grammar is not a substitute for the existing upper-bound check (94 focused PASS).
- [x] Run focused tests, then project `/test`, `/lint`, `/typecheck` workflows against this worktree and the established local `finanse_test` DB; inspect fresh results. Final: 95 focused; 1147 backend, 335 frontend, both lint/types PASS; exact source manifest unchanged. No provider tests.
- [x] Request one independent scoped review, resolve substantive findings with regression tests, update docs and commit only this change after verification. Review: optional decimal point clarified, null for ambiguous separators explicit; 2 RED → 95 focused GREEN followed by final full gate. No push/deploy.

## Release caveat

Local tests do not prove a specific invoice will be read correctly. Future deployment needs separately reviewed prompt/schema version metadata and matching policy fingerprint under the existing release procedure. Do not edit production configuration or replay historical jobs as part of this task.

## Review decisions and verification environment

- Preserved transcription of an unambiguous localized printed total into canonical output; no backend normalizer was added. Blanket refusal of Polish source formatting was not the approved prohibition on guessing/repairing invalid AI output. Ambiguous separators explicitly require null; human approval remains mandatory.
- Repository `.venv` could not collect baseline tests because its OpenAI SDK lacks Responses types. The existing isolated financial-document-venv ran the project workflows without dependency edits.
- `test-db-up` encountered occupied localhost55432. Removed only its newly created stopped resources; used the established identity-checked local finanse-refactor-testdb through the previously reviewed gate helper, clearing provider keys. No concurrent pytest or production DB access.
- Evidence: `/tmp/opencode/vision-amount-contract-20261102/`; review summary and final exact-source manifest retained. No deferred minors.
