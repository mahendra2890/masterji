from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import oauth, views

urlpatterns = [
    # Token-in-body flow (API clients, curl, tests). Throttled: the only
    # password it can check is the superuser's — see ThrottledTokenObtainPairView.
    path("token/", views.ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Cookie flow (browser)
    path("google/login/", oauth.google_login, name="google_login"),
    path("google/callback/", oauth.google_callback, name="google_callback"),
    path("refresh/", views.CookieTokenRefreshView.as_view(), name="cookie_refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("dev-login/", views.DevLoginView.as_view(), name="dev_login"),
]
