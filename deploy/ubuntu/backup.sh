#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}."
  exit 1
fi

OVERRIDE_COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
OVERRIDE_BACKUP_DIR="${BACKUP_DIR:-}"
OVERRIDE_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-}"

set -a
source "${ENV_FILE}"
set +a

if [[ -n "${OVERRIDE_COMPOSE_PROJECT_NAME}" ]]; then
  export COMPOSE_PROJECT_NAME="${OVERRIDE_COMPOSE_PROJECT_NAME}"
fi
if [[ -n "${OVERRIDE_BACKUP_DIR}" ]]; then
  BACKUP_DIR="${OVERRIDE_BACKUP_DIR}"
fi
if [[ -n "${OVERRIDE_RETENTION_DAYS}" ]]; then
  BACKUP_RETENTION_DAYS="${OVERRIDE_RETENTION_DAYS}"
fi

BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_DIR}"
WRITE_TEST="${BACKUP_DIR}/.write-test-${STAMP}"
if ! : >"${WRITE_TEST}" 2>/dev/null; then
  echo "Backup directory is not writable: ${BACKUP_DIR}" >&2
  echo "Fix on the VM:" >&2
  echo "  sudo mkdir -p ${BACKUP_DIR}" >&2
  echo "  sudo chown -R \$(id -un):\$(id -gn) ${BACKUP_DIR}" >&2
  exit 1
fi
rm -f "${WRITE_TEST}"

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f compose.production.yaml)

"${COMPOSE[@]}" exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
  >"${BACKUP_DIR}/database-${STAMP}.dump"

"${COMPOSE[@]}" exec -T web \
  tar -czf - -C /app/media . \
  >"${BACKUP_DIR}/media-${STAMP}.tar.gz"

find "${BACKUP_DIR}" -type f -mtime "+${RETENTION_DAYS}" \
  \( -name 'database-*.dump' -o -name 'media-*.tar.gz' \) -delete

echo "Backup created:"
echo "  ${BACKUP_DIR}/database-${STAMP}.dump"
echo "  ${BACKUP_DIR}/media-${STAMP}.tar.gz"
