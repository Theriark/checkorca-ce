# Notifications

Phases C9-B and C9-I (dev-work-plan rev 35, section C9 and the Interfaces chapter: Notifications, Settings, In-process events). C9-B built the model, the dispatcher and the e-mail kind; C9-I added the kinds slack, teams and webhook and the webhook payload v1 (`docs/webhook-payload.schema.json`). This page is the contract for C9-F (the `/notifications` pages and the digest settings).

Flips are the single source of alerts (`docs/evaluator.md`): a change of a job's state becomes at most one notification per channel and event. The daily digest and the 24-hour reminder are the only other notifications.

## Model

Revision `c9_notify` adds three tables and changes none, so the previous release runs on this schema.

| Table | Fields | Notes |
| --- | --- | --- |
| `channel` | `id`, `kind` (`email`, `slack`, `teams`, `webhook`), `label`, `enabled`, `config` (JSON), `secret_enc`, `last_status` (`sent`, `failed` or null), `last_status_at`, `last_error`, `created_at`, `updated_at` | `config` holds the kind's settings without secrets. `secret_enc` is the channel's one credential (the relay password; for slack, teams and webhook the URL), Fernet ciphertext made with `FERNET_KEY`. `last_*` describe the newest real delivery, never a test. No client data. |
| `channel_rule` | `id`, `channel_id`, `scope` (`all`, `client`, `job`), `scope_id`, `events` (one or more of `failing`, `missed`, `warning`, `recovered`, `digest`), `created_at` | `scope_id` is null for `all`, else the client's or the job's id (no foreign key: it points at either table). `digest` needs scope `all`. Deleting the channel deletes its rules. |
| `notification` | `id`, `channel_id`, `flip_id`, `event` (`failing`, `missed`, `warning`, `recovered`, `reminder`, `digest`), `digest_day`, `status` (`queued`, `retrying`, `sent`, `failed`), `attempts`, `error`, `created_at`, `next_attempt_at`, `last_attempt_at`, `sent_at` | About a flip (`flip_id` set) or the digest of `digest_day` (`flip_id` null). Unique per (`flip_id`, `channel_id`, `event`) and per (`channel_id`, `digest_day`). Deleting the channel deletes its history; deleting a flip deletes its notifications (so the previous release, which does not know this table, can still delete a client). |

Client delete (legal D-3, `app/repos/client_delete.py`) removes the notifications of the client's flips and the rules whose scope is the client or one of its jobs. Channels, rules for every job, other clients' notifications and digests stay.

## Events and rule matching

`app/notify/dispatcher.py` `event_of(from_state, to_state)`:

| Flip | Event |
| --- | --- |
| to `failing`, `missed` or `warning` | the same name |
| to `ok` from `failing`, `missed` or `warning` | `recovered` |
| anything else (to or from `unknown`, `paused`, `maintenance`; `unknown` to `ok`) | none |

A channel hears about a flip when it is enabled and has at least one rule whose events contain the flip's event and whose scope covers the job: `all`, `client` with the job's client, or `job` with the job. Two matching rules of one channel still give one notification. A disabled channel queues nothing; a channel disabled after a notification was queued fails it at the next attempt (`The channel is disabled.`, no retry).

## Queueing and sending

1. The evaluator commits its batch, then delivers `FlipCreated` to the event subscribers. `build_context` (`app/worker/loop.py`) adds the `NotificationQueue` subscriber, which locks the job (`FOR KEY SHARE`, so a client delete waits or goes first), reads the matching channels, asks the `EscalationPolicy` (`app/ext/notifications.py`) and inserts one `queued` notification per planned channel with `next_attempt_at` = now plus the step's delay. CE ships `AllAtOnce`: every matching channel, no delay. An insert that meets a unique key adds nothing, so a flip delivered twice queues once.
2. The tick hook `dispatch_notifications` runs after `evaluate_jobs` on every worker tick (60 seconds, on the injected `Clock`). It first catches up: a flip of the last 15 minutes that notifies but has no notification of its event yet, while a matching channel and rule existed at the flip, is queued as in step 1 for the channels and rules that existed at the flip (at most 200 per tick). That covers a worker stopped between the evaluator's commit and the queue's, and a subscriber that failed or timed out; queueing is therefore at least once, and the unique key keeps it to one notification. The flips the demo seed replayed (up to its audit event `seed.demo`) are left alone. Then it queues the digest and the reminders (below), then sends what is due (`queued` or `retrying` with `next_attempt_at` at or before now), oldest first, at most 200 per tick, and starts no new send after 30 seconds of the tick. Each notification is claimed in its own transaction, locked with its channel (`FOR NO KEY UPDATE SKIP LOCKED`, the order of a channel delete, so the two cannot deadlock) and sent through its channel's kind, with 90 seconds for the whole delivery. An unexpected error (making the message, the database) is a failed attempt of that notification only (`The notification could not be sent (<class>).`), so one broken notification ends `failed` on the ladder and never holds up the others. A channel with an attempt to retry gets no more attempts in that tick; its other notifications wait for the next tick.
3. After the commit of an attempt that ended a notification about a flip (`sent`, or `failed` for good), `NotificationSent` (`notification_id`, `flip_id`, `channel_id`, `status`) goes to the event subscribers. Digests raise no event.

