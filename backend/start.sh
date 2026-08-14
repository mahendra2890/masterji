#!/bin/sh
# Container boot: the database work, unless the host already did it, then serve.
set -e

# migrate.sh holds the DB-touching steps. It runs here on Render, where boot is
# the only hook there is, and as a Cloud Run Job on Cloud Run, where boot
# happens on every cold start — see DEPLOY-cloudrun.md.
#
# The default is 1, and it is deliberately the opposite of munshiji's, whose
# start.sh defaults the same switch off. That service got the switch before it
# was serving anyone. This one is already live on Render *with* migrate on
# boot, so the safe default is the one that leaves a running production service
# alone if the variable never arrives — a blueprint that doesn't sync, a
# dashboard edit that doesn't land. Cloud Run sets it to 0 explicitly, where a
# missing value is a wasted Neon connection rather than an unmigrated database.
if [ "${MIGRATE_ON_BOOT:-1}" = "1" ]; then
  sh migrate.sh
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
