// A minimal stand-in for `python -m api`'s JSON-RPC stdio protocol, used only
// by backend.test.ts: prints a ready event, then echoes "echo" requests and
// exits immediately (without responding) on a "crash" request, to exercise
// BackendClient's readiness/correlation/crash-detection behavior without a
// real Python process.
const readline = require("node:readline");

if (process.env.ATRIA_TEST_EXTRA_ENV) {
  process.stderr.write(`extra-env:${process.env.ATRIA_TEST_EXTRA_ENV}\n`);
}
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
