export async function call(url: string, method: string, name?: string, params: Record<string, unknown> = {}) {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "MCP-Protocol-Version": "2026-07-28",
    "Mcp-Method": method,
  };
  if (name) headers["Mcp-Name"] = name;
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  return response.json();
}
