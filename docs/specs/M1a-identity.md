# M1a — identity, preferences, login

**Goal:** log in from the frontend, see your profile, edit your preferences, log out.
One vertical slice, end to end.

This comes before activities because everything downstream depends on it: `Athlete` is a
OneToOne on `User`, `OwnedByAthlete` filters by the logged-in athlete, and Garmin connect
attaches a token to a session. Building activities first means scaffolding a fake user.

---

## Public registration — and what it drags in

This is going to be hosted, so anyone can sign up. That makes three things load-bearing
that would not have been for a single user. They are covered in
[docs/HOSTING.md](../HOSTING.md); the short version:

1. **Every registered user costs you money** — each one makes LLM calls against your $5.
2. **Garmin rate-limits by IP**, and every user's sync leaves from your one server IP.
3. **You are now holding other people's health data**, and briefly their Garmin passwords.

None of that blocks M1a. All of it changes what M1a has to get right, which is why
throttling and validation below are not optional extras.

### Endpoint

```
POST /api/auth/register/   {username, email, password} -> user + athlete, logged in
```

Create the `Athlete` **explicitly in the register view**, not via a `post_save` signal on
`User`. The signal is the standard trick and it fires for `createsuperuser`, for admin
edits, for fixtures, and for tests — all places you did not intend. Explicit creation also
lets you seed `timezone` from what the client detected, which is the difference between a
working default and everyone silently on UTC.

Wrap the user and athlete creation in `transaction.atomic()`. A `User` with no `Athlete`
is an account that authenticates and then 500s on every request.

Django's password validators are already configured in `settings.py` — `authenticate()`
and `set_password()` route through them. Do not hand-roll any of it.

**Return the same error for unknown username and wrong password.** Distinguishing them
tells an attacker which usernames exist.

### Throttling — required, not a hardening pass

DRF has this built in; no new dependency:

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "register": "5/hour",     # per IP
        "login":    "10/hour",    # per IP — brute-force ceiling
        "garmin":   "10/hour",    # per user — see HOSTING.md
        "ai":       "30/day",     # per user — this one is money
    },
}
```

Then `throttle_scope = "register"` on the view. Redis already backs the cache, so the
counters survive a restart.

An unthrottled login endpoint on a public host gets found by automated scanners within
days. This is not a hypothetical.

### Onboarding

Registration alone leaves an athlete with defaults that are wrong for them — UTC, a
guessed easy pace, Monday rest. After registering, the frontend walks through timezone,
available days, long-run day and (later) a race. Claude builds that; the backend just
needs `PATCH /api/athlete/` to accept it.

---

## 1. `apps/athletes/models.py`

### `Athlete` — the tenancy root

```python
user            OneToOneField(User, CASCADE, related_name="athlete")
display_name    CharField(120)
timezone        CharField(64, default="UTC")      # "Asia/Kolkata"

date_of_birth   DateField(null, blank)
weight_kg       FloatField(null, blank)           # scales hydration/fuelling later
resting_hr      PositiveSmallIntegerField(null, blank)
max_hr          PositiveSmallIntegerField(null, blank)   # observed, not 220-age

# Standing defaults, seconds per km. NOT what today's session prescribes.
easy_pace_min   PositiveSmallIntegerField(default=600)   # 10:00/km
easy_pace_max   PositiveSmallIntegerField(default=645)   # 10:45/km
hr_easy_min     PositiveSmallIntegerField(default=130)
hr_easy_max     PositiveSmallIntegerField(default=145)
hr_ceiling      PositiveSmallIntegerField(default=155)

run_cadence_threshold  PositiveSmallIntegerField(default=140)   # >= this is running

available_days  JSONField(default=default_available_days)
long_run_day    PositiveSmallIntegerField(default=6)     # 0 = Monday

garmin_connected   BooleanField(default=False)   # system-managed, never user-editable
garmin_last_sync   DateTimeField(null, blank)
created_at / updated_at
```

**The pace and HR fields are standing defaults, not session prescriptions.** Anything
describing *today's* session must read from the session object, never this profile. The
profile holds what those values start as; the session holds what they became after the
plan, the day type and the readiness adjustment. Reading the profile skips all three —
that is how a *running* heart rate once got prescribed for a walk in `run-project`.

### `available_days` — availability only

```python
def default_available_days() -> dict:
    # True = can train. Monday rest by default: new runners are injured by
    # frequency far more often than by distance.
    return {"0": False, "1": True, "2": False, "3": True,
            "4": False, "5": True, "6": True}
