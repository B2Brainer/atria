// Registers the seven IPC channels the preload bridge forwards to, each a
// thin pass-through to the BackendClient — the main process never interprets
// or logs the payload content itself (no credential material is read here).
import { ipcMain } from "electron";

import type { BackendClient } from "./backend";

export const CHANNELS = {
  initiate: "atria:initiate",
  get: "atria:get",
  listByCycle: "atria:list-by-cycle",
  listCycles: "atria:list-cycles",
  setCredential: "atria:set-credential",
  getCredentialStatus: "atria:get-credential-status",
  removeCredential: "atria:remove-credential",
} as const;

export function registerIpcHandlers(backend: BackendClient): void {
  ipcMain.handle(CHANNELS.initiate, (_event, request: unknown, cycleId: string) =>
    backend.call("initiate", { request, cycle_id: cycleId }),
  );
  ipcMain.handle(CHANNELS.get, (_event, recordId: string) =>
    backend.call("get", { record_id: recordId }),
  );
  ipcMain.handle(CHANNELS.listByCycle, (_event, cycleId: string) =>
    backend.call("list_by_cycle", { cycle_id: cycleId }),
  );
  ipcMain.handle(CHANNELS.listCycles, () => backend.call("list_cycles"));
  ipcMain.handle(CHANNELS.setCredential, (_event, providerId: string, secret: string) =>
    backend.call("set_credential", { provider_id: providerId, secret }),
  );
  ipcMain.handle(CHANNELS.getCredentialStatus, (_event, providerId: string) =>
    backend.call("get_credential_status", { provider_id: providerId }),
  );
  ipcMain.handle(CHANNELS.removeCredential, (_event, providerId: string) =>
    backend.call("remove_credential", { provider_id: providerId }),
  );
}
