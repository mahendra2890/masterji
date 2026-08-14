# Deploying Masterji — Vercel + Render + Neon, free tiers

Target: frontend at **masterji.mscsoftwares.in** (Vercel), API on Render
(Docker), Postgres on Neon. Order matters — each step feeds the next.

This is the live runbook. A second deployment of the same commits also runs on
Cloud Run, against this same database, so it can be exercised before anything
is pointed at it — see [DEPLOY-cloudrun.md](DEPLOY-cloudrun.md). Until the
switch described in its §7 is made, Render is what the frontend talks to and
nothing below has changed.

## 1. Neon (database)

1. neon.tech → new project in **AWS ap-southeast-1 (Singapore)** (same
   region as the Render service). If the free plan won't allow another
   project, create a second *database* inside the existing project instead.
2. Copy the connection string (`postgres://...sslmode=require`).

Free plan: 0.5 GB, compute autosuspends after ~5 idle minutes and resumes
in under a second — `conn_health_checks` in settings.py handles the
dropped connections.

## 2. Render (Django API)

1. render.com → **New → Blueprint** → pick this repo; it reads
   [render.yaml](render.yaml) (service `masterji-api`, Docker, Singapore).
2. Fill the prompted env vars:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon connection string |
   | `CORS_ALLOWED_ORIGINS` | `https://masterji.mscsoftwares.in,https://<app>.vercel.app` |
   | `CSRF_TRUSTED_ORIGINS` | same as above |
   | `FRONTEND_URL` | `https://masterji.mscsoftwares.in` |
   | `DJANGO_ALLOWED_HOSTS` | `masterji.mscsoftwares.in,<app>.vercel.app` (proxied requests arrive with X-Forwarded-Host; the Render host is trusted automatically) |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | from step 5 |
   | `OPENAI_API_KEY` | the coach's brain (litellm reads it) |
   | `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | your `/admin/` login |

   `LLM_MODEL` defaults to `openai/gpt-5.4-mini` in render.yaml — change
   it there (or in the dashboard) to switch provider later, e.g.
   `anthropic/claude-sonnet-5` + `ANTHROPIC_API_KEY`. Two optional vars sit
   above it and are in neither render.yaml nor the table because unset
   changes nothing: `LLM_JUDGE_MODEL` defaults to `LLM_MODEL` and serves the
   calls that decide something recorded on the row, and `LLM_VISION_MODEL`
   defaults to `LLM_JUDGE_MODEL` and must name a vision-capable model. To
   upgrade the verdicts alone, set `LLM_JUDGE_MODEL` to the non-mini sibling
   of whatever `LLM_MODEL` names (`openai/gpt-5.4` against today's default) —
   one variable, and the key you already have.

   `CACHE_URL` is optional in the same way, and it decides how exact the rate
   limits are. Unset, the counters live in each worker's own memory, so the
   ceilings in `DEFAULT_THROTTLE_RATES` hold per worker rather than per user —
   a real limit, but not the number the product says out loud, and a cold start
   resets it. Set it to a Redis connection string (Upstash's free tier is one
   `rediss://…` URL, and nothing else in the stack changes) and the counters
   are shared. The client library is already in the image, so this is a
   dashboard value and a restart, not a deploy.
3. Note the API URL: `https://masterji-api-XXXX.onrender.com`. Check
   `/api/health/` and `/admin/`.

Free tier: 512 MB, spins down after 15 idle minutes (see keep-alive
below). The first request after that pays for a container start plus
`migrate` on 0.1 CPU — about two minutes — and Render's edge fills the
silence with its own boot-log reel, which reads like a broken site.
Both doors onto a sleeping API answer with
[one note](components/WakingNote.tsx) that says how long the wait is and
goes through by itself once the API answers: `/admin/` through
[proxy.ts](proxy.ts), the app itself through
[AuthGate](components/AuthGate.tsx), which would otherwise render a blank
screen until `/api/auth/me/` came back. Add `?boot=logs` to any admin URL
to skip the note and watch Render's page instead. Streaming chat works on
the gthread workers set in [backend/start.sh](backend/start.sh).

## 3. Vercel (frontend)

1. vercel.com → **Add New → Project** → import this repo (root directory =
   repo root, framework auto-detects Next.js).
2. One env var: `API_URL=https://masterji-api-XXXX.onrender.com`.
   Do **not** set `NEXT_PUBLIC_API_URL` — browser calls must stay
   same-origin (`/api/*` proxy) so the httpOnly auth cookies are
   first-party.
