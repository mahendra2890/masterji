# Running the API on Cloud Run, alongside Render

Render stays exactly as it is and stays what the frontend talks to. This adds a
second deployment of the same commits, against the same Neon database, so it
can be exercised by hand before anything is pointed at it. [DEPLOY.md](DEPLOY.md)
remains the live runbook until the switch in §7 is made.

## Why

Render's free instance is 0.1 CPU. That is the whole story: the same image
boots in ~9.7s at 1 vCPU and takes ~2 minutes there, and a deploy is held open
until the health check passes, so deploys land at ~4m. #257 took ~59% off the
boot by shipping bytecode, which helped both numbers and changed neither shape.

Cloud Run bills the seconds it is *processing a request* rather than the hours
it is awake, which also inverts the keep-warm arithmetic — see
[munshiji's DEPLOY.md](../munshiji/DEPLOY.md) §"Why Cloud Run rather than
Render", which worked this out first and whose numbers this reuses.

## What is different from Render

**Migrations do not run on boot.** Cloud Run scales to zero, so boot happens on
every cold start, and two instances waking together would race the same
migration against one database. `backend/migrate.sh` runs as a Cloud Run Job
against the new image before the revision takes traffic, and the service sets
`MIGRATE_ON_BOOT=0`. `start.sh` defaults that to **1**, so Render is unchanged
by omission.

**There is no `RENDER_EXTERNAL_HOSTNAME`.** `settings.py` appends that to
`ALLOWED_HOSTS` when Render sets it; Cloud Run sets nothing equivalent, so
`DJANGO_ALLOWED_HOSTS` has to name both hosts explicitly — see §5.

## 0. Prerequisites

Already done in `portfolio-502209`: the four APIs are enabled, the
`github-actions` WIF pool and `github-actions-deployer` service account exist,
and the `masterji` Artifact Registry repo has been created. The project number
is `697438837887`.

A billing account is required even on the free tier. If a **spend cap** budget
is not already set on this project, set one before adding a third service —
budget *alerts* do not cap spending; spend caps do.

## 1. Secrets

Eight secrets, created by hand because their values must not pass through a
shell history, a CI log, or a chat transcript.

**Read the live service, not `render.yaml`.** The blueprint has R2 and web push
commented out, but the running Render service has both configured — so the
committed file understates what parity requires by seven variables. The
Environment tab is the source of truth.

**Three of these must be Render's existing values rather than new ones**, and
they fail in different ways if they are not:

| Secret | Copied because |
| --- | --- |
| `DJANGO_SECRET_KEY` | `SIMPLE_JWT` has no `SIGNING_KEY`, so it falls back to `SECRET_KEY`, as does the `signing.dumps` protecting the OAuth `state`. A new key invalidates every refresh token, admin session and in-flight login. |
| `VAPID_PRIVATE_KEY` + `VAPID_PUBLIC_KEY` | A browser's push subscription is bound to the `applicationServerKey` it subscribed with, which `nudges.py` serves from `VAPID_PUBLIC_KEY`. A new keypair silently orphans every existing subscription — they stay in the table and stop being deliverable. |
| `NUDGE_TOKEN` | Has to match the GitHub Actions repository secret of the same name, or the hourly tick gets a 401. |

**`masterji-secret-key` must be Render's existing `DJANGO_SECRET_KEY`, copied
out of the Render dashboard — not a fresh one.** `SIMPLE_JWT` sets no
`SIGNING_KEY`, so it falls back to `SECRET_KEY`, and so does the `signing.dumps`
that protects the OAuth `state` parameter. A different key means every refresh
token, every admin session and every in-flight Google login breaks the moment
the frontend is pointed here. `render.yaml` has `generateValue: true`, so the
live value only exists in the dashboard.

Each is one line, reading the value from the Render dashboard →
`masterji-api` → Environment. `--replication-policy=automatic` is explicit
because without it gcloud may prompt, and stdin is already consumed by the pipe
— matching how the munshiji and portfolio secrets are stored.

```bash
printf '%s' '<DJANGO_SECRET_KEY>'    | gcloud secrets create masterji-secret-key            --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<DATABASE_URL>'         | gcloud secrets create masterji-database-url          --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<GOOGLE_CLIENT_SECRET>' | gcloud secrets create masterji-google-client-secret  --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<OPENAI_API_KEY>'       | gcloud secrets create masterji-openai-api-key        --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<R2_ACCESS_KEY_ID>'     | gcloud secrets create masterji-r2-access-key-id      --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<R2_SECRET_ACCESS_KEY>' | gcloud secrets create masterji-r2-secret-access-key  --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<VAPID_PRIVATE_KEY>'    | gcloud secrets create masterji-vapid-private-key     --data-file=- --replication-policy=automatic --project portfolio-502209
printf '%s' '<NUDGE_TOKEN>'          | gcloud secrets create masterji-nudge-token           --data-file=- --replication-policy=automatic --project portfolio-502209
```

Then let Cloud Run's runtime service account read them — **before** creating the
Job or the service, or both fail with `Permission denied on secret`:

```bash
for s in masterji-secret-key masterji-database-url masterji-google-client-secret \
         masterji-openai-api-key masterji-r2-access-key-id masterji-r2-secret-access-key \
         masterji-vapid-private-key masterji-nudge-token; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:697438837887-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" --project portfolio-502209
done
```

`697438837887-compute@developer.gserviceaccount.com` is confirmed as the
service account `munshiji-api` actually runs as, not the documented default.

`DJANGO_SUPERUSER_*` is deliberately absent: the admin user already exists in
the shared database, so there is nothing to bootstrap.

## 2. Let GitHub Actions deploy this repo too

The WIF provider's attribute condition currently names only
`mahendra2890/munshiji`. Widen it and bind the deployer for this repo:

```bash
gcloud iam workload-identity-pools providers update-oidc github \
  --location=global --workload-identity-pool=github-actions --project=portfolio-502209 \
  --attribute-condition="assertion.repository=='mahendra2890/munshiji' || assertion.repository=='mahendra2890/masterji'"

gcloud iam service-accounts add-iam-policy-binding \
  github-actions-deployer@portfolio-502209.iam.gserviceaccount.com \
  --project=portfolio-502209 --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/697438837887/locations/global/workloadIdentityPools/github-actions/attribute.repository/mahendra2890/masterji"
```

Explicit `||` rather than `assertion.repository_owner=='mahendra2890'`, so
adding a repo stays a deliberate act. The condition is the only thing standing
between this pool and any repository on GitHub — after changing it, confirm
munshiji still deploys.

## 3. The first image

The workflow builds every later one. For the first, from a checkout of the
commit you want:

```bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev --quiet
docker buildx build --platform linux/amd64 \
  -t asia-southeast1-docker.pkg.dev/portfolio-502209/masterji/api:$(git rev-parse HEAD) \
  --push backend
```

`--platform linux/amd64` is not optional on an Apple Silicon machine. A native
arm64 image pushes and deploys without complaint and then fails to start.

## 4. The migrate Job

```bash
gcloud run jobs create masterji-migrate \
  --image asia-southeast1-docker.pkg.dev/portfolio-502209/masterji/api:<sha> \
  --region asia-southeast1 --project portfolio-502209 \
  --set-env-vars DJANGO_DEBUG=0 \
  --set-secrets DATABASE_URL=masterji-database-url:latest,DJANGO_SECRET_KEY=masterji-secret-key:latest \
  --command sh --args migrate.sh
```

Then, after every image push and before the revision takes traffic:

```bash
gcloud run jobs execute masterji-migrate --region asia-southeast1 --wait --project portfolio-502209
```

Against the shared database this is a no-op whenever Render has already applied
the same migrations — which, while Render remains primary, is always.

If a first attempt fails (e.g. the IAM grant had not propagated), Cloud Run
leaves the job resource behind and `create` then fails with `Job already
exists`. Use `update` with the same flags.

## 5. The service

```bash
gcloud run deploy masterji-api \
  --image asia-southeast1-docker.pkg.dev/portfolio-502209/masterji/api:<sha> \
  --region asia-southeast1 --project portfolio-502209 \
  --allow-unauthenticated --min-instances 0 --max-instances 2 \
  --memory 512Mi --cpu 1 \
  --set-env-vars "^@^MIGRATE_ON_BOOT=0@\
DJANGO_DEBUG=0@\
LLM_MODEL=<LLM_MODEL>@\
LLM_JUDGE_MODEL=<LLM_JUDGE_MODEL>@\
GUNICORN_WORKERS=2@\
GOOGLE_CLIENT_ID=<GOOGLE_CLIENT_ID>@\
FRONTEND_URL=https://masterji.mscsoftwares.in@\
DJANGO_ALLOWED_HOSTS=masterji.mscsoftwares.in@\
CSRF_TRUSTED_ORIGINS=https://masterji.mscsoftwares.in@\
R2_ACCOUNT_ID=<R2_ACCOUNT_ID>@\
R2_BUCKET=<R2_BUCKET>@\
VAPID_PUBLIC_KEY=<VAPID_PUBLIC_KEY>@\
VAPID_CONTACT=<VAPID_CONTACT>" \
  --set-secrets "DATABASE_URL=masterji-database-url:latest,\
DJANGO_SECRET_KEY=masterji-secret-key:latest,\
GOOGLE_CLIENT_SECRET=masterji-google-client-secret:latest,\
OPENAI_API_KEY=masterji-openai-api-key:latest,\
R2_ACCESS_KEY_ID=masterji-r2-access-key-id:latest,\
R2_SECRET_ACCESS_KEY=masterji-r2-secret-access-key:latest,\
VAPID_PRIVATE_KEY=masterji-vapid-private-key:latest,\
NUDGE_TOKEN=masterji-nudge-token:latest"
```

`R2_ENDPOINT` is absent on purpose — `settings.py` derives it from
`R2_ACCOUNT_ID`. Without the four R2 values `storage.is_configured()` returns
false and image proof upload is silently unavailable, which would make a
verification pass that never tried to upload a screenshot look clean.

`CORS_ALLOWED_ORIGINS` is also absent, because it is not set on Render either
and the defaults are localhost. The frontend reaches the API through Vercel's
proxy, so the browser sees one origin and CORS never fires. Matching Render
here is the point; setting it would be a difference to explain later.

Then add Cloud Run's own hostname, which you only learn from that output:

```bash
gcloud run services update masterji-api --region asia-southeast1 --project portfolio-502209 \
  --update-env-vars "^@^DJANGO_ALLOWED_HOSTS=masterji.mscsoftwares.in,masterji-api-697438837887.asia-southeast1.run.app@CSRF_TRUSTED_ORIGINS=https://masterji.mscsoftwares.in,https://masterji-api-697438837887.asia-southeast1.run.app"
```

`CSRF_TRUSTED_ORIGINS` needs the `run.app` origin for a reason that has no
equivalent on Render: `settings.py:155` appends the service's own origin to
that list *from `RENDER_EXTERNAL_HOSTNAME`*, which is how admin login works
there without the variable being set at all. Cloud Run injects no such
hostname, so the same origin has to be named by hand — otherwise `/admin/`
renders its login form and then rejects the POST as a CSRF failure, which
reads like a wrong password.

Two hosts for two reasons, and `settings.py:443` is why: `USE_X_FORWARDED_HOST`
is on under `DJANGO_DEBUG=0`, so Django sees whichever Host the Vercel proxy
forwards — the public one — while anything hitting the API directly (curl,
the keep-warm ping, your own verification) arrives as the `run.app` host. The
`^@^` prefix switches gcloud's list delimiter to `@` so the commas inside the
value are not read as separators.

`--min-instances 0` because one always-allocated instance is roughly 2.6M
instance-seconds a month against a 180k vCPU-second allowance. `--max-instances 2`
is a blast-radius limit, not a capacity plan.

## 6. Verifying, while Render is still primary

```bash
curl -s https://masterji-api-697438837887.asia-southeast1.run.app/api/health/
```

For anything past the health check, add the Cloud Run callback to the Google
OAuth client (Console → Credentials → Authorized redirect URIs, trailing slash
matters), because `accounts/oauth.py` builds the redirect from the request host:

```
https://masterji-api-697438837887.asia-southeast1.run.app/api/auth/google/callback/
```

`/admin/` works directly with the existing admin user — same database, and if
§1 was followed the same `SECRET_KEY` — but only once `CSRF_TRUSTED_ORIGINS`
names the `run.app` origin as above. Without it the login form appears and the
POST is rejected.

Worth exercising specifically, because each has its own configuration and a
health check proves none of them: a Google sign-in, one chat turn (`OPENAI_API_KEY`,
`LLM_MODEL`), one proof **with a screenshot** (the four R2 values, and
`LLM_VISION_MODEL` falling back through `LLM_JUDGE_MODEL`), and the record
export. Push is the one thing not worth triggering here — see §7.

**This is production data.** Not a staging copy: a write made against Cloud Run
is a write Render will serve a second later. That is what makes the verification
worth anything, and it is also why "try the destructive path and see" is not
available here.

## 7. The switch, when you are satisfied

In order, and each step is reversible until the last:

1. Point the frontend at Cloud Run — Vercel → masterji → Settings → Environment
   Variables → the API base URL → redeploy. Roll back by putting the old value
   back.
2. **Repoint the `API_URL` GitHub Actions repository secret** to the Cloud Run
   URL, no trailing slash. This is easy to miss because nothing surfaces it:
   the hourly `nudges` job in `checks.yml` POSTs to `$API_URL/api/coach/nudges/run/`,
   so leaving it pointed at Render means the evening nudge keeps being delivered
   by the service you are about to switch off — and when you do, the job starts
   failing an hour later with no obvious connection to the cutover.
3. Watch it. Both services are still running and the database is shared, so
   reverting is one environment variable.
4. Only then turn Render off. Suspending the service rather than deleting it
   keeps `render.yaml` meaningful and the rollback real for as long as you want
   it.

Until step 1, nothing a user touches has changed. Push notifications are worth
leaving until after the switch rather than testing in parallel: both services
hold the same VAPID keypair and read the same subscription table, so whichever
one is knocked can deliver to a real device.

## Keep-warm

Not needed for verification, and worth leaving off until step 1. Afterwards, a
ping every 10 minutes is ~4,380 requests/month at roughly 30ms of CPU — about
131 vCPU-seconds against a 180,000 allowance. The Render 750-hour arithmetic in
[DEPLOY.md](DEPLOY.md) §6 stops applying to this service once it moves, and the
allowance it was competing for goes back to the other service in that workspace.

Note the free tier is per **billing account** across all projects, and this
would be the third Cloud Run service on it.