```

`run-project` stored `{"1": "intervals", "6": "long"}` — the weekday *and what it is for*.
That works when one hardcoded table owns the plan. Here the generator decides what each
day is for, from the phase and last week's data. If the profile also declares Tuesday is
intervals, the two disagree and one silently wins.

Store only what the generator cannot know: which days you are free, plus `long_run_day`.

### `local_now` / `local_today` — copy verbatim from `run-project`

```python
@property
def local_now(self):
    """Now, in the athlete's own timezone.

    Django's TIME_ZONE is UTC, so timezone.localdate() answers a question nobody
    asked: at 00:48 in Kolkata it is still yesterday in UTC, and the whole app
    would show yesterday's session. Every 'today' must come from here.
    """
    from zoneinfo import ZoneInfo
    from django.utils import timezone
    try:
        zone = ZoneInfo(self.timezone or "UTC")
    except Exception:
        zone = ZoneInfo("UTC")
    return timezone.now().astimezone(zone)

@property
def local_today(self):
    return self.local_now.date()
```

Every date in this system goes through it. No exceptions. The bug it prevents is silent.

### `token_dir`

```python
@property
def token_dir(self) -> str:
    from django.conf import settings
    return f"{settings.GARMIN_TOKEN_DIR}/athlete_{self.pk}"
```

Per-athlete directory, so a second athlete never shares a Garmin session. The setting is
`GARMIN_TOKEN_DIR` here; `run-project` calls it `GARMIN_TOKEN_ROOT`, and the files you
copy at M1b reference the old name.

### `OwnedByAthlete`

```python
class OwnedByAthlete(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE,
                               related_name="%(class)ss")
    class Meta:
        abstract = True
```

Every tenant-scoped model inherits it, from the first one.

### `AthleteScopedMixin`

```python
class AthleteScopedMixin:
    """Filters every queryset to the requesting athlete. Not optional.

    A view that forgets this returns another athlete's data with no error and no
    log line — the failure is invisible until it is a breach.
    """
    def get_queryset(self):
        return super().get_queryset().filter(athlete=self.request.user.athlete)
```

Build it now, with one model, while it is easy to verify.

---

## 2. Auth — JWT, split storage

`djangorestframework-simplejwt`. The security of this design is entirely in **where each
token lives**, so that part is not optional.

| Token | Lifetime | Stored | Why |
|---|---|---|---|
| **access** | 15 min | **JS memory only** | Never `localStorage` — an injected script can read that and exfiltrate a valid token. Never a cookie — that would reintroduce CSRF. Sent as `Authorization: Bearer …`. |
| **refresh** | 7 days | **httpOnly cookie** | Unreadable by JS, so XSS cannot steal it. Blacklisted on logout, so logout actually revokes. |

An access token held only in memory dies on page refresh. That is intentional — the
frontend calls `/refresh/` once on load and gets a new one from the cookie. One extra
request buys you a token that survives no XSS and a logout that means something.

### > Why not `localStorage`

It is the common choice and the weak one. Any script that executes on your page — a
compromised dependency, an injected tag — can read it and send a valid token anywhere.
And logout cannot revoke a JWT, so a stolen token stays valid until it expires no matter
how many times the user signs out.

With a blacklisted refresh token, the blast radius of a stolen access token is 15 minutes.

### Settings

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    ...
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    # Without this, rotation issues a new refresh token and leaves the OLD one valid.
    # A stolen refresh token would then work for its full 7 days alongside the real one.
    "BLACKLIST_AFTER_ROTATION": True,
}

INSTALLED_APPS += ["rest_framework_simplejwt.token_blacklist"]
```

`token_blacklist` is a bundled app and needs a migration. Without it, `ROTATE_` and
`BLACKLIST_` are silently inert — the settings are accepted and do nothing.

### Endpoints

```
POST /api/auth/register/   {username, email, password} -> access in body, refresh in cookie
POST /api/auth/login/      {username, password}        -> access in body, refresh in cookie
POST /api/auth/refresh/    reads the cookie            -> new access, rotates the cookie
POST /api/auth/logout/     blacklists the refresh, clears the cookie -> 204
GET  /api/auth/me/         -> user + athlete, or 401
GET  /api/athlete/         -> the profile
PATCH /api/athlete/        -> update preferences
```

`register/`, `login/` and `refresh/` are `AllowAny`. **`AllowAny` does not mean
unthrottled** — those three are exactly the endpoints that need a rate limit.

