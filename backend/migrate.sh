#!/bin/sh
# Everything that touches the database before the app serves traffic.
#
# This is its own file rather than lines inside start.sh because it has two
# callers, and they need it at different moments:
#
#   Render    — one long-lived container, replaced on deploy, with no shell and
#               no job runner. Boot is the only hook there is, so start.sh runs
#               this itself (MIGRATE_ON_BOOT defaults to 1).
#   Cloud Run — scales to zero, so "boot" happens on every cold start, and two
#               instances waking together would race the same migration against
#               one database. The deploy workflow runs this as a Cloud Run Job
#               against the new image *before* the revision takes traffic, and
#               the service sets MIGRATE_ON_BOOT=0 so waking stays DB-free.
#
# Order matters: load_changelog reads a table that migrate may have just
# created, and ensure_admin writes a row that both of the above must exist for.
set -e

python manage.py migrate --noinput

# Changelog rows are files in backend/coach/changelog/, not data migrations —
# see the README there for why. Idempotent on (shipped_on, title), so this is
# a no-op on every run after the one that first saw the entry.
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
