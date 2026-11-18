# CI/CD

Checkorca-CE follows the Theriark release standard: one version line starting at 27.0.0, candidates `v27.0.0-rc.N`, and exactly three one-button workflows. No workflow moves `stage` or `main`; the gate scripts do that.

## Branches

| Branch | Holds | Moved by |
| --- | --- | --- |
| `development` | All work; feature branches merge here by pull request | Pull request merges |
| `stage` | Exactly what Stage runs | The Gate 2 script (fast-forward to the candidate tag) |
| `main` | What was released; default branch, so GitHub can dispatch the workflows | The Gate 3 script (merges `stage`) |

`main` is never merged into `development`.

## Workflows

| Workflow | File | What it does |
| --- | --- | --- |
| `CI` | `ci.yml` | The merge gate on a pull request labelled `ci-go` (set by the CI request broker) and on every push to `development`. After a green gate on `development` the job `deploy-development` builds the image once, pushes `ghcr.io/theriark/checkorca-ce:sha-<commit>` and deploys that digest to Development. `workflow_dispatch` with `mode=lock` only compiles the hashed requirement files and `frontend/package-lock.json` on a feature branch (npm without running package scripts) and commits them. |
| `Promote - Stage` | `promote-stage.yml` | Gate 2. Runs from `development` with no inputs: reads the digest and commit Development runs, runs the tests on that commit, creates or reuses the annotated tag `v27.x.y-rc.N`, tags the same digest in GHCR, deploys it to Stage and verifies health, digest and revision. |
| `Release` | `release.yml` | Gate 3. Runs from `development` with no inputs: reads what Stage runs (stage head, digest, candidate tag), never rebuilds, and creates the GHCR version tag, the annotated stable tag `v27.x.y` and the GitHub Release with notes from the merged pull requests. CE has no Production deployment. A re-run when everything exists changes nothing. |

Both gate workflows take an optional `dry_run` (default false) that checks everything and changes nothing.

All three share the concurrency group `checkorca-ce-delivery` with `cancel-in-progress: false`, so deployments never overlap and a live one is never cancelled. Pull request runs have their own group per branch and cancel superseded runs.

## The merge gate

| # | Check | Input that switches it on |
| --- | --- | --- |
| 1 | ruff check, ruff format check (the diff is printed), mypy (strict for schedule, evaluator, parsers via `pyproject.toml`) | `pyproject.toml` |
| 2 | pytest against PostgreSQL 16; no skipped test; coverage 80 percent overall and 95 percent for `app/schedule`, `app/evaluator`, `app/parsers` | `pyproject.toml` |
| 3 | `alembic upgrade head`, `alembic check`, `downgrade -1`, `upgrade head` | `alembic.ini` |
| 4 | Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest), `npm run e2e` (Playwright with axe; screenshots at 1440, 768, 390 in `frontend/screenshots`, uploaded) | `frontend/package.json` |
| 5 | pip-audit from the hashed dev lock (any known vulnerability; exceptions in an optional `.pip-audit-exceptions`, none today) and npm audit from moderate up through `tools/npm_audit_gate.py` (reviewed exceptions in `.npm-audit-exceptions` with a review date at most 90 days old, valid only while every vulnerable copy is `"dev": true` in `frontend/package-lock.json`) | Python app or frontend |
| 6 | Licence audit: `python tools/licence_audit.py` on the runtime packages, again with `--scope dev` on the development packages, and `npm run licence:audit` on every package of `frontend/package-lock.json`; reviewed exceptions in `licence-exceptions.toml` | `tools/licence_audit.py` or frontend |
| 7 | No `psycopg` in the lock files, no `checkorca-ee`/`checkorca_ee` reference in `app` or `frontend/src`, gitleaks credential scan (default rules) of the tree and of every commit of the pull request or push | Always |
| 8 | docker build; the image must not run as root | `Dockerfile` |
| 9 | Compose smoke: throwaway values generated for the run, `docker compose up --wait`, `/readyz` on port 8080 answers 200, then `scripts/smoke.sh` when present (from C4: one e-mail through the SMTP listener) | `docker-compose.yml` |
| DCO | `Signed-off-by: Name <e-mail>` on every commit of the pull request (DCO 1.1, CONTRIBUTING.md). On a push to `development` the new commits are checked except the merge or squash commits GitHub writes (this relies on the rule that nobody commits to `development` directly); a `github-actions[bot]` commit is exempt only when it is exactly a lock job commit (its message, only the lock files); a Dependabot commit is exempt only when GitHub committed it, GitHub reports its signature as verified, its subject starts with `Bump ` and it changes only dependency manifests, and on a pull request only when Dependabot opened it; a later signed commit of the same author can sign off an earlier one (retroactive sign-off, CONTRIBUTING.md). The check is `.github/scripts/dco.sh`, tested by `tests/test_dco.py` | Always |
| Brand | `sha256sum -c MANIFEST.sha256` in `frontend/public/brand`, and the folder holds exactly the files of the manifest | Always |
| SBOM | syft on the built image: `sbom.spdx.json` (SPDX JSON) uploaded as an artefact; the base image digests go to the run summary (legal R-4). grype scans the SBOM, OS layer included, and fails on a high or critical vulnerability that has a fix (reviewed exceptions in `.grype.yaml`). Dependabot proposes newer base image digests, Python and npm versions and action SHAs (`.github/dependabot.yml`) | `Dockerfile` |

