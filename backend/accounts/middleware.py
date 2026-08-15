"""A ceiling on password guessing at Django's own admin login.

The two surfaces in this deployment that take a password are
`POST /api/auth/token/` and `/admin/login/`, and neither one can unlock a
builder's account: every account here is Google-only and carries
`set_unusable_password()`. What they can unlock is the operator's superuser,
whose admin session is read/write over every builder's record — so these are
the endpoints where an unlimited guessing run costs the most and buys the
attacker the most.

The token endpoint is a DRF view and gets a scoped throttle like every other
ceiling in this codebase (`accounts.views.ThrottledTokenObtainPairView`).
`/admin/login/` is not a DRF view at all — DRF's throttling never runs for it,
so a scope would be silently ignored — which is why this exists as middleware
instead. Django ships nothing for it and the usual answer is a dependency
(django-axes) or an edge rule; this is neither, because the whole mechanism
is a counter with a window on it and a dependency would be a larger promise
than the thing being promised.

Two differences from the DRF ceiling, both deliberate:

- **Only failures count.** A throttle in front of a paid endpoint is rationing
  a budget, so every request spends from it. This is guarding a credential, so
  the thing worth counting is a wrong guess. A staff member who signs in
  correctly clears their own counter on the way past.
- **The window is fixed, not sliding.** `cache.add` starts it and is a no-op
  afterwards, so continued hammering cannot extend a lockout beyond the window
  its first failure opened.

Counted in the default cache, so this is shared exactly as far as CACHES is —
with CACHE_URL set it is one counter for the deployment, and without it one per
process, which is a weaker ceiling and still a ceiling. Same caveat, in the
same words, as the throttle rates in settings.

Two other middlewares live here because they are about the same request
metadata this one keys on: `ForwardedHeaderLogMiddleware` is the instrument for
`NUM_PROXIES`, and `EdgeSecretMiddleware` is what makes that number knowable at
all. Each says why in its own docstring.
"""

import hmac

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import NoReverseMatch, reverse
from loguru import logger
from rest_framework.throttling import BaseThrottle

from .throttling import trusted_ident

KEY_PREFIX = "admin-login-failures"

REFUSAL = "Too many sign-in attempts. Try again later.\n"

EDGE_HEADER = "X-Masterji-Edge"

EDGE_REFUSAL = "No.\n"


