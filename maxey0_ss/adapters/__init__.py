"""A2A, MCP-client and harness adapters.

Imports stay lazy so the core carries no adapter initialization cycles and no
optional provider dependency.

Three modules were removed at 0.3.0 after an audit found each referenced only
by itself:

``openai_agents.py``
    An `OpenAIAgentsAdapter` with the *same class name* as the live one in
    `harnesses/openai_agents.py` and an incompatible signature —
    `bind_agent(agent)` against `bind_agent(system, agent)`. Two importable
    classes with one name is worse than dead code: the failure is a confusing
    `TypeError` at a call site that looks correct.

``claude_code.py``
    A `ClaudeCodeAdapter` for the plugin lifecycle. The Claude Code integration
    is real and it is the *plugin* under `plugins/maxey0/`, which never imported
    this. A twenty-one line adapter named for the most visible distribution
    target, that the target does not use, is a label on the front door.

``registry.py``
    An `MCPResourceRegistry` with no reader. `a2a_directory.MCPDirectory` is the
    live registry.
"""
