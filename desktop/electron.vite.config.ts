import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { rollupOptions: { input: "src/main/index.ts" } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: "src/preload/index.ts",
        // Electron's default sandboxed renderer only runs a CommonJS preload
        // script — an ESM preload (what this package's "type": "module"
        // would otherwise produce) fails to execute under sandbox, so
        // contextBridge.exposeInMainWorld() silently never runs and
        // window.atria stays undefined. Force CJS output regardless.
        output: { format: "cjs", entryFileNames: "[name].js" },
      },
    },
  },
  renderer: {
    root: "src/renderer",
    plugins: [react()],
    build: {
      rollupOptions: { input: "src/renderer/index.html" },
    },
  },
});