class AdminLoginThrottleMiddleware:
    """Refuse `POST /admin/login/` from an address that has just guessed wrong
    `ADMIN_LOGIN_MAX_FAILURES` times inside `ADMIN_LOGIN_FAILURE_WINDOW_S`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or request.path != _login_path():
            return self.get_response(request)

        # `throttling.trusted_ident`, not DRF's own: this is the ceiling in
        # front of the one password that opens every builder's record, and
        # keying it on a header the caller can write is the finding in #334.
        # It moves with the scoped throttles rather than being left behind —
        # this middleware is the reason "which caller is this" is a shared
        # function instead of a throttle subclass.
        key = f"{KEY_PREFIX}:{trusted_ident(request)}"
        window = settings.ADMIN_LOGIN_FAILURE_WINDOW_S

        if (cache.get(key) or 0) >= settings.ADMIN_LOGIN_MAX_FAILURES:
            # Retry-After is the whole window rather than what is left of it:
            # the cache backends here do not portably report a key's remaining
            # TTL, and over-stating the wait is the safe direction to be wrong.
            return HttpResponse(REFUSAL, status=429, headers={"Retry-After": window})

        response = self.get_response(request)

        # Django's admin re-renders the login form on a bad password (200) and
        # redirects on a good one (302). Anything that is not a redirect is a
        # guess that did not work.
        if response.status_code == 302:
            cache.delete(key)
        else:
            cache.add(key, 0, window)
            try:
                cache.incr(key)
            except ValueError:
                # The key expired between the add and the incr — start again.
                cache.set(key, 1, window)
        return response


class ForwardedHeaderLogMiddleware:
    """The instrument for `NUM_PROXIES`, off unless somebody switches it on.

    `config/settings.py` declines to guess how many proxies append to
    `X-Forwarded-For` in front of this process, because guessing wrong in
    either direction breaks a ceiling — too high and a client forges the
    trusted position back, too low and every visitor behind the proxy shares
    one bucket. The only thing that settles it is the raw header from a real
    request, and there was no way to see one from inside the repository.

    So: set `LOG_FORWARDED_HEADERS=1`, load one page through the public
    domain, read the line, count the addresses the proxies appended, set
    `DRF_NUM_PROXIES`, and set this back to 0.

    It logs the whole header rather than a count, because the count is the
    thing in question. That means client addresses in a log line, which is why
    this is off by default and why the instruction above ends with turning it
    off again — it is a measurement, not telemetry.

    WHAT IT LOGS NOW, and why it grew. The count turned out not to be the
    answer: on 15 August 2026 the reading above settled `NUM_PROXIES=2`, and a
    second reading with a header sent DELIBERATELY showed that same position
    holds whatever the caller wrote, because Vercel forwards a client-supplied
    `X-Forwarded-For` rather than appending to it (#334). No position in that
    header is guaranteed, so the question changed from "how many hops" to
    "which header, if any, does our edge control".

    So this now prints every candidate the answer could be hiding in. The test
    each one has to pass is the one the first reading was too gentle to apply:
    send it yourself and see whether your value arrives. A header that comes
    back carrying what you wrote is forgeable and cannot key a ceiling; one
    that comes back carrying your real address was replaced by something
    upstream of the client, which is the property being looked for.
    """

    # Everything Vercel or Google might be putting a client address in. Logged
    # by name rather than by dumping all headers: the point is a short line a
    # human compares against what they just sent, and a full dump would bury it
    # while spilling cookies into the log.
    CANDIDATES = (
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_VERCEL_FORWARDED_FOR",
        "HTTP_X_REAL_IP",
        "HTTP_X_VERCEL_PROXIED_FOR",
        "HTTP_X_CLIENT_IP",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.LOG_FORWARDED_HEADERS:
            seen = {
                name.removeprefix("HTTP_").replace("_", "-").lower(): request.META[name]
                for name in self.CANDIDATES
                if name in request.META
            }
            # Both idents: DRF's, which is what the ceilings used to key on,
            # and ours. They differ exactly when the caller wrote part of
            # DRF's answer, so printing the pair is what makes a forgery
            # visible in one line rather than by comparing two runs.
            logger.info(
                "forwarded-headers path={} candidates={!r} remote_addr={!r} "
                "drf_ident={!r} trusted_ident={!r}",
                request.path,
                seen,
                request.META.get("REMOTE_ADDR"),
                BaseThrottle().get_ident(request),
                trusted_ident(request),
            )
        return self.get_response(request)


class EdgeSecretMiddleware:
    """Refuse anything that did not arrive through our own edge.

    WHAT THIS IS FOR, and it is not the obvious thing. The Cloud Run URL
    answers the public internet directly — deployed `--allow-unauthenticated`
    on purpose (DEPLOY-cloudrun.md §5) — so until now this process had *two*
    front doors with different numbers of proxies in front of them:

        browser  -> Vercel -> Google front end -> Django    (2 append)
        attacker ->           Google front end -> Django    (1 append)

    `NUM_PROXIES` is one integer, and an attacker is the only caller who gets
    to pick a door. Set it to 2 and the direct door stays forgeable; set it to
    1 and every real visitor shares one throttle bucket, where one refused
    attacker refuses everybody. That is why `config/settings.py` declines to
    guess a number, and why every anonymous ceiling in this deployment —
    including the two in front of the operator's password — does not currently
    bind (#255, #317).

    So this middleware's job is not really "add authentication". It is to
    **delete the second door**, leaving one chain whose length can be measured
    once and written down.

    WHAT IT COSTS TO BE WRONG, stated plainly: this sits in front of the whole
    API. A secret that is set on Cloud Run and missing on Vercel takes the
    product down completely rather than degrading it. That is the trade for a
    boundary that is checkable in this suite instead of only in production —
    see DEPLOY-cloudrun.md §8 for the rotation order that avoids it.

    THE RULES

    - **Inert unless configured.** No `EDGE_SHARED_SECRET`, no gate. Local
      development, the test suite and any deployment that has not adopted this
      are all unaffected, and none of them has the second door either.
    - **Off under DEBUG**, so a developer who does set the variable — to
      exercise this, say — does not have to unset it to use the app.
    - **Fail closed once it is on.** Configured means required: absent header,
      empty header and wrong header are the same 403. "Not configured" must
      never collapse into "no auth required", which is the property
      `NudgeRunView` already states in the same words.
    - **Constant-time compare**, so the refusal cannot be turned into an
      oracle that reads the secret out one character at a time.
    - **One answer for every refusal.** Absent and wrong are indistinguishable
      from outside; a 403 that said which would be a hint.

    THE TWO EXEMPTIONS, both of them callers that reach this service directly
    by design and would otherwise break:

    - `/api/health/` — the deploy-time check, the keep-warm ping
      (DEPLOY-cloudrun.md "Keep-warm") and `proxy.ts`'s wake probe. It costs a
      static JSON payload, carries no throttle scope and reads nothing, so
      exempting it hands an anonymous caller nothing and leaves no ceiling
      keyed on the door it comes through.
    - `/api/coach/nudges/run/` — the hourly tick, a GitHub Actions job POSTing
      from a runner rather than through Vercel (`.github/workflows/checks.yml`).
      It already carries its own shared secret and already refuses when that is
      unset, so a second secret in front of it would add nothing but a second
      thing to rotate — and a rotation that forgot it would silently stop every
      evening nudge in the product.

    Both are asked for by URL name rather than written down, for the reason
    `_login_path` gives.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        expected = settings.EDGE_SHARED_SECRET
        if not expected or settings.DEBUG or request.path in _edge_exempt_paths():
            return self.get_response(request)

        sent = request.headers.get(EDGE_HEADER, "")
        if not hmac.compare_digest(sent, expected):
            return HttpResponse(EDGE_REFUSAL, status=403, content_type="text/plain")
        return self.get_response(request)


def _edge_exempt_paths() -> frozenset[str]:
    """The paths `EdgeSecretMiddleware` lets past, by URL name so that moving a
    route cannot quietly turn an exemption into a 403 — or, worse, leave one
    pointing at whatever moved into the old path."""
    names = ("health", "coach_nudges_run")
    paths = set()
    for name in names:
        try:
            paths.add(reverse(name))
        except NoReverseMatch:  # pragma: no cover — both are always mounted
            pass
    return frozenset(paths)


def _login_path() -> str:
    """The admin's own login URL, asked for rather than written down, so
    mounting the admin somewhere other than `/admin/` cannot quietly turn this
    middleware off."""
    try:
        return reverse("admin:login")
    except NoReverseMatch:  # pragma: no cover — the admin is always mounted here
        return ""
