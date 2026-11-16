---
description: Uruchom typecheck (mypy backend + tsc frontend)
---

Sprawdź bieżący worktree z jawnie wskazanym Pythonem. Jeśli brakuje
`ADVISOR_DEV_PYTHON`, poproś o bezwzględną ścieżkę. Bez fallbacku, instalacji lub
automatycznych poprawek. Uruchom cały blok jednym wywołaniem Bash:

```bash
set -euo pipefail
: "${ADVISOR_DEV_PYTHON:?Podaj bezwzględną ścieżkę ADVISOR_DEV_PYTHON}"
case "$ADVISOR_DEV_PYTHON" in /*) ;; *) echo "Python musi mieć bezwzględną ścieżkę" >&2; exit 2 ;; esac
[[ -f "$ADVISOR_DEV_PYTHON" && -x "$ADVISOR_DEV_PYTHON" ]] || exit 2
PYTHON="$ADVISOR_DEV_PYTHON"
ROOT="$(env -i PATH=/usr/bin:/bin HOME="${TMPDIR:-/tmp/opencode}" \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  git rev-parse --show-toplevel)"
"$PYTHON" -I -B "$ROOT/ops/dev_environment.py" --root "$ROOT" --check typecheck
cd "$ROOT/backend"
"$PYTHON" -I -B -m mypy app ci_tools ../ops/dev_environment.py
cd "$ROOT/frontend"
npm run typecheck
```

Zgłoś osobne wyniki. Po błędzie backendu frontend nie był uruchomiony; nie maskuj
błędu jego wynikiem. Poprawki wymagają zgody. `docs/development/testing.md`.
