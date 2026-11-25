// A fixture that deliberately never emits the {"event":"ready"} handshake,
// used only by backend.test.ts to force a genuine readiness-timeout
// rejection (exercising BackendClient's readyTimeoutMs path) without
// waiting on the real 10s default.
setInterval(() => {}, 1000);
