# Notifications

Phase C9-B (dev-work-plan rev 35, section C9 and the Interfaces chapter: Notifications, Settings, In-process events). This page is the contract for C9-I (the kinds slack, teams and webhook) and C9-F (the `/notifications` pages and the digest settings).

Flips are the single source of alerts (`docs/evaluator.md`): a change of a job's state becomes at most one notification per channel and event. The daily digest and the 24-hour reminder are the only other notifications.

## Model

Revision `c9_notify` adds three tables and changes none, so the previous release runs on this schema.

| Table | Fields | Notes |
| --- | --- | --- |
| `channel` | `id`, `kind` (`email`, `slack`, `teams`, `webhook`), `label`, `enabled`, `config` (JSON), `secret_enc`, `last_status` (`sent`, `failed` or null), `last_status_at`, `last_error`, `created_at`, `updated_at` | `config` holds the kind's settings without secrets. `secret_enc` is the channel's one credential (the relay password; for C9-I a webhook URL or signing key), Fernet ciphertext made with `FERNET_KEY`. `last_*` describe the newest real delivery, never a test. No client data. |
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

`app/ext/notifications.py` `ChannelKind`: `name`, `secret_label`, `secret_targets`, `check_config(config, has_secret)` and `async send(config, secret, message, outbound)`. `app/notify/registry.py` holds the registered kinds; CE registers `email`. A channel whose kind is not registered is listed with `available: false` and can only be deleted.

`Message` carries `event`, `subject`, `text`, `url` and, for the digest, `html` and `digest_day`; for a flip or a reminder, `flip` (`FlipFacts`: flip, job and client ids and names, `from_state`, `to_state`, `reason`, `at`, `scheduled_for`, `url` of the job page). Webhook kinds should build their payload from `flip`, not from the text.

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

Register a kind per name in `default_kinds()`; no schema change. Rules for an HTTP kind:

- Call `check_target` (`app/security/ssrf.py`) with the `Outbound` rules passed to `send` before every request, connect to one of `Target.addresses` (keep the host name for TLS and the Host header) and follow no redirect.
- Put the secret part (a Slack or Teams webhook URL, a signing key) in the channel secret, never in `config`; list the config keys that decide where the secret goes in `secret_targets`.
- Raise `DeliveryError` with one sentence that names no secret and no URL path; a timeout of your own must stay under 90 seconds.
- Development: the Mock Platform runs on the private Docker network, so testing a webhook kind there needs `OUTBOUND_ALLOWED_HOSTS=mock-platform` (Delivery sets Dokploy environment values).

## SSRF rules

`check_target(url, allow_private, allowed_hosts)`:

1. `http` or `https` only, with a host, no user name or password, at most 2,000 characters.
2. The host is resolved (every IPv4 and IPv6 address, 5 seconds at most); a literal address is taken as it is.
3. Every address must be public. Refused: loopback, private (RFC 1918, `fc00::/7`), link-local (`169.254.0.0/16`, `fe80::/10`), shared (`100.64.0.0/10`), multicast, reserved (site-local `fec0::/10` too), unspecified, the cloud metadata addresses (`169.254.169.254`, `169.254.170.2`, `fd00:ec2::254`, `100.100.100.200`), and IPv6 addresses carrying one of them (IPv4-mapped, SIIT `::ffff:0:a.b.c.d`, IPv4-compatible `::a.b.c.d`, 6to4, NAT64).
4. `ALLOW_PRIVATE_TARGETS=true` allows every other address; a host exactly equal to an entry of `OUTBOUND_ALLOWED_HOSTS` (comma-separated, case-insensitive, no wildcard, no subdomain) is allowed whatever else it resolves to. Neither allows a cloud metadata address.

A refusal is `TargetRefused` with one readable sentence, for example `10.0.0.5 is a private address. Outbound requests go to public addresses only. An admin can allow this host with OUTBOUND_ALLOWED_HOSTS, or private targets with ALLOW_PRIVATE_TARGETS.` The API answers it as a 422 problem document (`title` `Target refused`, `detail` the sentence, `errors[0].field` `body.url`).

## API (for C9-F)

Every change needs an admin session and `X-CSRF-Token`; lists and reads take an admin or technician session, or an API token of scope read. Problem documents as everywhere (`docs/auth.md`).

| Route | Answer |
| --- | --- |
| `GET /api/v1/channels` | `ChannelPage` (oldest first, cursor) |
| `POST /api/v1/channels` | `ChannelOut` 201; body `kind`, `label`, `enabled`, `config`, `secret`; 422 names the field (`body.config.<key>`, `body.secret`, `body.kind`) |
| `GET /api/v1/channels/{id}` | `ChannelOut` |
| `PATCH /api/v1/channels/{id}` | `ChannelOut`; config keys sent replace the stored ones (null removes one); `secret` replaces, `""` removes; 422 `Secret required` when a target key changes without the secret; 409 for a kind not registered |
| `DELETE /api/v1/channels/{id}` | 204, with its rules and history |
| `POST /api/v1/channels/{id}/test` | `ChannelTestResult` `{ok, detail}`: sends a test message now (up to 90 seconds); not retried, does not change `last_status` |
| `POST /api/v1/channels/check-url` | `TargetCheckResult` (`host`, `port`, `addresses`, `allowed_by`) or 422 `Target refused`; resolves only, sends nothing |
| `GET /api/v1/channel-rules?channel_id=` | `RulePage` with `scope_name` (`Client` or `Client / Job`) |
| `POST /api/v1/channel-rules` | `RuleOut` 201; 422 for an unknown channel, client or job, a scope that does not fit `scope_id`, or `digest` outside scope `all` |
| `PATCH /api/v1/channel-rules/{id}` | `RuleOut`; a new scope other than `all` needs its `scope_id` in the same request |
| `DELETE /api/v1/channel-rules/{id}` | 204 |
| `GET /api/v1/notifications?status=&channel_id=` | `NotificationPage`, newest first (cursor); each item has the channel's label and kind and, for a flip, the job and client |
| `GET /api/v1/settings` | `DigestSettingsOut` `{digest_time_local: "HH:MM", digest_timezone, reminder_24h}` (admin only) |
| `PATCH /api/v1/settings` | the same; at least one field; `digest_timezone` must be an IANA zone (admin only) |

`ChannelOut` never carries the secret: `secret_set`, `secret_hint` (`****` when a secret is set, else null; never characters of a password a person chose) and `secret_label`. Jobs (`JobOut`) carry `acknowledged_by` (`{id, email}`, `email` null for an API token) next to `acknowledged_at`.

Audit events: `channel.create`, `channel.update` (field names only; the secret as `secret`), `channel.delete`, `channel.test` (`ok`), `channel_rule.create`, `channel_rule.update`, `channel_rule.delete`, `settings.update`. They show in the activity timeline as configuration changes.

## Demo seed

The demo seed replays two weeks of history with `subscribers=()` (`app/seed/demo.py`), so its made-up flips queue no notification, and the dispatcher's catch-up starts after the seed's audit event `seed.demo` (`tests/seed/test_demo.py`). Jobs it leaves behind are real jobs afterwards: their later flips notify like any other.
