# Checkorca-CE

Self-hosted backup and job-status monitor for small MSPs. Checkorca-CE collects backup and scheduled-job results from alert e-mails, webhooks and HTTP pings, knows which jobs should report and when, and shows every morning which clients are verified, failed or silent. Its key job is to catch a backup that never reported.

This is the Community Edition, free under the [MIT licence](LICENSE).

## Status

Pre-release. The repository, CI and release workflows are in place; the application is being built and nothing is ready to install yet. The first release will be 27.0.0. Until then there are no supported versions.

## What the Community Edition will include

- One organisation, unlimited clients, jobs and local users (admin and technician roles).
- Results in by HTTP ping, webhook, its own SMTP listener, IMAP polling and `.eml` upload.
- An expected schedule per job (interval, cron or daily times, time zone, grace, maximum runtime), so a silent job is caught.
- Declarative parser packs for vendor alert e-mails, a generic keyword pack, a test bench and a pack editor. Vendor packs start as unverified and are written from public documentation.
- A morning check page and e-mail digest per client: verified, failed, silent.
- Alerts by e-mail, Slack, Microsoft Teams and generic webhook; read-only REST API; CSV export; 90 days of history.
- Docker Compose install, health endpoints, metrics and an optional outbound dead-man heartbeat.

## Stack

Python 3.12, FastAPI, SQLAlchemy 2 with asyncpg, Alembic and PostgreSQL 16 for the API and worker; React, TypeScript and Vite for the web app. One container image runs the web and worker roles.

## Development

- `development` is the integration branch. Work happens on feature branches with pull requests into it; see [CONTRIBUTING.md](CONTRIBUTING.md).
- CI, the Stage promotion and the release are described in [docs/ci-cd.md](docs/ci-cd.md).

## Security

Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## Licence

MIT, see [LICENSE](LICENSE).
