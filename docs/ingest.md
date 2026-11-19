# Ingest: data model, worker and the contract for the receivers

Phase C4-B built the store, the worker loop and the read API. Phase C4-I (Integration and Protocol Engineer) builds the receivers (SMTP, IMAP, HTTP ingest, ping, upload) against this contract without changing the C4-B code. Sources: dev-work-plan rev 35 (C4 and the Interfaces chapter), rnd-report-2 5.4, 5.7, 5.9 to 5.11.

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
- `imap` inbox: host, port (993), username, folder (`INBOX`), poll_seconds (60 to 86400, default 300), tls (true). The password is write-only: the API stores `SecretBox.encrypt(password)` and answers `secret_set` plus a masked hint (`****` and the last four characters, or `****` for short ones).
- `upload` inbox: the target of `.eml` uploads; no address and no URL.
- Deleting an inbox stops its address, URL and token at once; its messages stay with `inbox_id` NULL until the purge.

Lookups for the receivers, always with the `SYSTEM` principal and the context's policy (`app/repos/inboxes.py`):

```python
inboxes = InboxRepository(db, context.policy)
inbox = await inboxes.find_by_code(SYSTEM, local_part, kinds=("smtp",))           # RCPT TO
inbox = await inboxes.find_by_code(SYSTEM, inbox_code, kinds=("smtp", "webhook"))  # POST ingest/email
inbox = await inboxes.find_by_token(SYSTEM, bearer_value)                          # webhook token
```

## store_raw

```python
from app.ingest.store import MAX_MESSAGE_BYTES, MessageTooLarge, StoredRaw, store_raw

stored: StoredRaw = await store_raw(
    db,                 # AsyncSession; store_raw never commits
    policy,             # AccessPolicy (context.policy or services.policy)
    principal,          # SYSTEM in receivers; the caller's Principal in routes
    inbox_id=inbox.id,  # the inbox the message arrived in
    raw=raw,            # bytes as received (RFC 822)
    received_at=now,    # aware datetime from the injected Clock
)
await db.commit()       # then answer 250 / mark Seen / answer 202
```

- `len(raw) > MAX_MESSAGE_BYTES` (5 MiB) raises `MessageTooLarge` before anything is read or written. The SMTP listener also refuses oversize DATA itself (SIZE and a `handle_DATA` length check).
- Duplicates: the same `Message-ID` header, or the same `body_sha256`, in the same inbox, stores nothing and returns `StoredRaw(id=<earlier row>, duplicate=True)`. Two unique constraints decide, so two deliveries at the same moment still store one row (the second waits for the first transaction). `body_sha256` is SHA-256 of the `Date` header and the body with line endings normalised: a forwarded copy with a new Message-ID is a duplicate, while a script that mails the same words every day is not.
- A stored message gets `sha256`, `size`, decoded headers (at most 200, values at most 4,000 characters, RFC 2047 decoded, invalid bytes replaced, NUL removed), `body_zlib`, `parse_state` `pending` and `purge_after = received_at + settings.retention_raw_days`; the inbox's `last_message_at` moves forward.
- Duplicates are counted once: a receiver answers success for a duplicate (250, 202) and records nothing else.
- The parser (C5-B) reads `parse_state = 'pending'` rows with SKIP LOCKED; `app.ingest.store.raw_bytes(body_zlib)` decompresses with the same 5 MiB cap; `app.ingest.mime.message_text(raw)` gives the text (C4-I's `html_text.py` should replace the HTML branch).

## record_result

```python
from app.ingest.results import ParsedResult
from app.ingest.store import ResultRejected, record_result

result_id = await record_result(
    db, policy, principal,
    ParsedResult(status="success", job_name="Nightly server backup",
                 client_hint="Fictional Dental Clinic", started_at=..., finished_at=...,
                 run_id="...", details={...}),
    received_at=now,
    job_id=job.id,            # known job (ping, POST results with job_id or ping_token); else None
    raw_message_id=None,      # the stored message, for parsed mail
)
await db.commit()
```

- `ParsedResult` fields follow the Interfaces chapter: `status` (`success`, `warning`, `failed`, `started`, `unknown`), `job_name`, `client_hint`, `started_at`, `finished_at` (aware datetimes), `run_id`, `details` (JSON object), `spans` (test bench only, not stored).
- `ResultRejected` (a `ValueError`; its text names the field, never the value) for an unknown status, a name, hint or run id over 200 characters, a naive datetime, details that are not JSON, contain NUL or exceed 16 KiB. Routes answer 422 with it.
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
    async def start(self, context: WorkerContext) -> None: ...   # start serving and return
    async def stop(self) -> None: ...                            # stop and release everything

type ReceiverFactory = Callable[[WorkerContext], Receiver]
RECEIVERS: tuple[ReceiverFactory, ...] = ()   # C4-I adds the SMTP listener and the IMAP poller
```

`WorkerContext` carries `settings` (`smtp_port` 2525, `inbox_domain`), `engine`, `sessionmaker`, `clock`, `policy` (CE: AllowAllPolicy) and `secret_box`. Receivers run only while the worker holds the lock, so exactly one SMTP listener and one IMAP poller exist per installation. A receiver that fails to start is logged and skipped; the worker keeps ticking. C4-I's SMTP abstraction (aiosmtpd or the own fallback receiver) implements this `Receiver`.

IMAP: decrypt with `context.secret_box.decrypt(inbox.imap_password_enc)` only inside the poller, build `app.ext.ingest.MailboxAccount` (its repr hides the password), and acknowledge (Seen) only after `store_raw` committed. `MailboxConnector` and `ResultSource` (`app/ext/ingest.py`) are the seams EE implements later.

## HTTP routes C4-I adds

| Route | Auth | Contract |
| --- | --- | --- |
| `POST /api/v1/ingest/email/{inbox_code}` | `Authorization: Bearer` with an ingest-scope API token, or the inbox's own webhook token (only for its own inbox) | raw RFC 822 body; `find_by_code(kinds=("smtp", "webhook"))`, 404 for an unknown code; 413 above 5 MiB; `store_raw`; 202 with `message_id` (the stored row id) and `duplicate` |
| `POST /api/v1/results` | ingest-scope API token | ParsedResult plus `job_id`, `ping_token`, or `client_hint` and `job_name`; `record_result`; 202 |
| `GET/POST /api/v1/ping/{ping_token}[/start|/fail]` | the ping token | `JobRepository` lookup by ping token; `record_result` with `success`, `started` or `failed`; 200 `OK`; 120 a minute per token |
| `POST /api/v1/messages/upload` | session (CSRF) | multipart `file` and `inbox_id`; `store_raw` into that inbox |

The read routes are in place: `GET /inboxes`, `/inboxes/{id}`, `/messages`, `/messages/{id}`, `/results`, `/jobs/{id}/results`, `/system/status`. Token-authenticated routes are not session routes: `tests/api/test_csrf_api.py` reads every state-changing route from the app, so C4-I adds them to its exemption list with the reason.

## Readiness and System status

- `/readyz` answers 200 only when the database answers and the heartbeat is younger than 3 minutes; otherwise 503 with `worker` = `missing`, `stale` or `unknown`. `ROLE=all` (Dokploy) runs the worker in the same container, so Development stays ready while its worker ticks.
- `GET /api/v1/system/status`: `worker` (`heartbeat_at`, `age_seconds`, `stale`, `holder`, `started_at`), `inboxes` (`id`, `kind`, `label`, `last_message_at`), `queue.pending_messages`, `version`, `revision`. C8-B adds the notification queues and the evaluator lag.
