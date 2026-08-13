#!/bin/sh
# Container boot: migrate, changelog, optional admin bootstrap, then serve.
set -e

python manage.py migrate --noinput

# Changelog rows are files in backend/coach/changelog/, not data migrations —
# see the README there for why. Idempotent on (shipped_on, title), so this is
# a no-op on every boot after the one that first saw the entry.
#
# `|| true` on the same reasoning as ensure_admin below: a changelog is not
# worth refusing to boot over, and a malformed entry fails CI through
# ChangelogFileTests long before it can get here.
python manage.py load_changelog || true

# DJANGO_SUPERUSER_EMAIL (+ _USERNAME/_PASSWORD) → create or promote the
# admin user. Idempotent; never blocks startup.
if [ -n "$DJANGO_SUPERUSER_EMAIL" ]; then
  python manage.py ensure_admin || true
fi

# gthread: a streaming chat response holds a thread, not a whole worker.
# ONE worker process, sized for Render's free instance (512MB / 0.1 CPU):
# the workload is I/O-bound (LLM calls, Neon, R2), so concurrency comes from
# threads, which share one copy of Django+litellm instead of paying for it
# per process. Two workers put the box close enough to the memory ceiling
# that a busy spell failed the 5-second health probe and Render restarted
# the instance. More CPU later → raise GUNICORN_WORKERS, not threads.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  --worker-class gthread \
  --threads "${GUNICORN_THREADS:-12}" \
  --access-logfile -
