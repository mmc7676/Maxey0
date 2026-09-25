import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";
import { renameSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The Maxey0 MCP server reads exactly one artifact: `dist/mcp-app.html`.
 * See `maxey0_ss/mcp_surface.py::_super_space_html`. Vite emits `index.html`,
 * so the build is only correct once that file is inlined AND renamed.
 */
function emitMcpAppHtml(): Plugin {
  return {
    name: "maxey0-emit-mcp-app-html",
    closeBundle() {
      const out = resolve(__dirname, "dist");
      renameSync(resolve(out, "index.html"), resolve(out, "mcp-app.html"));
    },
  };
}

export default defineConfig({
  plugins: [react(), viteSingleFile(), emitMcpAppHtml()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});
