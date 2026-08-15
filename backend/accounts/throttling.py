"""Who a ceiling is counting, when the caller gets to write part of the answer.

Every anonymous ceiling in this deployment — the two public reads, the cohort
code lookup, and the two in front of the operator's password — asks the same
question: which caller is this? DRF answers it with `BaseThrottle.get_ident`,
which reads `X-Forwarded-For` and trusts the last `NUM_PROXIES` entries.

That answer does not work here, and the reason is worth stating once so nobody
re-derives it from the setting name. Measured against production on 15 and
16 August 2026:

  * Vercel does not append the caller's address when the caller already sent
    `X-Forwarded-For`. It forwards theirs, so the position `NUM_PROXIES` trusts
    is one the caller can write.
  * Worse, it does that INCONSISTENTLY. Six requests with the same forged
    header, same client, seconds apart: the value survived four times and was
    replaced twice. Not by method, not by path — request to request.

The inconsistency is the part that matters. A header that is forgeable two
thirds of the time reads as trustworthy in any small sample, which is exactly
how `NUM_PROXIES=2` came to be measured, pinned, and wrong (#317, #334). It is
also why the probe in #255 gave 6/20 against 14/20 rather than 0/20 against
20/20.

WHAT IS TRUSTWORTHY. In the same six requests, with every candidate forged on
every one:

    x-forwarded-for          forged value survived 4/6
    x-real-ip                                      3/6
    x-vercel-forwarded-for                         2/6
    x-vercel-proxied-for                           0/6

`x-vercel-proxied-for` carried the true client address every time, including on
every request that sent a `X-Vercel-Proxied-For` of its own. Vercel's own
infrastructure writes it and overwrites what the caller supplied.

WHY WE MAY BELIEVE IT, which is not a property of the header alone. Anybody can
send `X-Vercel-Proxied-For` to a server willing to read it. What makes this one
safe is #317: `EdgeSecretMiddleware` refuses everything that did not come
through our edge, so the only requests that reach a throttle came through
Vercel, which rewrote the header on the way. The header is trustworthy BECAUSE
the gate is shut, and the two are interlocked below rather than merely
documented together — the same shape `DRF_NUM_PROXIES` uses, and for the same
reason: an invariant that costs one condition to hold should not be left to a
runbook.
"""

from django.conf import settings
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

# Vercel writes this one and overwrites a caller's version of it. Every other
# candidate in the module docstring is forgeable at least some of the time.
TRUSTED_HEADER = "HTTP_X_VERCEL_PROXIED_FOR"


def trusted_ident(request) -> str:
    """The address to count this caller against.

    Falls back to DRF's own answer whenever the trusted header is not available
    — no edge secret, or no header on the request. That covers local
    development, the test suite, any deployment that has not adopted the gate,
    and the exempt callers that reach this service directly. None of those is
    made worse by the fallback; it is what they already had.
    """
    if settings.EDGE_SHARED_SECRET:
        # Single-valued in every observation. Split anyway, and take the first
        # entry rather than the last: Vercel writes this header, so if a second
        # hop ever starts appending to it, the client's address stays leftmost.
        forwarded = request.META.get(TRUSTED_HEADER, "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return BaseThrottle().get_ident(request)


class TrustedIdentThrottle(ScopedRateThrottle):
    """`ScopedRateThrottle`, counting the caller rather than what they claim.

    Everything else about it is unchanged: which bucket a view draws from is
    still the view's own `throttle_scope`, and the rates still live in
    `settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`.
    """

    def get_ident(self, request):
        return trusted_ident(request)
