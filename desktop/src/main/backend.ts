// Owns the Python backend subprocess's full lifecycle (Increment 5, Resolved
// Decision 2): spawn on launch, a readiness handshake before routing
// requests, crash detection with a bounded restart policy, and graceful
// termination on app quit — no orphaned process, no silently lost in-flight
// request.
import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface } from "node:readline";

const MAX_RESTART_ATTEMPTS = 3;
const DEFAULT_READY_TIMEOUT_MS = 10_000;
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
  // Only a failure AFTER the backend has reached readiness at least once
  // triggers an automatic restart. A failure during the very first attempt
  // (start() is still awaiting `this.ready`) must not: start() awaits one
  // specific promise instance, and reassigning `this.ready` to a new
  // restart attempt behind its back would leave start() rejecting with
  // the ORIGINAL error while a replacement backend silently spins up
  // un-awaited by anyone. The first attempt's failure is reported to
  // start()'s caller instead, who decides whether to retry.
  private everReady = false;
  // True exactly when no further automatic recovery is in flight: either
  // this attempt was the first and it failed (no restart is attempted —
  // see everReady above), or restart attempts are exhausted. call() checks
  // this directly rather than inferring unavailability from this.ready's
  // settled state or the current child's exitCode/signalCode: a stale
  // `this.ready` can be a long-settled RESOLVED promise from an attempt
  // that became ready and only crashed later (settleReady is already null
  // by then, so a later failure has nothing left to reject), and relying
  // on exitCode/signalCode alone depends on their having been set by the
  // time call() checks them (not guaranteed for a spawn that never
  // produced a real process at all) — an explicit flag has neither
  // dependency. Cleared the moment any attempt reaches readiness.
  private unavailable = false;

  constructor(
    private readonly command: string,
    private readonly args: string[],
    private readonly cwd: string,
    private readonly onLog: (line: string) => void = () => {},
    // Test-only override: a fixture that deliberately never becomes ready
    // needs a short bound, not the real 10s default, to exercise the
    // readiness-rejection path in a reasonable test runtime.
    private readonly readyTimeoutMs: number = DEFAULT_READY_TIMEOUT_MS,
  ) {}

  async start(): Promise<void> {
    this.ready = this.spawnAndWaitReady();
    this.preventUnhandledRejection(this.ready);
    await this.ready;
  }

  // A readiness failure with no in-flight call() awaiting it yet (notably,
  // a restart triggered by onProcessFailure() with nobody currently calling
  // the backend) would otherwise be an unhandled promise rejection — Node
  // terminates the process on one by default. This attaches a side
  // observer that swallows it for Node's bookkeeping only; `this.ready`
  // itself is untouched, so a later `await this.ready` (in call() or a
  // fresh start()) still sees and re-throws the real rejection.
  private preventUnhandledRejection(promise: Promise<void>): void {
    promise.catch(() => {});
  }

  private rejectAllPending(error: Error): void {
    for (const pending of this.pending.values()) {
      pending.reject(error);
    }
    this.pending.clear();
  }

  private spawnAndWaitReady(): Promise<void> {
    const child = spawn(this.command, this.args, { cwd: this.cwd });
    this.process = child;

    const stdoutLines = createInterface({ input: child.stdout });
    const stderrLines = createInterface({ input: child.stderr });
    stderrLines.on("line", (line) => this.onLog(line));

    let settleReady: ((error: Error | null) => void) | null = null;
    // A spawn/stdio 'error', an 'exit', and a readiness timeout are three
    // independent sources that can all fire for the same failed attempt —
    // this guards the restart/give-up bookkeeping (onProcessFailure) so it
    // runs exactly once per spawnAndWaitReady() call, no matter which
    // source notices first or whether more than one does.
    let failureHandled = false;

    const readyPromise = new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        onProcessFailure(new BackendUnavailableError("backend did not report readiness in time"));
      }, this.readyTimeoutMs);

      settleReady = (error) => {
        settleReady = null;
        clearTimeout(timeout);
        if (error) reject(error);
        else resolve();
      };

      stdoutLines.on("line", (line) => {
        // A stale child's (see below) belated output must never resolve or
        // reject a LATER attempt's readiness, nor be dispatched as a
        // message against the current child's pending calls.
        if (child !== this.process) return;
        let message: RpcMessage;
        try {
          message = JSON.parse(line) as RpcMessage;
        } catch {
          // Never log the line's own content: a malformed stdout line from
          // the backend could itself be secret-shaped (the same reasoning
          // api/rpc.py's non-object-message handling applies on its side
          // of this same channel) — only its length is safe to report.
          this.onLog(`malformed backend stdout line (${line.length} chars, not valid JSON)`);
          return;
        }
        if (settleReady && message.event === "ready") {
          this.everReady = true;
          this.unavailable = false;
          settleReady(null);
          return;
        }
        this.handleMessage(message);
      });
    });

    // The one place that settles this attempt's readiness, tears down a
    // still-alive child (a readiness timeout or a stdin failure doesn't
    // necessarily mean the process itself exited — without this it would
    // become an orphan once we move on), and runs the bounded restart/
    // give-up decision. Invoked by 'exit', a spawn/stdio 'error', the
    // readiness timeout, and a stdin 'error' alike, so none of them can
    // bypass the restart counter, and `failureHandled` ensures it runs
    // exactly once per attempt regardless of how many of them fire.
    const onProcessFailure = (error: Error): void => {
      if (child !== this.process || failureHandled) return;
      failureHandled = true;
      settleReady?.(error);
      this.rejectAllPending(error);

      if (this.shuttingDown) {
        // stop() already owns an orderly SIGTERM-then-timeout-then-SIGKILL
        // teardown of this exact child; escalating straight to SIGKILL
        // here (e.g. on a stdin error racing stop()'s own SIGTERM) would
        // cut that short instead of letting it finish gracefully. Still
        // mark unavailable: no replacement is coming during a shutdown, so
        // a call() racing this failure (registering a pending entry after
        // rejectAllPending() above already ran) must still refuse instead
        // of hanging on a reply that will never arrive.
        this.unavailable = true;
        return;
      }
      if (child.exitCode === null && child.signalCode === null) {
        this.tryKill(child, "SIGKILL");
      }
      if (!this.everReady) {
        // The very first attempt never reached readiness: start() is
        // still awaiting exactly this promise, and already receives
        // `error` via settleReady above. Restarting behind its back here
        // would spin up a second, un-awaited backend racing start()'s own
        // rejection — instead, the caller decides whether to retry. No
        // replacement is coming, so call() must refuse too.
        this.unavailable = true;
        return;
      }
      if (this.restartCount >= MAX_RESTART_ATTEMPTS) {
        this.onLog(`backend exceeded ${MAX_RESTART_ATTEMPTS} restart attempts; giving up`);
        this.unavailable = true;
        return;
      }
      this.restartCount += 1;
      this.onLog(`restarting backend (attempt ${this.restartCount}/${MAX_RESTART_ATTEMPTS})`);
      this.ready = this.spawnAndWaitReady();
      this.preventUnhandledRejection(this.ready);
    };

    child.on("exit", (code) => {
      if (child !== this.process) return;
      this.onLog(`backend process exited (code ${code ?? "unknown"})`);
      onProcessFailure(
        new BackendUnavailableError("backend process exited while a request was pending"),
      );
    });

    // Without this listener, a failed spawn (the command not found, a bad
    // ATRIA_PYTHON override) emits an uncaught 'error' event on the
    // ChildProcess, which crashes the whole Electron main process rather
    // than surfacing as a normal BackendUnavailableError. A failed spawn is
    // not guaranteed to also emit 'exit' on every platform/Node version, so
    // this runs the same onProcessFailure() path directly rather than
    // relying solely on 'exit' to eventually notice (failureHandled above
    // ensures a later 'exit' for this same attempt is a no-op, not a
    // second restart).
    child.on("error", (err) => {
      if (child !== this.process) return;
      this.onLog(`backend process error: ${err.message}`);
      onProcessFailure(new BackendUnavailableError(`backend process error: ${err.message}`));
    });

    // child.on("error") does NOT receive errors from the stdin stream
    // itself (e.g. EPIPE writing to an already-exited process) — those are
    // a separate EventEmitter with their own 'error' event, uncaught by
    // default. Routed through onProcessFailure (not just a pending-call
    // rejection) because a stdin failure on an otherwise-still-alive child
    // leaves it unresponsive forever if nothing restarts/gives up on it;
    // the `child !== this.process` guard stops a late error from a
    // torn-down previous child from reaching calls already pending against
    // a freshly restarted one.
    child.stdin.on("error", (err) => {
      if (child !== this.process) return;
      this.onLog(`backend stdin error: ${err.message}`);
      onProcessFailure(new BackendUnavailableError(`backend stdin error: ${err.message}`));
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

  async call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    // A failed attempt's own rejection can itself trigger a replacement
    // spawn (onProcessFailure reassigns this.ready synchronously, before
    // this await's continuation runs) — catching once and proceeding would
    // let call() write to that replacement before IT has reached
    // readiness. Keep following this.ready until it settles successfully,
    // stops changing (no further replacement is coming), or unavailable is
    // set (a terminal failure, chased no further).
    let pendingReady = this.ready;
    for (;;) {
      await pendingReady.catch(() => undefined);
      if (this.unavailable || this.ready === pendingReady) break;
      pendingReady = this.ready;
    }
    if (this.unavailable) {
      throw new BackendUnavailableError("backend process is not running");
    }
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
    // child.pid is undefined when the process never actually spawned (e.g.
    // ENOENT) — such a child may never emit 'exit' at all, so without this
    // check stop() would otherwise wait out the full
    // GRACEFUL_SHUTDOWN_TIMEOUT_MS every time, delaying whatever waits on
    // stop() (e.g. the startup-failure error dialog) for no reason.
    if (!child || child.exitCode !== null || child.signalCode !== null || child.pid === undefined) {
      return;
    }

    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        this.tryKill(child, "SIGKILL");
        resolve();
      }, GRACEFUL_SHUTDOWN_TIMEOUT_MS);
      child.once("exit", () => {
        clearTimeout(timeout);
        resolve();
      });
      if (!this.tryKill(child, "SIGTERM")) {
        // kill() itself failed synchronously (rare, but documented as
        // possible for an invalid signal/permission case) — nothing will
        // ever fire 'exit' for this attempt, so resolve immediately rather
        // than waiting out the timeout for an event that can't arrive.
        clearTimeout(timeout);
        resolve();
      }
    });
  }

  // child.kill() is documented to return false (not throw) on an ordinary
  // failure to deliver the signal, but this still guards against any
  // unexpected throw so stop() itself can never reject — its callers
  // (before-quit, the startup-failure path) depend on that.
  private tryKill(child: ChildProcessWithoutNullStreams, signal: NodeJS.Signals): boolean {
    try {
      return child.kill(signal);
    } catch (err) {
      this.onLog(`backend kill(${signal}) failed: ${(err as Error).message}`);
      return false;
    }
  }
}
