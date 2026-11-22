# Checkorca-CE image: one image for the web and worker roles (ROLE or command).
# Base images are pinned by multi-arch index digest; the SBOM job of ci.yml
# records them for every build.

# 1. The web app (Vite, React). Only dist/ reaches the final image.
FROM node:22-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. Python packages from the hashed runtime lock, and THIRD_PARTY_NOTICES.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
# --require-hashes refuses anything that is not in the lock; no development
# package can enter the image.
COPY requirements.txt /tmp/requirements.txt
# pip itself leaves the virtual environment afterwards: nothing installs
# packages at run time.
RUN /opt/venv/bin/pip install --require-hashes --no-deps -r /tmp/requirements.txt \
    && /opt/venv/bin/python -m pip uninstall -y pip
# Python and npm licence texts plus the Debian statement (legal R-3, R-4). The
# script and the frontend build folder are only mounted for this step.
RUN --mount=type=bind,source=tools/third_party_notices.py,target=/mnt/third_party_notices.py \
    --mount=type=bind,from=frontend,source=/build,target=/mnt/frontend \
    /opt/venv/bin/python /mnt/third_party_notices.py \
        --site-packages /opt/venv/lib/python3.12/site-packages \
        --frontend /mnt/frontend \
        --output /THIRD_PARTY_NOTICES

# 3. Runtime: no build tools, uid 10001.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROLE=all
RUN groupadd --system --gid 10001 checkorca \
    && useradd --system --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin checkorca
COPY --from=builder /opt/venv /opt/venv
# Debian security fixes the pinned base image does not carry yet (found by the
# grype scan of ci.yml), and no pip in the runtime image. Drop zlib1g
# once Dependabot's base digest ships zlib1g 1:1.3.dfsg+really1.3.1-1+deb13u1
# or later (CVE-2026-85091). Drop libc6 and libc-bin once the base digest ships
# 2.41-12+deb13u5 or later (CVE-2026-19499, CVE-2026-5435); on 2026-11-22 the
# newest python:3.12-slim (the pinned digest) still had 2.41-12+deb13u4.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade \
        zlib1g libc6 libc-bin \
    && rm -rf /var/lib/apt/lists/* \
    && /usr/local/bin/python -m pip uninstall -y pip
WORKDIR /srv/checkorca
COPY LICENSE NOTICE ./
COPY --from=builder /THIRD_PARTY_NOTICES ./THIRD_PARTY_NOTICES
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY --from=frontend /build/dist ./frontend/dist
# The commit the image is built from (CI passes the source SHA); /healthz
# reports it. Last, so a new commit keeps every layer above cached.
ARG REVISION=""
ENV REVISION=${REVISION}
LABEL org.opencontainers.image.title="Checkorca-CE" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${REVISION}"
USER 10001:10001
# 8080: web app and API. 2525: SMTP listener of the worker (phase C4).
EXPOSE 8080 2525
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).status == 200 else 1)"]
CMD ["python", "-m", "app", "all"]
