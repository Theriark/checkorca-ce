# Backup and restore

Phase C10-B. What an operator of a self-hosted Checkorca-CE keeps, how, and
how it comes back. The Docker Compose install of the README is the example;
`scripts/backup.sh` and `scripts/restore.sh` work against it. On another
install the same `pg_dump`/`pg_restore` against your PostgreSQL does the
same job.

## What a backup must hold

1. **The database** (`scripts/backup.sh`): every client, job, result, raw
   message, occurrence, flip, notification, user, session and setting of the
   installation, in one custom-format dump. Nothing outside this database is
   in it.
2. **The environment secrets** (`.env`, kept in a password manager, never
   in the dump or next to it): `SECRET_KEY`, `FERNET_KEY`, and
   `METRICS_TOKEN` and `EXTERNAL_HEARTBEAT_URL` when set, plus the seed
   passwords of a Development or Stage install. Without the same
   `SECRET_KEY` a restored install cannot read its old session cookies and
   API tokens; without the `FERNET_KEY` that was current when the backup was
   made, the stored credentials (the IMAP passwords, channel secrets) cannot
   be decrypted.
3. **Every `FERNET_KEY` you ever used**, for as long as you keep backups
   made under it (docs/auth.md, rotation): a backup from before a rotation
   restores rows that only the old key can read.

```sh
bash scripts/backup.sh                       # writes checkorca-backup-<UTC time>.dump
bash scripts/backup.sh /safe/place/name.dump # or names the file itself
```

Back up daily: the retention purge (docs/ingest.md) keeps raw messages 30
days by default, results and flip history 90 days, audit events 365 days, so
an older backup is the only place a purged row still exists. A restore
brings purged rows back until the next daily purge removes them again.

## Restore

```sh
bash scripts/restore.sh checkorca-backup-20261124-013000.dump
```

The script stops the app, replaces the database content with the dump's, and
starts the app again; the web container runs the migrations on start, so a
dump of the previous release moves forward cleanly (the one-release-back
rule of [upgrade.md](upgrade.md)). Then:

1. `GET /healthz` answers the running version; `GET /readyz` answers 200
   once the worker has ticked (up to a minute).
2. Sign in with the accounts of the backup; sessions of the backup are only
   readable with the same `SECRET_KEY`.
3. Spot-check the Morning check and one client page.

Rollback after a bad upgrade is the same procedure with the backup made
before the upgrade (docs/ci-cd.md, Rollback).

## What a backup never touches

Checkorca-CE watches backups and job results of other systems; its own
backup is only this database (legal D-5). The retention purge, an upgrade
and a restore never read or write the MSP's backup files, backup jobs or
their results: those live outside this server, and Checkorca only stores the
alert mails and pings they send. Conversely, a database backup of an MSP's
own systems never contains Checkorca data; back up Checkorca itself as
described here.
