import path from "node:path";

import { app, BrowserWindow, dialog } from "electron";

import { BackendClient } from "./backend";
import { registerIpcHandlers } from "./ipc";
import { installCrashCapture, Logger } from "./logger";

// A distinct override name from the Python backend's own `ATRIA_LOG_PATH`
// (api/config.py): the backend subprocess inherits this process's env plus
// whatever override startBackend() computes for it below, so reusing the
// same variable name here would make an operator's one `ATRIA_LOG_PATH`
// override point both processes at the same file, which neither rotates
// cooperatively.
const logger = new Logger(
  process.env.ATRIA_MAIN_LOG_PATH ?? path.join(app.getPath("logs"), "atria-main.log"),
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
  let backendEnv: Record<string, string> = {};

  if (process.env.ATRIA_PYTHON != null) {
    // Test/override hook (established in Increment 5): an explicit
    // interpreter path, invoked directly with no `uv run` wrapper. Still
    // respects app.isPackaged for cwd: a packaged build has no repository
    // checkout at all, so an operator debugging a packaged build with a
    // custom interpreter still needs the bundled backend source's cwd, not
    // repoRoot (which would not exist).
    pythonCommand = process.env.ATRIA_PYTHON;
    pythonArgs = ["-m", "api"];
    cwd = app.isPackaged ? packagedBackendDir : repoRoot;
  } else if (app.isPackaged) {
    // Packaged build (Increment 6): spawn the bundled, standalone Python
    // runtime against the bundled backend source — no `uv`/dev Python
    // installation required on the target machine. Its database/log/backup
    // locations must NOT fall back to their dev-mode defaults (repo-root-
    // relative, which here would resolve under the signed .app bundle's own
    // Contents/Resources — read-only once signed, and replaced wholesale on
    // every update): point them at this app's writable, update-safe,
    // per-user data directory instead.
    pythonCommand = packagedPythonExecutable;
    pythonArgs = ["-m", "api"];
    cwd = packagedBackendDir;
    const userDataDir = app.getPath("userData");
    backendEnv = {
      ATRIA_DB_PATH: path.join(userDataDir, "atria.sqlite3"),
      ATRIA_LOG_PATH: path.join(userDataDir, "logs", "atria-backend.log"),
    };
  } else {
    // Development: the repository's own `uv`-managed environment.
    pythonCommand = "uv";
    pythonArgs = ["run", "python", "-m", "api"];
    cwd = repoRoot;
  }

  backend = new BackendClient(
    pythonCommand,
    pythonArgs,
    cwd,
    (line) => {
      console.error(`[atria-backend] ${line}`);
      // A heuristic level, not a parsed one: the backend's own structured
      // JSON log file (api/logging_config.py) carries the real level per
      // record — this only keeps an obviously-failing line from being
      // filed as INFO in the Electron main process's own log.
      if (/\b(ERROR|CRITICAL|Traceback)\b/.test(line)) {
        logger.error(line, { source: "backend" });
      } else {
        logger.info(line, { source: "backend" });
      }
    },
    undefined,
    backendEnv,
  );
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
