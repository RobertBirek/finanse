---
description: Kolekcja backendu offline bez DB oraz testy jednostkowe frontendu
---

Domyślnie wykonaj TYLKO kolekcję backendu offline oraz `vitest run` frontendu.
Nie uruchamiaj pełnego pytest ani fixture DB. Osobna zgoda i dowód własności
nowej syntetycznej bazy są wymagane do pełnych testów backendu.

Jeśli brakuje `ADVISOR_DEV_PYTHON`, poproś o bezwzględną ścieżkę interpretera.
Bez fallbacku, instalacji, interaktywnego sudo lub powtórki z siecią hosta.
Uruchom poniższy blok w całości jednym wywołaniem Bash:

```bash
set -euo pipefail
: "${ADVISOR_DEV_PYTHON:?Podaj bezwzględną ścieżkę ADVISOR_DEV_PYTHON}"
case "$ADVISOR_DEV_PYTHON" in /*) ;; *) echo "Python musi mieć bezwzględną ścieżkę" >&2; exit 2 ;; esac
[[ -f "$ADVISOR_DEV_PYTHON" && -x "$ADVISOR_DEV_PYTHON" ]] || exit 2
PYTHON="$ADVISOR_DEV_PYTHON"
ROOT="$(env -i PATH=/usr/bin:/bin HOME="${TMPDIR:-/tmp/opencode}" \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  git rev-parse --show-toplevel)"
"$PYTHON" -I -B "$ROOT/ops/dev_environment.py" --root "$ROOT" --check test
COMMIT="$(env -i PATH=/usr/bin:/bin HOME="${TMPDIR:-/tmp/opencode}" \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  git -C "$ROOT" rev-parse HEAD)"
umask 077
REPORT="$(mktemp -d "${TMPDIR:-/tmp/opencode}/advisor-checks.XXXXXXXX")"
mkdir "$REPORT/home"
printf 'Backend collection artifacts: %s\n' "$REPORT"
CALLER_UID="$(id -u)"
CALLER_GID="$(id -g)"
sudo -n -- unshare --net \
  setpriv --reuid "$CALLER_UID" --regid "$CALLER_GID" --init-groups --no-new-privs \
  env -i PATH=/usr/bin:/bin HOME="$REPORT/home" \
  LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  ENVIRONMENT=test PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
  SECRET_KEY=synthetic-offline-collection OPENAI_API_KEY= LLM_API_KEY= \
  TEST_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:9/finanse_test \
  DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:9/finanse_test \
  REDIS_URL=redis://127.0.0.1:9/0 \
  "$PYTHON" -I -B -c \
  'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); sys.argv[0]="ci_tools.runner"; runpy.run_module("ci_tools.runner",run_name="__main__")' \
  "$ROOT/backend" collect --output "$REPORT/manifest.json" --commit "$COMMIT" --timeout-seconds 40
cd "$ROOT/frontend"
npm test
```

Raportuj backend jako **kolekcję**, nigdy jako „testy backendu PASS”. Manifest,
`collection/run.log` i `collection/process.json` dotyczą tylko kolekcji. Fixture
i test bodies nie są wykonywane, ale moduły testowe są importowane. Brak sudo,
unshare lub setpriv zatrzymuje blok przed frontendem. Wynik Vitest podaj osobno.
Nie naprawiaj błędów bez zatwierdzenia. Szczegóły: `docs/development/testing.md`.
