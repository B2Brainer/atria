import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { installCrashCapture, LOG_BACKUP_COUNT, Logger } from "./logger";

describe("Logger", () => {
  let dir: string;
  let logPath: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "atria-logger-"));
    logPath = path.join(dir, "atria-main.log");
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("writes a JSON line per record", () => {
    const logger = new Logger(logPath);
    logger.info("hello", { source: "test" });

    const lines = readFileSync(logPath, "utf8").trim().split("\n");
    expect(lines).toHaveLength(1);
    const record = JSON.parse(lines[0]);
    expect(record.message).toBe("hello");
    expect(record.level).toBe("INFO");
    expect(record.source).toBe("test");
  });

  it("rotates once the active file reaches the configured size, retaining at most LOG_BACKUP_COUNT files", () => {
    const logger = new Logger(logPath);
    const chunk = "x".repeat(2000);
    for (let i = 0; i < 12000; i += 1) {
      logger.info(chunk);
    }

    const rotated = [1, 2, 3, 4].filter((n) => existsSync(`${logPath}.${n}`));
    expect(rotated.length).toBeLessThanOrEqual(LOG_BACKUP_COUNT);
    expect(existsSync(`${logPath}.${LOG_BACKUP_COUNT + 1}`)).toBe(false);
    expect(existsSync(logPath)).toBe(true);
  });

  it("captures an uncaught exception as a log record", () => {
    const logger = new Logger(logPath);
    installCrashCapture(logger);

    process.emit("uncaughtException", new Error("boom"));

    const lines = readFileSync(logPath, "utf8").trim().split("\n");
    const record = JSON.parse(lines[lines.length - 1]);
    expect(record.level).toBe("ERROR");
    expect(record.error).toBe("boom");
  });
});
