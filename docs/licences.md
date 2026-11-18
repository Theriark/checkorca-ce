# Dependency licences

Checkorca-CE is MIT licensed. This file records every direct runtime dependency: its licence as read in the LICENSE file of its own source repository, its maintainer and its last release (legal L-3, C-2). The CI licence audit (merge gate check 6, `tools/licence_audit.py`) checks every installed package, transitive ones included, against the allow-list; reviewed exceptions are in [`licence-exceptions.toml`](../licence-exceptions.toml).

Allow-list (docs/ci-cd.md): MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF-2.0, Python-2.0, CNRI-Python, 0BSD, Unlicense, CC0-1.0. LGPL, GPL, AGPL, SSPL and unknown licences fail and can never be an exception. psycopg (LGPL) must not appear in a lock file; asyncpg is the driver.

## Direct runtime dependencies (Python)

All LICENSE files were read on 2026-11-18 from the default branch of the repository named in the table. "Last release" is the newest version on PyPI on that day; the version actually installed is pinned with hashes in `requirements.txt`.

| Dependency | SPDX licence | LICENSE file read | Maintainer | Last release |
| --- | --- | --- | --- | --- |
| fastapi | MIT | fastapi/fastapi `LICENSE`: MIT, Copyright (c) 2018 Sebastián Ramírez | Sebastián Ramírez and the FastAPI organisation | 0.163.2, 2026-11-17 |
| uvicorn | BSD-3-Clause | Kludex/uvicorn `LICENSE.md`: three-clause BSD, Copyright 2017-present Encode OSS Ltd | Encode OSS Ltd, repository kept by Kludex | 0.54.0, 2026-09-25 |
| starlette | BSD-3-Clause | Kludex/starlette `LICENSE.md`: three-clause BSD, Copyright 2018 Encode OSS Ltd | Encode OSS Ltd, repository kept by Kludex | 1.10.0, 2026-10-24 |
| pydantic | MIT | pydantic/pydantic `LICENSE`: MIT, Copyright 2017 to present Pydantic Services Inc. and individual contributors | Pydantic Services Inc. | 2.14.3, 2026-11-05 |
| pydantic-settings | MIT | pydantic/pydantic-settings `LICENSE`: MIT, Copyright (c) 2022 Samuel Colvin and other contributors | Pydantic | 2.16.3, 2026-11-13 |
| sqlalchemy (with the asyncio extra) | MIT | sqlalchemy/sqlalchemy `LICENSE`: MIT, Copyright 2005-2026 SQLAlchemy authors and contributors | SQLAlchemy project | 2.1.9, 2026-11-16 |
| asyncpg | Apache-2.0 | MagicStack/asyncpg `LICENSE`: Apache License 2.0, Copyright 2016-present the asyncpg authors and contributors | MagicStack | 0.32.0, 2026-10-06 |
| alembic | MIT | sqlalchemy/alembic `LICENSE`: MIT, Copyright 2009-2026 Michael Bayer | SQLAlchemy project (Michael Bayer) | 1.20.1, 2026-10-22 |
| httpx | BSD-3-Clause | encode/httpx `LICENSE.md`: three-clause BSD, Copyright 2019 Encode OSS Ltd | Encode OSS Ltd | 0.28.1, 2024-12-06 (no release for almost two years; watched) |
| argon2-cffi | MIT | hynek/argon2-cffi `LICENSE`: MIT, Copyright (c) 2015 Hynek Schlawack and the argon2-cffi contributors | Hynek Schlawack | 25.1.0, 2025-06-03 |
| cryptography | Apache-2.0 OR BSD-3-Clause | pyca/cryptography `LICENSE`: the choice of `LICENSE.APACHE` or `LICENSE.BSD` (those two files were not opened) | Python Cryptographic Authority (pyca) | 50.0.2, 2026-09-30 |
| prometheus-client | Apache-2.0 AND BSD-2-Clause | prometheus/client_python `LICENSE`: Apache License 2.0; its `NOTICE` says it bundles decorator 4.0.10 under the two-clause BSD licence | The Prometheus Authors | 0.26.0, 2026-07-24 |
| PyYAML | MIT | yaml/pyyaml `LICENSE`: MIT, Copyright 2017-2021 Ingy döt Net, 2006-2016 Kirill Simonov | The YAML project | 6.0.3, 2025-09-25 |
| jsonschema | MIT | python-jsonschema/jsonschema `COPYING`: MIT, Copyright (c) 2013 Julian Berman | Julian Berman | 4.26.0, 2026-01-07 |
| regex | Apache-2.0 AND CNRI-Python | mrabarnett/mrab-regex `LICENSE.txt`: derived from the `re` module of CPython under CNRI's Python 1.6 licence; all additions under Apache 2.0 | Matthew Barnett | 2026.11.18, 2026-11-18 |
| croniter | MIT | pallets-eco/croniter `LICENSE`: MIT, Copyright (C) 2010-2012 Matsumoto Taichi | Pallets Community Ecosystem (pallets-eco) | 7.0.0, 2026-11-09 |
| aiosmtpd | Apache-2.0 | aio-libs/aiosmtpd `LICENSE`: Apache License 2.0 | aio-libs | 1.4.6, 2024-05-18 (pinned exactly by the plan) |
| python-multipart | Apache-2.0 | Kludex/python-multipart `LICENSE.txt`: Apache License 2.0 (the file keeps the template copyright line) | Kludex | 0.0.34, 2026-11-16 |

