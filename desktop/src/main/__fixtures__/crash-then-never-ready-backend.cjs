// A fixture used only by backend.test.ts to exercise the ONE scenario that
// genuinely needs preventUnhandledRejection(): a successful initial start(),
// then a crash whose restart attempt never becomes ready — with nothing
// (not even a fire-and-forget .catch()) touching that specific restart
// promise until a later call(), if ever. start()'s own `await this.ready`
// already protects the FIRST attempt — this fixture lets a test reach the
// restart attempt specifically, which a never-emits-"ready" fixture alone
// cannot (there is no successful first attempt to crash out of).
//
// First invocation: behaves like fake-backend.cjs (emits ready, echoes,
// exits on "crash") and writes a marker file. Second invocation (marker
// already exists): never emits "ready".
const fs = require("node:fs");
const readline = require("node:readline");

const markerPath = process.env.ATRIA_TEST_RESTART_MARKER;
const isRestart = fs.existsSync(markerPath);

if (isRestart) {
  setInterval(() => {}, 1000);
} else {
  fs.writeFileSync(markerPath, "spawned");
  process.stdout.write(`${JSON.stringify({ id: null, event: "ready" })}\n`);

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
