"""Auth contract tests.

These assert the *security properties* of the token design, not just that login works:
that the refresh token never reaches JavaScript, that rotation invalidates the old one,
and that logout actually revokes. Each of those fails silently if misconfigured — a
missing token_blacklist migration makes logout look fine and revoke nothing.
"""

import pytest
from django.conf import settings
from django.contrib.auth.models import User

from apps.athletes.models import Athlete

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
LOGOUT = "/api/auth/logout/"
ME = "/api/auth/me/"
ATHLETE = "/api/athlete/"

GOOD = {"username": "rohit", "password": "correct-horse-battery-1", "email": "r@example.com"}


@pytest.fixture(autouse=True)
def _no_throttling(settings):
    """Throttles are per-IP and would fail the 6th test in a run, not the 6th real user."""
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {k: None for k in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},
    }


def register(client, **overrides):
    return client.post(REGISTER, {**GOOD, **overrides}, content_type="application/json")


def auth(client, access):
    return {"HTTP_AUTHORIZATION": f"Bearer {access}"}


# --- registration ------------------------------------------------------------

@pytest.mark.django_db
def test_register_creates_user_and_athlete(client):
    response = register(client)
    assert response.status_code == 201, response.content

    user = User.objects.get(username="rohit")
    assert Athlete.objects.filter(user=user).exists()
    assert response.json()["athlete"]["display_name"] == "rohit"


@pytest.mark.django_db
def test_register_rejects_weak_password(client):
    response = register(client, password="abc")
    assert response.status_code == 400
    assert not User.objects.filter(username="rohit").exists()


@pytest.mark.django_db
def test_duplicate_username_leaves_nothing_behind(client):
    assert register(client).status_code == 201
    response = register(client, email="other@example.com")

    assert response.status_code == 400
    # The atomic block matters: a User with no Athlete authenticates and then 500s.
    assert User.objects.filter(username="rohit").count() == 1
    assert Athlete.objects.count() == 1


# --- token placement ---------------------------------------------------------

@pytest.mark.django_db
def test_login_puts_access_in_body_and_refresh_only_in_an_httponly_cookie(client):
    register(client)
    response = client.post(
        LOGIN, {"username": "rohit", "password": GOOD["password"]},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content

    body = response.json()
    assert body["access"]
    # The whole design rests on this: a refresh token in the body would be reachable
    # from JavaScript, which is what we are avoiding.
    assert "refresh" not in body

    cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == settings.REFRESH_COOKIE_PATH


@pytest.mark.django_db
def test_wrong_password_and_unknown_user_are_indistinguishable(client):
    register(client)
    wrong = client.post(LOGIN, {"username": "rohit", "password": "nope"},
                        content_type="application/json")
    unknown = client.post(LOGIN, {"username": "ghost", "password": "nope"},
                          content_type="application/json")

    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json()


# --- session lifecycle -------------------------------------------------------

@pytest.mark.django_db
def test_me_requires_a_bearer_token(client):
    access = register(client).json()["access"]

    assert client.get(ME).status_code == 401
    assert client.get(ME, **auth(client, access)).json()["user"]["username"] == "rohit"


@pytest.mark.django_db
def test_rotation_invalidates_the_previous_refresh_token(client):
    register(client)
    original = client.cookies[settings.REFRESH_COOKIE_NAME].value

    first = client.post(REFRESH)
    assert first.status_code == 200
    assert first.json()["access"]

    rotated = client.cookies[settings.REFRESH_COOKIE_NAME].value
    assert rotated != original

    # Replaying the old token must fail. If token_blacklist is absent from
    # INSTALLED_APPS or unmigrated, this passes with 200 and nothing is revoked.
    client.cookies[settings.REFRESH_COOKIE_NAME] = original
    assert client.post(REFRESH).status_code == 401


@pytest.mark.django_db
def test_logout_revokes_rather_than_just_forgetting(client):
    register(client)
    refresh = client.cookies[settings.REFRESH_COOKIE_NAME].value

    assert client.post(LOGOUT).status_code == 204

    # Present the token again as a stolen copy would; the blacklist must reject it.
    client.cookies[settings.REFRESH_COOKIE_NAME] = refresh
    assert client.post(REFRESH).status_code == 401


@pytest.mark.django_db
def test_refresh_without_a_cookie_is_401_not_500(client):
    assert client.post(REFRESH).status_code == 401


# --- profile -----------------------------------------------------------------

@pytest.mark.django_db
def test_preferences_round_trip(client):
    access = register(client).json()["access"]
    response = client.patch(
        ATHLETE, {"timezone": "Asia/Kolkata", "weight_kg": 68.5},
        content_type="application/json", **auth(client, access),
    )
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] == "Asia/Kolkata"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload,field",
    [
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"available_days": {str(i): False for i in range(7)}}, "available_days"),
        ({"available_days": {"0": True}}, "available_days"),
        ({"easy_pace_min": 700, "easy_pace_max": 600}, "easy_pace_max"),
        ({"hr_easy_min": 150, "hr_easy_max": 140}, "hr_ceiling"),
        ({"long_run_day": 0}, "long_run_day"),  # Monday is unavailable by default
    ],
)
def test_invalid_preferences_are_rejected(client, payload, field):
    access = register(client).json()["access"]
    response = client.patch(ATHLETE, payload, content_type="application/json",
                            **auth(client, access))

    assert response.status_code == 400, f"{payload} was accepted"
    assert field in response.json()


