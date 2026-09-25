import { defineConfig, type Plugin } from "vitest/config";

/**
 * Wrangler's Text module rule turns `*.html` imports into strings. Vitest does
 * not know that rule, so reproduce it here -- otherwise the tests would exercise
 * a different module graph than the deployed Worker.
 */
function textModules(): Plugin {
  return {
    name: "maxey0-text-modules",
    transform(code, id) {
      if (!id.endsWith(".html")) return null;
      return { code: `export default ${JSON.stringify(code)};`, map: null };
    },
  };
}

export default defineConfig({
  plugins: [textModules()],
  test: { environment: "node", include: ["test/**/*.test.ts"] },
});
