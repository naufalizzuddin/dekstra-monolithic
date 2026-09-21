#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 DATABASE_DUMP MEDIA_ARCHIVE"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

DATABASE_DUMP="$(realpath "$1")"
MEDIA_ARCHIVE="$(realpath "$2")"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}."
  exit 1
fi

OVERRIDE_COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"

set -a
source "${ENV_FILE}"
set +a

if [[ -n "${OVERRIDE_COMPOSE_PROJECT_NAME}" ]]; then
  export COMPOSE_PROJECT_NAME="${OVERRIDE_COMPOSE_PROJECT_NAME}"
fi

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f compose.production.yaml)

echo "This replaces the current database and media files."
read -r -p "Type RESTORE to continue: " CONFIRMATION
if [[ "${CONFIRMATION}" != "RESTORE" ]]; then
  echo "Restore cancelled."
  exit 1
fi

"${COMPOSE[@]}" stop web worker beat

"${COMPOSE[@]}" exec -T db \
  pg_restore --clean --if-exists --no-owner \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  <"${DATABASE_DUMP}"

"${COMPOSE[@]}" run --rm --no-deps -T web \
  sh -c "find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf - -C /app/media" \
  <"${MEDIA_ARCHIVE}"

"${COMPOSE[@]}" up -d web worker beat
"${COMPOSE[@]}" ps
echo "Restore completed."
