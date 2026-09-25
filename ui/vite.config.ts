import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build lands inside the Python package, where `app.py`'s static handler
// already serves anything under `static/`. So a built UI is picked up with no
// server change, and an absent one changes nothing: the Studio's zero-install
// promise is that `python server/run_studio.py` works on a bare Python 3.10+,
// and a front end that required `npm install` first would quietly end that.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "../server/maxey0_studio/static/app",
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5177,
    // `npm run dev` talks to a Studio you started separately, so the two can be
    // restarted independently.
    proxy: { "/api": "http://127.0.0.1:7676" },
  },
});
