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
"""

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import NoReverseMatch, reverse
from loguru import logger
from rest_framework.throttling import BaseThrottle

KEY_PREFIX = "admin-login-failures"

REFUSAL = "Too many sign-in attempts. Try again later.\n"


class AdminLoginThrottleMiddleware:
    """Refuse `POST /admin/login/` from an address that has just guessed wrong
    `ADMIN_LOGIN_MAX_FAILURES` times inside `ADMIN_LOGIN_FAILURE_WINDOW_S`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "POST" or request.path != _login_path():
            return self.get_response(request)

        key = f"{KEY_PREFIX}:{BaseThrottle().get_ident(request)}"
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
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.LOG_FORWARDED_HEADERS:
            logger.info(
                "forwarded-headers path={} xff={!r} remote_addr={!r} ident={!r}",
                request.path,
                request.META.get("HTTP_X_FORWARDED_FOR"),
                request.META.get("REMOTE_ADDR"),
                BaseThrottle().get_ident(request),
            )
        return self.get_response(request)


def _login_path() -> str:
    """The admin's own login URL, asked for rather than written down, so
    mounting the admin somewhere other than `/admin/` cannot quietly turn this
    middleware off."""
    try:
        return reverse("admin:login")
    except NoReverseMatch:  # pragma: no cover — the admin is always mounted here
        return ""
