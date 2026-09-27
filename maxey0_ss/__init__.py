"""Maxey0-SuperSpace core API.

One name per role, and no others. Twelve spellings of this product were in the
tree at 0.2.0 — four of them class aliases exported from right here — and a
reader had no way to tell which was the real one. `tests/test_ontology.py`
enforces the table below in both directions: a retired spelling that reappears
fails, and a canonical name that stops being used fails too.

===============  ==========================  ===============================
role             token                       where it appears
===============  ==========================  ===============================
product          ``Maxey0-SuperSpace``       prose, titles, manifests
short form       ``Maxey0``                  prose where the full name is noise
python package   ``maxey0_ss``               the implementation's imports
import name      ``maxey0``                  the short front door (``maxey0/``)
MCP namespace    ``maxey0-ss``               every tool and resource
distribution id  ``maxey0``                  PyPI (``pip install maxey0``)
system class     ``SuperSpaceSystem``        the API
===============  ==========================  ===============================

Six spellings were retired at 0.3.0. They are named in `tests/test_ontology.py`
and nowhere else, including here: a file that lists the strings it forbids is a
file that contains them, and the check that enforces the rule would then have to
exempt the module that states it. The class aliases are gone rather than
deprecated — this has never been published, so there is no consumer to break,
and a deprecated alias is a twelfth spelling that survives into the release it
was meant to end.
"""

#: The one version literal in the Python package.
#:
#: Ten files declared "1.0.0" independently and `check_manifests()` compared
#: three of them, so `mcp_2026.build_router` could report a `serverInfo.version`
#: that disagreed with `mcp_surface.SERVER_VERSION` and nothing would notice.
#: `tests/test_version.py` asserts every other declaration agrees with this one.
__version__ = "0.3.2"

# Load .env before anything reads the environment. AuthConfig.load(),
# is_public_deployment() and the cache all resolve at construction time, so a
# .env loaded later is a .env that was never loaded: every authorization
# variable documented as wired was silently ignored and an unauthenticated
# caller became LOCAL_ADMIN.
from .settings import load_env_file as _load_env_file

_load_env_file()

from .system import SuperSpaceSystem  # noqa: E402

__all__ = ["SuperSpaceSystem", "__version__"]
