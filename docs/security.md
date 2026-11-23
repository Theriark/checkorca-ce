# Security notes

How the server treats what it sends out and the credentials it stores. Reporting a vulnerability: `SECURITY.md`. Sign-in, sessions, CSRF and API tokens: `docs/auth.md`.

## Stored credentials (legal D-6)

Columns ending in `_enc` hold Fernet ciphertext made with `FERNET_KEY` (`app/security/crypto.py`): the IMAP password of an inbox, the external heartbeat URL and, from phase C9, the secret of a notification channel (`channel.secret_enc`: the relay password, or the URL of a slack, teams or webhook channel, whose path is often the credential). They are write-only:

- No API answer carries one: forms get `secret_set` and a masked hint (for an inbox `****` and the last four characters of a secret of 12 or more characters; for a channel `****` only, see below).
- Audit events name changed fields (`secret`), never values.
- A delivery error stored in `notification.error` or `channel.last_error` has the channel's secret replaced by `****`; the e-mail kind's errors are fixed sentences that never repeat the relay's answer.
- Logs carry ids, classes and counts (`app/logging.py`); an exception keeps its class and stack, not its text.
- Changing where a secret is sent (an inbox's IMAP host, port, TLS or user name; an e-mail channel's host, port, STARTTLS or user name) needs the secret again, so a stored secret never follows a new target. A URL channel's target is its secret: a new URL replaces it whole.
- A URL channel answers `config: {url_set, url_host}` only; delivery errors and SSRF refusals name the host, the address, the port or the HTTP status, never the path or query.

`tests/api/test_notifications_api.py` puts a canary relay password and a canary webhook URL in and checks the API, the exports, the digest preview, the activity timeline, the notification history, the audit trail and the logs; `tests/notify/test_webhook_kinds.py` checks that a canary URL path never reaches a delivery error or a log.

## Outbound requests (SSRF)

Every outbound HTTP request made on an admin's behalf goes through `app/security/ssrf.py` `check_target`: the webhook, Slack and Teams channels (phase C9-I: when a channel is created or its URL changed, and before every send and test) and the outbound heartbeat (phase C10). Only `http` and `https`; the host is resolved and every address must be public: loopback, private, link-local (where cloud metadata services answer), shared, multicast, reserved and unspecified addresses, the metadata addresses and IPv6 forms of them are refused. The caller connects to a checked address and follows no redirect (a `3xx` is a failed delivery, so a redirect to a private address is never reached), so a DNS answer cannot change between the check and the request. TLS certificates are verified against the URL's host. One request has 10 seconds after the guard's DNS step.

Two settings relax the rule, for a target on the operator's own network:

| Variable | Default | Effect |
| --- | --- | --- |
| `ALLOW_PRIVATE_TARGETS` | `false` | `true` allows every address except the never set below (the scheme rule stays) |
| `OUTBOUND_ALLOWED_HOSTS` | empty | comma-separated host names allowed whatever they resolve to, except an address of the never set; exact matches only (no wildcard, no subdomain) |

The never set is never called, whatever the two settings say: the cloud metadata addresses (`169.254.169.254`, `169.254.170.2`, `fd00:ec2::254`, `100.100.100.200`) and, since phase C9-I, every link-local address (`169.254.0.0/16`, `fe80::/10`), each also inside an IPv6 address (IPv4-mapped, SIIT, IPv4-compatible, 6to4, NAT64). Opening private targets on a cloud server therefore does not open its instance credentials to a webhook URL. C9-I decided the C9-B security review note this way because metadata services also answer on other link-local addresses than the listed ones, and no webhook receiver of an MSP lives on link-local; an operator who needs one there has no setting for it, by design.

A refusal is a readable sentence (`10.0.0.5 is a private address. ...`); the API answers it as a 422 problem document. `POST /api/v1/channels/check-url` (admins) runs the check on a URL without sending anything.

### The SMTP relay is not filtered

The relay of an e-mail channel (`host`, `port`) is **not** checked by the SSRF guard. MSPs usually send through an internal relay (an Exchange or Postfix server on their own network, a smart host on a private address), so refusing private addresses would make the e-mail channel unusable for them. Only an admin can set or change a relay, the connection speaks SMTP only (no HTTP request is made to it), and the stored relay password only goes to the host it was entered for (see above). Use `starttls: true` with a relay outside a trusted network; the server then requires a certificate the system trusts before it logs in. With `starttls: false` and a user name, the relay password crosses the network in clear text: use that only for a relay on a trusted network.

Channel answers show `secret_hint` as `****` only: a relay password is chosen by a person, so even its last four characters are not shown to technicians or read tokens (inbox IMAP passwords keep the last-four hint).

## Notifications

What a notification carries: the client and job names, the change of state, its reason and a link to the job (`docs/notifications.md`). No message content of the backup mails, no result details and no credentials. The digest HTML escapes every name and has no script, image or remote content (`app/notify/digest.py`). E-mail header values are single lines, so a name with a line break cannot add a header. Slack and Teams bodies escape every field that carries a name, a reason or a label (`&`, `<`, `>` as entities, so a name cannot mention `@channel` or add a link; for Teams `[` and `]` as numeric references too, so a Markdown link or image stays text); the webhook payload is JSON and carries names as plain strings, for the receiver to escape where it renders them (`docs/notifications.md`).
