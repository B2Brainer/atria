// The sole bridge surface between the isolated renderer and the main
// process (Increment 5 Expected Behavior item 11 / Acceptance Criterion 17):
// exposes exactly the seven operations, nothing else — no direct `require`,
// `fs`, `child_process`, or unrestricted Node API reaches renderer code.
import { contextBridge, ipcRenderer } from "electron";

import { CHANNELS } from "../main/ipc";
import type {
  AtriaBridge,
  CredentialStatus,
  InteractionRecord,
  InteractionRequest,
  SuccessOutcome,
} from "../shared/types";

const bridge: AtriaBridge = {
  initiate: (request: InteractionRequest, cycleId: string) =>
    ipcRenderer.invoke(CHANNELS.initiate, request, cycleId) as Promise<InteractionRecord>,
  get: (recordId: string) =>
    ipcRenderer.invoke(CHANNELS.get, recordId) as Promise<InteractionRecord>,
  listByCycle: (cycleId: string) =>
    ipcRenderer.invoke(CHANNELS.listByCycle, cycleId) as Promise<InteractionRecord[]>,
  listCycles: () => ipcRenderer.invoke(CHANNELS.listCycles) as Promise<string[]>,
  setCredential: (providerId: string, secret: string) =>
    ipcRenderer.invoke(CHANNELS.setCredential, providerId, secret) as Promise<SuccessOutcome>,
  getCredentialStatus: (providerId: string) =>
    ipcRenderer.invoke(CHANNELS.getCredentialStatus, providerId) as Promise<CredentialStatus>,
  removeCredential: (providerId: string) =>
    ipcRenderer.invoke(CHANNELS.removeCredential, providerId) as Promise<SuccessOutcome>,
};

contextBridge.exposeInMainWorld("atria", bridge);
