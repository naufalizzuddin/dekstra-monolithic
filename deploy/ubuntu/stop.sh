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

docker compose --env-file "${ENV_FILE}" \
  -f compose.production.yaml \
  down --remove-orphans

echo "Monolith stopped. Database, Redis, media, and static volumes were preserved."
