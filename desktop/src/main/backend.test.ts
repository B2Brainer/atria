// Acceptance criterion 5: backend crash/restart/no-orphan behavior; criterion
// 3: JSON-RPC correlation. Exercised against a fake fixture process (see
// __fixtures__/fake-backend.cjs) rather than a real Python backend, so these
// stay fast and deterministic.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { BackendClient, BackendUnavailableError } from "./backend";

const fixturesDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "__fixtures__");
const fixturePath = path.join(fixturesDir, "fake-backend.cjs");
const neverReadyFixturePath = path.join(fixturesDir, "never-ready-backend.cjs");

let client: BackendClient | null = null;

afterEach(async () => {
  if (client) await client.stop();
  client = null;
});

describe("BackendClient", () => {
  it("resolves start() once the backend reports readiness", async () => {
    client = new BackendClient("node", [fixturePath], process.cwd());
    await expect(client.start()).resolves.toBeUndefined();
  });

  it("correlates a request to its response by id", async () => {
    client = new BackendClient("node", [fixturePath], process.cwd());
    await client.start();

    const result = await client.call<string>("echo", { value: "hello" });

    expect(result).toBe("hello");
  });

  it("rejects a pending request with a distinguishable error when the backend crashes", async () => {
    const logs: string[] = [];
    client = new BackendClient("node", [fixturePath], process.cwd(), (line) => logs.push(line));
    await client.start();

    await expect(client.call("crash")).rejects.toThrow(BackendUnavailableError);
    // The crash also triggers an automatic restart (see the next test); let
    // that settle before this test (and its afterEach stop()) ends, so no
    // dangling readiness timeout fires after the suite has moved on.
    await new Promise((resolve) => setTimeout(resolve, 200));
  });

  it("restarts the backend after a crash, up to the bounded attempt limit", async () => {
    client = new BackendClient("node", [fixturePath], process.cwd());
    await client.start();

    await client.call("crash").catch(() => undefined);
    // The restart happens asynchronously off the "exit" event; give it a tick.
    await new Promise((resolve) => setTimeout(resolve, 200));

    const result = await client.call<string>("echo", { value: "still-alive" });
    expect(result).toBe("still-alive");
  });

  it("gives up restarting after the bounded attempt limit is exhausted", async () => {
    client = new BackendClient("node", [fixturePath], process.cwd());
    await client.start();

    // MAX_RESTART_ATTEMPTS = 3: the backend crashes four times in a row —
    // one more than the bound — and must stop restarting after the third.
    for (let attempt = 0; attempt < 4; attempt += 1) {
      await client.call("crash").catch(() => undefined);
      await new Promise((resolve) => setTimeout(resolve, 200));
    }

    await expect(client.call("echo", { value: "x" })).rejects.toThrow(BackendUnavailableError);
  });

  it("a readiness failure never surfaces as an unhandled promise rejection", async () => {
    // Regression: a readiness rejection (here, a genuine timeout — the
    // fixture never emits "ready") with no in-flight call() awaiting it
    // must not be an unhandled rejection — Node terminates the process on
    // one by default. A short readyTimeoutMs keeps this fast instead of
    // waiting the real 10s default.
    const unhandled: unknown[] = [];
    const onUnhandledRejection = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandledRejection);

    try {
      client = new BackendClient(
        "node",
        [neverReadyFixturePath],
        process.cwd(),
        () => {},
        50,
      );
      // Deliberately not awaited: this is exactly the "nothing is awaiting
      // this readiness promise yet" scenario the fix protects against.
      void client.start().catch(() => undefined);
      await new Promise((resolve) => setTimeout(resolve, 200));
    } finally {
      process.off("unhandledRejection", onUnhandledRejection);
    }

    expect(unhandled).toEqual([]);
  });

  it("rejects start() promptly (not after the full readiness timeout) when the spawn fails", async () => {
    // Regression: before the child.on("error", ...) handler settled
    // readiness directly, a failed spawn (ENOENT) relied solely on 'exit'
    // firing to notice — not guaranteed on every platform/Node version —
    // and even then, a misleading "did not report readiness in time" only
    // surfaced after the full (here, 10s) timeout.
    const logs: string[] = [];
    client = new BackendClient("this-command-does-not-exist", [], process.cwd(), (line) =>
      logs.push(line),
    );

    await expect(client.start()).rejects.toThrow(/backend process error/);

    expect(logs.some((line) => line.includes("backend process error"))).toBe(true);
  });

  it("a stdin write failure rejects pending calls instead of crashing the process", async () => {
    // Regression: child.on("error", ...) alone does not receive errors from
    // the stdin stream itself — a write to an already-destroyed stdin
    // (the real EPIPE race: the process exits between call()'s liveness
    // check and its synchronous write) emits its own uncaught 'error'
    // unless stdin has its own listener.
    const unhandled: unknown[] = [];
    const onUnhandledRejection = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandledRejection);

    try {
      client = new BackendClient("node", [fixturePath], process.cwd());
      await client.start();

      const pendingCall = client.call("echo", { value: "x" });
      // Reach past the public API to force the exact race a liveness check
      // can't fully close: the stream itself fails after the call believed
      // the process alive.
      (client as unknown as { process: { stdin: { destroy(): void } } }).process.stdin.destroy();

      await expect(pendingCall).rejects.toThrow(BackendUnavailableError);
      await new Promise((resolve) => setTimeout(resolve, 100));
    } finally {
      process.off("unhandledRejection", onUnhandledRejection);
    }

    expect(unhandled).toEqual([]);
  });

  it("stop() resolves promptly (not after the shutdown timeout) for a spawn-failed child", async () => {
    // Regression: a child that never actually spawned (ENOENT) has no pid
    // and may never emit 'exit', so stop()'s old liveness guard (exitCode/
    // signalCode only) would proceed to kill() it and wait out the full
    // 5s GRACEFUL_SHUTDOWN_TIMEOUT_MS for an 'exit' that can't arrive.
    client = new BackendClient("this-command-does-not-exist", [], process.cwd());
    await client.start().catch(() => undefined);

    const start = Date.now();
    await client.stop();
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(1000);
  });

  it("stop() terminates the child process and leaves no orphan", async () => {
    client = new BackendClient("node", [fixturePath], process.cwd());
    await client.start();

    await client.stop();

    await expect(client.call("echo", { value: "x" })).rejects.toThrow(BackendUnavailableError);
  });
});
