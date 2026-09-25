# Build

Node 20+ is recommended by the MCP Apps documentation.

```bash
npm install
npm run typecheck
npm run build
```

The Maxey0 Python MCP server automatically serves `dist/mcp-app.html` when it exists and falls back to `../super_space.html` when the React bundle has not been built.
