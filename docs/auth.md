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

Errors are RFC 9457 problem documents (`application/problem+json`, also in the OpenAPI document) with `request_id`; validation errors list `field` and `message` and never repeat the submitted value. Lists take `cursor` and `limit` (50, at most 200) and answer `items` and `next_cursor`. Request bodies under `/api/` are limited to 64 KiB (413).

## Sessions and CSRF

- Cookie `checkorca_session`: HttpOnly, Secure, SameSite=Lax, path `/`. It holds 32 random bytes; the `app_session` row keeps only their SHA-256.
- Because the cookie is Secure, sign-in works only over HTTPS or on `localhost`. A compose install opened as `http://<lan-address>:8080` completes first run but the browser never keeps the session: put it behind TLS or use localhost.
- A session ends 12 hours after its last use. Each use moves the expiry (at most once a minute) and renews the cookie. However often it is used, a session ends 7 days after sign-in.
- Every POST, PUT, PATCH and DELETE of a session must send the session's CSRF token in `X-CSRF-Token` (from `auth/login`, `auth/first-run` or `auth/me`); otherwise 403. Only `auth/login` and `auth/first-run` are exempt: no session exists yet, and both accept only a JSON body, which a cross-site form cannot send. `tests/api/test_csrf_api.py` reads the routes from the app, so a new state-changing route is covered automatically.
- Disabling a user or setting a new password ends the user's other sessions.

## Sign-in protection

- Passwords: Argon2id (argon2-cffi defaults), 12 to 128 characters for new passwords. At most two hashes run at once (each holds 64 MiB).
- Five failed sign-ins lock the account for five minutes (423 with `Retry-After`). A new password set by an admin clears the lock. An unknown address, a disabled account and a wrong password get the same 401 after the same Argon2 work, but the 423 of the lockout shows that an address has an account, and anyone can keep a known account locked by failing five times every five minutes. Both are accepted trade-offs of the planned 423.
- Rate limits (token buckets in the web process): sign-in and first run 10 a minute per client address; API tokens 120 a minute per token.
- Behind a reverse proxy the client address is the proxy's unless uvicorn trusts it. Set `FORWARDED_ALLOW_IPS` to the proxy network (for Dokploy, the CIDR of the network Traefik connects from) so uvicorn takes the right-most untrusted `X-Forwarded-For` hop. Never use `*`: uvicorn then takes the left-most entry, which the client chooses. Without the setting every client shares one sign-in bucket and the audit trail records the proxy address. The app accepts only a parseable IP address as the client address.

## Headers

Every answer carries `Content-Security-Policy` (`default-src 'self'`, scripts only from the site, never inline; inline styles allowed for the UI library), `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` and `X-Request-ID`. When `BASE_URL` is https, `Strict-Transport-Security: max-age=31536000` too. API answers add `Cache-Control: no-store`.

## API tokens

`chk_` plus 24 random bytes (URL-safe base64). The database keeps the SHA-256 only. Scripts send `Authorization: Bearer <token>`; the scope is `ingest` or `read`. Routes that accept tokens declare `require_token("ingest")` or `require_token("read")` (`app/api/deps.py`); the ingest routes arrive in phase C4.

A job's ping URL holds its ping token, which alone lets a script report results for that job. Jobs read with an API token therefore carry `ping_url` as null; only signed-in users see it.

## Stored credentials

Columns ending in `_enc` hold Fernet ciphertext made with `FERNET_KEY` (`app/security/crypto.py`). The API never returns a stored credential, at most a masked hint (`****` and the last four characters). The first is `settings.external_heartbeat_url_enc`, the stored form of an admin-set dead-man URL of a later phase; the phase C10 watcher reads the `EXTERNAL_HEARTBEAT_URL` deployment setting instead (docs/ci-cd.md).

### FERNET_KEY rotation (C10-B)

`FERNET_KEY` may name several keys, comma-separated: every key decrypts, the first encrypts. To rotate: generate a new key, put `FERNET_KEY` as `new,old` (the new one first), deploy or restart with it, run `python -m app rotate-fernet`, and once it answers `rotated N stored credential(s)` set `FERNET_KEY` to the new key alone and restart. The command re-encrypts every `_enc` column in one transaction and prints only counts, never a key or a secret value; a row no named key can read refuses it with exit code 2 and changes nothing (an old key is still missing). While both keys are named, the server reads old and new rows alike, so the swap is never visible.

## Access layer

- `Principal` (`app/access`): a user (id and role), an API token (id and scope) or the system (sign-in, session lookup, first run and seed run before anyone is signed in).
- `AccessPolicy`: `check(principal, action)` for every repository call and `scope(principal, resource, query)` for list queries. CE uses `AllowAllPolicy`; the role rules (users and tokens are admin only) sit on the routes. EE replaces the policy with per-client scopes. The system lookups (`find_by_email`, `count`, `find_active`, `resolve`, `lock_active_admins`) do not call `scope`, so a policy must not rely on `scope` alone for them.
- Repositories (`app/repos`): every public method takes the Principal first and is decorated with `@guarded(verb)`; a repository class with an undecorated public method, or a public static or class method, fails at import time. `tests/repos/test_access_policy.py` calls every method with a refusing policy and a database that fails on use.
- Audit (`app/ext/audit.py`): `AuditSink.record(db, event)` in the caller's transaction; the CE sink writes `audit_event`. Events hold ids, the action, the client address and field names, never content.

## Development seed accounts

With `DEV_SEED=1`, `python -m app web` and `all` ensure the admin and the technician of `DEV_SEED_ACCOUNTS` (in that order) with `DEV_SEED_PASSWORD_ADMIN` and `DEV_SEED_PASSWORD_TECHNICIAN` after the migrations and before the HTTP port opens, so the first-run page of a fresh Development or Stage site is closed. `python -m app seed` does the same on its own. The seed refuses (exit code 2, nothing written) unless the `BASE_URL` host starts with `ce-dev-` or `ce-stg-` or is `localhost`, and it logs only that the accounts are ensured.

## Logs

JSON, one object per line, with `request_id` (`app/logging.py`). The access log names the route template, never the raw path or query. Exceptions keep their class and stack frames but not their text, also when `python -m app` fails outside a request (exit code 1), and database errors never carry bound parameters (`hide_parameters`). The known secrets are replaced by `[redacted]`, and SQLAlchemy, httpx and multipart stay at warning level whatever `LOG_LEVEL` says, because they would log SQL parameters, URLs or form fields.
