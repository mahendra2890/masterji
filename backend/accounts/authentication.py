from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError


class CookieJWTAuthentication(JWTAuthentication):
    """JWT auth that also accepts the access token from an httpOnly cookie.

    Header wins when present (curl, tests, other API clients). Cookie mode is
    what the browser uses after social login — SameSite=Lax keeps the cookie
    off cross-site POSTs, which is what makes this CSRF-safe without the
    session/CSRF-token machinery.

    A cookie the browser sends on its own is not an assertion the way an
    Authorization header is: an unusable one means "signed out", not "bad
    request". So it yields anonymous rather than a 401 — otherwise the
    AllowAny endpoints that exist to recover from exactly that
    (/api/auth/refresh/, /logout/, /dev-login/) would 401 too, leaving no
    way back in. Two cookies hit this in practice: the >15-minute-old access
    token every idle tab holds, and — on localhost, where sibling projects
    share a host, a cookie name and the insecure dev SECRET_KEY — a validly
    signed token for a user id this database has never seen.

    Protected views still refuse, from the permission layer. A bad
    Authorization header keeps failing loudly: that's a client bug worth
    surfacing, not a stale browser.
    """

    def authenticate(self, request):
        if self.get_header(request) is not None:
            return super().authenticate(request)

        raw_token = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE)
        if not raw_token:
            return None
        try:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except (TokenError, AuthenticationFailed):
            return None  # InvalidToken subclasses AuthenticationFailed
