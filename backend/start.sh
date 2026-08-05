#!/bin/sh
# Container boot: migrate, optional admin bootstrap, then serve.
set -e

python manage.py migrate --noinput

# DJANGO_SUPERUSER_EMAIL (+ _USERNAME/_PASSWORD) → create or promote the
# admin user. Idempotent; never blocks startup.
if [ -n "$DJANGO_SUPERUSER_EMAIL" ]; then
  python manage.py ensure_admin || true
fi

# gthread workers: a streaming chat response holds a thread, not a whole
# worker — with sync workers, Render free's 2 workers would cap the service
# at 2 concurrent chats and starve the health check.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --worker-class gthread \
  --threads "${GUNICORN_THREADS:-8}" \
  --access-logfile -
