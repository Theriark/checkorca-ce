#!/usr/bin/env bash
# Smoke test of the SMTP listener (C4-I): one synthetic e-mail to the worker on
# port 2525, asserted through the API on port 8080. CI runs it in job 9 (compose
# smoke) after `docker compose up -d --build --wait`; it also works against any
# running install:
#
#   bash scripts/smoke.sh
#
# On a fresh install it creates the first admin (smoke.admin@example.com) with a
# throwaway password. On an install that already has users, set
# SMOKE_ADMIN_EMAIL and SMOKE_ADMIN_PASSWORD. It creates one smtp inbox labelled
# synthetic, sends one message twice, expects exactly one stored row with the
# message's Message-ID and subject, and deletes the inbox again. Only the Python
# standard library is needed; nothing secret is printed.
#
# SMOKE_BASE_URL (http://localhost:8080), SMOKE_SMTP_HOST (localhost) and
# SMOKE_SMTP_PORT (2525) point it elsewhere.
set -euo pipefail

export SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost:8080}"
export SMOKE_SMTP_HOST="${SMOKE_SMTP_HOST:-localhost}"
export SMOKE_SMTP_PORT="${SMOKE_SMTP_PORT:-2525}"

exec python3 - <<'PY'
import email.utils
import json
import os
import secrets
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage

BASE = os.environ["SMOKE_BASE_URL"].rstrip("/")
SMTP_HOST = os.environ["SMOKE_SMTP_HOST"]
SMTP_PORT = int(os.environ["SMOKE_SMTP_PORT"])
SESSION_COOKIE = "checkorca_session"


def fail(message):
    print(f"smoke: FAIL {message}", file=sys.stderr)
    sys.exit(1)


class Api:
    """JSON calls with the session cookie and CSRF token of one sign-in.

    The cookie is kept by hand: it is Secure, and the compose install answers
    on plain http://localhost.
    """

    def __init__(self):
        self.cookie = None
        self.csrf = None

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(BASE + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        if self.csrf and method != "GET":
            request.add_header("X-CSRF-Token", self.csrf)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status, raw, headers = response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            status, raw, headers = error.code, error.read(), error.headers
        for value in headers.get_all("Set-Cookie") or []:
            name, _, rest = value.partition("=")
            if name.strip() == SESSION_COOKIE:
                self.cookie = f"{SESSION_COOKIE}={rest.split(';', 1)[0]}"
        found = json.loads(raw) if raw and "json" in headers.get_content_type() else None
        return status, found


def sign_in(api):
    address = os.environ.get("SMOKE_ADMIN_EMAIL", "smoke.admin@example.com")
    password = os.environ.get("SMOKE_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
    account = {"email": address, "password": password}
    status, body = api.call("POST", "/api/v1/auth/first-run", account)
    if status == 404:
        # Users exist: sign in with SMOKE_ADMIN_EMAIL and SMOKE_ADMIN_PASSWORD.
        status, body = api.call("POST", "/api/v1/auth/login", account)
    if status not in (200, 201) or not body:
        fail(f"sign-in answered {status}")
    api.csrf = body["csrf_token"]


def synthetic_message(to):
    message = EmailMessage()
    message["From"] = "Backup Server <backup@example.com>"
    message["To"] = to
    message["Subject"] = "[Success] Nightly server backup (synthetic smoke test)"
    message["Date"] = email.utils.formatdate(usegmt=True)
    message["Message-ID"] = f"<smoke-{uuid.uuid4().hex}@example.com>"
    message.set_content(
        "Synthetic smoke test of Checkorca-CE.\n"
        "Job: Nightly server backup\nResult: Success\n"
    )
    return message


def send(message, wait_seconds=60):
    """Deliver over SMTP; the listener starts once the worker holds its lock."""
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            with smtplib.SMTP(
                SMTP_HOST, SMTP_PORT, local_hostname="smoke.test", timeout=10
            ) as client:
                refused = client.send_message(message)
        except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused) as error:
            fail(f"SMTP refused the message ({type(error).__name__} {error})")
        except OSError as error:
            if time.monotonic() > deadline:
                fail(f"SMTP {SMTP_HOST}:{SMTP_PORT} not reachable ({type(error).__name__})")
            time.sleep(2)
            continue
        if refused:
            fail(f"SMTP refused recipients: {sorted(refused)}")
        return


def stored(api, inbox_id):
    query = urllib.parse.urlencode({"inbox_id": inbox_id})
    status, body = api.call("GET", f"/api/v1/messages?{query}")
    if status != 200:
        fail(f"GET /api/v1/messages answered {status}")
    return body["items"]


def main():
    api = Api()
    sign_in(api)
    status, inbox = api.call(
        "POST", "/api/v1/inboxes", {"kind": "smtp", "label": "Smoke test (synthetic)"}
    )
    if status != 201:
        fail(f"POST /api/v1/inboxes answered {status}")
    try:
        message = synthetic_message(inbox["address"])
        send(message)
        deadline = time.monotonic() + 30
        while not (items := stored(api, inbox["id"])):
            if time.monotonic() > deadline:
                fail("the message did not appear in GET /api/v1/messages")
            time.sleep(1)
        if [item["message_id"] for item in items] != [message["Message-ID"]]:
            fail(f"expected one message with the sent Message-ID, found {len(items)}")
        if items[0]["subject"] != message["Subject"]:
            fail("the stored subject differs from the sent one")
        # The same message again is accepted and stored once.
        send(message, wait_seconds=0)
        if len(stored(api, inbox["id"])) != 1:
            fail("the same Message-ID was stored twice")
        print(f"smoke: OK, message {items[0]['id']} stored once via SMTP port {SMTP_PORT}")
    finally:
        status, _ = api.call("DELETE", f"/api/v1/inboxes/{inbox['id']}")
        if status != 204:
            print(f"smoke: warning, inbox delete answered {status}", file=sys.stderr)


main()
PY
