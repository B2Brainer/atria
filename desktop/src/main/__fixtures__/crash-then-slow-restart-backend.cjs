// A fixture used only by backend.test.ts to prove call() waits for a
// RESTART attempt's own readiness rather than proceeding against it
// immediately. First invocation: behaves like fake-backend.cjs (emits
// ready immediately, echoes, exits on "crash") and writes a marker file.
// Second invocation (marker exists): delays emitting "ready" so a test can
// observe whether a call() issued right after the crash waited for it.
const fs = require("node:fs");
const readline = require("node:readline");

const markerPath = process.env.ATRIA_TEST_RESTART_MARKER;
const isRestart = fs.existsSync(markerPath);
const RESTART_READY_DELAY_MS = 150;

function serve() {
  const rl = readline.createInterface({ input: process.stdin });
  rl.on("line", (line) => {
    const message = JSON.parse(line);
    if (message.method === "crash") {
      process.exit(1);
    }
    const response = { id: message.id, result: message.params?.value };
    process.stdout.write(`${JSON.stringify(response)}\n`);
  });
}

if (isRestart) {
  setTimeout(() => {
    process.stdout.write(`${JSON.stringify({ id: null, event: "ready" })}\n`);
    serve();
  }, RESTART_READY_DELAY_MS);
} else {
  fs.writeFileSync(markerPath, "spawned");
  process.stdout.write(`${JSON.stringify({ id: null, event: "ready" })}\n`);
  serve();
}
