from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import clear_auth_cookies, set_auth_cookies
from .models import User
from .serializers import UserSerializer


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
        except User.DoesNotExist:
            # A cryptographically valid token for a user this database has
            # never seen (another app's cookie on localhost, or a deleted
            # account). That's a dead session, not a server error.
            return Response(
                {"detail": "Unknown session."}, status=status.HTTP_401_UNAUTHORIZED
            )
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
