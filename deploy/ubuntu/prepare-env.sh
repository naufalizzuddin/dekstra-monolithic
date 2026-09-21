#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 SERVER_IP_OR_DOMAIN [WEB_PORT]"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

HOST="$1"
WEB_PORT="${2:-8000}"

if [[ ! "${WEB_PORT}" =~ ^[0-9]+$ || "${WEB_PORT}" -lt 1 || "${WEB_PORT}" -gt 65535 ]]; then
  echo "WEB_PORT must be a number between 1 and 65535."
  exit 1
fi

if [[ -f .env.production ]]; then
  echo ".env.production already exists. Move or remove it before regenerating."
  exit 1
fi

if [[ "${WEB_PORT}" == "80" ]]; then
  ORIGIN="http://${HOST}"
else
  ORIGIN="http://${HOST}:${WEB_PORT}"
fi

SECRET_KEY="$(openssl rand -base64 48 | tr -d '\n')"
DATABASE_PASSWORD="$(openssl rand -hex 32)"

cat >.env.production <<EOF
COMPOSE_PROJECT_NAME=dekstra-monolith

WEB_BIND_ADDRESS=127.0.0.1
WEB_PORT=${WEB_PORT}

DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=${HOST},127.0.0.1,localhost,host.docker.internal,web
DJANGO_OTP_EXPOSE_IN_RESPONSE=true
DJANGO_CSRF_TRUSTED_ORIGINS=${ORIGIN}
DJANGO_USE_X_FORWARDED_HOST=false
DJANGO_SECURE_SSL_REDIRECT=false
DJANGO_SESSION_COOKIE_SECURE=false
DJANGO_CSRF_COOKIE_SECURE=false
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false

POSTGRES_DB=dekstra_db
POSTGRES_USER=dekstra
POSTGRES_PASSWORD=${DATABASE_PASSWORD}

GUNICORN_WORKERS=8
GUNICORN_TIMEOUT=120
CELERY_WORKER_CONCURRENCY=2

EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

BACKUP_RETENTION_DAYS=14
EOF

chmod 600 .env.production
echo "Created ${ROOT_DIR}/.env.production"
echo "Review the email settings before deployment."
