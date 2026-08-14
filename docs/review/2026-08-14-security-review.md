# Security review — 14 August 2026

A snapshot, not a maintained document. It reviews `main` at `93f5139`, and like
its three predecessors it is meant to age: as the issues below close, this
becomes a record of what was thought on one day rather than a description of the
product. Nothing here is load-bearing for the claims in
[README.md](../../README.md) — if the two ever disagree, the README is the
product and this is an opinion about it.

It follows [13 August (product)](2026-08-13-product-review.md),
[14 August (tech and flow)](2026-08-14-tech-and-flow-review.md), and
[14 August (UI/UX, from driving)](2026-08-14-ui-ux-drive-review.md). None of
those had a security lens — the tech review says so in its own limits: it "is a
code review, not a load test," and no reviewer had looked at the perimeter, the
auth flow, or the abuse surface as such. This one does only that.

The findings live as GitHub issues **#252–#255**. What is written here is the
part that does not survive being cut into four pieces: why the surface is
mostly sound, which few things aren't, and — the most losable thing in any
review — what was checked and deliberately **not** filed.

## How it was produced, and what that is worth

One reviewer, one lens: an attacker with no account, then an attacker with an
ordinary Google account, then a curious insider — reading the real tree at
`93f5139` and, where a claim could only be settled by running, running it
against the production settings path (`DJANGO_DEBUG=0`, a throwaway SQLite test
DB) rather than guessing.

Three limits worth stating:

