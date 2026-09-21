#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ENV_FILE:-.env.production}"
export ENV_FILE

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.production.example and edit it first."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Run deploy/ubuntu/install-docker.sh first."
  exit 1
fi

docker compose version >/dev/null

env_value() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- | tr -d '\r'
}

require_real_value() {
  local key="$1"
  local value
  value="$(env_value "${key}")"
  if [[ -z "${value}" ]]; then
    echo "${key} must be set in ${ENV_FILE}."
    exit 1
  fi
  if [[ "${value}" == *replace* || "${value}" == *change-me* || "${value}" == *changeme* ]]; then
    echo "${key} still uses a placeholder in ${ENV_FILE}."
    exit 1
  fi
}

require_no_placeholder() {
  local key="$1"
  local value
  value="$(env_value "${key}")"
  if [[ "${value}" == *SERVER_IP* || "${value}" == *api.example.com* || "${value}" == *example.com* ]]; then
    echo "${key} still uses a placeholder host/domain in ${ENV_FILE}."
    exit 1
  fi
}

if [[ "${SKIP_ENV_PLACEHOLDER_CHECK:-0}" != "1" ]]; then
  require_real_value DJANGO_SECRET_KEY
  require_real_value POSTGRES_PASSWORD
  require_no_placeholder DJANGO_ALLOWED_HOSTS
  require_no_placeholder DJANGO_CSRF_TRUSTED_ORIGINS

  if [[ "$(env_value POSTGRES_PASSWORD)" == "dekstra" ]]; then
    echo "POSTGRES_PASSWORD must not use the development default."
    exit 1
  fi
  DJANGO_SECRET_KEY_VALUE="$(env_value DJANGO_SECRET_KEY)"
  if [[ "${#DJANGO_SECRET_KEY_VALUE}" -lt 32 ]]; then
    echo "DJANGO_SECRET_KEY must be at least 32 characters."
    exit 1
  fi
fi

if ! grep -Eq '^DJANGO_DEBUG=(false|0)$' "${ENV_FILE}"; then
  echo "DJANGO_DEBUG must be false in ${ENV_FILE}."
  exit 1
fi

COMPOSE=(docker compose --env-file "${ENV_FILE}" -f compose.production.yaml)

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build --pull
"${COMPOSE[@]}" up -d --remove-orphans

echo "Waiting for the application health check..."
for _ in $(seq 1 40); do
  STATUS="$("${COMPOSE[@]}" ps --format json web 2>/dev/null || true)"
  if grep -q '"Health":"healthy"' <<<"${STATUS}"; then
    break
  fi
  sleep 3
done

WEB_BIND="$("${COMPOSE[@]}" port web 8000)"
WEB_HEALTH_HOST="${WEB_BIND%:*}"
WEB_HEALTH_PORT="${WEB_BIND##*:}"
if [[ "${WEB_HEALTH_HOST}" == "0.0.0.0" || "${WEB_HEALTH_HOST}" == "::" || "${WEB_HEALTH_HOST}" == "[::]" ]]; then
  WEB_HEALTH_HOST="127.0.0.1"
fi
WEB_HEALTH_URL="http://${WEB_HEALTH_HOST}:${WEB_HEALTH_PORT}/health/"
if ! curl --fail --silent --show-error "${WEB_HEALTH_URL}" >/dev/null; then
  "${COMPOSE[@]}" ps
  "${COMPOSE[@]}" logs --tail=100 web worker beat db redis
  echo "Backend health check failed at ${WEB_HEALTH_URL}."
  exit 1
fi
"${COMPOSE[@]}" exec -T web python manage.py migrate --check
"${COMPOSE[@]}" exec -T web python manage.py check --deploy
"${COMPOSE[@]}" exec -T worker celery -A dekstra inspect ping
"${COMPOSE[@]}" ps

echo "Deployment completed."
