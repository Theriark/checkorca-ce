# Ingest: data model, worker and the contract for the receivers

Phase C4-B built the store, the worker loop and the read API. Phase C4-I (Integration and Protocol Engineer) built the receivers (SMTP, IMAP, HTTP ingest, results, ping, upload) on this contract; they are described in [Receivers](#receivers-c4-i). Sources: dev-work-plan rev 35 (C4 and the Interfaces chapter), rnd-report-2 5.4, 5.7, 5.9 to 5.11.

## Tables (revision `c4_ingest`)

| Table | Holds | Client delete map |
| --- | --- | --- |
| `inbox` | kind (`smtp`, `imap`, `webhook`, `upload`), label, `code`, webhook `token_sha256`, IMAP settings with `imap_password_enc` (Fernet), `sender_allowlist`, `require_auth_results`, `last_message_at` | no (holds no client data) |
| `raw_message` | `inbox_id` (NULL after the inbox is deleted), `client_id`, `received_at`, `message_id`, `sha256` (of the bytes), `body_sha256` (duplicate key), `size`, `headers` (JSONB `[[name, value], ...]`), `body_zlib`, `parse_state` (`pending`, `parsed`, `unmatched`, `error`), `purge_after` | yes: rows with the client's `client_id` |
| `job_result` | `job_id` (NULL while unmatched), `client_hint`, `job_name`, `status` (`success`, `warning`, `failed`, `started`, `unknown`), `started_at`, `finished_at`, `received_at`, `raw_message_id`, `run_id`, `details` (JSONB) | yes: results of the client's jobs and of the client's messages |
| `worker_heartbeat` | one row (id 1): `beat_at`, `holder`, `started_at` | no |

`raw_message.client_id` stays NULL until the matcher (C5-B) binds the message's results. C5-B sets it when every result of the message belongs to jobs of one client; a message that names several clients (a digest) keeps NULL and is removed by the retention purge, not by a client delete.

## Inboxes

- `code`: 24 random lower-case letters and digits (`app.security.tokens.new_inbox_code`), unique, stored plain because the SMTP listener looks it up at RCPT time. Codes are compared in lower case.
- `smtp` inbox: address `code@MAIL_DOMAIN`. `MAIL_DOMAIN` is a setting (code default empty: the host of `BASE_URL`, so Development uses `code@ce-dev-checkorca.theriark.dev`). `Settings.inbox_domain` gives the domain.
- `smtp` and `webhook` inboxes: ingest URL `BASE_URL/api/v1/ingest/email/{code}`.
- `webhook` inbox: a token `chki_` plus 24 random bytes (URL-safe base64), returned once by `POST /inboxes` (`webhook_token`) and by `POST /inboxes/{id}/token` (rotation), stored as SHA-256. The API answers only `webhook_token_set`.
- `imap` inbox: host, port (993), username, folder (`INBOX`), poll_seconds (60 to 86400, default 300), tls (true). The password is write-only: the API stores `SecretBox.encrypt(password)` and answers `secret_set` plus a masked hint (`****` and the last four characters, or `****` for passwords under 12 characters). The hint is the C1 helper (`mask_hint`) that the settings secrets already use, so a technician can tell which password is stored; decision recorded on THE-2008.
- `upload` inbox: the target of `.eml` uploads; no address and no URL.
- Deleting an inbox stops its address, URL and token at once; its messages stay with `inbox_id` NULL until the purge.

Lookups for the receivers, always with the `SYSTEM` principal and the context's policy (`app/repos/inboxes.py`):

```python
inboxes = InboxRepository(db, context.policy)
# RCPT TO
inbox = await inboxes.find_by_code(SYSTEM, local_part, kinds=("smtp",))
# POST ingest/email/{inbox_code}
inbox = await inboxes.find_by_code(SYSTEM, inbox_code, kinds=("smtp", "webhook"))
# A webhook inbox's own token
inbox = await inboxes.find_by_token(SYSTEM, bearer_value)
```

## store_raw

```python
from app.ingest.store import MAX_MESSAGE_BYTES, MessageTooLarge, StoredRaw, store_raw

# store_raw never commits: the caller commits, then answers 250, marks the
# message Seen or answers 202.
stored: StoredRaw = await store_raw(
    db,  # AsyncSession
    policy,  # context.policy or services.policy
    principal,  # SYSTEM in receivers; the caller's Principal in routes
    inbox_id=inbox.id,  # the inbox the message arrived in
    raw=raw,  # bytes as received (RFC 822)
    received_at=now,  # aware datetime from the injected Clock
)
await db.commit()
```

- `len(raw) > MAX_MESSAGE_BYTES` (5 MiB) raises `MessageTooLarge` before anything is read or written. The SMTP listener also refuses oversize DATA itself (SIZE and a `handle_DATA` length check).
- Duplicates: the same `Message-ID` header, or the same `body_sha256`, in the same inbox, stores nothing and returns `StoredRaw(id=<earlier row>, duplicate=True)`. Two unique constraints decide, so two deliveries at the same moment still store one row (the second waits for the first transaction). `body_sha256` is SHA-256 of the `Date`, `From`, `To` and `Subject` headers and the body with line endings normalised: a forwarded copy with a new Message-ID is a duplicate, while two alerts that differ only in the Subject, or the same words on another day, are not. A message without a `Date` header gets a key of its own, so only its Message-ID can make it a duplicate (the SMTP listener and the HTTP route do not add a Date).
- A stored message gets `sha256`, `size`, decoded headers (at most 200, values at most 4,000 characters, RFC 2047 decoded, invalid bytes replaced, NUL removed), `body_zlib`, `parse_state` `pending` and `purge_after = received_at + settings.retention_raw_days`; the inbox's `last_message_at` moves forward.
- Duplicates are counted once: a receiver answers success for a duplicate (250, 202) and records nothing else.
- The parser (C5-B) reads `parse_state = 'pending'` rows with SKIP LOCKED; `app.ingest.store.raw_bytes(body_zlib)` decompresses with the same 5 MiB cap; `app.parsers.engine.mail_from_raw(raw)` gives the headers and the visible text (`app.ingest.mime.message_text`, HTML through `html_text.py`) the engine reads. The engine is described in [docs/parsers.md](parsers.md).

## record_result

```python
from app.ingest.results import ParsedResult
from app.ingest.store import ResultRejected, record_result

result_id = await record_result(
    db,
    policy,
    principal,
    ParsedResult(
        status="success",
        job_name="Nightly server backup",
        client_hint="Fictional Dental Clinic",
        started_at=...,
        finished_at=...,
        run_id="...",
        details={...},
    ),
    received_at=now,
    job_id=job.id,  # the known job (ping, results API with job_id); else None
    raw_message_id=None,  # the stored message, for parsed mail
)
await db.commit()
```

- `ParsedResult` fields follow the Interfaces chapter: `status` (`success`, `warning`, `failed`, `started`, `unknown`), `job_name`, `client_hint`, `started_at`, `finished_at` (aware datetimes), `run_id`, `details` (JSON object), `spans` (test bench only, not stored). A `Span` is `field`, `start`, `end` and `source`: `body` (the visible text, the default) or the `subject`, `from` or `to` header the offsets count in (added by C5-I; additive, the default keeps C4 callers unchanged).
- `ResultRejected` (a `ValueError`; its text names the field, never the value) for an unknown status, a name, hint or run id over 200 characters, a naive datetime, details that are not JSON, hold a NUL character (in a key or a value at any depth, a tuple or list value included: the check reads the details as they are stored; C5-I, THE-2011 note 1) or a lone surrogate, or exceed 16 KiB. Routes answer 422 with it.
- Never commits; never changes `parse_state` (C5-B does).

## Worker: lock, heartbeat, tick hooks, receivers

`app/worker/loop.py`. The worker role (`python -m app worker`, and `all` beside the web server) runs `Worker(context).run(stop)`:

1. Takes the advisory lock `WORKER_LOCK` (4_270_003, `app/db/locks.py`) on a dedicated autocommit connection; a second worker logs once and retries every 15 seconds without ticking.
2. Starts every receiver of `RECEIVERS`, then ticks every 60 seconds on the injected `Clock`: writes the heartbeat row (`beat_at`, `holder` = host name and pid, `started_at`), then runs every hook of `TICK_HOOKS` with `(context, now)`. A hook error is logged (class and frames, no text) and never stops the tick.
3. A lost lock connection stops the receivers and goes back to step 1. `stop` (SIGTERM) stops the receivers, unlocks and returns.

The Receiver hook point for C4-I:

```python
class Receiver(Protocol):
    name: str

    async def start(self, context: WorkerContext) -> None:
        """Start serving and return."""

    async def stop(self) -> None:
        """Stop serving and release everything."""


type ReceiverFactory = Callable[[WorkerContext], Receiver]
# C4-I: the SMTP listener on SMTP_PORT and the IMAP poller.
RECEIVERS: tuple[ReceiverFactory, ...] = (SmtpReceiver, ImapPoller)
```

`WorkerContext` carries `settings` (`smtp_port` 2525, `inbox_domain`), `engine`, `sessionmaker`, `clock`, `policy` (CE: AllowAllPolicy) and `secret_box`. Receivers run only while the worker holds the lock, so one SMTP listener and one IMAP poller run per installation. Between ticks the holder checks its lock every 15 seconds: after a lost lock session the old and the new holder's receivers can overlap for about that long, and the duplicate keys of the store keep one row per message. A receiver that fails to start is logged and skipped; the worker keeps ticking.

IMAP: decrypt with `context.secret_box.decrypt(inbox.imap_password_enc)` only inside the poller, build `app.ext.ingest.MailboxAccount` (its repr hides the password), and acknowledge (Seen) only after `store_raw` committed. `MailboxConnector` and `ResultSource` (`app/ext/ingest.py`) are the seams EE implements later.

## Receivers (C4-I)

Every channel calls `accept_message` (`app/ingest/receive.py`): the 5 MB cap with at most 256 KB of headers, the inbox's sender rules, then `store_raw`. Its callers commit and only then answer 250, mark the mail Seen or answer 202. A duplicate (same Message-ID or content hash in the same inbox) counts as success and stores nothing.

Untrusted headers cost bounded time: the size and sender checks run in a thread, off the event loop, and a header value is cut to 8,000 characters before RFC 2047 decoding (`mime.header_value`; Python's decoder is quadratic, so an uncut 5 MB header took minutes and froze the loop).

### Sender checks

- `sender_allowlist` (empty: anyone): every address of the `From` header must be listed, as itself (`alerts@example.com`) or by its domain (`@example.com`). Subdomains are not included. A message without a From address is refused.
- `require_auth_results`: the topmost `Authentication-Results` header must report `dkim=pass` with a signing domain equal to the From domain or a parent domain of it. The signing domain is `header.d`, else the domain of `header.i` (after its last `@`; a local part chosen by the signer never counts, and a `header.i` without an `@` counts for nothing). The header is parsed as sent, without RFC 2047 encoded-word decoding, and whole: one longer than 8,000 characters once unfolded counts as no `dkim=pass` (a cut value could end inside a domain). Before it is split into results at `;`, one left-to-right pass turns every comment into a space and every quoted string, such as a quoted local part `"a@example.com"@example.net`, into one opaque word: neither a `;`, an `@` nor a property inside it counts. Only a quoted string that is the whole `header.d` or `header.i` value and a plain domain or address (`header.d="example.com"`) keeps its text; it is the whole value when nothing but whitespace or comments stands between it and the end, a `;` or the next property. Whitespace, a fold, a comment or a `.` before an `@` still make the quoted text a local part (`header.i="a@example.com" (x) @example.net` names example.net). A header with a quote or parenthesis left over after that pass (an unbalanced quote or a nested comment) counts as no `dkim=pass`. The header is written by the mail server that received the message, so the check helps for an IMAP mailbox or a forwarder behind such a server. A sender that talks to the SMTP listener directly can write its own header: the inbox address (24 random characters) stays the real secret, and docs/security.md (C11) records this residual risk.
- A refusal stores nothing. Its reason is a fixed text that names no address: SMTP `550 5.7.1`, HTTP 422 `Message refused`, IMAP marks the message Seen (it would be refused again) and counts it in the log.

### SMTP listener (`app/ingest/smtp.py`)

aiosmtpd 1.4.6 on the worker's event loop, port `SMTP_PORT` (2525) on all interfaces of the container. It never relays, sends no bounce and needs no authentication.

| Step | Rule | Answer |
| --- | --- | --- |
| connect | at most 20 connections at a time and 3 per source IP address; greeting `Checkorca-CE ESMTP` (no library version) | `421 4.7.0` past either |
| idle | 30 seconds without a command closes the connection (DATA included: a 5 MB message must arrive within 30 s of the DATA command) | connection closed |
| MAIL | 60 messages a minute per source IP address (token bucket); `SIZE=` above 5 MB | `451 4.7.1`; `552` |
| RCPT | `code@MAIL_DOMAIN` of an smtp inbox, code compared in lower case; anything else, a webhook inbox's code or another domain included | `550 5.1.1 No such inbox` |
| RCPT | at most 20 recipients per message | `452 4.5.3` |
| RCPT | at most 10 unknown addresses per connection | `421 4.7.0` to the 11th, then the connection closes |
| DATA | 5 MB (aiosmtpd's SIZE limit, and again in `handle_DATA`), of which at most 256 KB of headers | `552` |
| DATA | stored once per inbox in one transaction, committed before the answer; sender rules per inbox | `250 2.0.0`; `550 5.7.1` when every inbox refuses |
| any | a database error or an unexpected error | `451 4.3.0` (the sender retries; the duplicate keys keep one row) |

The per-source limits see the peer address of the TCP connection. Anything in front of port 2525 that does not keep the client address collapses its senders into one source that shares the 3 sessions and 60 messages a minute: Docker's userland proxy does this for IPv6 clients on a bridge network without IPv6, and so does a TCP proxy without PROXY protocol (Swarm ingress, a Traefik TCP router). Publish 2525 on IPv4 only (`0.0.0.0:2525:2525`) or with host networking where that matters.

STARTTLS is offered when `SMTP_TLS_CERT_FILE` and `SMTP_TLS_KEY_FILE` name PEM files mounted into the container (both or neither; TLS 1.2 or newer). With `ROLE` `worker` or `all` both files must exist and be readable, or the process refuses to start: a missing file would otherwise leave port 2525 closed while `/readyz` answers 200. Without them the listener speaks plain SMTP. Logs carry counts only; aiosmtpd's own logger (`mail.log`, which writes addresses) is kept at error level.

### IMAP poller (`app/ingest/imap.py`)

Every 30 seconds the poller polls each imap inbox whose `poll_seconds` have passed, one inbox at a time, with imaplib in a thread (30 s socket timeout). TLS (port 993) verifies the server's certificate and name; `tls` false is plain IMAP for a server on the MSP's own network, and sends the password unencrypted. The IMAP host is set by a signed-in admin or technician and is not filtered like outbound webhooks: MSPs read mailboxes on internal servers. Because the poller signs in with the stored password, `PATCH /inboxes/{id}` refuses a new host, port, TLS setting or user name with 422 unless the password is sent again: the stored one never goes to a server it was not given for.

1. Decrypt the password into a `MailboxAccount` (only here).
2. `UID SEARCH UNSEEN`, at most 50 messages, sizes first; bodies with `BODY.PEEK[]`, so nothing becomes Seen by being read. A message over 5 MB is not downloaded: it is marked Seen and counted in a warning.
3. `accept_message` and commit, one message per transaction.
4. `UID STORE +FLAGS (\Seen)` for what was stored, was a duplicate or was refused. A message whose store failed stays unseen and is fetched again by the next poll. A ref is `UIDVALIDITY:UID`, so a rebuilt folder never gets the wrong message marked.

A failed login or a lost connection is logged with the inbox id and the error class and tried again at the inbox's next poll; one failing inbox never stops the others.

### HTTP routes (`app/api/v1/ingest.py`)

| Route | Auth | Contract |
| --- | --- | --- |
| `POST /api/v1/ingest/email/{inbox_code}` | `Authorization: Bearer` with an ingest-scope API token (any smtp or webhook inbox), or a webhook inbox's own `chki_` token (only its own inbox, else 403) | raw RFC 822 body (`message/rfc822`); 401 without a valid token, 403 for a read token; 404 for an unknown code or another kind; 413 above 5 MiB or 256 KB of headers; 422 for an empty body, a body without From, Subject, Date or Message-ID headers, or the sender rules; 202 `{message_id, duplicate}` |
| `POST /api/v1/results` | ingest-scope API token | `NewResult`: `status`, `job_id` or `ping_token` (404 when no job has it; not both), else `client_hint` and `job_name` (not blank); `started_at` and `finished_at` with a time zone; `run_id`; `details` (JSON object, at most 16 KiB); 422 for anything else; 202 `{result_id, job_id}` (`job_id` null until the matcher binds it) |
| `GET` or `POST /api/v1/ping/{ping_token}`, `/ping/{ping_token}/start`, `/ping/{ping_token}/fail` | the ping token in the URL | records `success`, `started` or `failed` for the job with `details` `{"source": "ping"}`; 200 `text/plain` `OK`; 404 for an unknown token, 422 for a malformed one |
| `POST /api/v1/messages/upload` | session with `X-CSRF-Token`, admin or technician | multipart `file` (the .eml, read up to 5 MiB) and `inbox_id` (any kind); 404 for an unknown inbox; the same 413 and 422 rules; audit event `message.upload`; 202 `{message_id, duplicate}` |

Rate limits: 120 requests a minute per API token (all its routes), per webhook inbox token and per ping URL, then 429 with `Retry-After`. Only a known credential spends a bucket, so unknown tokens cannot push real ones out of the limiter. Request bodies are capped by the middleware (`BODY_LIMITS`): 5 MiB for raw mail, 5 MiB plus 16 KiB of multipart framing for the upload, 64 KiB elsewhere.

The token routes read no cookie, so they need no CSRF token: their credential is the Authorization header or the URL, which a cross-site form cannot send or does not know. `tests/api/test_csrf_api.py` lists them as `TOKEN_ROUTES` and checks that a signed-in browser without a token writes nothing. A ping URL records a result on GET too (curl, wget and schedulers use GET); treat the URL like a password.

The read routes: `GET /inboxes`, `/inboxes/{id}`, `/messages`, `/messages/{id}`, `/results`, `/jobs/{id}/results`, `/system/status`. A message detail gives the visible text of an HTML-only mail (`app/ingest/html_text.py`, the first 1 MB of the HTML: script, style, title and comments dropped, entities decoded); the web app shows it escaped.

### Smoke test

`scripts/smoke.sh` runs in CI job 9 after `docker compose up`: it creates the first admin with a throwaway password, an smtp inbox, sends one synthetic message to the worker on port 2525 twice and expects one row with its Message-ID and subject in `GET /api/v1/messages`, then deletes the inbox. Against an install that has users, set `SMOKE_ADMIN_EMAIL` and `SMOKE_ADMIN_PASSWORD`.

## Readiness and System status

- `/readyz` answers 200 only when the database answers and the heartbeat is younger than 3 minutes; otherwise 503 with `worker` = `missing`, `stale` or `unknown`. `ROLE=all` (Dokploy) runs the worker in the same container, so Development stays ready while its worker ticks.
- `GET /api/v1/system/status`: `worker` (`heartbeat_at`, `age_seconds`, `stale`, `holder`, `started_at`), `inboxes` (`id`, `kind`, `label`, `last_message_at`), `queue.pending_messages`, `version`, `revision`. C8-B adds the notification queues and the evaluator lag.
