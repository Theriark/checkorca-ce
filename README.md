<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/wordmark-ce-dark.svg">
  <img src="frontend/public/brand/wordmark-ce.svg" alt="Checkorca-CE" width="320">
</picture>

# Checkorca-CE

Self-hosted backup and job-status monitor for small MSPs. Checkorca-CE collects backup and scheduled-job results from alert e-mails, webhooks and HTTP pings, knows which jobs should report and when, and shows every morning which clients are verified, failed or silent. Its key job is to catch a backup that never reported.

This is the Community Edition, free under the [MIT licence](LICENSE).

Checkorca-CE is an independent open-source project. It is not affiliated with, endorsed by or sponsored by any backup or software vendor whose products it can read alerts from; their names are trademarks of their owners and are used only to describe compatibility.

## Status

Pre-release. The application skeleton, the container image and the CI merge gate are in place; the features are being built and nothing is ready for production use yet. The first release will be 27.0.0.

## What the Community Edition will include

- One organisation, unlimited clients, jobs and local users (admin and technician roles).
- Results in by HTTP ping, webhook, its own SMTP listener, IMAP polling and `.eml` upload.
- An expected schedule per job (interval, cron or daily times, time zone, grace, maximum runtime), so a silent job is caught.
- Declarative parser packs for vendor alert e-mails, a generic keyword pack, a test bench and a pack editor. Vendor packs start as unverified and are written from public documentation.
- A morning check page and e-mail digest per client: verified, failed, silent.
- Alerts by e-mail, Slack, Microsoft Teams and generic webhook; read-only REST API; CSV export; 90 days of history.
- Docker Compose install, health endpoints, metrics and an optional outbound dead-man heartbeat.

## Try the skeleton with Docker Compose

Create a `.env` file next to `docker-compose.yml` with four values of your own: `POSTGRES_PASSWORD` (URL-safe, because it becomes part of the database URL: for example `openssl rand -hex 24`), `SECRET_KEY` (at least 32 characters, for example `openssl rand -hex 32`), `FERNET_KEY` (a Fernet key: 32 random bytes, URL-safe base64) and `BASE_URL` (for example `http://localhost:8080`). Then:

```sh
docker compose up -d --build --wait
curl http://localhost:8080/readyz
```

The web app and API answer on port 8080, the worker's SMTP listener (from phase C4) on port 2525. A complete quick start follows before the first release.

## Stack

Python 3.12, FastAPI, SQLAlchemy 2 with asyncpg, Alembic and PostgreSQL 16 for the API and worker; React, TypeScript and Vite for the web app. One container image (non-root, uid 10001) runs the web and worker roles: `python -m app all|web|worker|migrate|seed`.

## Development

- `development` is the integration branch. Work happens on feature branches with pull requests into it; every commit is signed off (DCO 1.1). See [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md).
- CI, the Stage promotion and the release are described in [docs/ci-cd.md](docs/ci-cd.md); dependency licences in [docs/licences.md](docs/licences.md).

## Security

Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## Licence

MIT, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