Retry ladder, on the injected clock:

| Attempt | When | On failure |
| --- | --- | --- |
| 1 | when queued | `retrying`, next attempt after 1 minute |
| 2 | +1 minute | `retrying`, next after 5 minutes |
| 3 | +5 minutes | `retrying`, next after 30 minutes |
| 4 | +30 minutes | `failed` (final) |

A success at any attempt sets `sent`, `sent_at` and clears `error`. `error` is one readable sentence from the kind, cut to 300 characters, with the channel's secret replaced by `****`; an error that is not a `DeliveryError` is stored and logged by its class and stack only, never its text. Failures retrying cannot mend (a disabled channel, a kind not registered, a secret that does not decrypt with `FERNET_KEY`) fail at once. Delivery is at least once: a crash after the relay accepted a message and before the commit sends it again.

`system/status` `queue.pending_notifications` counts `queued` and `retrying`; `queue.failed_notifications` counts the notifications that failed for good with their last attempt in the last 24 hours. The activity timeline (`kind=notification`) lists sent and failed notifications at their last attempt.

## Daily digest

The digest of a local day `D` covers the runs due in the 24 hours up to `settings.digest_time_local` of `D` in `settings.digest_timezone` (`app/notify/windows.py` `digest_window`) and is rendered by the `ReportRenderer` (`app/notify/digest.py`, the same one `digest/preview` shows): subject with counts and the date, HTML and text.

On every tick the dispatcher takes the local date `D` of now; once now has reached the digest time of `D` it queues a `digest` notification of `D` for every enabled channel with a `digest` rule that has none of `D` yet. The unique key (`channel_id`, `digest_day`) makes it once per channel and local day:

- A digest time the clocks skip (01:30 on the spring day in Europe/Lisbon, 02:30 in America/New_York) counts with the offset before the change, so it goes out one hour later on the wall clock that day.
- A digest time the clocks repeat (01:30 on the autumn day in both zones) counts at its first occurrence; the second one finds the digest sent.
- A worker that was down at the digest time sends that day's digest when it comes back the same local day; a missed day is not sent later.
- A channel created, or given a `digest` rule, after the digest time gets that day's digest at the next tick.
- A new digest time or zone counts from the next digest; a day's digest is never sent twice to a channel.

The digest names clients and jobs only inside the body (escaped in the HTML), never in the subject.

## 24-hour reminder

`settings.reminder_24h` (false by default). When true, the dispatcher queues one `reminder` per channel for a flip to `failing` or `missed` that the channel was notified of, 24 hours after the flip, while the job has had no later flip and is not acknowledged. Flips more than 26 hours old when the setting is turned on are not reminded. A reminder is retried like any other notification.

## Channel kinds

`app/ext/notifications.py` `ChannelKind`: `name`, `secret_label`, `secret_targets`, `url_key`, `check_config(config, has_secret)` and `async send(config, secret, message, outbound)`. `url_key` names the config key that carries a URL credential (`url` for slack, teams and webhook; null for email). `app/notify/registry.py` holds the registered kinds; CE registers `email`, `slack`, `teams` and `webhook`, every value of `channel.kind`. A channel whose kind is not registered (a plugin kind of a later edition) is listed with `available: false` and can only be deleted.

