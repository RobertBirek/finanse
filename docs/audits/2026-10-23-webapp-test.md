# Web application test — 2026-10-23

## Tested releases and boundaries

- Production frontend8a7cda5, backend/worker6811809; no deployment/config changes.
- Production: anonymous read-only browser/API smoke; no credentials, login POST,
  uploads, financial writes, AI calls or retries of existing documents.
- Authenticated views: existing Playwright suite with synthetic API, using the exact
  packaged production assets at releases/8a7cda5/frontend-dist rather than dev server.
  This does not certify authenticated production operations or DB/worker integrations.

## Production results

- Python Playwright / system Chrome, 320/375/768/1440px: /login, /today,
  /documents and /finances/transactions return200 and end on login for anonymous users.
- No page JS errors, horizontal document overflow, unexpected external requests or
  attempted API mutations. Local fonts loaded. Native form rejects empty/invalid email
  before any login request; screenshots saved outside Git.
- /api/health200; documents, finance/accounts, work/tasks and advisor/conversations401.
- Axe selected WCAG2A/2AA/2.1AA rules on production login375/1440: zero violations.
  Automated scan is not a complete manual accessibility certification.
- Frontend/backend/worker/Stirling: running, zero restarts, no OOM kill at check time.

## Regression suite

- E2E: 29 passed, 1 intentional desktop skip for mobile-only agenda (56.1s).
- Vitest: 194 passed across24 files (21.64s); ESLint and TypeScript PASS.
- Production JS/CSS and both font hashes match the release assets used by E2E.

E2E covers search/filter/pagination/Back, currency detail dialog and focus restoration,
API errors vs empty states, mobile dialog focus, document filters, explicit AI approval
(synthetic mutation), local styles/focus, long account names/touch targets, compact
calendar, retry of reference data, Today reading order/time sorting/active boundary.

## Limitations and evidence

- No authenticated production session was supplied. Actual user-account read/write,
  production file upload/OCR and actual LLM execution have NOT been exercised.
- No cross-engine Safari/Firefox, physical mobile device or load/capacity test.
- Existing mobile-only agenda scenario is intentionally skipped on desktop.
- Artifacts: /tmp/opencode/webapp-test-8a7cda5 (production-report.json, screenshots,
  test logs and browser results); test helper /tmp/opencode/test-personal-advisor-production.py.
