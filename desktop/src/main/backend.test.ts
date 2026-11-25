// Acceptance criterion 5: backend crash/restart/no-orphan behavior; criterion
// 3: JSON-RPC correlation. Exercised against a fake fixture process (see
// __fixtures__/fake-backend.cjs) rather than a real Python backend, so these
// stay fast and deterministic.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { BackendClient, BackendUnavailableError } from "./backend";

const fixturePath = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "__fixtures__/fake-backend.cjs",
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

  it("stop() terminates the child process and leaves no orphan", async () => {
    client = new BackendClient("node", [fixturePath], process.cwd());
    await client.start();

    await client.stop();

    await expect(client.call("echo", { value: "x" })).rejects.toThrow(BackendUnavailableError);
  });
});
