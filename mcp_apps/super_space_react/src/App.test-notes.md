# App verification notes

The prior app referenced `app`, `isConnected`, and `error` without initializing them. The production source now obtains these values from:

```ts
const { app, isConnected, error } = useApp({
  appInfo: { name: "Maxey0-SuperSpace", version: "3.0.0" },
  capabilities: {},
});
```

Server-tool calls are made only after the host bridge reports `isConnected`.
