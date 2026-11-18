"""Session cookie, CSRF and lockout rules.

The cookie checkorca_session holds a random secret (HttpOnly, Secure,
SameSite=Lax); the app_session row keeps its SHA-256. A session expires 12 hours
after its last use: each request moves the expiry, at most once a minute; seven
days after sign-in it ends however often it is used. Every
state-changing request of a session must send the session's CSRF token in the
X-CSRF-Token header. Five failed sign-ins lock an account for five minutes.
"""

import hmac
from datetime import timedelta

from fastapi import Response

SESSION_COOKIE = "checkorca_session"
CSRF_HEADER = "X-CSRF-Token"
SESSION_TTL = timedelta(hours=12)
# However often a session is used, it ends this long after sign-in.
SESSION_MAX_AGE = timedelta(days=7)
# last_seen_at and expires_at move at most once per interval and session.
TOUCH_INTERVAL = timedelta(minutes=1)
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=5)


def set_session_cookie(response: Response, secret: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        secret,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax"
    )


def csrf_matches(expected: str, provided: str | None) -> bool:
    """Constant-time comparison of the header with the session's token."""
    if not provided:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))