`Message` carries `event`, `subject`, `text`, `url`, `at` (the flip's time, the digest's `generated_at`, the test's now) and, for the digest, `html`, `digest_day` and `digest` (the `Digest` with its counts and items); for a flip or a reminder, `flip` (`FlipFacts`: flip, job and client ids and names, the job's `kind`, `from_state`, `to_state`, `reason`, `at`, `scheduled_for`, the occurrence's `deadline`, `url` of the job page). The slack, teams and webhook kinds build their bodies from `flip` and `digest`, never by parsing the text.

### email (CE)

| config key | Default | Rule |
| --- | --- | --- |
| `host` | required | host name or IP address of the admin's relay |
| `port` | 587 | 1 to 65535 |
| `starttls` | true | the relay must offer STARTTLS and present a certificate the system trusts; the login happens after it |
| `username` | null | with a user name the secret (the relay password) is required |
| `from_address` | required | one plain e-mail address (no display name, comma, angle bracket, quote or control character) |
| `to` | required | 1 to 20 plain addresses, repeats dropped |

Changing `host`, `port`, `starttls` or `username` needs the password again (422), so a stored password never follows a new target. `smtplib` runs in a thread with 20 seconds per network step and 75 seconds for the whole session, so the thread has ended before the 90-second delivery limit. Once the relay accepted the message, a bad answer to `QUIT` or a dropped connection does not count as a failure (no second copy). With `starttls` false and a user name, the password crosses the network in clear text: C9-F should warn about that in the form. Header values are single lines (a line break in a client or job name cannot add a header); messages carry `Auto-Submitted: auto-generated`. The relay host is not checked by the SSRF guard (`docs/security.md`). Development uses the Mock Platform capture relay `mock-platform:1025` with `starttls` false (simulated).

### slack, teams, webhook (C9-I)

`app/notify/webhook.py`, registered in `default_kinds()` without a schema change. All three POST one JSON body to one URL the admin chose; they differ only in the body (`app/notify/payloads.py`).

| config key | Sent | Stored and answered |
| --- | --- | --- |
| `url` | required on create: `http://` or `https://`, a host, no user name or password, no spaces or control characters, ASCII only (an international host in punycode, the path percent-encoded), at most 2,000 characters | never stored in `config`: the URL is the channel's secret (`secret_enc`, Fernet), write-only |
| `url_set` | ignored | `true` once a URL is stored |
| `url_host` | ignored | the URL's host in lower case (no port, path or query) |

- The URL is sent as `config.url`, never as `secret` (422 on `body.secret`). Its path often is the credential (a Slack or Teams incoming webhook token), so `ChannelOut` answers `config: {url_set, url_host}`, `secret_set` and the `****` hint only. Any other config key is refused (422 `Unknown setting.`).
- The target is checked by the SSRF guard before the URL is stored, on create and on a PATCH that sends a new `config.url`, and again before every send and test. A refusal is 422 `Target refused` with the guard's sentence (`errors[0].field` `body.config.url`). PATCH with `config.url` null or empty is refused: a channel cannot lose its target. A new URL replaces the stored one; `secret_targets` is empty, since the URL always arrives with its own value.
- Delivery: `check_target`, then HTTP/1.1 `POST` to one of the checked addresses (the host name stays in TLS and `Host`; certificates are verified), `Content-Type: application/json`, `Accept: application/json`, `User-Agent: Checkorca-CE/<version>`, `Connection: close`; an IPv6 literal keeps its brackets in `Host`. The first address that accepts the connection is used; a connection that cannot be made tries the next one. Once the request was written, a dropped connection ends the attempt (`The connection to the target dropped (...)`) and no other address gets the body, since the receiver may already have it. 10 seconds for the whole request, after up to 5 seconds of DNS.
- Answer: any `2xx` is `sent`. A `3xx` is a failure and is **not** followed (`The target answered 302 and redirects are not followed.`), so a redirect to a private address is never reached. Any other status, a timeout, a TLS failure, a refused or unreachable connection or a non-HTTP answer is a failure. Every failure is a `DeliveryError` sentence that names the status or the cause and the port, never the path or query of the URL, and follows the retry ladder like an e-mail failure; one notification per flip, channel and event stays the rule, and `NotificationSent` fires as for e-mail.
- No signature header in version 1: the URL itself is the credential, as with Slack and Teams incoming webhooks. Receivers should use an unguessable path and HTTPS.

#### Webhook payload v1

`docs/webhook-payload.schema.json` (JSON Schema 2020-12) is the published contract; `tests/notify/test_webhook_kinds.py` validates every payload against it and compares each event with a golden file (`tests/notify/golden/webhook-<event>.json`). Times are ISO 8601 UTC with `Z` at second precision; ids are UUID strings. `schema_version` is 1; a later version adds fields and raises the number.

| Field | Events | Value |
| --- | --- | --- |
| `event` | all | `failing`, `missed`, `warning`, `recovered`, `reminder`, `digest` or `test` |
| `at` | all | the flip's time; the digest's `generated_at`; the test's now |
| `url` | all | the job page; the Morning check for the digest and the test |
| `product` | all | `Checkorca-CE` |
| `schema_version` | all | `1` |
| `job` | flip events | `{id, name, kind}` |
| `client` | flip events | `{id, name}` |
| `state`, `previous_state` | flip events | the job's state after and before the flip (`ok`, `failing`, `missed`, `warning`, ...) |
| `reason` | flip events | the flip's reason, plain text |
| `occurrence` | flip events | `{scheduled_for, deadline}` of the run that caused the flip (`deadline` null when the occurrence is gone), or null for a flip without a due run |
| `date` | digest | the local day `D`, `YYYY-MM-DD` |
| `counts` | digest | `{verified, failed, silent, warning}`, the complete numbers |
| `items` | digest | `[{client, job, state}]`, the jobs that need attention, silent first, then failed, then warning; at most 100 (the rest is in `counts`) |

A `reminder` carries the facts of the flip it reminds of. A `test` carries the five common fields only.

```json
{"event": "missed", "at": "2027-01-05T07:30:00Z", "url": "https://ce-dev-checkorca.theriark.dev/jobs/2222...", "product": "Checkorca-CE", "schema_version": 1,
 "job": {"id": "2222...", "name": "Nightly server backup", "kind": "backup"}, "client": {"id": "3333...", "name": "Fictional Dental Clinic"},
 "state": "missed", "previous_state": "ok", "reason": "The run was due at 23:00 and nothing reported by 01:00.",
 "occurrence": {"scheduled_for": "2027-01-04T23:00:00Z", "deadline": "2027-01-05T01:00:00Z"}}
```

#### Slack and Teams bodies

Built from the same `Message` (golden files `slack-<event>.json`, `teams-<event>.json`):

- **slack**: an incoming-webhook body: `text` (the message on one line, what Slack shows in a notification), a `header` block (the subject, `plain_text`, at most 150 characters) and `section` blocks (the change, reason and due time; a link to the job; for the digest the counts, up to 10 jobs, how many more, and a link to the Morning check).
- **teams**: a `MessageCard`: `themeColor` from the status colours, `summary` and `title` (the subject), `text` (the plain message) and, for the digest, the counts and up to 10 jobs as `facts`.
- No user content is rendered as markup: every field that carries a client or job name, a reason or a label is escaped (`&`, `<`, `>` as entities, so a name cannot mention `@channel` or inject a link in Slack; for Teams `[` and `]` as numeric references too, so a Markdown link or image in a name stays text). Fields are cut to their limits between whole characters, never inside an entity.

#### Development

The Mock Platform (`http://mock-platform:8080/` plus a capture path) runs on the private Docker network, so a live check there needs `OUTBOUND_ALLOWED_HOSTS=mock-platform` on Development only (a Platform and Release Engineer task sets it in Dokploy). Everything it receives is simulated.

## SSRF rules

`check_target(url, allow_private, allowed_hosts)`:

1. `http` or `https` only, with a host, no user name or password, no IPv6 zone (`%` in the host), at most 2,000 characters.
2. The host is resolved (every IPv4 and IPv6 address, 5 seconds at most); a literal address is taken as it is.
3. Every address must be public. Refused: loopback, private (RFC 1918, `fc00::/7`), link-local (`169.254.0.0/16`, `fe80::/10`), shared (`100.64.0.0/10`), multicast, reserved (site-local `fec0::/10` too), unspecified, the cloud metadata addresses (`169.254.169.254`, `169.254.170.2`, `100.100.100.200`, `168.63.129.16`, `fd00:ec2::/32`), and IPv6 addresses carrying one of them (IPv4-mapped, SIIT `::ffff:0:a.b.c.d`, IPv4-compatible `::a.b.c.d`, 6to4, NAT64).
4. `ALLOW_PRIVATE_TARGETS=true` allows every other address; a host exactly equal to an entry of `OUTBOUND_ALLOWED_HOSTS` (comma-separated, case-insensitive, no wildcard, no subdomain) is allowed whatever else it resolves to. Neither allows a link-local address (`169.254.0.0/16`, `fe80::/10`, also inside an IPv6 address) or a cloud metadata address: the never set.

Phase C9-I decided the C9-B security review note: link-local joined the never set. Cloud metadata services answer on link-local addresses beyond the listed ones, and no webhook receiver of an MSP lives there, so `ALLOW_PRIVATE_TARGETS=true` on a cloud server no longer opens that range.

A refusal is `TargetRefused` with one readable sentence that names the host and the address, never the path, for example `10.0.0.5 is a private address. Outbound requests go to public addresses only. An admin can allow this host with OUTBOUND_ALLOWED_HOSTS, or private targets with ALLOW_PRIVATE_TARGETS.`; a never-set address ends `Link-local and metadata addresses are never called, whatever OUTBOUND_ALLOWED_HOSTS and ALLOW_PRIVATE_TARGETS say.` The API answers it as a 422 problem document (`title` `Target refused`, `detail` the sentence) whose `errors[0].field` is `body.url` for `check-url`, `body.config.url` for channel create and update, and `config.url` for `channels/{id}/test`. During a send it is the notification's error and follows the retry ladder.

`tests/notify/test_webhook_kinds.py` runs the SSRF table per kind (`10.0.0.5`, `127.0.0.1`, `169.254.169.254`, `::1`, `fd00::`, a name resolving to a private address, a non-HTTP scheme, a redirect to a private address) and the timeout; `tests/security/test_ssrf.py` covers the guard itself.

## API (for C9-F)

Every change needs an admin session and `X-CSRF-Token`; lists and reads take an admin or technician session, or an API token of scope read. Problem documents as everywhere (`docs/auth.md`).

| Route | Answer |
| --- | --- |
| `GET /api/v1/channels` | `ChannelPage` (oldest first, cursor) |
| `POST /api/v1/channels` | `ChannelOut` 201; body `kind`, `label`, `enabled`, `config`, `secret` (slack, teams, webhook: the URL in `config.url`, no `secret`); 422 names the field (`body.config.<key>`, `body.secret`, `body.kind`); 422 `Target refused` for a URL the SSRF guard refuses |
| `GET /api/v1/channels/{id}` | `ChannelOut` |
| `PATCH /api/v1/channels/{id}` | `ChannelOut`; config keys sent replace the stored ones (null removes one); `secret` replaces, `""` removes; 422 `Secret required` when a target key changes without the secret; a URL kind takes a new `config.url` (checked first, 422 `Target refused`) and refuses a null or empty one; 409 for a kind not registered |
| `DELETE /api/v1/channels/{id}` | 204, with its rules and history |
| `POST /api/v1/channels/{id}/test` | `ChannelTestResult` `{ok, detail}`: sends a test message now (up to 90 seconds); not retried, does not change `last_status`; 422 `Target refused` when the guard now refuses a URL kind's stored target (recorded as a failed `channel.test`) |
| `POST /api/v1/channels/check-url` | `TargetCheckResult` (`host`, `port`, `addresses`, `allowed_by`) or 422 `Target refused`; resolves only, sends nothing |
| `GET /api/v1/channel-rules?channel_id=` | `RulePage` with `scope_name` (`Client` or `Client / Job`) |
| `POST /api/v1/channel-rules` | `RuleOut` 201; 422 for an unknown channel, client or job, a scope that does not fit `scope_id`, or `digest` outside scope `all` |
| `PATCH /api/v1/channel-rules/{id}` | `RuleOut`; a new scope other than `all` needs its `scope_id` in the same request |
| `DELETE /api/v1/channel-rules/{id}` | 204 |
| `GET /api/v1/notifications?status=&channel_id=` | `NotificationPage`, newest first (cursor); each item has the channel's label and kind and, for a flip, the job and client |
| `GET /api/v1/settings` | `DigestSettingsOut` `{digest_time_local: "HH:MM", digest_timezone, reminder_24h}` (admin only) |
| `PATCH /api/v1/settings` | the same; at least one field; `digest_timezone` must be an IANA zone (admin only) |

`ChannelOut` never carries the secret: `secret_set`, `secret_hint` (`****` when a secret is set, else null; never characters of a password a person chose) and `secret_label` (`Relay password`, `Slack webhook URL`, `Teams webhook URL`, `Webhook URL`). A URL kind's `config` is `{url_set, url_host}` only. Jobs (`JobOut`) carry `acknowledged_by` (`{id, email}`, `email` null for an API token) next to `acknowledged_at`.

Audit events: `channel.create`, `channel.update` (field names only; the secret as `secret`), `channel.delete`, `channel.test` (`ok`), `channel_rule.create`, `channel_rule.update`, `channel_rule.delete`, `settings.update`. They show in the activity timeline as configuration changes.

## Demo seed

The demo seed replays two weeks of history with `subscribers=()` (`app/seed/demo.py`), so its made-up flips queue no notification, and the dispatcher's catch-up starts after the seed's audit event `seed.demo` (`tests/seed/test_demo.py`). Jobs it leaves behind are real jobs afterwards: their later flips notify like any other.
