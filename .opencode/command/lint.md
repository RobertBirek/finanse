---
description: Uruchom lint (ruff backend + eslint frontend)
---

Uruchom lint w projekcie Personal Advisor:

1. Backend: `cd /opt/finanse/backend && .venv/bin/ruff check app/ tests/`
2. Frontend: `cd /opt/finanse/frontend && npm run lint`

Jeśli są naruszenia:
- Drobne, automatyczne poprawki (ruff `--fix`, eslint `--fix`) wykonaj po zgłoszeniu.
- Poważniejsze naruszenia przeanalizuj i zaproponuj sposób naprawy.

Po poprawkach uruchom lint ponownie i potwierdź, że przechodzi bez ostrzeżeń.
