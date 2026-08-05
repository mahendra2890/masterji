from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """JWT auth that also accepts the access token from an httpOnly cookie.

    Header wins when present (curl, tests, other API clients). Cookie mode is
    what the browser uses after social login — SameSite=Lax keeps the cookie
    off cross-site POSTs, which is what makes this CSRF-safe without the
    session/CSRF-token machinery.
    """

    def authenticate(self, request):
        if self.get_header(request) is not None:
            return super().authenticate(request)

        raw_token = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE)
        if not raw_token:
            return None
        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