Do not use simplejwt's stock `TokenObtainPairView`: it returns **both** tokens in the JSON
body, which puts the refresh token in JS reach and defeats the whole design. Subclass it
and move the refresh token into the cookie:

```python
response.set_cookie(
    "refresh_token", str(refresh),
    httponly=True,                        # JS cannot read it
    secure=not settings.DEBUG,            # HTTPS only in production
    samesite="Lax",                       # blocks cross-site sends
    max_age=7 * 24 * 3600,
    path="/api/auth/",                    # only sent to the auth endpoints
)
```

`path="/api/auth/"` matters: it means the cookie is not attached to every API call, only
the two that need it.

`logout/` must blacklist the refresh token *and* clear the cookie. Doing only one leaves
either a live token or a stale cookie that 401s confusingly on next load.

**Return the same error for unknown username and wrong password.** Distinguishing them
tells an attacker which usernames exist.

### No CSRF endpoint needed

Dropping session auth drops the CSRF requirement with it — the access token travels in an
`Authorization` header, which browsers do not attach automatically. The refresh cookie is
`SameSite=Lax`, so it is not sent on cross-site POSTs either.

If you later move the access token into a cookie, CSRF protection comes straight back.

### `AthleteSerializer`

Editable: `display_name`, `timezone`, `date_of_birth`, `weight_kg`, `resting_hr`,
`max_hr`, the four pace/HR band fields, `hr_ceiling`, `run_cadence_threshold`,
`available_days`, `long_run_day`.

**Read-only: `garmin_connected`, `garmin_last_sync`, `user`, timestamps.** Those are
system-managed — a client that can PATCH `garmin_connected=True` can make the UI lie
about whether sync works.

Validate:

- `timezone` is a real zone — `ZoneInfo(value)` raises otherwise, and a bad one silently
  degrades every date in the app to UTC.
- `easy_pace_min < easy_pace_max`, `hr_easy_min < hr_easy_max < hr_ceiling`.
- `available_days` has exactly keys `"0"`–`"6"` with boolean values, and **at least one
  `True`** — zero training days makes the plan generator produce an empty plan with no
  explanation.
- `long_run_day` names a day that is `True` in `available_days`.

That last pair is the sort of thing an athlete does by accident at 11pm and then wonders
why the plan looks broken.

---

## Done tests

| Check | Expect |
|---|---|
| `manage.py check` then `makemigrations` / `migrate` | clean, no hand-edited migration |
| `POST /api/auth/register/` | 201, `User` + `Athlete` created, logged in |
| Register with a 4-char password | 400 from Django's validators |
| Register with a taken username | 400, no half-created `User` left behind |
| Register 6 times in an hour from one IP | 6th returns 429 |
| 11 failed logins in an hour | 429, not an 11th password attempt |
| Register as user B, `GET /api/athlete/` | B's profile, never A's |
| `GET /api/auth/me/` while logged out | 403 |
| `POST /api/auth/login/` | 200, access in body, refresh in an httpOnly cookie |
| Inspect the login response body | contains **no** refresh token |
| `document.cookie` in the browser console | refresh token **not** visible |
| `GET /api/auth/me/` with the Bearer header | your athlete |
| `GET /api/auth/me/` with no header | 401 |
| `POST /api/auth/refresh/` | new access token, cookie rotated |
| Reuse the OLD refresh token after a rotation | 401 — proves the blacklist migrated |
| `PATCH /api/athlete/` with `timezone: "Asia/Kolkata"` | 200 |
| `PATCH` with `timezone: "Mars/Olympus"` | 400, not a silent fallback to UTC |
| `PATCH` with `garmin_connected: true` | ignored, stays false |
| `PATCH` with all `available_days` false | 400 |
| `athlete.local_today` at 00:30 IST | today in Kolkata, **not** yesterday in UTC |
| `POST /api/auth/logout/`, then `refresh/` with the old cookie | 401 — logout actually revoked |

The timezone test is the one to actually run rather than assume. Set your machine's clock
if you have to — it is the bug class that cost `run-project` the most.

---

## What Claude builds alongside

Registration and login screens, the onboarding flow (timezone, available days, long-run
day), a settings page for every editable field, and the token layer: access token kept in
a module variable, a fetch wrapper that attaches the Bearer header, a refresh-on-load
call, and a single-flight retry that refreshes once on a 401 and replays the request
rather than bouncing you to login mid-session.

Tell me when `/api/auth/me/` answers and I will wire the frontend to it.
