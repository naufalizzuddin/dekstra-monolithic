#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE
SNAPSHOT_PATH="${SNAPSHOT_PATH:-loadtest/generated/loadtest-fixture.dump}"
MANIFEST_PATH="${MANIFEST_PATH:-loadtest/generated/accounts.json}"

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  -f compose.production.yaml
  -f compose.loadtest-target.yaml
)

if [[ ! -f "${SNAPSHOT_PATH}" ]]; then
  echo "Missing ${SNAPSHOT_PATH}."
  echo "Create the baseline first:"
  echo "  bash deploy/ubuntu/start-load-test-mode.sh"
  exit 1
fi

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "Missing ${MANIFEST_PATH}."
  echo "Create the baseline first:"
  echo "  bash deploy/ubuntu/start-load-test-mode.sh"
  exit 1
fi

"${COMPOSE[@]}" stop web worker beat
"${COMPOSE[@]}" exec -T redis redis-cli FLUSHALL
"${COMPOSE[@]}" exec -T db sh -c \
  'dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
"${COMPOSE[@]}" exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
  < "${SNAPSHOT_PATH}"
"${COMPOSE[@]}" up -d web worker beat

echo "Restored load-test database snapshot from ${SNAPSHOT_PATH}."
echo "Manifest remains available at ${MANIFEST_PATH}."
