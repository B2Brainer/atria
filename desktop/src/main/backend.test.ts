// Acceptance criterion 5: backend crash/restart/no-orphan behavior; criterion
// 3: JSON-RPC correlation. Exercised against a fake fixture process (see
// __fixtures__/fake-backend.cjs) rather than a real Python backend, so these
// stay fast and deterministic.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { BackendClient, BackendUnavailableError } from "./backend";

const fixturesDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "__fixtures__");
const fixturePath = path.join(fixturesDir, "fake-backend.cjs");
const neverReadyFixturePath = path.join(fixturesDir, "never-ready-backend.cjs");
const crashThenNeverReadyFixturePath = path.join(
  fixturesDir,
  "crash-then-never-ready-backend.cjs",
);

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

  it("start()'s own initial readiness rejection never surfaces as an unhandled promise rejection", async () => {
    // start() itself always awaits this.ready right after assigning it, so
    // this mainly documents that the first attempt is safe by construction
    // — the scenario with no safety net at all is the restart path,
    // covered by the next test.
    const unhandled: unknown[] = [];
    const onUnhandledRejection = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandledRejection);

    try {
      client = new BackendClient("node", [neverReadyFixturePath], process.cwd(), () => {}, 50);
      await expect(client.start()).rejects.toThrow(BackendUnavailableError);
    } finally {
      process.off("unhandledRejection", onUnhandledRejection);
    }

    expect(unhandled).toEqual([]);
  });

  it("a restart attempt's readiness rejection never surfaces as an unhandled promise rejection", async () => {
    // Regression: the one scenario start()'s own `await this.ready` does
    // NOT cover — a crash-triggered restart (onProcessFailure's
    // `this.ready = this.spawnAndWaitReady()`) whose new attempt never
    // becomes ready, with no in-flight call() or anything else awaiting
    // that specific promise. A fixture that behaves normally on its first
    // spawn but never emits "ready" on its second (tracked via a marker
    // file, since env is inherited into the child) reaches this exact
    // path: succeed -> crash -> restart -> restart's readiness hangs.
    const markerDir = mkdtempSync(path.join(tmpdir(), "atria-restart-marker-"));
    const markerPath = path.join(markerDir, "spawned");
    const previousMarker = process.env.ATRIA_TEST_RESTART_MARKER;
    process.env.ATRIA_TEST_RESTART_MARKER = markerPath;

    const unhandled: unknown[] = [];
    const onUnhandledRejection = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandledRejection);
    const logs: string[] = [];

    try {
      client = new BackendClient(
        "node",
        [crashThenNeverReadyFixturePath],
        process.cwd(),
        (line) => logs.push(line),
        // Generous enough that the FIRST attempt's genuine "ready" (a real
        // spawned subprocess under potential runner load) reliably lands
        // within it, while still short enough that the wait below can
        // comfortably outlast at least one additional (restart) timeout.
        150,
      );
      await client.start();

      // Crash with no pending call racing it, so nothing awaits the
      // restart's readiness promise until this test's own assertion below.
      await client.call("crash").catch(() => undefined);
      await new Promise((resolve) => setTimeout(resolve, 600));
    } finally {
      process.off("unhandledRejection", onUnhandledRejection);
      if (previousMarker === undefined) delete process.env.ATRIA_TEST_RESTART_MARKER;
      else process.env.ATRIA_TEST_RESTART_MARKER = previousMarker;
      rmSync(markerDir, { recursive: true, force: true });
    }

    expect(unhandled).toEqual([]);
    // The restart's own readiness timeout must route through
    // onProcessFailure (killing the hung child and applying the bounded
    // restart policy) rather than only rejecting the readiness promise —
    // confirmed by at least one further restart attempt being logged
    // (the crash-triggered restart, plus the timeout-triggered one(s) that
    // follow it within the 200ms window, exact count timing-sensitive).
    expect(logs.filter((line) => line.includes("restarting backend")).length).toBeGreaterThanOrEqual(2);
  });

  it("a failure during the very first attempt does not trigger a silent background restart", async () => {
    // Regression: restarting behind start()'s back on its very first
    // attempt would leave a second, un-awaited backend racing start()'s
    // own rejection. A failure before readiness has ever been reached
    // must be reported to start()'s caller only, never auto-restarted.
    const logs: string[] = [];
    client = new BackendClient("node", [neverReadyFixturePath], process.cwd(), (line) =>
      logs.push(line), 50);

    await expect(client.start()).rejects.toThrow(BackendUnavailableError);
    await new Promise((resolve) => setTimeout(resolve, 100));

    expect(logs.some((line) => line.includes("restarting backend"))).toBe(false);
  });

  it("call() rejects after a failed first start(), rather than proceeding against a dead child", async () => {
    // Regression: a prior fix made `await this.ready` swallow its own
    // rejection (`.catch(() => undefined)`), relying solely on
    // exitCode/signalCode to catch this in call() — but a child that never
    // actually spawned (this fixture never becomes ready, which here is
    // the same "no real process" shape as an ENOENT spawn) may leave both
    // null, so that guard alone cannot be trusted to fire.
    client = new BackendClient("node", [neverReadyFixturePath], process.cwd(), () => {}, 50);
    await client.start().catch(() => undefined);

    await expect(client.call("echo", { value: "x" })).rejects.toThrow(BackendUnavailableError);
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
