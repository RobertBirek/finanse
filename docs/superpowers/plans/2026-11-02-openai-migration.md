# OpenAI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przenieść całe generatywne AI aplikacji na zatwierdzone modele OpenAI i wydać spójnie na produkcję.

**Architecture:** Jeden mały klient Responses, adaptery doradcy i dokumentów. Zachowane
kontrakty bazy/API oraz polityki autoryzacji i vision; brak nowej migracji tego przyrostu.

**Tech Stack:** Python3.12, FastAPI, Pydantic2, SQLAlchemy async, OpenAI SDK2.54.0/httpx0.27, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-02-openai-migration-design.md`

## Global Constraints

- Sol dla doradcy; Terra dla tekstu i obrazów, nazwy modeli tylko w konfiguracji deploymentu.
- Wszystkie generatywne wywołania aplikacji korzystają z OpenAI; brak fallbacku do DeepSeek.
- `store=false`; bez hosted tools, Conversations, backfillu lub realnych dokumentów w smoke.
- PostgreSQL i obecne ToolExecution są źródłem prawdy; mutacje wymagają potwierdzenia.
- Osobne ustawienia vision i jawna polityka/epoka pozostają obowiązkowe.
- Zachować strict vision/Decimal, limity transportu, no retries SDK i safe error codes.
- Nie zmieniać oryginałów, ledger, płatności, schematu DB ani zastanych dirty docs Velo/Q7.
- Testy wyłącznie finanse_test127.0.0.1:55432; nigdy produkcja/preview. Jeden DB suite naraz.
- Sekrety tylko prywatne env; żadnych kluczy w wynikach, commitach lub argumentach procesów.

## Review Focus

1. Historyczne tool calls po zmianie API — replay call_id i wyników bez ponownej egzekucji.
2. Reasoning/incomplete/refusal lub puste output — bez egzekucji/publikacji niepełnego wyniku.
3. Stara konfiguracja DeepSeek plus nowy klucz — odmowa przed egress, bez wycieku.
4. Narzędzie mutujące — ten sam pending_confirmation/audit, zero wywołań executora.
5. Wire contract i SDK — prawdziwy MockTransport, POST /v1/responses, nie tylko mock metody.

### Task 1: Klient Responses i wszystkie adaptery AI

**Files:**
- Create `backend/app/openai_client.py`, `backend/tests/test_openai_client.py`.
- Modify `backend/app/config.py`, `backend/requirements.txt`, `.env.example`.
- Modify `backend/app/advisor/service.py`, `backend/app/advisor/tools/registry.py`.
- Modify `backend/app/documents/extractor.py`, `backend/app/documents/vision_client.py`.
- Test/update `backend/tests/test_advisor/`, `backend/tests/test_documents/test_extractor.py`,
  `test_vision_client.py`, `test_review*.py`, `test_vision_*.py` as affected by wire mocks.

**Interfaces:**
- `create_openai_client(*, api_key: str, base_url: str, timeout: float) -> AsyncOpenAI`
  supplies bounded httpx transport, no redirects/env proxies, max_retries=0.
- `response_text(response: Response) -> str` accepts completed message/output_text only;
  explicit failure on refusal/incomplete/failed/empty or unexpected output.
- Existing domain function signatures and API/DB formats remain unchanged.
- Config: OPENAI_API_KEY (not LLM_API_KEY), LLM_BASE_URL=https://api.openai.com/v1,
  LLM_PROVIDER=openai, LLM_MODEL empty until configured; DOCUMENT_TEXT_MODEL separately
  configured; LLM_MAX_OUTPUT_TOKENS4096, DOCUMENT_TEXT_MAX_OUTPUT_TOKENS2000,
  LLM_REASONING_EFFORT=low, DOCUMENT_TEXT_REASONING_EFFORT=none;
  DOCUMENT_VISION_REASONING_EFFORT=none and existing vision budgets remain.
- New text clients must reject non-OpenAI target before sending OPENAI_API_KEY, including
  stale DeepSeek env; missing key/model returns existing safe domain errors, not fake success.
- Vision config remains explicit and independently keyed, preserving mockable wire adapter;
  production provider/base_url are openai/https://api.openai.com/v1.
- Advisor Responses tools flatten function/name/parameters, explicit strict=false preserves
  existing optional arguments and executor validation. No additional tools are registered.
- Keep legacy persisted chat-shaped tool_calls; convert history to Responses items with
  function_call/function_call_output, matched by call_id. Include encrypted reasoning and
  replay current response output within tool iterations; do not rely on server-side state.
- Client closure guaranteed in finally; no raw model/input/exception details logged.

- [x] **1 RED:** add MockTransport POST contract tests for Sol tool roundtrip, Terra strict
  image and JSON text, store=false, configured models/budgets/reasoning, no obsolete
  temperature/max_tokens/messages/response_format. Existing accepted payloads still validate.
- [x] **2 Observe RED:** targeted tests using guarded gate environment; record actual failures.
- [x] **3 Implement:** pin SDK2.54.0, implement named interfaces and migrate all three adapters.
  Vision response parsing retains invalid_model_output/provider error mapping/transport bounds.
  Advisor reasoning/tool handling must not execute any calls on non-completed/refused output.
- [x] **4 GREEN:** migrated regressions for history/read-tool errors/unknown/malformed arguments,
  pending confirmation and bad output/terminal errors, no changed business expectations.
  Test stale DeepSeek key/endpoint rejection and no fallback, response/client closure.
- [x] **5 Full gate/commit:** command equivalents /lint /typecheck /test with isolated env,
  frontend build and E2E; report commands/counts. Commit source/tests/config only after PASS.

### Task 2: Weryfikacja i zatwierdzone wydanie produkcyjne

**Files:** `ops/prepare_release.py` (existing tooling, no source modification expected),
`docs/audits/2026-11-02-openai-production-release.md`, CHANGELOG/TASKS/JOURNAL.

**Interfaces:** consumes reviewed Task1 commit, authentic verified runtime built from that
requirements revision, private env and existing production release9db255b/Compose hardening.

- [x] **1 Verify:** synthetic live Sol text+fake tool result and Terra text+normalized image
  through application adapters. Reject bad credentials/unavailable models before prod apply.
- [x] **2 Prepare:** encrypted fresh backup, restore drill, local migration rehearsal and data
  invariants; package exact Git SHA/frontend dist with truthful runtime revision. Independent
  review of migration diff and operational scope, not a repeat of already accepted vision plan.
- [x] **3 Apply:** only approved backend/worker/frontend and schema c2→7f8→92 after rehearsal;
  no user-data imports. Keep rollback to9db255b; no automatic schema downgrade.
- [x] **4 Enable/verify:** OpenAI config for all clients, vision policy expected_epoch CAS;
  HTTPS/assets/health/auth and read-only runtime configuration checks, old data/original hashes,
  data-service IDs and observation. Real provider smoke uses synthetics only, no stored docs.
- [x] **5 Docs/commit:** record actual SHA/images/backup/rehearsal/gate/smoke/status/limits;
  distinguish deployed code from active vision and do not assert phone certification.
