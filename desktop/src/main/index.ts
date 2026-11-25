import path from "node:path";

import { app, BrowserWindow, dialog } from "electron";

import { BackendClient } from "./backend";
import { registerIpcHandlers } from "./ipc";

// The repository root (one level above `desktop/`), where `python -m api`
// must be invoked from so its `core`/`adapters`/`api` package imports resolve.
const repoRoot = path.resolve(app.getAppPath(), "..");

let backend: BackendClient | null = null;
let mainWindow: BrowserWindow | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    backgroundColor: "#F4F4F9",
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}

async function startBackend(): Promise<void> {
  const pythonCommand = process.env.ATRIA_PYTHON ?? "uv";
  const pythonArgs =
    process.env.ATRIA_PYTHON != null ? ["-m", "api"] : ["run", "python", "-m", "api"];

  backend = new BackendClient(pythonCommand, pythonArgs, repoRoot, (line) => {
    console.error(`[atria-backend] ${line}`);
  });
  await backend.start();
  registerIpcHandlers(backend);
}

app.whenReady().then(async () => {
  try {
    await startBackend();
  } catch (err) {
    // Without this catch, a failed startBackend() (spawn failure, readiness
    // timeout) is an unhandled promise rejection: no window ever opens, the
    // user sees nothing, and the process is left in an ambiguous state.
    // backend may have partially started (a child process spawned but
    // never reached readiness) — stop() is a no-op if it didn't, and
    // guarantees no orphan if it did, before this process exits.
    await backend?.stop();
    dialog.showErrorBox(
      "Atria failed to start",
      `The application backend could not be started: ${(err as Error).message}`,
    );
    app.exit(1);
    return;
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", async (event) => {
  if (!backend) return;
  event.preventDefault();
  const toStop = backend;
  backend = null;
  await toStop.stop();
  app.exit(0);
});