## Transitive runtime packages with a reviewed exception

| Package | Licence | Pulled in by | Decision |
| --- | --- | --- | --- |
| certifi | MPL-2.0 | httpx | Allowed unmodified (legal-input L-1 a, dev-work-plan decision 7). certifi/python-certifi `LICENSE` read 2026-11-18: the Mozilla CA bundle under the MPL-2.0. Shipped unmodified, licence text in THIRD_PARTY_NOTICES. |
| cffi | MIT-0 | argon2-cffi-bindings, cryptography | MIT No Attribution: the MIT grant without the attribution condition (python-cffi/cffi `LICENSE` read 2026-11-18). More permissive than MIT, but not on the allow-list, so it is a recorded runtime exception for review. |

Every other transitive package passes the allow-list from its own metadata. fastapi now also requires opentelemetry-api (Apache-2.0).

## croniter: source and fallback (legal L-2)

- **Source.** PyPI project `croniter`, repository https://github.com/pallets-eco/croniter (the project URL in its PyPI metadata), maintained in the Pallets Community Ecosystem. Last release 7.0.0 on 2026-11-09.
- **Containment.** Only `app/schedule/_cron.py` imports croniter (phase C3); the rest of the code uses the schedule library's own `ScheduleSpec`, `occurrences` and `deadline`. The DST golden tables of `tests/schedule/golden` pin the behaviour.
- **Fallback.** If croniter stops being maintained, changes behaviour that breaks the golden tables, or gets a licence change, `_cron.py` is replaced by an own parser for five-field cron expressions (lists, ranges, steps, month and day names) behind the same interface and the same golden tables. The phase C0-B spike records croniter with `zoneinfo` in `docs/spikes.md`.
- Other planned fallbacks of the same kind: an own SMTP receiver for aiosmtpd, pg8000 in a thread pool for asyncpg (C0-B).

## Web app (npm)

The built web app ships React and React DOM (MIT, Meta Platforms) and scheduler (MIT). Every npm package, development ones included, is audited from `frontend/package-lock.json` by `npm run licence:audit`. The build and test tools under MPL-2.0, CC-BY-4.0 or BlueOak-1.0.0 (axe-core, @axe-core/playwright, lightningcss with its platform binaries, caniuse-lite; minimatch, one copy of lru-cache and @isaacs/nonrecursive-glob-match) are development-only exceptions in `licence-exceptions.toml`; they are never in the image. The Blue Oak Model License 1.0.0 is permissive and OSI approved, but not on the allow-list.

## Development packages (Python)

Development tools are audited in their own environment (`tools/licence_audit.py --scope dev`). hypothesis (MPL-2.0) and pathspec (MPL-2.0, through mypy) are development-only exceptions.

## System packages of the image

The image is built on `python:3.12-slim` (Debian), pinned by digest in the `Dockerfile`, and installs no extra Debian packages; it only applies Debian security updates that the pinned base does not carry yet (zlib1g today, found by the grype scan of the SBOM job) and removes pip. Those packages keep their own licences, some GPL or LGPL; nothing of Checkorca-CE links to them. THIRD_PARTY_NOTICES in the image lists them and points to `/usr/share/doc/<package>/copyright`; the SBOM of each build (`sbom.spdx.json`) lists them with versions (legal R-4). A counsel review of this statement is a pre-release step, not a build blocker.
