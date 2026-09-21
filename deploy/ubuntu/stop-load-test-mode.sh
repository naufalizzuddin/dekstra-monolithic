#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE

LOAD_COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  -f compose.production.yaml
  -f compose.loadtest-target.yaml
  -f compose.monitoring.yaml
)

"${LOAD_COMPOSE[@]}" exec -T web \
  python manage.py prepare_load_test --purge-only
"${LOAD_COMPOSE[@]}" stop prometheus node-exporter cadvisor
"${LOAD_COMPOSE[@]}" rm -f prometheus node-exporter cadvisor

bash deploy/ubuntu/deploy.sh
echo "Load-test mode is disabled and normal production settings are active."
