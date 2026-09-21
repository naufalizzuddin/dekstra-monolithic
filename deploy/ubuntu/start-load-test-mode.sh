#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE
export WEB_BIND_ADDRESS="${WEB_BIND_ADDRESS:-0.0.0.0}"
LOADTEST_CITIZENS="${LOADTEST_CITIZENS:-60}"
LOADTEST_AUTH_CITIZENS="${LOADTEST_AUTH_CITIZENS:-500}"
LOADTEST_PENDING_PER_STAGE="${LOADTEST_PENDING_PER_STAGE:-5000}"
LOADTEST_REGISTRATIONS="${LOADTEST_REGISTRATIONS:-25000}"
LOADTEST_COMPLETED_DOCUMENTS="${LOADTEST_COMPLETED_DOCUMENTS:-2500}"
SNAPSHOT_PATH="${SNAPSHOT_PATH:-loadtest/generated/loadtest-fixture.dump}"
MANIFEST_PATH="${MANIFEST_PATH:-loadtest/generated/accounts.json}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}."
  exit 1
fi

COMPOSE=(
  docker compose
  --env-file "${ENV_FILE}"
  -f compose.production.yaml
  -f compose.loadtest-target.yaml
  -f compose.monitoring.yaml
)

bash deploy/ubuntu/backup.sh
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" up --build -d --remove-orphans
"${COMPOSE[@]}" exec -T web python manage.py load_letter_templates
"${COMPOSE[@]}" exec -T web python manage.py prepare_load_test \
  --reset \
  --citizens "${LOADTEST_CITIZENS}" \
  --auth-citizens "${LOADTEST_AUTH_CITIZENS}" \
  --pending-per-stage "${LOADTEST_PENDING_PER_STAGE}" \
  --registrations "${LOADTEST_REGISTRATIONS}" \
  --completed-documents "${LOADTEST_COMPLETED_DOCUMENTS}"
mkdir -p loadtest/generated
"${COMPOSE[@]}" cp \
  web:/app/loadtest/generated/accounts.json \
  "${MANIFEST_PATH}"
"${COMPOSE[@]}" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "${SNAPSHOT_PATH}"
"${COMPOSE[@]}" exec -T worker celery -A dekstra inspect ping
"${COMPOSE[@]}" ps

echo "Scenario-based load-test mode is active."
echo "Fixed OTP: ${DJANGO_LOAD_TEST_OTP:-246810}"
echo "Prepared full load-test manifest: ${MANIFEST_PATH}"
echo "Prepared database snapshot: ${SNAPSHOT_PATH}"
echo "Prepared ${LOADTEST_REGISTRATIONS} pending registration candidates."
echo "Prepared $((LOADTEST_PENDING_PER_STAGE * 4)) approval/application candidates."
echo "Prepared ${LOADTEST_COMPLETED_DOCUMENTS} final document tokens."
echo "Prometheus is bound to VM localhost:9090."
echo "Web backend is bound through Docker on ${WEB_BIND_ADDRESS}:${WEB_PORT:-8000}."
