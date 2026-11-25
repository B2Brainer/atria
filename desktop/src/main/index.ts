import path from "node:path";

import { app, BrowserWindow, dialog } from "electron";

import { BackendClient } from "./backend";
import { registerIpcHandlers } from "./ipc";
import { installCrashCapture, Logger } from "./logger";

const logger = new Logger(
  process.env.ATRIA_LOG_PATH ?? path.join(app.getPath("logs"), "atria-main.log"),
);
installCrashCapture(logger);

// The repository root (one level above `desktop/`), where `python -m api`
// must be invoked from so its `core`/`adapters`/`api` package imports resolve.
// In a packaged build there is no repository checkout: the bundled backend
// (standalone Python runtime + `core`/`adapters`/`api` source, Increment 6)
// ships under `process.resourcesPath/backend` instead, via electron-builder's
// `extraResources`.
const repoRoot = path.resolve(app.getAppPath(), "..");
const packagedBackendDir = path.join(process.resourcesPath, "backend");
const packagedPythonExecutable = path.join(
  process.resourcesPath,
  "python-dist",
  "bin",
  "python3",
);

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
  let pythonCommand: string;
  let pythonArgs: string[];
  let cwd: string;

  if (process.env.ATRIA_PYTHON != null) {
    // Test/override hook (established in Increment 5): an explicit
    // interpreter path, invoked directly with no `uv run` wrapper.
    pythonCommand = process.env.ATRIA_PYTHON;
    pythonArgs = ["-m", "api"];
    cwd = repoRoot;
  } else if (app.isPackaged) {
    // Packaged build (Increment 6): spawn the bundled, standalone Python
    // runtime against the bundled backend source — no `uv`/dev Python
    // installation required on the target machine.
    pythonCommand = packagedPythonExecutable;
    pythonArgs = ["-m", "api"];
    cwd = packagedBackendDir;
  } else {
    // Development: the repository's own `uv`-managed environment.
    pythonCommand = "uv";
    pythonArgs = ["run", "python", "-m", "api"];
    cwd = repoRoot;
  }

  backend = new BackendClient(pythonCommand, pythonArgs, cwd, (line) => {
    console.error(`[atria-backend] ${line}`);
    logger.info(line, { source: "backend" });
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
