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


def set_impersonation_cookie(response, access_token, max_age: int) -> None:
    """Hand the browser a read-only session and take the refresh away.

    Two differences from `set_auth_cookies`, and both of them are the feature:

    - **Access only.** No refresh cookie is set, so this session cannot rotate
      itself forward and simply stops working at `max_age`.
    - **Any refresh cookie already there is cleared.** Without this, an
      operator who was signed in as themselves would keep their own refresh
      cookie, and the app's first 401 after expiry would quietly rotate them
      back into their OWN account — the same screen, a different person's
      data, and nothing on it saying so.
    """
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE, path=REFRESH_PATH)
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE,
        str(access_token),
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        path="/",
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE, path="/")
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE, path=REFRESH_PATH)
