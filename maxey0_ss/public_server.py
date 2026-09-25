from __future__ import annotations

import uvicorn

from .api.app import app
from .ratelimit import UVICORN_PROXY_HEADERS
from .settings import settings


def main() -> None:
    """Serve the public MCP surface.

    Host and port come from MAXEY0_HOST / MAXEY0_PORT, which were declared in
    `.env.example` and previously ignored in favor of a hard-coded 0.0.0.0:8765.

    `proxy_headers` is off. uvicorn's default trusts X-Forwarded-For from
    loopback and rewrites `scope["client"]` before any middleware runs, and
    cloudflared connects from loopback -- so the rate limiter would never see
    which peer actually connected, which is the one fact that decides whether
    CF-Connecting-IP is believed. `RateLimitMiddleware` restores the scheme
    from X-Forwarded-Proto for the same trusted peers; see `maxey0_ss.ratelimit`.
    """
    cfg = settings()
    uvicorn.run(app, host=cfg.host, port=cfg.port, proxy_headers=UVICORN_PROXY_HEADERS)


if __name__ == "__main__":
    main()
