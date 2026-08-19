"""Health check that actually checks.

A health endpoint returning a constant is worse than none: it turns a real outage
into a green dashboard. This one opens a cursor and pings Redis, and names the
dependency that failed rather than answering a bare 503.
"""

import json

from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def _check_db() -> tuple[bool, str]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, ""
    except Exception as exc:  # noqa: BLE001 — the reason is the payload
        return False, str(exc)


def _check_redis() -> tuple[bool, str]:
    try:
        import redis

        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def health(request):
    db_ok, db_error = _check_db()
    redis_ok, redis_error = _check_redis()
    ok = db_ok and redis_ok

    payload = {"status": "ok" if ok else "degraded", "db": db_ok, "redis": redis_ok}
    if not ok:
        payload["errors"] = {
            k: v for k, v in (("db", db_error), ("redis", redis_error)) if v
        }
    return JsonResponse(payload, status=200 if ok else 503, json_dumps_params={"indent": None})