@pytest.mark.django_db
def test_garmin_fields_are_not_client_writable(client):
    access = register(client).json()["access"]
    response = client.patch(ATHLETE, {"garmin_connected": True},
                            content_type="application/json", **auth(client, access))

    assert response.status_code == 200
    # A client that could set this could make the UI claim sync works when it does not.
    assert response.json()["garmin_connected"] is False


@pytest.mark.django_db
def test_athlete_endpoint_never_returns_another_athlete(client):
    register(client)
    other = register(client, username="friend", email="f@example.com")
    assert other.status_code == 201

    response = client.get(ATHLETE, **auth(client, other.json()["access"]))
    assert response.json()["display_name"] == "friend"


# --- the timezone trap -------------------------------------------------------

@pytest.mark.django_db
def test_local_today_uses_the_athletes_zone_not_utc():
    """At 00:30 in Kolkata it is still yesterday in UTC.

    Django's TIME_ZONE is UTC, so timezone.localdate() would file that run under the
    wrong day. This is the bug class that cost run-project the most.
    """
    from datetime import datetime, timezone as dt_timezone
    from unittest import mock

    user = User.objects.create_user("tz", password="correct-horse-battery-1")
    athlete = Athlete.objects.create(user=user, display_name="tz", timezone="Asia/Kolkata")

    # 2026-08-19 19:30 UTC == 2026-08-20 01:00 IST
    frozen = datetime(2026, 8, 19, 19, 30, tzinfo=dt_timezone.utc)
    with mock.patch("django.utils.timezone.now", return_value=frozen):
        assert athlete.local_today.isoformat() == "2026-08-20"
        assert frozen.date().isoformat() == "2026-08-19"


@pytest.mark.django_db
def test_unknown_timezone_falls_back_rather_than_crashing():
    user = User.objects.create_user("bad", password="correct-horse-battery-1")
    athlete = Athlete.objects.create(user=user, display_name="bad", timezone="Nope/Nope")
    assert athlete.local_today is not None


# --- onboarding --------------------------------------------------------------

@pytest.mark.django_db
def test_new_athlete_starts_un_onboarded(client):
    """The router needs an explicit flag.

    Navigating to onboarding after registration raced the auth guard's redirect to
    "/" and lost, silently skipping onboarding. State the answer in the data instead.
    """
    assert register(client).json()["athlete"]["onboarding_complete"] is False


@pytest.mark.django_db
def test_completing_onboarding_persists(client):
    access = register(client).json()["access"]
    response = client.patch(
        ATHLETE,
        {"available_days": {**{str(i): False for i in range(7)}, "2": True, "6": True},
         "long_run_day": 6, "onboarding_complete": True},
        content_type="application/json", **auth(client, access),
    )
    assert response.status_code == 200, response.content
    assert response.json()["onboarding_complete"] is True
    assert response.json()["training_days_per_week"] == 2
