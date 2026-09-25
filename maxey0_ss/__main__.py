"""Console entrypoint for the Maxey0-SuperSpace HTTP surface.

pyproject declares `maxey0-ss = "maxey0_ss.__main__:main"`, and this module
defined no `main`, so the installed command failed on every invocation.
"""
from __future__ import annotations

import os

from .api.app import app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main() -> None:
    """Serve the API. Binds loopback unless MAXEY0_HOST says otherwise.

    Loopback is the default because a deployment that becomes reachable
    without MAXEY0_PUBLIC=1 treats every caller as admin.
    """
    import uvicorn

    from .ratelimit import UVICORN_PROXY_HEADERS

    # proxy_headers off, as in maxey0-ss-public: with it on, uvicorn rewrites
    # the client address from X-Forwarded-For before the rate limiter runs, so
    # any proxy on loopback could choose the address the limiter keys on, and
    # auth.manifest's `uvicorn_proxy_headers: false` would be false here.
    uvicorn.run(
        app,
        host=os.getenv("MAXEY0_HOST", DEFAULT_HOST),
        port=int(os.getenv("MAXEY0_PORT", DEFAULT_PORT)),
        proxy_headers=UVICORN_PROXY_HEADERS,
    )


if __name__ == "__main__":
    main()
