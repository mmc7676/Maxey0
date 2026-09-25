# The SuperSpace MCP App

`ui://maxey0-ss/super-space.html` is a first-class MCP resource, not a
decoration. This is its full chain, and how each link was verified.

## Chain

```
src/App.tsx, src/main.tsx                 React source, MCP Apps bridge
        │  npm run typecheck               tsc --noEmit, clean
        │  npm run build                   vite + singlefile
        ▼
dist/mcp-app.html                          one self-contained file, 463,986 bytes
        │  mcp_surface.super_space_html()
        ▼
Resource(ui://maxey0-ss/super-space.html)  text/html;profile=mcp-app
        │  registered by both transports
        ▼
Tool maxey0-ss.super_space                 _meta.ui.resourceUri → the URI above
Tool maxey0-ss.scw.observe_host_window               _meta.ui.resourceUri, requires_scw
```

## Bridge

`src/App.tsx` uses the MCP Apps React bridge:

```tsx
const { app, isConnected, error } = useApp({
  appInfo: { name: "Maxey0-SuperSpace", version: "3.0.0" },
  capabilities: {},
});
useHostStyles(app, app?.getHostContext() ?? null);
...
await app.callServerTool({ name, arguments: args });
```

`useHostStyles` takes `(app, initialContext)` and must therefore be called
*after* `useApp()` has produced `app`. It was previously called with no
arguments, before `useApp()`, which did not compile. Fixed.

## Build configuration

The Python side reads exactly one path: `dist/mcp-app.html`. Vite emits
`dist/index.html` and, by default, a separate JS chunk. Neither matches. The
build therefore pins three things in `vite.config.ts`:

- `viteSingleFile()` plus `assetsInlineLimit` and `cssCodeSplit:false` — inline
  everything, because an MCP App is delivered as one HTML document and cannot
  fetch sibling assets from the host;
- `inlineDynamicImports` — no code-splitting;
- `emitMcpAppHtml()` — renames `index.html` to `mcp-app.html` at `closeBundle`.

Without all three the server silently serves the stub instead.

## Artifact identity

`dist/` is gitignored, so the artifact is a build product, not source. To keep
that honest, the surface reports what it is actually serving:

```python
from maxey0_ss.mcp_surface import super_space_artifact
super_space_artifact()
# {'kind': 'built', 'path': 'mcp-app.html', 'bytes': 463986,
#  'sha256': 'b4a18845deb7e294...', 'uri': 'ui://maxey0-ss/super-space.html'}
```

Exposed as the `maxey0-ss.app.artifact` tool and inside `maxey0-ss.health`, so
production verification can assert artifact identity over the wire rather than
trusting the filesystem. `kind: "fallback-stub"` means the App was never built.

`test_artifact_identity_matches_the_bytes_actually_served` asserts the reported
sha256 is the digest of the bytes the resource returns.

## Verified

Driven as a real MCP client over stdio (`ClientSession.read_resource`):

```
ui resource : text/html;profile=mcp-app 463968 chars
app artifact: built 463986 sha256 b4a18845deb7e294
```

Not verified: rendering inside a live host. That needs a host to load the
resource and is not something source inspection can establish.
