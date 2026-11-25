// Shared IPC-boundary types — the renderer-visible shape of the seven JSON-RPC
// operations `api/` exposes (Increment 5, Design References: data/code.md).
// Mirrors core/interaction/models.py and core/records/models.py field-for-field;
// no field is added here beyond what those models already establish.

export interface ExecutionMetrics {
  input_tokens: number;
  output_tokens: number;
  duration: number;
  cost: string;
}

export interface InteractionResult {
  output: string;
  status: string;
  metrics: ExecutionMetrics | null;
}

export interface InteractionRequest {
  input: string;
  provider_id: string;
  model_id: string;
  parameters: Record<string, unknown>;
}

export interface InteractionRecord {
  id: string;
  cycle_id: string;
  sequence: number;
  request: InteractionRequest;
  result: InteractionResult | null;
  created_at: string;
}

export type CredentialStatusValue = "configured" | "not_configured";

export interface CredentialStatus {
  configured: boolean;
  status: CredentialStatusValue;
  masked_preview: string | null;
}

export interface SuccessOutcome {
  success: boolean;
}

// The bridge preload exposes on window.atria — the renderer's only way to
// reach the backend (Increment 5 Expected Behavior item 11: renderer isolation).
export interface AtriaBridge {
  initiate(request: InteractionRequest, cycleId: string): Promise<InteractionRecord>;
  get(recordId: string): Promise<InteractionRecord>;
  listByCycle(cycleId: string): Promise<InteractionRecord[]>;
  listCycles(): Promise<string[]>;
  setCredential(providerId: string, secret: string): Promise<SuccessOutcome>;
  getCredentialStatus(providerId: string): Promise<CredentialStatus>;
  removeCredential(providerId: string): Promise<SuccessOutcome>;
}

declare global {
  interface Window {
    atria: AtriaBridge;
  }
}
