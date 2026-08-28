"""Auth and profile.

The security of this design is entirely in *where each token lives*:

* **Access token** — 15 minutes, returned in the response body, held in JS memory only
  on the client. Never localStorage (any injected script can read it and exfiltrate a
  valid token) and never a cookie (that would reintroduce CSRF).
* **Refresh token** — 7 days, set as an httpOnly cookie the client cannot read, rotated
  on every use and blacklisted on logout so signing out actually revokes.

The blast radius of a stolen access token is therefore 15 minutes. Stored in
localStorage it would be valid until expiry with no way to revoke it.
"""

from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Athlete
from .serializers import AthleteSerializer, RegisterSerializer, UserSerializer


def _set_refresh_cookie(response, refresh: str):
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh,
        httponly=True,                                  # JS cannot read it
        secure=not settings.DEBUG,                      # HTTPS only in production
        samesite="Lax",                                 # not sent on cross-site POSTs
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=settings.REFRESH_COOKIE_PATH,              # not attached to every API call
    )
    return response


def _session_payload(athlete: Athlete) -> dict:
    return {
        "user": UserSerializer(athlete.user).data,
        "athlete": AthleteSerializer(athlete).data,
    }


def _issue(athlete: Athlete, http_status=status.HTTP_200_OK):
    """One login/register response: access in the body, refresh in the cookie."""
    refresh = RefreshToken.for_user(athlete.user)
    payload = _session_payload(athlete)
    payload["access"] = str(refresh.access_token)
    response = Response(payload, status=http_status)
    return _set_refresh_cookie(response, str(refresh))


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        athlete = serializer.save()
        return _issue(athlete, status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        user = authenticate(request, username=username, password=password)

        # Deliberately identical for an unknown username and a wrong password.
        # Distinguishing them tells an attacker which usernames exist.
        if user is None or not user.is_active:
            return Response(
                {"detail": "Incorrect username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        athlete = Athlete.objects.filter(user=user).first()
        if athlete is None:
            # Only reachable for a superuser made with createsuperuser, which does not
            # go through RegisterSerializer. Create the row rather than 500 later.
            athlete = Athlete.objects.create(user=user, display_name=user.username)
        return _issue(athlete)


class RefreshView(APIView):
    """Exchange the refresh cookie for a new access token, rotating the cookie."""

    permission_classes = [AllowAny]
    throttle_scope = "refresh"

    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return Response(
                {"detail": "No refresh token."}, status=status.HTTP_401_UNAUTHORIZED
            )

        serializer = TokenRefreshSerializer(data={"refresh": raw})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, Exception):  # noqa: BLE001 — expired, malformed, blacklisted
            response = Response(
                {"detail": "Refresh token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie(
                settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH
            )
            return response

        data = serializer.validated_data
        response = Response({"access": data["access"]})
        # ROTATE_REFRESH_TOKENS is on, so a new refresh comes back and the old one is
        # blacklisted. Move it into the cookie rather than the body.
        if "refresh" in data:
            _set_refresh_cookie(response, data["refresh"])
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # already expired or blacklisted; clearing the cookie is enough

        response = Response(status=status.HTTP_204_NO_CONTENT)
        # Both halves matter: blacklisting without clearing leaves a stale cookie that
        # 401s confusingly on the next load; clearing without blacklisting leaves a
        # live token that logout did not actually revoke.
        response.delete_cookie(
            settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH
        )
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        athlete = Athlete.objects.filter(user=request.user).first()
        if athlete is None:
            athlete = Athlete.objects.create(
                user=request.user, display_name=request.user.username
            )
        return Response(_session_payload(athlete))


class AthleteDetailView(generics.RetrieveUpdateAPIView):
    """The requesting athlete's own profile. There is no lookup by id, by design."""

    serializer_class = AthleteSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return Athlete.objects.get(user=self.request.user)
