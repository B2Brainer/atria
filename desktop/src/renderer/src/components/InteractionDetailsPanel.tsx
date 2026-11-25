import type { InteractionRecord } from "../../../shared/types";

interface Props {
  record: InteractionRecord;
  onClose(): void;
}

export default function InteractionDetailsPanel({ record, onClose }: Props) {
  return (
    <aside className="details-panel">
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <h2>Interaction details</h2>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <section>
        <h3>Overview</h3>
        <div>Provider: {record.request.provider_id}</div>
        <div>Model: {record.request.model_id}</div>
        <div>Status: {record.result?.status ?? "pending"}</div>
        <div>ID: {record.id}</div>
      </section>

      {record.result?.metrics && (
        <section>
          <h3>Metrics</h3>
          <div>Duration: {record.result.metrics.duration.toFixed(2)} s</div>
          <div>Input tokens: {record.result.metrics.input_tokens}</div>
          <div>Output tokens: {record.result.metrics.output_tokens}</div>
          <div>Cost: {record.result.metrics.cost}</div>
        </section>
      )}

      <section>
        <h3>Input</h3>
        <div>{record.request.input}</div>
      </section>

      {record.result && (
        <section>
          <h3>Output</h3>
          <div>{record.result.output}</div>
        </section>
      )}

      <section>
        <h3>Parameters</h3>
        <pre>{JSON.stringify(record.request.parameters, null, 2)}</pre>
        {/* A static label naming the storage mechanism, never the secret
            itself — consistent with the no-credential-material-in-IPC
            constraint (Increment 5 Expected Behavior item 10). */}
        <div>Credential: macOS Keychain</div>
      </section>

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <button type="button" onClick={() => navigator.clipboard.writeText(JSON.stringify(record))}>
          Copy record
        </button>
        <button type="button" onClick={() => exportAsJsonFile(record)}>
          Export JSON
        </button>
        {/* No "Delete" action: this increment exposes no record-deletion
            operation (the Scope/Resolved Decisions permit exactly one new
            core/ports/ addition, list_cycles(), and a delete capability is
            not it) — adding one here would be new core/ scope beyond what
            was approved. */}
      </div>
    </aside>
  );
}

function exportAsJsonFile(record: InteractionRecord): void {
  const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${record.id}.json`;
  link.click();
  URL.revokeObjectURL(url);
}
