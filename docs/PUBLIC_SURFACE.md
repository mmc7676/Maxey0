# Public surface / internal implementation boundary

The public package intentionally exposes:
- MCP tools/resources and MCP App UI resources.
- A2A agent card and task/message endpoint.
- Stable REST API and Python package APIs.
- CLI and host-specific manifests.
- SCW schemas, lifecycle, admission, provenance, replay contracts.
- Harness adapters.

The public package does not embed:
- provider API keys or OAuth credentials;
- user databases or memory contents;
- production MCP server credentials;
- deployment-specific private network topology;
- host-private model context.

Developers can run the whole stack locally or deploy the MCP/A2A API remotely. The implementation remains inspectable because the repository is open source; operational state is not bundled into the release.
