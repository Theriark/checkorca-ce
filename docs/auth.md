# Sign-in, sessions, API tokens and the access layer (phase C1)

What phase C1-B built and the rules the later phases rely on. The endpoints are in [openapi.json](openapi.json); `tests/api/test_openapi_snapshot.py` keeps that file equal to the app (regenerate it with `python -m tools.openapi_snapshot`).

## Endpoints (`/api/v1`)

| Route | Who | What |
| --- | --- | --- |
| `GET auth/setup-state` | anyone | `needs_first_run`: true while no user exists |
| `GET auth/first-run` | anyone | 200 while no user exists, 404 once one does |
| `POST auth/first-run` | anyone, once | creates the first admin and signs in (201); 404 once any user exists |
| `POST auth/login` | anyone | `user` and `csrf_token`; 401 for a wrong address or password, 423 while locked, 429 when rate limited |
| `POST auth/logout` | session | ends this session (204) |
| `GET auth/me` | session | `id`, `email`, `role`, `csrf_token` |
| `GET, POST users`; `GET, PATCH, DELETE users/{user_id}` | admin | accounts; at least one enabled admin always remains (409); an admin cannot delete their own account |
| `GET, POST tokens`; `DELETE tokens/{token_id}` | admin | API tokens; the value is returned once, by `POST`; `DELETE` revokes |

Errors are RFC 9457 problem documents (`application/problem+json`) with `request_id`; validation errors list `field` and `message` and never repeat the submitted value. Lists take `cursor` and `limit` (50, at most 200) and answer `items` and `next_cursor`.

## Sessions and CSRF

- Cookie `checkorca_session`: HttpOnly, Secure, SameSite=Lax, path `/`. It holds 32 random bytes; the `app_session` row keeps only their SHA-256.
- A session ends 12 hours after its last use. Each use moves the expiry (at most once a minute) and renews the cookie.
- Every POST, PUT, PATCH and DELETE of a session must send the session's CSRF token in `X-CSRF-Token` (from `auth/login`, `auth/first-run` or `auth/me`); otherwise 403. Only `auth/login` and `auth/first-run` are exempt: no session exists yet, and both accept only a JSON body, which a cross-site form cannot send. `tests/api/test_csrf_api.py` reads the routes from the app, so a new state-changing route is covered automatically.
- Disabling a user or setting a new password ends the user's other sessions.

## Sign-in protection

- Passwords: Argon2id (argon2-cffi defaults), 12 to 128 characters for new passwords. At most two hashes run at once (each holds 64 MiB).
- Five failed sign-ins lock the account for five minutes (423 with `Retry-After`). A new password set by an admin clears the lock.
- Rate limits (token buckets in the web process): sign-in and first run 10 a minute per client address; API tokens 120 a minute per token.
- Behind a reverse proxy the client address is the proxy's unless uvicorn trusts it: set `FORWARDED_ALLOW_IPS` to the proxy address so `X-Forwarded-For` is used. Without it every client shares one sign-in bucket.

## Headers

Every answer carries `Content-Security-Policy` (`default-src 'self'`, scripts only from the site, never inline; inline styles allowed for the UI library), `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` and `X-Request-ID`. API answers add `Cache-Control: no-store`.

## API tokens

`chk_` plus 24 random bytes (URL-safe base64). The database keeps the SHA-256 only. Scripts send `Authorization: Bearer <token>`; the scope is `ingest` or `read`. Routes that accept tokens declare `require_token("ingest")` or `require_token("read")` (`app/api/deps.py`); the ingest routes arrive in phase C4.

## Stored credentials

Columns ending in `_enc` hold Fernet ciphertext made with `FERNET_KEY` (`app/security/crypto.py`). The API never returns a stored credential, at most a masked hint (`****` and the last four characters). The first is `settings.external_heartbeat_url_enc` (used from phase C10).

## Access layer

- `Principal` (`app/access`): a user (id and role), an API token (id and scope) or the system (sign-in, session lookup, first run and seed run before anyone is signed in).
- `AccessPolicy`: `check(principal, action)` for every repository call and `scope(principal, resource, query)` for list queries. CE uses `AllowAllPolicy`; the role rules (users and tokens are admin only) sit on the routes. EE replaces the policy with per-client scopes.
- Repositories (`app/repos`): every public method takes the Principal first and is decorated with `@guarded(verb)`; a repository class with an undecorated public method fails at import time. `tests/repos/test_access_policy.py` calls every method with a refusing policy and a database that fails on use.
- Audit (`app/ext/audit.py`): `AuditSink.record(db, event)` in the caller's transaction; the CE sink writes `audit_event`. Events hold ids, the action, the client address and field names, never content.

## Development seed accounts

With `DEV_SEED=1`, `python -m app web` and `all` ensure the admin and the technician of `DEV_SEED_ACCOUNTS` (in that order) with `DEV_SEED_PASSWORD_ADMIN` and `DEV_SEED_PASSWORD_TECHNICIAN` after the migrations and before the HTTP port opens, so the first-run page of a fresh Development or Stage site is closed. `python -m app seed` does the same on its own. The seed refuses (exit code 2, nothing written) unless the `BASE_URL` host starts with `ce-dev-` or `ce-stg-` or is `localhost`, and it logs only that the accounts are ensured.

## Logs

JSON, one object per line, with `request_id` (`app/logging.py`). The access log names the route template, never the raw path or query. Exceptions keep their class and stack frames but not their text. The known secrets are replaced by `[redacted]`, and SQLAlchemy, httpx and multipart stay at warning level whatever `LOG_LEVEL` says, because they would log SQL parameters, URLs or form fields.