`STRICT` in `ci.yml` is `"true"` since phase C0 (THE-1909): every check above must succeed and a skipped check fails the gate. With `false` (before the application existed) checks without their input were skipped and shown as skipped, never as passed, and a tripwire failed the run if an application file landed.

Licence allow-list for runtime dependencies (rnd-report-2 5.1): MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF-2.0, Python-2.0, CNRI-Python, 0BSD, Unlicense, CC0-1.0; MPL-2.0 only for development packages that are not shipped. LGPL, GPL, AGPL, SSPL and unknown fail.

### Contract for the application (phase C0)

- Python package in `app/`, tests in `tests/`, hashed `requirements.txt` and `requirements-dev.txt` (from `requirements.in` and `requirements-dev.in` through the lock job). The lock job installs pip-tools only from the hashed `.github/lock-tools/requirements.txt` and commits and pushes with git hooks off.
- Frontend in `frontend/` with `package-lock.json` and the npm scripts `lint`, `typecheck`, `test`, `e2e`, `licence:audit`.
- The image takes the build argument `REVISION`, runs as a non-root user, serves `/healthz` and `/readyz` on port 8080 and reports `revision` in the `/healthz` JSON.
- `docker-compose.yml` (web on 8080, worker on 2525, PostgreSQL 16 with the volume `pgdata`) reads `POSTGRES_PASSWORD`, `SECRET_KEY`, `FERNET_KEY` and `BASE_URL` from `.env`; the compose smoke test generates throwaway values for each run.
- Runtime settings as declared in `deploy/dokploy.json`: `SECRET_KEY`, `FERNET_KEY`, `DATABASE_URL` (asyncpg), `BASE_URL`, `ROLE` (`all` runs web and worker in one container), `METRICS_TOKEN`, `ALLOW_PRIVATE_TARGETS` (`false`), the Development seed `DEV_SEED`, `DEV_SEED_ACCOUNTS`, `DEV_SEED_PASSWORD_ADMIN`, `DEV_SEED_PASSWORD_TECHNICIAN`, and `DEV_DEMO_DATA`. Code defaults, not declared: `PORT` 8080, `SMTP_PORT` 2525, `LOG_LEVEL` info.

## Deployment wiring

- Development: `ce-dev-checkorca.theriark.dev`. Stage: `ce-stg-checkorca.theriark.dev`. No Production.
- `deploy/dokploy.json` declares the runtime (PostgreSQL 16, environment entries by kind, seed accounts). The setup broker's `dokploy_prepare` creates it in Dokploy with generated values that nobody sees, then sets the repository variable `DEPLOY_DEVELOPMENT_ENABLED=true`. Until then a merge deploys nothing.
- The Dokploy application ids come from the setup broker's `github_repo_status` and are written into the workflows: `DEV_APPLICATION_ID` `zdq2bYVkPCKllskIYhYQZ` (ci.yml, promote-stage.yml) and `STAGE_APPLICATION_ID` `fCwRCuJlf50NfQhaLImDx` (promote-stage.yml, release.yml). An id that is empty or malformed makes `deploy-development`, `Promote - Stage` and `Release` refuse before any read or write.
- Dependabot opens its pull requests against `development` (`target-branch` on every entry of `.github/dependabot.yml`). GitHub reads that file from the default branch `main`, so the setting takes effect once the first release has merged it there.
- `.github/actions/dokploy-deploy` deploys one `image@sha256` digest to one existing application: it checks that the application carries the expected domain, records the previous image as the rollback target, updates and deploys once (never replays a write), waits for the new deployment, requires two healthy answers and confirms the exact digest. On failure it restores the previous image.

### Secrets and variables (names only)

| Name | Kind | Where | Set by |
| --- | --- | --- | --- |
| `DOKPLOY_URL` | Actions secret | repository | setup broker (`github_repo_setup`) |
| `DOKPLOY_API_KEY` | Actions secret | repository | setup broker |
| `CF_ACCESS_CLIENT_ID` | Actions secret | repository | setup broker |
| `CF_ACCESS_CLIENT_SECRET` | Actions secret | repository | setup broker |
| `DEPLOY_DEVELOPMENT_ENABLED` | Actions variable | repository | setup broker (`dokploy_prepare`) |
| `development`, `stage` | Environments | repository | setup broker |
| `GITHUB_TOKEN` | built in | every run | GitHub |

CI on pull requests needs no secret.

## Rollback

Rollback is not a button. Revert the change on `development`; the merge deploys the reverted commit to Development, and the next Gate 2 promotes it. Every deployment summary records the previous image digest. The database is never downgraded in place: migrations stay compatible with the previous release.
