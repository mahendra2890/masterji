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
   `anthropic/claude-sonnet-5` + `ANTHROPIC_API_KEY`.
3. Note the API URL: `https://masterji-api-XXXX.onrender.com`. Check
   `/api/health/` and `/admin/`.

Free tier: 512 MB, spins down after 15 idle minutes (~1 min cold start —
see keep-alive below). Streaming chat works on the gthread workers set in
[backend/start.sh](backend/start.sh).

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

## 6. Keep-alive

Render free sleeps after 15 idle minutes. Point UptimeRobot or
cron-job.org at `https://masterji-api-XXXX.onrender.com/api/health/`
every 5 minutes. The health check never touches the DB (protects Neon's
compute budget); the DB is woken opportunistically when a login starts.

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
