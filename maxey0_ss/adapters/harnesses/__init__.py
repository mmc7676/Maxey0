"""Harness adapters: one binding per execution framework.

Each binds an agent to a window so that what the harness does is attributed and
recorded. None of them vendors a vendor SDK — the dependency is optional and the
import is deferred to the moment it is needed, so a build that never uses
LangChain never imports it.
"""
from .base import HarnessAdapter, HarnessBinding, HarnessCapabilities
from .claude_agent_sdk import ClaudeAgentSDKAdapter
from .google_adk import GoogleADKAdapter
from .langchain import LangChainAdapter
from .microsoft import MicrosoftAgentFrameworkAdapter
from .nvidia import NvidiaNeMoAdapter
from .openai_agents import OpenAIAgentsAdapter

#: harness id -> adapter class. The registry every other layer reads.
ADAPTERS = {
    "claude-agent-sdk": ClaudeAgentSDKAdapter,
    "openai-agents": OpenAIAgentsAdapter,
    "langchain": LangChainAdapter,
    "google-adk": GoogleADKAdapter,
    "microsoft": MicrosoftAgentFrameworkAdapter,
    "nvidia": NvidiaNeMoAdapter,
}

__all__ = [
    "ADAPTERS",
    "ClaudeAgentSDKAdapter",
    "GoogleADKAdapter",
    "HarnessAdapter",
    "HarnessBinding",
    "HarnessCapabilities",
    "LangChainAdapter",
    "MicrosoftAgentFrameworkAdapter",
    "NvidiaNeMoAdapter",
    "OpenAIAgentsAdapter",
]
