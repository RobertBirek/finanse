# Security Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uwierzytelnić sesje po stronie serwera, ochronić mutacje przed CSRF i nadużyciem oraz wdrożyć odtwarzalny offsite backup przed produkcyjną rotacją sekretów.

**Architecture:** Sesja jest losowym tokenem przechowywanym w cookie, a PostgreSQL zachowuje tylko jego hash i stan unieważnienia. CSRF middleware kontroluje cookie, nagłówek i Origin; limiter Redis działa wyłącznie na wrażliwych trasach. Skrypty operacyjne są wersjonowane w repozytorium, lecz dane dostępowe Restic pozostają wyłącznie w `/docker/finanse/.env`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL 16, Redis 7, React 18, Axios, Restic, pytest, Vitest.

---

### Task 1: Backup i restore drill

**Files:**
- Create: `ops/backup.sh`, `ops/restore-verify.sh`, `docs/operations/backup-restore.md`
- Modify: `/docker/finanse/Makefile`
- Test: `backend/tests/test_ops/test_backup_scripts.py`

- [x] **Step 1: Write failing static tests.** Assert scripts require `RESTIC_REPOSITORY` and `RESTIC_PASSWORD_FILE`, run `pg_dump --format=custom`, save an Alembic revision and commit SHA in `manifest.json`, and use the approved Restic retention flags.
- [x] **Step 2: Run the focused test.**
  Run: `cd backend && .venv/bin/pytest tests/test_ops/test_backup_scripts.py -v`
  Expected: FAIL because files do not exist.
- [x] **Step 3: Implement `ops/backup.sh`.** Use `set -euo pipefail`; require `BACKUP_WORKDIR`, `DATABASE_URL_SYNC`, `UPLOAD_DIR`, `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE`; create a private temporary directory; run `pg_dump --format=custom --file "$workdir/postgres.dump" "$DATABASE_URL_SYNC"`; archive upload files; run `alembic current` in backend; write a JSON manifest with `git rev-parse HEAD`, revision and `sha256sum`; call `restic backup`; call `restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6`; always remove the temporary directory.
- [x] **Step 4: Implement `ops/restore-verify.sh`.** Require `RESTIC_*`, `RESTORE_DATABASE_URL_SYNC` and an empty `RESTORE_DIR`; restore a chosen snapshot into the private workdir; execute `pg_restore --clean --if-exists` only against the explicitly named isolated database; run `alembic upgrade head`; run SQL checks that every transaction has at least two postings and signed posting total zero; verify archived upload checksums against manifest.
- [x] **Step 5: Add Makefile targets.** Add `backup` and `restore-verify` targets that execute only versioned scripts and never interpolate secret values into output.
- [x] **Step 6: Run focused tests and ShellCheck if installed.**
- [x] **Step 7: Commit.** `git commit -m "feat: dodaj backup i weryfikację odtworzenia"`

### Task 2: Fail-fast settings i zamknięcie rejestracji

**Files:**
- Modify: `backend/app/config.py`, `.env.example`, `backend/app/identity/router.py`
- Create: `backend/tests/test_config.py`
- Modify: `backend/tests/test_identity/test_auth.py`

- [ ] **Step 1: Write failing tests.** Production settings with missing, placeholder or shorter-than-32-byte `SECRET_KEY` must raise validation error. Production register must return 404; development register must retain its current flow.
- [ ] **Step 2: Implement typed settings.** Add `SESSION_EXPIRE_MINUTES`, `REGISTRATION_ENABLED`, allowlisted `TRUSTED_ORIGINS`, and limit settings. In a `model_validator`, fail in production for unsafe secret and force `REGISTRATION_ENABLED=False` unless explicitly overridden only for tests.
- [ ] **Step 3: Gate registration.** Return 404 before email lookup when registration is disabled. Preserve development and test registration.
- [ ] **Step 4: Update `.env.example` without real secrets.** Document every required setting and use non-deployable placeholders.
- [ ] **Step 5: Run focused tests, Ruff and mypy.**
- [ ] **Step 6: Commit.** `git commit -m "fix: wymuś bezpieczną konfigurację produkcji"`

### Task 3: Unieważnialne sesje

**Files:**
- Modify: `backend/app/identity/models.py`, `backend/app/identity/service.py`, `backend/app/identity/schemas.py`, `backend/app/identity/router.py`
- Create: `backend/migrations/versions/<revision>_server_side_sessions.py`, `backend/tests/test_identity/test_sessions.py`

- [ ] **Step 1: Write failing integration tests.** Login returns 204 and both cookies, no JSON token. A request with cookie authenticates. Logout causes the exact same cookie to return 401. A second session for the user remains valid. Expired or revoked session returns 401.
- [ ] **Step 2: Implement model and migration.** Add `token_hash` unique index, `csrf_token_hash`, `revoked_at`, `last_seen_at`; backfill existing rows safely and make new fields non-null only after backfill.
- [ ] **Step 3: Implement service helpers.** `create_session`, `get_active_session`, `revoke_session`, `hash_secret`; use `secrets.token_urlsafe(32)`, SHA-256 and constant-time comparison. Never log or persist raw values.
- [ ] **Step 4: Replace JWT auth.** Login and register create sessions; `get_current_user` accepts only `advisor_session`; logout revokes the session. Remove `TokenResponse`, OAuth2 bearer dependency and JWT helpers once tests prove no consumer remains.
- [ ] **Step 5: Run integration tests against isolated PostgreSQL, then migration upgrade/downgrade/upgrade.**
- [ ] **Step 6: Commit.** `git commit -m "feat: dodaj unieważnialne sesje serwerowe"`