3. Deploy, then fix up the Render CORS/CSRF vars with the real
   `<app>.vercel.app` host if you used placeholders.

## 4. Domain (Namecheap → Vercel)

1. Vercel project → Settings → Domains → add `masterji.mscsoftwares.in`.
2. Namecheap → mscsoftwares.in → **Advanced DNS** → add record:
   **CNAME | host `masterji` | value `cname.vercel-dns.com` | TTL Automatic**.
   (The portfolio's apex A record is untouched.)
3. Wait for Vercel to show **Valid Configuration**; SSL is automatic.

## 5. Google OAuth

Google Cloud Console → APIs & Services → Credentials → create (or reuse)
an OAuth 2.0 Client ID, **Authorized redirect URIs** (trailing slashes
matter):

- `https://masterji.mscsoftwares.in/api/auth/google/callback/`
- `https://masterji-api-XXXX.onrender.com/api/auth/google/callback/`
- `http://localhost:3000/api/auth/google/callback/` (local dev, optional —
  the dev sign-in button works without Google entirely)

First-time users are created automatically on first Google login — there
is no signup form.

## 6. Keep-alive — don't, unless this is your only free service

Render free sleeps after 15 idle minutes. Waking costs more here than
Render's own "about one minute": §2 measures about two, because the first
request pays `migrate` on 0.1 CPU as well as the container start. The
obvious fix is a 5-minute pinger on `/api/health/`, and that is a trap once
you have more than one free service:

> "Render grants 750 Free instance hours to each workspace **per calendar
> month**" … "If you consume all of your Free instance hours during a given
> month, Render suspends **all** of your Free web services until the start
> of the next month."
> — [render.com/docs/free](https://render.com/docs/free)

A 31-day month is 744 hours, so **one** always-pinged service consumes the
entire workspace allowance. A second one exhausts it around day 15 and takes
every other free service down with it until the 1st. Sleeping services cost
nothing, so on-demand wake-ups for several apps are far cheaper than keeping
one warm.

The recommendation: **run no pinger.** Take the cold start and let the note
§2 describes stand in front of it — that note exists precisely so the wait
reads as a wait rather than as a broken site.
Add one only if this is the single free web service in the workspace, or
window it to the hours you actually demo (cron-job.org supports schedules;
UptimeRobot's free tier doesn't).

Whatever you do, keep the ping off the database. `/api/health/` never
touches the DB on purpose — Neon gets 100 CU-hours per project per month and
resumes from autosuspend in about a second, so it's woken opportunistically
when a login starts instead.

## 7. Verify

1. `https://masterji-api-XXXX.onrender.com/api/health/` → `{"status": "ok"}`
2. `https://masterji.mscsoftwares.in/demo/` renders
3. Sign in with Google → onboarding → create a goal
4. Chat replies stream; "Request phase advance" with no proofs → refusal
5. Declare + prove → proof reaction arrives; streak ticks
6. All of the above on a phone

## 8. Web push — the evening nudge (optional, and off until you do this)

Nothing below is set by default, and that is the whole design: with the three
VAPID variables unset the feature is **off end to end** — the subscribe
endpoint answers 503, the app draws no switch, and the hourly job exits
cleanly. There is no half-wired state where a builder is asked for
notification permission the server can never use, which matters because a
browser gives you that prompt exactly once.

### 8.1 Generate the VAPID keypair

VAPID (RFC 8292) is how Google's and Mozilla's push services know who is
sending. The private key is the entire authority to push to every subscription
this app holds — treat it like `DJANGO_SECRET_KEY`. **Never commit either
half.** Run this locally; it prints two single-line strings and writes nothing
to disk:

```
cd backend && uv run python -c "import base64;from cryptography.hazmat.primitives.asymmetric import ec;from cryptography.hazmat.primitives import serialization as s;k=ec.generate_private_key(ec.SECP256R1());b=lambda x:base64.urlsafe_b64encode(x).rstrip(b'=').decode();print('VAPID_PRIVATE_KEY='+b(k.private_numbers().private_value.to_bytes(32,'big')));print('VAPID_PUBLIC_KEY='+b(k.public_key().public_bytes(s.Encoding.X962,s.PublicFormat.UncompressedPoint)))"
```

The private key comes out 43 characters and the public one 87. Both are
base64url with the padding stripped, which is the form the browser wants for
`applicationServerKey` and the form `pywebpush` parses for the signature.

There is also `uv run vapid --gen`, which is the tool most write-ups reach for
— **do not use it here.** It writes `private_key.pem` / `public_key.pem` into
the working directory, and pywebpush will not accept the PEM's contents as an
environment variable (it base64-decodes the string it is handed, and chokes on
the `-----BEGIN` header). A key file is also the wrong shape for Render, where
secrets are dashboard values. If you have already run it, delete both `.pem`
files — `backend/` is not in `.gitignore` for them.

Rotating the keypair invalidates every subscription in the database. Builders
are re-subscribed silently the next time they open the app, so the cost is one
missed evening, not a support thread — but there is no reason to rotate
without one.

### 8.2 Set them on Render (§2's env vars, plus these)

| Variable | Value |
| --- | --- |
| `VAPID_PUBLIC_KEY` | the 87-character string printed above |
| `VAPID_PRIVATE_KEY` | the 43-character string printed above |
| `VAPID_CONTACT` | `mailto:you@example.com` — required by the spec, and read by actual humans at Mozilla if this sender misbehaves. Use an address you answer. |
| `NUDGE_TOKEN` | a long random string, e.g. `openssl rand -hex 32`. This is the only thing standing between the open internet and "nudge everybody now". |

`NUDGE_TIMEOUT_S` (default 10) bounds one delivery and needs no setting.

**`NUDGE_TOKEN` unset does not mean "no auth required".** The endpoint refuses
with 503 while it is empty — see `NudgeRunView` — so a half-finished setup is
a closed door rather than an open one.

### 8.3 Set the two GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value |
| --- | --- |
| `API_URL` | `https://masterji-api-XXXX.onrender.com` (no trailing slash) |
| `NUDGE_TOKEN` | the same string you put on Render |

The `nudges` job in [checks.yml](.github/workflows/checks.yml) exits cleanly
when either is missing, so a fork's scheduled runs are quiet rather than red.

### 8.4 What actually fires it

An **hourly** `schedule:` trigger on the existing workflow — `17 * * * *` —
and the job it runs does nothing but `POST /api/coach/nudges/run/`. Every
decision about who gets a nudge is server-side in
[backend/coach/nudges.py](backend/coach/nudges.py).

Hourly, with the server selecting who is due, rather than a job set for the
hour a nudge should arrive: free-tier scheduled runs are best-effort and slip
by **minutes to hours**, so a job set for 21:00 delivers at a random time.
This was decided in #142 and the reasoning is worth not re-litigating.

Two GitHub behaviours to know:

- Scheduled workflows only ever run from the **default branch**. A change to
  the `schedule:` block does nothing until it is on `main`.
- GitHub **disables scheduled workflows in a repository with no pushes for 60
  days**, and emails the owner. If nudges stop arriving on a quiet month, that
  is the first thing to check — Actions → the workflow → *Enable*.

### 8.5 Verify it

There is no way to make a scheduled run happen sooner, so the workflow also
takes `workflow_dispatch`. Actions → **checks** → *Run workflow*. It runs the
`nudges` job alone (the check jobs skip themselves on that event) and prints
the tick's own answer:

```
{"due": 1, "builders": 1, "sent": 1}
```

`due: 0` is the normal answer for most hours and means the selection ran and
found nobody — not a failure. To make yourself due: declare a task, do not
file a proof, and run it after 17:00 **your local time** (the zone is captured
from your browser when you subscribe, which is why the server can know that).

Or call it directly:

```
curl -i -X POST https://masterji-api-XXXX.onrender.com/api/coach/nudges/run/ -H "X-Nudge-Token: $NUDGE_TOKEN"
```

A 401 means the token does not match; a 503 means `NUDGE_TOKEN` is unset on
Render.

On the app itself: the switch is the last line of the Today card. Chrome and
Firefox on Android and desktop just work. **iOS needs the app installed to the
home screen first** — Safari exposes `PushManager` only to an installed PWA,
which is why phase one's manifest is a dependency of this rather than a
neighbour of it. The switch says so on iOS instead of drawing a control that
cannot work.

## Optional: OpenTelemetry

Set `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_API_KEY` on Render
to stream traces (Django/psycopg/requests auto-instrumented, plus a
`coach.turn` span per interaction). Unset = tracing off.
