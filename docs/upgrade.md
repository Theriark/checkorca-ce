# Upgrading a self-hosted installation

Phase C10-B. How a Checkorca-CE install moves from one release to the next.
Releases are `vMAJOR.MINOR.PATCH` (`27.0.0` is the first); release
candidates are tagged `v27.0.0-rc.N` and are for testing, not for
production installs. The Docker Compose install of the README is the
example; on another install the same steps apply to your own deployment of
the image.

## The one-release-back rule

An upgrade is supported from **exactly one release back**: the migrations of
release N run on the schema of release N-1. An install that is older must
step through every release in between (upgrade one release at a time), or
start fresh and import its data. Never restore a newer backup into an older
image.

The image runs the migrations itself: the web container (Dokploy: the one
`ROLE=all` container) applies them on start, before the HTTP port opens.
Migrations are forward-only and additive within a release pair, so the
previous release keeps running on the new schema during the switch
(docs/ci-cd.md, Rollback).

## Procedure

1. Back up first: `bash scripts/backup.sh`
   ([backup-restore.md](backup-restore.md)). The dump is the rollback.
2. Pull the new image (or rebuild: `docker compose build`) and start it:
   `docker compose up -d --wait`. The web container migrates on start.
3. Watch `GET /healthz`: `version` is the new release and `revision` the
   commit the image was built from. `GET /readyz` answers 200 once the
   worker has ticked (up to a minute).
4. Sign in, read the Morning check, and look at one job page and one
   notification channel. `/metrics` (docs/ci-cd.md) shows the evaluator lag
   back at 0 and the queues empty once the first tick has run.

If anything is wrong, roll back with the dump and the previous image
(`scripts/restore.sh`, then `docker compose` with the old tag): the
database is never downgraded in place — the restore replaces it with the
state the backup holds.

## The FERNET_KEY rotation with an upgrade

A rotation is not an upgrade, but the two meet: put `FERNET_KEY` as
`new,old` (the new key first), restart, run `python -m app rotate-fernet`,
then set `FERNET_KEY` to the new key alone and restart again
(docs/auth.md). A backup made between the two steps must keep the old key
readable. Never lose an old key while any backup that needs it exists.

## What an upgrade never touches

The retention purge, the migrations and a restore write only Checkorca's own
database (legal D-5). The backups and job results that Checkorca watches —
the MSP's clients' systems — are outside this server and are never read,
written or deleted by an upgrade.
