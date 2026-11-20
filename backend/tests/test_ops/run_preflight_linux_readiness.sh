#!/usr/bin/env bash
# Explicit synthetic qualification; never contacts a Docker daemon or database.
set -euo pipefail
umask 077

: "${ADVISOR_DEV_PYTHON:?Set the absolute development Python path}"
: "${FINANSE_TEST_PINNED_COMPOSE:?Set the absolute pinned Compose path}"
for executable in "$ADVISOR_DEV_PYTHON" "$FINANSE_TEST_PINNED_COMPOSE"; do
  [[ "$executable" = /* && -f "$executable" && -x "$executable" ]] || exit 2
done
[[ "$(id -u)" == 0 ]] || { echo 'Linux isolation tests require root' >&2; exit 2; }

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
evidence=$(mktemp -d /tmp/opencode/preflight-linux-readiness.XXXXXXXX)
mkdir "$evidence/home"
printf 'Synthetic readiness evidence directory: %s\n' "$evidence"
unshare --net env -i PATH=/usr/bin:/bin HOME="$evidence/home" \
  ENVIRONMENT=test SECRET_KEY=synthetic-readiness \
  TEST_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:9/finanse_test \
  DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:9/finanse_test \
  REDIS_URL=redis://127.0.0.1:9/0 OPENAI_API_KEY= LLM_API_KEY= \
  FINANSE_TEST_PINNED_COMPOSE="$FINANSE_TEST_PINNED_COMPOSE" \
  "$ADVISOR_DEV_PYTHON" -I -B -m pytest -q \
  --junitxml="$evidence/readiness.xml" tests/test_ops/preflight_linux_readiness.py

"$ADVISOR_DEV_PYTHON" -I -B - "$evidence/readiness.xml" <<'PY'
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

report = Path(sys.argv[1])
suite = ET.parse(report).getroot().find("testsuite")
if suite is None or tuple(suite.get(k) for k in ("tests", "failures", "errors", "skipped")) != (
    "2", "0", "0", "0"
):
    raise SystemExit("Both synthetic readiness checks must pass without skips")
print(f"Synthetic qualification: 2 passed; SHA-256 {hashlib.sha256(report.read_bytes()).hexdigest()}")
PY
