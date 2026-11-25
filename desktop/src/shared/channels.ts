// The IPC channel names, shared between the main process (registers
// ipcMain.handle on each) and the preload bridge (invokes ipcRenderer on
// each). Deliberately its own module with no Electron import: the preload
// script previously imported this constant from `main/ipc.ts`, which also
// imports `electron`'s `ipcMain` — bundling a main-process-only module
// (with a main-only API) into the sandboxed preload context for no reason
// beyond this one constant. A module with any future top-level side effect
// in `main/ipc.ts` would then execute in preload too.
export const CHANNELS = {
  initiate: "atria:initiate",
  get: "atria:get",
  listByCycle: "atria:list-by-cycle",
  listCycles: "atria:list-cycles",
  setCredential: "atria:set-credential",
  getCredentialStatus: "atria:get-credential-status",
  removeCredential: "atria:remove-credential",
} as const;
