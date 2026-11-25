#!/usr/bin/env bash
set -euo pipefail
revision=$(git rev-parse HEAD)
[[ "$revision" == "${GITHUB_SHA:-$revision}" ]]
[[ -z "$(git status --porcelain)" ]]
export RELEASE_BACKEND="local/finanse-backend:$revision"
export RELEASE_WORKER="local/finanse-worker:$revision"
export RELEASE_FRONTEND="local/finanse-frontend:$revision"
docker build --label "org.opencontainers.image.revision=$revision" -t "$RELEASE_BACKEND" backend
docker tag "$RELEASE_BACKEND" "$RELEASE_WORKER"
docker build --label "org.opencontainers.image.revision=$revision" -t "$RELEASE_FRONTEND" frontend
stack=(docker compose -p "finanse-ci-${GITHUB_RUN_ID:-local}" -f ops/one-command/acceptance.compose.yaml)
trap '"${stack[@]}" down --volumes' EXIT
"${stack[@]}" up --wait --wait-timeout 75 postgres redis
"${stack[@]}" run --rm --no-deps --user 0:0 backend chown 10001:10001 /app/uploads
"${stack[@]}" run --rm --no-deps backend alembic upgrade head
"${stack[@]}" up -d --no-build backend worker frontend
curl -fsS --retry 30 --retry-all-errors --retry-delay 1 --max-time 4 http://127.0.0.1:5178/api/health
(cd frontend && npx --no-install playwright test --config release-e2e/playwright.config.ts)
for attempt in {1..45}; do
  if [[ "$("${stack[@]}" exec -T redis redis-cli EXISTS arq:queue:health-check)" == 1 ]]; then break; fi
  sleep 1
done
[[ "$("${stack[@]}" exec -T redis redis-cli EXISTS arq:queue:health-check)" == 1 ]]
[[ "$("${stack[@]}" ps --status running --services worker)" == worker ]]
schema=$("${stack[@]}" exec -T postgres psql -U synthetic -d synthetic -XAt -c 'SELECT version_num FROM alembic_version')
out=${RUNNER_TEMP:-/tmp}/finanse-release-${revision}
mkdir "$out"
docker save "$RELEASE_BACKEND" "$RELEASE_WORKER" "$RELEASE_FRONTEND" | gzip -1 > "$out/images.tar.gz"
python3 ops/one-command/manifest.py "$revision" "$schema" "$out" "$RELEASE_BACKEND" "$RELEASE_WORKER" "$RELEASE_FRONTEND"
