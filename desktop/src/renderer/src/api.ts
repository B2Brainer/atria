// Typed, renderer-side wrapper over window.atria (the preload bridge) — the
// renderer's only path to the backend's seven operations.
import type {
  CredentialStatus,
  InteractionRecord,
  InteractionRequest,
  SuccessOutcome,
} from "../../shared/types";

export const atria = {
  initiate: (request: InteractionRequest, cycleId: string): Promise<InteractionRecord> =>
    window.atria.initiate(request, cycleId),
  get: (recordId: string): Promise<InteractionRecord> => window.atria.get(recordId),
  listByCycle: (cycleId: string): Promise<InteractionRecord[]> =>
    window.atria.listByCycle(cycleId),
  listCycles: (): Promise<string[]> => window.atria.listCycles(),
  setCredential: (providerId: string, secret: string): Promise<SuccessOutcome> =>
    window.atria.setCredential(providerId, secret),
  getCredentialStatus: (providerId: string): Promise<CredentialStatus> =>
    window.atria.getCredentialStatus(providerId),
  removeCredential: (providerId: string): Promise<SuccessOutcome> =>
    window.atria.removeCredential(providerId),
};
