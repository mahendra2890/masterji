# Deploying Masterji — Vercel + Render + Neon, free tiers

Target: frontend at **masterji.mscsoftwares.in** (Vercel), API on Render
(Docker), Postgres on Neon. Order matters — each step feeds the next.

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

Render free sleeps after 15 idle minutes and takes ~1 minute to wake. The
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

The recommendation: **run no pinger.** Accept the ~1 minute first-hit wait.
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

## Optional: OpenTelemetry

Set `OTEL_EXPORTER_OTLP_ENDPOINT` + `OTEL_EXPORTER_OTLP_API_KEY` on Render
to stream traces (Django/psycopg/requests auto-instrumented, plus a
`coach.turn` span per interaction). Unset = tracing off.
