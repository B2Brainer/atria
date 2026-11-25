// Structured (JSON-lines), size-rotated local logging for the Electron main
// process (Increment 6's resolved logging requirement — mirrors
// `api/logging_config.py`'s parameters: a maximum individual file size of
// 5 MB, and at most 3 retained rotated files (4 files total on disk,
// including the active file)). No log record may ever contain a resolved
// secret, credential value, provider authentication header, or sensitive
// interaction content — only non-sensitive operational metadata.
import { existsSync, mkdirSync, renameSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";

export const LOG_MAX_BYTES = 5 * 1024 * 1024;
export const LOG_BACKUP_COUNT = 3;

export class Logger {
  constructor(private readonly logPath: string) {
    mkdirSync(path.dirname(logPath), { recursive: true });
  }

  info(message: string, extra?: Record<string, unknown>): void {
    this.write("INFO", message, extra);
  }

  error(message: string, extra?: Record<string, unknown>): void {
    this.write("ERROR", message, extra);
  }

  private write(level: string, message: string, extra?: Record<string, unknown>): void {
    this.rotateIfNeeded();
    const record = { timestamp: new Date().toISOString(), level, message, ...extra };
    writeFileSync(this.logPath, `${JSON.stringify(record)}\n`, { flag: "a" });
  }

  private rotateIfNeeded(): void {
    if (!existsSync(this.logPath) || statSync(this.logPath).size < LOG_MAX_BYTES) return;

    for (let index = LOG_BACKUP_COUNT; index >= 1; index -= 1) {
      const source = `${this.logPath}.${index}`;
      if (!existsSync(source)) continue;
      if (index === LOG_BACKUP_COUNT) {
        unlinkSync(source);
      } else {
        renameSync(source, `${this.logPath}.${index + 1}`);
      }
    }
    renameSync(this.logPath, `${this.logPath}.1`);
  }
}

/** Installs process-level crash capture: an uncaught exception or unhandled
 * promise rejection is recorded (crash diagnostic) rather than silently lost
 * to Electron's default top-level reporting. */
export function installCrashCapture(logger: Logger): void {
  process.on("uncaughtException", (error) => {
    logger.error("uncaught exception in Electron main process", {
      error: error.message,
      stack: error.stack,
    });
    // Attaching this handler suppresses Node's own default behavior for an
    // uncaught exception (print + terminate) -- per spec, the exception is
    // "captured ... before the process exits", not captured in place of
    // exiting. Logger's writes are synchronous (writeFileSync), so the
    // record above is already durable before this runs.
    process.exit(1);
  });
  process.on("unhandledRejection", (reason) => {
    // Lower severity than an uncaught exception by convention (and not
    // what the spec's "process exits" language describes): logged, but
    // does not itself terminate the process.
    logger.error("unhandled promise rejection in Electron main process", {
      error: reason instanceof Error ? reason.message : String(reason),
    });
  });
}
