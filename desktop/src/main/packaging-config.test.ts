// Increment 6 — static/config checks for packaging, signing/notarization,
// the release workflow, and the no-auto-update constraint. These assert on
// the committed configuration files' shape, not on an actual signed build
// (which requires real Apple Developer credentials — see AC 2's PENDING
// sub-check, specs/increment-06-distribution-and-operations.md).
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const DESKTOP_ROOT = path.resolve(__dirname, "../..");
const REPO_ROOT = path.resolve(DESKTOP_ROOT, "..");

const electronBuilderConfig = readFileSync(
  path.join(DESKTOP_ROOT, "electron-builder.yml"),
  "utf8",
);
const releaseWorkflow = readFileSync(
  path.join(REPO_ROOT, ".github/workflows/release.yml"),
  "utf8",
);
const ciWorkflow = readFileSync(path.join(REPO_ROOT, ".github/workflows/ci.yml"), "utf8");
const packageJson = JSON.parse(readFileSync(path.join(DESKTOP_ROOT, "package.json"), "utf8"));

describe("electron-builder packaging configuration (AC 1, 2)", () => {
  it("bundles the standalone Python runtime and backend source as extraResources", () => {
    expect(electronBuilderConfig).toMatch(/from:\s*resources\/python-dist/);
    expect(electronBuilderConfig).toMatch(/to:\s*python-dist/);
    expect(electronBuilderConfig).toMatch(/from:\s*resources\/backend/);
    expect(electronBuilderConfig).toMatch(/to:\s*backend/);
  });

  it("targets macOS dmg and zip artifacts", () => {
    expect(electronBuilderConfig).toMatch(/- dmg/);
    expect(electronBuilderConfig).toMatch(/- zip/);
  });

  it("is configured for hardened-runtime signing and an afterSign notarization hook", () => {
    expect(electronBuilderConfig).toMatch(/hardenedRuntime:\s*true/);
    expect(electronBuilderConfig).toMatch(/entitlements:\s*build\/entitlements\.mac\.plist/);
    expect(electronBuilderConfig).toMatch(/afterSign:\s*scripts\/notarize\.cjs/);
  });
});

describe("notarization credentials (AC 2, 3)", () => {
  it("the release workflow supplies signing/notarization credentials from GitHub Actions secrets, never a hardcoded value", () => {
    expect(releaseWorkflow).toMatch(/CSC_LINK:\s*\$\{\{\s*secrets\.CSC_LINK\s*\}\}/);
    expect(releaseWorkflow).toMatch(/CSC_KEY_PASSWORD:\s*\$\{\{\s*secrets\.CSC_KEY_PASSWORD\s*\}\}/);
    expect(releaseWorkflow).toMatch(/APPLE_ID:\s*\$\{\{\s*secrets\.APPLE_ID\s*\}\}/);
    expect(releaseWorkflow).toMatch(
      /APPLE_APP_SPECIFIC_PASSWORD:\s*\$\{\{\s*secrets\.APPLE_APP_SPECIFIC_PASSWORD\s*\}\}/,
    );
    expect(releaseWorkflow).toMatch(/APPLE_TEAM_ID:\s*\$\{\{\s*secrets\.APPLE_TEAM_ID\s*\}\}/);
  });

  it("the notarize hook skips (not fails) when Apple credentials are absent", () => {
    const notarizeHook = readFileSync(path.join(DESKTOP_ROOT, "scripts/notarize.cjs"), "utf8");
    expect(notarizeHook).toMatch(/if \(!isSigned \|\| !appleId \|\| !applePassword \|\| !teamId\)/);
    expect(notarizeHook).toMatch(/return;/);
  });

  it("the release workflow labels an unsigned build's artifacts distinctly from a signed release", () => {
    expect(releaseWorkflow).toMatch(/unsigned/);
  });
});

describe("release workflow trigger independence from ci.yml (AC 4)", () => {
  it("release.yml triggers only on a version-tag push", () => {
    expect(releaseWorkflow).toMatch(/tags:\s*\n\s*-\s*"v\*"/);
    expect(releaseWorkflow).not.toMatch(/pull_request:/);
  });

  it("ci.yml's own push/pull_request triggers are unaffected by this increment", () => {
    expect(ciWorkflow).toMatch(/push:/);
    expect(ciWorkflow).toMatch(/pull_request:/);
    expect(ciWorkflow).not.toMatch(/tags:/);
  });
});

describe("no auto-update dependency (AC 5)", () => {
  it("declares no electron-updater (or equivalent) dependency", () => {
    const allDeps = {
      ...(packageJson.dependencies ?? {}),
      ...(packageJson.devDependencies ?? {}),
    };
    expect(Object.keys(allDeps)).not.toContain("electron-updater");
  });

  it("no source file references an update-check/autoUpdater API", () => {
    // A grep-equivalent check over the main process source, the only place
    // such a call could plausibly be wired in.
    const indexSource = readFileSync(path.join(DESKTOP_ROOT, "src/main/index.ts"), "utf8");
    expect(indexSource).not.toMatch(/autoUpdater/);
    expect(indexSource).not.toMatch(/checkForUpdates/);
  });
});
