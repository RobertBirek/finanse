# Document Auto Finance Drafts Implementation Plan

> **For agentic workers:** Use executing-plans inline with TDD; one fresh whole-branch review. Track tasks with checkboxes and the owned ledger.

**Goal:** Nowy upload → odczyt + kategoria → szkic; czytelne niezależne statusy obu etapów.
**Architecture:** Istniejący odczyt i bills.prepare_bill, trwały DB intent i batch
projection; AI zwraca wyłącznie sugestię z katalogu właściciela.
**Tech Stack:** PostgreSQL/SQLAlchemy, FastAPI, ARQ, Pydantic, React/TanStack Query.
**Spec:** docs/superpowers/specs/2026-11-17-document-auto-finance-drafts-design.md.

## Global Constraints

Nie zmieniać księgi/płatności/zadań, nie uruchamiać historycznego backfillu lub
OCR na danych użytkownika. Nie nadpisywać ręcznych wyborów. Bez realnego AI/DB,
push lub deployu w tym zakresie. Zachować istniejące docs-only notatki sesji.
Python wybrany wcześniej i zatwierdzony preflight: ADVISOR_DEV_PYTHON z istniejącego venv.

## Review Focus

- Ready OCR != finansowe powiązanie; zatwierdzony bill nie znika przy błędzie nowego odczytu.
- Ponowny upload/retry/dwa delivery → jeden szkic, bez nadpisania istniejącego.
- Inny owner/nieaktywny category/key spoza katalogu → brak sugestii/wycieku.
- Ręczna kategoria, także wyczyszczona, nie jest nadpisywana przez późny wynik.
- Awaria rejestracji nie powoduje powtórnego płatnego OCR/AI, GET nigdy nie enqueues.

### Task 1: Trwały intent i projekcja statusu

Files: new documents/finance_draft_models.py, finance_draft_queries.py,
finance_draft_schemas.py; modify documents/{models,schemas,service}.py and
alembic env; new additive migration and tests/test_documents/test_finance_draft_status.py.

Interfaces: FinanceDraftSummary(state, error_code, bill_id, review, lifecycle).
`get_finance_summaries(db, user_id, ids) -> dict[UUID,FinanceDraftSummary]`.
Intent: unique(document_id), owner/document/revision FK, state/error and timestamps.
Revision: nullable suggested_category_id FK; no backfill. Migration parent efaf78432563.

- [ ] RED: batch owner-scoped projection, no source vs draft vs approved vs archived,
  stopped intent, nullable category and migration non-destructive shape.
- [ ] Run focused offline tests; expected missing contracts, no DB access.
- [ ] Implement models/schema/projection and one extra batched read in document_responses.
- [ ] GREEN focused tests + collection; integration tests added for CI, not run locally.
- [ ] Verify lint/types/test before commit `feat: dodaj trwały intent i status finansowy dokumentu`.

### Task 2: Automatyczny szkic i katalog kategorii w odczycie

Files: new documents/{finance_drafts,category_catalog}.py;
modify documents/{service,review_service,review_schemas,extractor,vision_client,
vision_schemas,vision_worker,job_service,vision_config}.py;
worker.py, config.py, finance/bills.py; tests for contracts/workers/catalog.

Interfaces: `create_finance_draft_intent(db,user_id,document_id)` (new upload only);
`prepare_pending_finance_draft(db,intent_id)` calls prepare_bill with stable key;
`dispatch_finance_drafts(ctx)` only delivers eligible committed intents.
Catalog packet: public aliases+paths / private alias→UUID; resolver revalidates
owner and category when attaching optional suggested_category_id.

- [ ] RED: new upload creates intent; duplicate does not; no old rows adopted.
  Supported complete review → one draft; incomplete/archive/other → safe state;
  existing link preserved; replay/concurrent delivery guarded.
- [ ] RED catalog: unknown/deleted/foreign/inactive/cyclic/technical taxonomy,
  null model choice, budget limits and hostile text; image/text parity.
- [ ] Observe failures offline, implement DB orchestration and optional enriched
  extraction contract, preserving legacy payload without catalog.
- [ ] GREEN: no ledger/declaration writes, no extra provider invocation; migration
  integration/concurrency tests queued for CI. Config limits in Settings, not hardcoded.
- [ ] Full devchecks, commit `feat: przygotuj szkice finansowe po odczycie dokumentów`.

### Task 3: Statusy, linki, szkice i edytowalna sugestia w UI

Files: api/{documents,bills}.ts; DocumentList, DocumentUpload; documents/
{documentStatus,DocumentReview,useReviewForm}; finance/bills/{BillRegister,BillDetail};
focused Vitest tests.

Consumes Task1 finance summary and Task2 optional suggested_category_id.
No GET mutations, known actor/generation guards and normal Query invalidation.

- [ ] RED: separate recognition/finance badges, correct route to existing bill,
  no link fabricated from ready; draft action opens review of source.
- [ ] RED: suggested category prefilled only for owned active option; manual
  selection/clear survives late results/retry; no category creation; no-suggestion.
- [ ] Implement accessible labels, direct actions, draft presentation and polling
  while DB intent pending. Upload notice includes category catalog data export.
- [ ] GREEN focused Vitest, full frontend suite/lint/types/build.
- [ ] Full devchecks, commit `feat: pokaż obieg dokumentów i sugestie kategorii`.

### Task 4: Odbiór, dokumentacja i jeden review

- [ ] Run all focused offline contracts, project /lint /typecheck /test, frontend build.
- [ ] Fresh readonly whole-branch review, fix Important/Critical once by RED→GREEN,
  record deferred minors; no second reviewer.
- [ ] Update CHANGELOG/TASKS/JOURNAL and local audit; state explicitly that live
  migration/provider/runtime not verified. Commit results locally, no push/deploy.
- [ ] Preserve evidence, finish branch and ask separately about integration.