### Task 4: CSRF i Origin middleware

**Files:**
- Create: `backend/app/security/__init__.py`, `backend/app/security/csrf.py`, `backend/tests/test_security/test_csrf.py`
- Modify: `backend/app/main.py`, `backend/app/identity/router.py`, `frontend/src/lib/api.ts`

- [ ] **Step 1: Write failing integration tests.** Authenticated `POST`, `PATCH` and `DELETE` without `X-CSRF-Token` return 403. Matching CSRF cookie/header and trusted Origin succeed. Foreign/missing Origin returns 403 in production. Login accepts trusted Origin without session.
- [ ] **Step 2: Implement middleware.** Protect unsafe HTTP methods except preflight. For authenticated mutations look up active session and compare header hash to `csrf_token_hash`; reject missing/mismatched tokens. Validate Origin against `settings.trusted_origins`. Use a generic 403 message.
- [ ] **Step 3: Issue and clear CSRF cookie.** Use `advisor_csrf`, `secure=settings.ENVIRONMENT == "production"`, `samesite="strict"`, same lifetime and path as session.
- [ ] **Step 4: Configure Axios.** Read only `advisor_csrf` and set `X-CSRF-Token` for unsafe requests through a request interceptor; never place session token in JavaScript.
- [ ] **Step 5: Run focused backend/frontend tests.**
- [ ] **Step 6: Commit.** `git commit -m "feat: chroń mutacje tokenem CSRF"`

### Task 5: Redis rate limiting i security audit

**Files:**
- Create: `backend/app/security/rate_limit.py`, `backend/tests/test_security/test_rate_limit.py`
- Modify: `backend/app/identity/router.py`, `backend/app/advisor/router.py`, `backend/app/documents/router.py`, `backend/app/audit/service.py`

- [ ] **Step 1: Write failing tests.** Nth login attempt returns 429 with `Retry-After`; user-scoped Advisor and upload limits are independent; Redis connection failure blocks login, Advisor and upload but not authenticated GET; rate-limit and session events produce redacted audit rows.
- [ ] **Step 2: Implement atomic limiter.** Use a Redis Lua script that increments a hashed key and sets expiry only on first increment. Expose dependencies `limit_login`, `limit_advisor`, `limit_upload`; config supplies limits/windows.
- [ ] **Step 3: Apply dependencies.** Login uses client IP hash plus normalized email hash. Advisor uses user ID. Upload uses user ID plus client IP hash. Return `HTTP_429_TOO_MANY_REQUESTS` and header.
- [ ] **Step 4: Add audit events.** Record `login_success`, `logout`, `session_rejected`, `csrf_rejected`, `rate_limited`; only hashes/identifiers, never raw secrets or email.
- [ ] **Step 5: Run focused tests and full identity/advisor/documents integration tests.**
- [ ] **Step 6: Commit.** `git commit -m "feat: dodaj limity i audyt bezpieczeństwa"`

### Task 6: Frontend session UX

**Files:**
- Modify: `frontend/src/stores/authStore.ts`, `frontend/src/lib/api.ts`, `frontend/src/pages/Login.tsx`, `frontend/src/components/ProtectedRoute.tsx`
- Create: `frontend/src/stores/authStore.test.ts`, `frontend/src/components/ProtectedRoute.test.tsx`
- Modify: `frontend/src/pages/Login.test.tsx`

- [ ] **Step 1: Write failing tests.** `/auth/me` 500 keeps an infrastructure error state instead of redirecting; 401 redirects to `/login?returnTo=<local path>`; a successful login returns to that validated local path; `//host` and external return URLs fall back to `/today`.
- [ ] **Step 2: Implement explicit auth states.** Distinguish `unauthenticated` from `unavailable`; retain current route on 401; display retry state for 5xx/network errors.
- [ ] **Step 3: Update Login and ProtectedRoute.** Safely parse local `returnTo`; preserve a11y labels and current loading behavior.
- [ ] **Step 4: Run frontend tests, lint, typecheck and build.**
- [ ] **Step 5: Commit.** `git commit -m "fix: popraw obsługę wygaśniętej sesji"`

### Task 7: Verification i production release

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`, `docs/operations/backup-restore.md`

- [ ] **Step 1: Run `make test`, `make test-integration`, `make lint`, `make typecheck`, frontend build and migration cycle.**
- [ ] **Step 2: Configure Restic credentials and sync PostgreSQL DSN outside git.** Run a backup and `ops/restore-verify.sh`; stop if either fails.
- [ ] **Step 3: Rotate `SECRET_KEY`, PostgreSQL password and LLM key using the secret store; set `.env` mode to `0600`.** Do not print values.
- [ ] **Step 4: Apply migration and deploy backend, frontend and worker as one release.**
- [ ] **Step 5: Smoke test login, authenticated read, CSRF-protected mutation, logout, rejected post-logout request and health/readiness.**
- [ ] **Step 6: Update docs with exact evidence and commit.** `git commit -m "docs: opisz wdrożenie security baseline"`
