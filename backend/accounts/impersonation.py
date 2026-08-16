"""Seeing the app as one builder sees it, without being able to touch it.

WHAT THIS REPLACES, because the thing it replaces is the argument for it.
Until now, answering "what is this builder actually looking at" meant pulling
`DJANGO_SECRET_KEY` and `DATABASE_URL` out of Cloud Run onto a laptop, minting
a token with `RefreshToken.for_user`, and pasting it into the `access_token`
cookie by hand. Three costs, and the middle one is the worst:

- the production signing key left the boundary and landed in shell history;
- what came out was a full read/write session, so anything typed landed in
  that builder's transcript as their own `Message`, billed a `ModelCall` to
  them and could move their gate, with nothing anywhere recording that it was
  the operator rather than them;
- there is no revocation in this deployment — `token_blacklist` is not
  installed — so a token minted that way lives its whole lifetime.

The first is fixed by minting on the server. The third is bounded by a short
lifetime and by setting no refresh cookie. The second is fixed by the rule
this module exists to state:

**An impersonated session is READ-ONLY.** The claim below is what marks a
token as one, `ImpersonationReadOnlyMiddleware` is what refuses every unsafe
method carrying it, and the two are in the same repository so neither can
drift into being decoration.

WHY READ-ONLY IS THE WHOLE FEATURE AND NOT A SETTING. A write made while
impersonating is, in the database, indistinguishable from one the builder made
themselves — same `user`, same row, same timestamps. A banner does not fix
that, and an audit row only says a session happened, not which of the rows in
it were the operator's. The only version of this that cannot corrupt somebody's
record is the one that cannot write at all. If writes are ever wanted they
arrive carrying their own marker on the row, not by loosening this.

WHY THE ADMIN AND NOT AN API ENDPOINT. The gate has to be a password, and the
only password in this deployment is the operator's superuser — which is
already the admin's own login, already rate-limited by
`AdminLoginThrottleMiddleware`, and already CSRF-protected by a real form. A
DRF endpoint would have had to re-acquire all three, and would have been a
second door to the same capability.
"""

from datetime import timedelta

from django.conf import settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

# The claim that marks a token as an operator wearing somebody else's account.
# Its presence is the whole signal: the middleware refuses unsafe methods when
# it is there, and `MeView` reports it so the app can say so on screen.
#
# The operator's USERNAME rather than their id, because both readers want a
# name — the banner shows it to whoever is looking at the screen, and the
# audit row is read by a person too. The id is on the `Impersonation` row,
# which is where a join belongs.
IMPERSONATOR_CLAIM = "impersonator"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def lifetime() -> timedelta:
    """How long an impersonated session lasts.

    Deliberately shorter than a real one and with no refresh cookie behind it,
    so it expires into the signed-out landing page rather than rotating itself
    forward. Nothing can end one early — there is no blacklist here — so this
    number IS the revocation story, and it should stay small enough that
    "wait for it" is an acceptable answer to "undo that".
    """
    return timedelta(seconds=settings.IMPERSONATION_LIFETIME_S)


def issue(operator, target) -> AccessToken:
    """An access token for `target`, stamped with who is really holding it.

    An access token and not a refresh: `RefreshToken.for_user` would hand out
    something that can rotate itself into a fresh pair for a week, which is
    exactly the session this feature must not be able to become.
    """
    token = AccessToken.for_user(target)
    token[IMPERSONATOR_CLAIM] = operator.get_username()
    token.set_exp(lifetime=lifetime())
    return token


def impersonator_in(request) -> str | None:
    """The operator behind this request, or None for every ordinary one.

    Reads and validates the token itself rather than asking DRF, because the
    caller is middleware: DRF's authentication runs per-view, well after the
    point where an unsafe method has to be refused. The duplicated verify
    costs one HMAC on requests that carry a token at all.

    Both places a token can arrive, in `CookieJWTAuthentication`'s order —
    header first, then cookie — so this cannot disagree with the layer that
    decides who the request is from.

    Every failure is None, and that is not a hole: a token this cannot verify
    is one DRF will refuse too, so the request is already going to 401. Being
    quiet here means a malformed token produces "sign in again" rather than a
    confusing 403 about impersonation.
    """
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        raw = header.removeprefix("Bearer ").strip()
    else:
        raw = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE, "")
    if not raw:
        return None
    try:
        claims = AccessToken(raw)
    except TokenError:
        return None
    operator = claims.get(IMPERSONATOR_CLAIM)
    return operator if isinstance(operator, str) and operator else None
