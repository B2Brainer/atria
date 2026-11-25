// Regression guard: a sandboxed Electron renderer (the default since Electron
// 20, and this app's default — no `sandbox: false` is set) can only execute a
// CommonJS preload script. An ESM preload (what this package's "type":
// "module" would otherwise produce, and what electron-vite emitted before
// `electron.vite.config.ts` was corrected) fails to execute under sandbox
// with NO visible error in the main process — contextBridge.exposeInMainWorld
// silently never runs, window.atria stays undefined, and every renderer call
// fails with "Cannot read properties of undefined (reading '<method>')".
// This was caught only by an actual GUI click-through, not by any unit test,
// so it is pinned here against the real build output.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

import { beforeAll, describe, expect, it } from "vitest";

const desktopRoot = path.resolve(__dirname, "../..");
const preloadOutputPath = path.join(desktopRoot, "out/preload/index.js");
// The already-installed local binary, not `npx electron-vite`: npx resolves
// and may fetch from the registry if its local-first lookup ever misses,
// which a test has no business doing (network access, version drift).
const electronViteBin = path.join(desktopRoot, "node_modules/.bin/electron-vite");

beforeAll(() => {
  execFileSync(electronViteBin, ["build"], { cwd: desktopRoot, stdio: "pipe" });
}, 60_000);

describe("preload build output", () => {
  it("is built as CommonJS, not ESM", () => {
    const source = readFileSync(preloadOutputPath, "utf-8");

    expect(source).toContain("require(");
    expect(source).not.toMatch(/^\s*import\s/m);
    expect(source).not.toMatch(/^\s*export\s/m);
  });
});