- **Every finding that could be demonstrated was demonstrated**, and the two
  headline ones are measurements, not readings. The brute-force finding (#252)
  is a captured run of 80 wrong-password attempts returning zero `429`s; the
  header finding (#253) is `manage.py check --deploy` output. Neither is an
  estimate. Where a finding is a reading of the code rather than a run (the
  OAuth binding, the throttle key), it says so and names what would confirm it.
- **The production database and the live R2 bucket were not touched.** No
  secret was read, no real account was enumerated, nothing was sent to the real
  deployment. Findings about the deployed configuration (the admin cookies, the
  proxy count) are read off `config/settings.py`, `render.yaml`,
  `next.config.ts` and the framework defaults, and each names what it would take
  to confirm against the running service.
- **The LLM prompt-injection surface is out of scope here** and belongs to a
  content review with a real key. Every builder-supplied string that reaches a
  prompt is already length-bounded (`CHAT_MAX_CHARS`, `PROOF_MAX_CHARS`,
  `DECLARATION_MAX_CHARS` in `config/settings.py:385-387`) and fenced, which is
  the structural half; whether the model honours the fence is a judgement about
  what the model *says*, which no static read can make and the three prior
  reviews all deferred for the same reason.

## The headline: this backend is well defended, and that is the finding

It is worth leading with, because it is true and because it changes what the
four issues below mean. The expensive classes of web vulnerability were looked
for specifically and are **not** here:

- **Tenancy / IDOR.** `coach/views.py:1` states the rule — "every queryset
  filters by `request.user`" — and every pk-addressable endpoint keeps it.
  `GoalHistoryView`, `GoalExportView`, `AdvanceView`, `MetricView`,
  `RetireView`, `ProofImageView`, `ShareRecordView`, `JudgeDeclarationView` and
  the cohort views were each read: all fetch through
  `get_object_or_404(Model.objects.filter(user=request.user), pk=pk)` (or the
  `goal__user` / `checkin__goal__user` chain), so a foreign id 404s rather than
  leaking. The docstrings even name the property. No object-level hole was
  found.
- **Mass assignment.** `UserSerializer` (`accounts/serializers.py`) exposes only
  `tone` and `mode`; `id`, `username`, `email` are read-only and
  `is_staff`/`is_superuser` are not fields at all, so `PATCH /api/auth/me/`
  cannot escalate. `GoalUpdateView` holds `phase` and `status` read-only, so a
  title edit cannot walk the gate.
- **SSRF.** The proof-link check (`coach/links.py`) validates the resolved
  address against `is_global` **before** opening a socket, never follows a
  redirect, and never reads a body — the three properties that keep it from
  becoming a read primitive against the cloud metadata endpoint. The one
  residual (DNS rebinding between the validating lookup and the socket's own
  lookup) is **already tracked and decided** in #136, which built the pin,
  measured it, and chose to leave the hole open while the payoff stays one
  status code. Nothing to refile.
- **Erasure.** `accounts/erasure.py` walks the model graph rather than a
  hand-list, so a new related model is cleaned up for free; it scrubs the
  identity (email/username/password), deactivates (which SimpleJWT honours
  immediately, killing live tokens), and hard-deletes the one row that is a live
  capability rather than a record (`PushSubscription`). DPDP-conscious and
  pinned by a test.
- **The new push channel (#244).** Read closely because it is the freshest
  surface. The cron endpoint (`coach/nudges.py:381`) sets
  `authentication_classes = []`, refuses when `NUDGE_TOKEN` is unset (rather
  than collapsing to no-auth), and compares with `hmac.compare_digest`
  (constant-time). The workflow (`.github/workflows/checks.yml`) runs on
  `pull_request` (not `pull_request_target`), passes the token as a header (not
  a URL that would log), holds `permissions: contents: read`, and forks get no
  secrets so the job exits clean. The payload is encrypted to the device keys
  (RFC 8291) before it leaves. Nothing to file.

Against that backdrop the four findings are perimeter and auth-hardening —
defense-in-depth around a sound core, not open doors. That is the honest
severity and the issues say so.

## The findings that lead

**1. The two password-login surfaces have no brute-force limit, and the only
accounts they unlock are the superusers (#252).**

`POST /api/auth/token/` (SimpleJWT) and `/admin/login/` (Django admin, proxied
onto the product domain by `next.config.ts:32`) both accept unlimited wrong
guesses — measured, 80 rapid wrong-password POSTs to `token/` returned `[401]`
and never a `429`. `DEFAULT_THROTTLE_RATES` deliberately declares no default
rate, so the endpoints that cost a *credential* inherit no ceiling. Every real
account is Google-only with an unusable password, so the sole thing these can
unlock is the first-boot superuser (`render.yaml:45`) — whose admin session is
full read/write over every builder's diary. Defense-in-depth (a strong random
operator password is unguessable at any rate), but the crown-jewel credential
has nothing between it and an online guessing run. The clean fix is a scoped
`login` throttle, or removing `token/` outright since it authenticates no real
user.

**2. The admin's session/CSRF cookies aren't Secure, and there's no HSTS or
SSL-redirect in production (#253).**

`manage.py check --deploy` reports W004/W008/W012/W016. The app's *own* JWT
cookies are already `Secure` (hand-set in `accounts/cookies.py`) — this is
specifically the framework-default `sessionid`/`csrftoken` that the **admin**
uses, on a login form proxied onto the primary domain. A staff session is the
same full-DB authority as #252, reachable here by network downgrade rather than
by guessing. The fix is one block inside the existing `if not DEBUG:` guard,
with the standard HSTS caution (start the max-age short).

## The two lower ones

**3. OAuth `state` isn't bound to the browser — login CSRF / session fixation
(#254).** `google_callback` verifies the state's signature and age but nothing
ties it to the browser that started the login (the `nonce` is minted and never
checked; no cookie). An attacker can complete the callback in a victim's
browser with an attacker-obtained `code`, signing the victim into the
*attacker's* account, where everything the victim then writes is
attacker-readable. Bounded impact, standard fix: a short-lived state cookie
compared at the callback.

**4. The public throttle keys on a forgeable `X-Forwarded-For` (#255).** With
`NUM_PROXIES` unset, DRF's `get_ident` keys the anonymous `changelog` /
`shared-record` ceiling on the whole `X-Forwarded-For` string, which a client
can vary per request to rotate buckets and walk around the 300/min brake. Low
severity — cheap read endpoints, a brake not a security control — but the code's
own comment reasons as though the key were the trustworthy proxy-set tail, and
it isn't. Fix: set `NUM_PROXIES` to the real proxy count.

## What was checked and deliberately not filed

The most losable content in any review, because an issue tracker has no way to
record a decision *not* to file something.

- **The JWT-cookie CSRF posture is sound, not a finding.** State-changing
  endpoints authenticate by the `access_token` cookie with no CSRF token, which
  looks alarming until you follow it: the cookie is `SameSite=Lax`, so it is not
  sent on cross-site POST/DELETE/PATCH, and cross-origin credentialed `fetch` is
  blocked by the CORS allow-list (`CORS_ALLOWED_ORIGINS` is a fixed list, not
  `*`). `accounts/authentication.py` documents exactly this. There is no
  state-changing `GET`. The design is deliberate and correct.
- **`DELETE /api/auth/me/` with no confirmation field is not a finding.**
  `views.py:32` explains it: there is no password on these accounts, the session
  cookie is the only thing a typed confirmation could re-prove, and the
  two-press guard and export offer live on the screen. Add CSRF safety from the
  `SameSite`/CORS posture above and this is fine.
- **The SSRF DNS-rebinding residual is #136's, already decided.** Restated here
  so it doesn't age out of view: the mitigations that keep it worth one status
  code (address validation before connect, no redirects, no body read) are all
  present and test-pinned. Do not reopen unless a future change wants to follow
  a redirect or read a body — at which point #136 says the pin comes first.
- **`DEBUG`-gated dev-login is correctly gated.** `DevLoginView` raises `Http404`
  unless `settings.DEBUG`, so it is invisible in production. Verified.
- **No secret-scanning finding.** No key, token, or password is committed in the
  tree; every one (`DJANGO_SECRET_KEY`, `VAPID_PRIVATE_KEY`, `NUDGE_TOKEN`, the
  R2 and OpenAI keys, the superuser password) is `sync: false` in `render.yaml`
  or an Actions secret, and `settings.py` fails the boot in production rather
  than shipping an insecure default. The one nuance worth a sentence: the
  `security.W009` short-secret warning fires only because the deploy check was
  run with a throwaway key — the real production secret is long.

## The index

The four findings live as GitHub issues **#252–#255**, each carrying the
mechanism, the measurement or the reading behind it, and the files it lands in.
All four are `effort:S` — not by design, but because this review found no
large security problems. The core is well built; what is wrong with the
perimeter is cheap.

| # | P | E | Title |
|---|---|---|---|
| [252](https://github.com/mahendra2890/masterji/issues/252) | next | S | No brute-force limit on `/api/auth/token/` or `/admin/login/` — the only accounts they unlock are the superusers |
| [253](https://github.com/mahendra2890/masterji/issues/253) | next | S | Admin session/CSRF cookies aren't Secure and there's no HSTS/SSL-redirect in production |
| [254](https://github.com/mahendra2890/masterji/issues/254) | later | S | OAuth state isn't bound to the browser — login CSRF / session fixation |
| [255](https://github.com/mahendra2890/masterji/issues/255) | later | S | The public changelog/shared-record throttle keys on a client-forgeable `X-Forwarded-For` |
