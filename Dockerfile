# The Maxey0-SuperSpace Python origin, served behind a Cloudflare Tunnel.
#
# One container, two processes, supervised by deploy/entrypoint.sh under tini:
#   - the origin (`maxey0_ss.public_server`) bound to 127.0.0.1:8765, and
#   - cloudflared, which dials OUT to Cloudflare and is the only way in.
# Nothing is EXPOSEd, so the container has no ingress of its own; the origin
# hostname reaches it only through the tunnel.
#
# Base image pinned by tag. The tag still moves with CPython 3.11 and Debian
# security patches; pinning it by digest (`python:3.11-slim-trixie@sha256:...`)
# is the follow-up that makes a rebuild bit-for-bit the image that was tested.
FROM python:3.11-slim-trixie

# cloudflared, pinned and checksum-verified. Both values are from the official
# release, https://github.com/cloudflare/cloudflared/releases/tag/2026.9.1,
# whose "SHA256 Checksums" section lists this digest for cloudflared-linux-amd64
# (GitHub's own asset digest for the same file agrees). Bump them together; a
# mismatch fails the build rather than shipping an unverified binary.
ARG CLOUDFLARED_VERSION=2026.9.1
ARG CLOUDFLARED_SHA256=03f1f25d1cc93b9ad6c60569d44060bc4f17ed97075760ed8cfca4b12dcd68cc

# Non-secret defaults only. Secrets (TUNNEL_TOKEN, MAXEY0_MCP_TOKEN_HASHES)
# arrive at runtime from the host's secret store and never through this file,
# a build argument, or a copied .env.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    MAXEY0_HOST=127.0.0.1 \
    MAXEY0_PORT=8765 \
    MAXEY0_ENV=production \
    MAXEY0_PUBLIC=1 \
    MAXEY0_AUTH_MODE=bearer \
    SCW_HOME=/data/scw

# tini reaps zombies and forwards signals: as PID 1 under Docker, and under a
# platform's own init (when that is PID 1) as a registered subreaper, hence `-s`
# in the ENTRYPOINT. setpriv (util-linux, already in the
# base image) is how the entrypoint drops root; the build fails if it is gone
# rather than producing an image whose entrypoint refuses to start.
# Two unprivileged users, one per process: see deploy/entrypoint.sh for why the
# origin must not share a uid with the process holding the tunnel token.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates tini; \
    rm -rf /var/lib/apt/lists/*; \
    command -v setpriv; \
    useradd --system --uid 10001 --user-group --create-home --home-dir /home/maxey0 --shell /usr/sbin/nologin maxey0; \
    useradd --system --uid 10002 --user-group --create-home --home-dir /home/cloudflared --shell /usr/sbin/nologin cloudflared; \
    mkdir -p /data/scw; \
    chown maxey0:maxey0 /data/scw; \
    chmod 0700 /data/scw

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    [ "$arch" = amd64 ] || { echo "cloudflared is pinned for linux-amd64; this build is $arch" >&2; exit 1; }; \
    python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" \
        "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-amd64" \
        /tmp/cloudflared; \
    echo "${CLOUDFLARED_SHA256}  /tmp/cloudflared" | sha256sum -c -; \
    install -m 0755 /tmp/cloudflared /usr/local/bin/cloudflared; \
    rm /tmp/cloudflared; \
    cloudflared --version

WORKDIR /app

# Dependencies are read from pyproject.toml's [project].dependencies, so the
# image cannot drift from the package's own declaration, and pinned by the
# constraints frozen from the tested venv. The package itself is NOT installed
# into site-packages: settings.py, mcp_surface.py and observability/bridge.py
# resolve .env, mcp_apps/ and server/ relative to the source tree, and a
# site-packages copy would silently serve the stub App and drop the
# observe/gate tools. It runs from /app via PYTHONPATH instead.
COPY pyproject.toml ./
COPY deploy/constraints.txt deploy/constraints.txt
RUN set -eux; \
    python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" \
        > /tmp/requirements.txt; \
    pip install -r /tmp/requirements.txt -c deploy/constraints.txt; \
    rm /tmp/requirements.txt

# Only what the origin reads, at the layout it expects. Never `COPY . .`:
# .env and config/credentials.json are read automatically when present.
COPY maxey0_ss/ maxey0_ss/
COPY server/ server/
COPY mcp_apps/super_space.html mcp_apps/super_space.html
# The MCP App bundle. mcp_apps/super_space_react/dist/ is gitignored build
# output that may be stale or missing on the building machine; the edge Worker
# serves this tracked copy, asserted byte-identical to the origin's by
# test_edge_app_artifact_is_byte_identical_to_the_origin. Serving the same
# file here keeps the App the origin reports (`maxey0-ss.app.artifact`) the same
# bytes, and the same sha256, as the App the edge serves.
COPY workers/mcp-edge/src/generated/super-space.html mcp_apps/super_space_react/dist/mcp-app.html
COPY deploy/entrypoint.sh deploy/entrypoint.sh

# A CRLF entrypoint fails at start with "not found"; fail the build instead.
# Then prove the image can import and build the app it will serve.
RUN set -eux; \
    chmod 0755 deploy/entrypoint.sh; \
    if grep -q "$(printf '\r')" deploy/entrypoint.sh; then echo "deploy/entrypoint.sh has CRLF line endings" >&2; exit 1; fi; \
    sh -n deploy/entrypoint.sh; \
    test ! -e .env; \
    test ! -e config/credentials.json; \
    HOME=/tmp/import-check SCW_HOME=/tmp/import-check/scw python -c "import maxey0_ss.public_server"; \
    rm -rf /tmp/import-check

# No USER: the entrypoint starts as root only to hand a root-owned state volume
# to the origin's user, then runs each process as its own unprivileged user.
ENTRYPOINT ["/usr/bin/tini", "-s", "--", "/app/deploy/entrypoint.sh"]
