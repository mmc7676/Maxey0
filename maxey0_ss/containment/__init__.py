"""Containment: the enforcement seam and the evidence that it held.

Three pieces, deliberately separable:

- ``protocol``    the contract a provider satisfies  (published)
- ``attestation`` hash-chained evidence and verifier  (published)
- ``structural``  the default provider                (published by default)

The enforcement engine is chosen by configuration through
:func:`containment_provider`, so which engine a deployment runs — and therefore
what a repository has to disclose — is a deployment decision rather than a fork
of the codebase. The attestation format and its verifier stay public either way,
because a containment claim nobody can check is not a claim.

``MAXEY0_CONTAINMENT_PROVIDER`` selects the engine. ``structural`` is the
default and the only one this build implements; any other value names a provider
that must be supplied, and is refused rather than silently downgraded.
"""
from __future__ import annotations

import os

from .attestation import GENESIS, Attestation, AttestationLog, VerificationResult, compute_digest
from .hierarchy import (
    UNBOUNDED,
    Constitution,
    ConstitutionTree,
    ConstitutionViolation,
    DenialBreaker,
    bounded,
    narrowed,
)
from .protocol import (
    ContainmentDecision,
    ContainmentError,
    ContainmentProvider,
    Operation,
)
from .structural import PROVIDER_NAME, StructuralContainment

#: Engines this build can construct. A deployment-supplied provider registers here.
PROVIDERS: dict[str, type] = {PROVIDER_NAME: StructuralContainment}

PROVIDER_ENV = "MAXEY0_CONTAINMENT_PROVIDER"


class UnknownContainmentProvider(RuntimeError):
    """A provider was requested that this build cannot construct.

    Refusing is the point. Falling back to the default would mean a deployment
    that believes it is running a stricter engine while it is not, and the
    attestations would name the wrong provider.
    """


def containment_provider(
    name: str | None = None,
    *,
    log: AttestationLog | None = None,
    tree: ConstitutionTree | None = None,
    breaker: DenialBreaker | None = None,
) -> ContainmentProvider:
    """Construct the configured containment engine.

    `tree` and `breaker` pass through because a provider built without them
    enforces no chartered ceiling and no refusal limit. The default
    construction left both inert in every path running through
    SuperSpaceSystem, ContextService and the HTTP surface, so the hierarchy
    constrained only code that built a provider by hand.
    """
    requested = (name or os.getenv(PROVIDER_ENV, PROVIDER_NAME)).strip() or PROVIDER_NAME
    factory = PROVIDERS.get(requested)
    if factory is None:
        raise UnknownContainmentProvider(
            f"containment provider {requested!r} is not available in this build. "
            f"Known: {sorted(PROVIDERS)}. Register one in containment.PROVIDERS, "
            f"or unset {PROVIDER_ENV}."
        )
    return factory(log=log, tree=tree, breaker=breaker)


__all__ = [
    "Attestation",
    "AttestationLog",
    "Constitution",
    "ConstitutionTree",
    "ConstitutionViolation",
    "ContainmentDecision",
    "ContainmentError",
    "ContainmentProvider",
    "DenialBreaker",
    "GENESIS",
    "Operation",
    "PROVIDERS",
    "PROVIDER_ENV",
    "PROVIDER_NAME",
    "StructuralContainment",
    "UNBOUNDED",
    "UnknownContainmentProvider",
    "VerificationResult",
    "bounded",
    "compute_digest",
    "containment_provider",
    "narrowed",
]
