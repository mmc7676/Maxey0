# SCW enforceable address

Maxey0 treats an SCW as an application-level enforceable address space rather than as an MCP transport session.

Format:

`scw://<topic>/<concept>/<skill>/<region>/<scw_id>`

The address is visible to the application and can be passed explicitly across stateless MCP requests. It is not a claim that an LLM can inspect hidden host/model context.

MCP supplies transport and capability routing. Maxey0 resolves and admits the SCW address before governed execution.
