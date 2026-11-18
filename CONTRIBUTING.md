# Contributing

Checkorca-CE is pre-release and changes quickly. Contributions are welcome. Please read the [code of conduct](CODE_OF_CONDUCT.md) first.

## Licence of contributions and sign-off (DCO)

Contributions are licensed under the [MIT licence](LICENSE) of this repository. Checkorca-CE uses the [Developer Certificate of Origin 1.1](https://developercertificate.org/) instead of a contributor licence agreement.

Every commit must end with a `Signed-off-by` line that names you and your e-mail address:

```
Signed-off-by: Ada Example <ada@example.com>
```

`git commit -s` adds it for you. Use the same name and e-mail address as the commit author. By signing off you certify the DCO 1.1, in short: you wrote the change or have the right to submit it under the project's licence, and you understand that the contribution and your sign-off are public and kept permanently. The CI job `DCO - Signed-off-by on every commit` fails a pull request with an unsigned commit. To fix one, amend it with `git commit --amend -s` (or `git rebase --signoff` for several) and push again. When the history cannot be rewritten, add a new signed-off commit by the same author with one line per unsigned commit:

```
I, Ada Example <ada@example.com>, hereby add my Signed-off-by to this commit: <full 40-character commit SHA>
```

## Branches and pull requests

- Never commit directly to `development`, `stage` or `main`.
- Work on a feature branch named `feat/checkorca-ce-<task or topic>` and open a draft pull request into `development`.
- Keep one pull request to one reviewable change.
- Mark the pull request ready only when the CI merge gate (`Merge gate summary`) is green and every box of the pull request checklist is ticked.
- The author of a pull request does not review it.

## Checks

The merge gate runs ruff and mypy, pytest on PostgreSQL 16 with coverage, the Alembic migration cycle, frontend lint, type check, Vitest and Playwright with axe, pip-audit and npm audit, the licence audit for Python and npm, a check for LGPL drivers, EE references and committed credentials, a non-root docker build, a compose smoke test, the DCO sign-off, the brand file manifest and an SBOM of the image. See [docs/ci-cd.md](docs/ci-cd.md).

## Dependencies

Every dependency must be under a licence on the allow-list in [docs/ci-cd.md](docs/ci-cd.md) (MIT, BSD, Apache-2.0, ISC and similar). LGPL, GPL, AGPL and SSPL are refused; anything else needs a reviewed entry in [licence-exceptions.toml](licence-exceptions.toml). Python dependencies are pinned with hashes, npm dependencies by `frontend/package-lock.json`.

## Test data

Test data is synthetic and labelled as such: `example.com` and `.test` addresses, `192.0.2.0/24` and `2001:db8::/32` IP addresses, fictional companies. Never commit secrets, credentials or real client data.

## Security

Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).
