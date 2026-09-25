"""Every way this product is installed, declared once. See `registry`."""
from .registry import (
    BY_ID,
    BY_PLATFORM,
    DISTRIBUTION_ID,
    HARNESSES,
    MCP_NAMESPACE,
    MCP_PROTOCOL,
    PRODUCT,
    REMOTE_MCP_URL,
    TARGETS,
    Target,
    public_manifest,
)

__all__ = [
    "BY_ID", "BY_PLATFORM", "DISTRIBUTION_ID", "HARNESSES", "MCP_NAMESPACE",
    "MCP_PROTOCOL", "PRODUCT", "REMOTE_MCP_URL", "TARGETS", "Target",
    "public_manifest",
]
