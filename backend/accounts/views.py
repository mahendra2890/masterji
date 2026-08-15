from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import erasure
from .cookies import clear_auth_cookies, set_auth_cookies
from .models import User
from .serializers import UserSerializer
from .throttling import TrustedIdentThrottle


class MeView(APIView):
    """Who am I? The frontend calls this after login to get the profile;
    PATCH updates the coach tone preference."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        """Leave, and take the account with you.

        Nothing in the product calls this. The control and its panel were
        taken off the dashboard in #242 and the client function went with
        them, deliberately: deletion stays possible on request, and the
        erasure it performs stays exercised by the tests below, but the app
        no longer offers a door to it.

        No confirmation field and no password check, deliberately. There is no
        password on these accounts — sign-in is Google — so the only thing a
        typed confirmation could prove is that the request came from the
        screen that asked for it, which the session cookie already proves.
        That reasoning was written when a two-press control and an export
        offer stood in front of this, and they are what made a bare endpoint
        safe. They are gone, so the safety is gone with them — whoever puts a
        caller back owes the second press and the record offer somewhere, on
        the screen or here, before this is reachable by a single click again.

        The cookies are cleared on the way out for the same reason logout
        clears them: the browser must not be left holding credentials for an
        account that no longer answers. The access token in it is already
        dead — `erase` deactivates the user, and simplejwt refuses an inactive
        one — so this is tidiness rather than the lock.
        """
        erasure.erase(request.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """simplejwt's username+password endpoint, with a ceiling on it.

    Nothing a builder uses reaches this view: sign-in is Google, and every
    account it creates carries `set_unusable_password()`, so the only
    credential this endpoint can possibly verify is the operator's superuser
    from render.yaml — the one that opens the admin. It stays mounted for the
    clients its docstring in urls.py names (curl, other API clients), and it
    stops being an unmetered oracle for that one password.

    The scope is separate from the ones in coach.throttles for the reason those
    exist at all: those ration a budget an honest builder spends, and the
    refusals are written in the coach's voice because a builder reads them.
    Nobody reads this one but a script, so it keeps DRF's own wording.
    """

    throttle_classes = [TrustedIdentThrottle]
    throttle_scope = "login"


class CookieTokenRefreshView(APIView):
    """Rotate tokens using the refresh cookie (browser flow).

    API clients that hold tokens themselves use /api/auth/token/refresh/.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE)
        if not raw:
            return Response(
                {"detail": "No refresh cookie."}, status=status.HTTP_401_UNAUTHORIZED
            )
        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, User.DoesNotExist):
            # Every way a refresh cookie can fail to become a session, and all
            # of them mean the same thing to the browser: sign in again.
            #
            # User.DoesNotExist is a valid token for a user this database has
            # never seen (another app's cookie on localhost, a deleted account).
            # TokenError is the rest — expired, malformed, or signed with a
            # SECRET_KEY this deploy no longer uses. simplejwt's own
            # TokenViewBase converts that one into a 401; this view reimplements
            # that method and used not to, so the exception escaped DRF (it is
            # not an APIException) and Django answered 500 in text/html.
            #
            # That was not merely the wrong code. lib/auth-client.ts reads any
            # non-JSON reply as "the instance is still booting", so the app sat
            # on "The server is waking up." and retried every three seconds
            # forever, on a screen with no way out — and "/" paints the app
            # rather than the landing while an access cookie exists, so there
            # was no escape but clearing cookies by hand. A SECRET_KEY rotation
            # would have done that to every signed-in builder at once.
            #
            # The dead cookie is cleared on the way out so the next request is
            # the clean "No refresh cookie." 401 above: one bad answer, then a
            # working landing page, instead of a loop.
            response = Response(
                {"detail": "Session expired — sign in again."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_auth_cookies(response)
            return response
        response = Response({"ok": True})
        # ROTATE_REFRESH_TOKENS is on, so a new refresh token comes back too
        set_auth_cookies(response, RefreshToken(serializer.validated_data["refresh"]))
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({"ok": True})
        clear_auth_cookies(response)
        return response


class DevLoginView(APIView):
    """DEBUG-only cookie login so the full browser flow works locally
    without Google credentials. 404s (like any unknown route) in prod."""

    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.DEBUG:
            raise Http404
        username = (request.data.get("username") or "dev").strip() or "dev"
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": f"{username}@dev.local"}
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        response = Response({"ok": True, "username": user.username})
        set_auth_cookies(response, RefreshToken.for_user(user))
        return response
