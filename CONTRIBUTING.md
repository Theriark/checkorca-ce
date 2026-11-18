# Contributing

Checkorca-CE is pre-release. Contributions are welcome once the first application phase has landed; until then, expect rapid change.

## Licence of contributions

By submitting a contribution you agree that it is licensed under the [MIT licence](LICENSE) of this repository.

## Branches and pull requests

- Never commit directly to `development`, `stage` or `main`.
- Work on a feature branch named `feat/checkorca-ce-<task or topic>` and open a draft pull request into `development`.
- Keep one pull request to one reviewable change.
- Mark the pull request ready only when the CI merge gate (`Merge gate summary`) is green and the checklist in the pull request template is complete.
- The author of a pull request does not review it.

## Checks

The merge gate runs ruff and mypy, pytest with PostgreSQL 16 and coverage, Alembic migration checks, frontend lint, type check, Vitest and Playwright with axe, pip-audit and npm audit, a licence audit for Python and npm, a check for LGPL drivers, EE references and committed credentials, a docker build and a compose smoke test. See [docs/ci-cd.md](docs/ci-cd.md) for which checks are active.

## Dependencies

Every runtime dependency must be under a licence on the allow-list in [docs/ci-cd.md](docs/ci-cd.md) (MIT, BSD, Apache-2.0, ISC and similar). LGPL, GPL, AGPL and SSPL are refused. Python dependencies are pinned with hashes.

## Security

Report vulnerabilities privately, see [SECURITY.md](SECURITY.md). Never commit secrets, credentials or real client data; test data is synthetic and labelled as such.
