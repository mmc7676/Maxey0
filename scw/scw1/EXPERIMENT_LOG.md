# SCW1 final build experiment log

Run: `scw1-public-build-2026-09-12`

## Input

## Build gates
- [x] Context / Execution / Engineering-Observation planes present.
- [x] SCW default deployer present.
- [x] A2A directory and endpoint present.
- [x] MCP directory and delivery present.
- [x] Stateless MCP 2026-07-28 public adapter present.
- [x] MCP Apps `ui://` resource and `_meta.ui.resourceUri` linkage present.
- [x] Host-mediated ChatGPT context-window observation contract present.
- [x] Claude Code / Codex / Claude / ChatGPT distribution metadata present.
- [x] Claude Agent SDK / OpenAI Agents SDK / LangChain / Google ADK adapters present.

## Test result
`262 passed, 1 skipped, 11 subtests passed` using the available runtime. The single skipped module requires the optional third-party `mcp` Python SDK, which is declared as an optional dependency; the public MCP 2026 adapter is independently tested without that SDK.

## Protocol test result
`4 passed` in `maxey0_ss/tests/test_mcp_2026.py`.

## Boundary result
The ChatGPT context observer is intentionally host-mediated. It accepts context partitions explicitly supplied by the host/app and does not claim privileged access to hidden model context.

## Release rule
No marketplace publication is claimed by this artifact. The repository contains the manifests and integration bundles required for platform-side submission/deployment; platform approval/listing remains an external operation.
