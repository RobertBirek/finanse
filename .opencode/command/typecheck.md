---
description: Uruchom typecheck (mypy backend + tsc frontend)
---

Uruchom typecheck w projekcie Personal Advisor:

1. Backend: `cd /opt/finanse/backend && .venv/bin/mypy app/`
2. Frontend: `cd /opt/finanse/frontend && npm run typecheck`

Jeśli są błędy typów — napraw je (typy są obowiązkowe w tym projekcie)
i uruchom typecheck ponownie, aż przejdzie bez błędów.
