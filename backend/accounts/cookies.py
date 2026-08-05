from django.conf import settings

ACCESS_MAX_AGE = 15 * 60
REFRESH_MAX_AGE = 7 * 24 * 3600
# The refresh token is only ever needed by the auth endpoints themselves,
# so path-scope its cookie — the browser won't attach it anywhere else.
REFRESH_PATH = "/api/auth/"


def set_auth_cookies(response, refresh_token) -> None:
    """Attach access + refresh JWTs as httpOnly cookies."""
    secure = not settings.DEBUG
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE,
        str(refresh_token.access_token),
        max_age=ACCESS_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE,
        str(refresh_token),
        max_age=REFRESH_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=secure,
        path=REFRESH_PATH,
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE, path="/")
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE, path=REFRESH_PATH)
