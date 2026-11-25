// Owns the Python backend subprocess's full lifecycle (Increment 5, Resolved
// Decision 2): spawn on launch, a readiness handshake before routing
// requests, crash detection with a bounded restart policy, and graceful
// termination on app quit — no orphaned process, no silently lost in-flight
// request.
import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface } from "node:readline";

const MAX_RESTART_ATTEMPTS = 3;
const READY_TIMEOUT_MS = 10_000;
const GRACEFUL_SHUTDOWN_TIMEOUT_MS = 5_000;

interface PendingCall {
  resolve(value: unknown): void;
  reject(reason: Error): void;
}

interface RpcMessage {
  id: number | string | null;
  result?: unknown;
  error?: { message: string };
  event?: string;
}

export class BackendUnavailableError extends Error {}

/** Spawns, supervises, and talks JSON-RPC to the `python -m api` backend. */
export class BackendClient {
  private process: ChildProcessWithoutNullStreams | null = null;
  private nextId = 1;
  private readonly pending = new Map<number, PendingCall>();
  private restartCount = 0;
  private shuttingDown = false;
  private ready: Promise<void> = Promise.resolve();

  constructor(
    private readonly command: string,
    private readonly args: string[],
    private readonly cwd: string,
    private readonly onLog: (line: string) => void = () => {},
  ) {}

  async start(): Promise<void> {
    this.ready = this.spawnAndWaitReady();
    await this.ready;
  }

  private spawnAndWaitReady(): Promise<void> {
    const child = spawn(this.command, this.args, { cwd: this.cwd });
    this.process = child;

    const stdoutLines = createInterface({ input: child.stdout });
    const stderrLines = createInterface({ input: child.stderr });
    stderrLines.on("line", (line) => this.onLog(line));

    const readyPromise = new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new BackendUnavailableError("backend did not report readiness in time"));
      }, READY_TIMEOUT_MS);

      let resolvedReady = false;
      stdoutLines.on("line", (line) => {
        let message: RpcMessage;
        try {
          message = JSON.parse(line) as RpcMessage;
        } catch {
          this.onLog(`malformed backend stdout line: ${line}`);
          return;
        }
        if (!resolvedReady && message.event === "ready") {
          resolvedReady = true;
          clearTimeout(timeout);
          resolve();
          return;
        }
        this.handleMessage(message);
      });
    });

    child.on("exit", (code) => {
      this.onLog(`backend process exited (code ${code ?? "unknown"})`);
      this.handleExit();
    });

    return readyPromise;
  }

  private handleMessage(message: RpcMessage): void {
    if (typeof message.id !== "number") return;
    const pending = this.pending.get(message.id);
    if (!pending) return;
    this.pending.delete(message.id);
    if (message.error) {
      pending.reject(new Error(message.error.message));
    } else {
      pending.resolve(message.result);
    }
  }

  private handleExit(): void {
    const error = new BackendUnavailableError("backend process exited while a request was pending");
    for (const pending of this.pending.values()) {
      pending.reject(error);
    }
    this.pending.clear();

    if (this.shuttingDown) return;

    if (this.restartCount >= MAX_RESTART_ATTEMPTS) {
      this.onLog(`backend exceeded ${MAX_RESTART_ATTEMPTS} restart attempts; giving up`);
      return;
    }
    this.restartCount += 1;
    this.onLog(`restarting backend (attempt ${this.restartCount}/${MAX_RESTART_ATTEMPTS})`);
    this.ready = this.spawnAndWaitReady();
  }

  async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    await this.ready;
    const child = this.process;
    if (!child || child.exitCode !== null || child.signalCode !== null) {
      throw new BackendUnavailableError("backend process is not running");
    }
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
      child.stdin.write(`${JSON.stringify({ id, method, params })}\n`);
    });
  }

  async stop(): Promise<void> {
    this.shuttingDown = true;
    const child = this.process;
    if (!child || child.exitCode !== null || child.signalCode !== null) return;

    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        child.kill("SIGKILL");
        resolve();
      }, GRACEFUL_SHUTDOWN_TIMEOUT_MS);
      child.once("exit", () => {
        clearTimeout(timeout);
        resolve();
      });
      child.kill("SIGTERM");
    });
  }
}
