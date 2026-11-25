import { useEffect, useState } from "react";

import { atria } from "../api";
import type { CredentialStatus } from "../../../shared/types";

const PROVIDERS = ["anthropic", "openai", "google"] as const;

export default function Settings({ onBackToChat }: { onBackToChat(): void }) {
  const [statuses, setStatuses] = useState<Record<string, CredentialStatus>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const entries = await Promise.all(
        PROVIDERS.map(
          async (providerId) => [providerId, await atria.getCredentialStatus(providerId)] as const,
        ),
      );
      setStatuses(Object.fromEntries(entries));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleSave = async (providerId: string) => {
    const secret = drafts[providerId];
    if (!secret) return;
    try {
      setError(null);
      await atria.setCredential(providerId, secret);
      setDrafts((prev) => ({ ...prev, [providerId]: "" }));
      setEditing((prev) => ({ ...prev, [providerId]: false }));
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleRemove = async (providerId: string) => {
    try {
      setError(null);
      await atria.removeCredential(providerId);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="settings-screen">
      <nav className="settings-nav">
        <div onClick={onBackToChat} style={{ cursor: "pointer", marginBottom: 16 }}>
          ← Back to chat
        </div>
        <div>Providers</div>
        <div>Preferences</div>
      </nav>
      <div className="settings-content">
        {error && <div className="error-banner">{error}</div>}
        <p>API keys are stored in the macOS Keychain and never written to the interaction record.</p>
        {PROVIDERS.map((providerId) => {
          const status = statuses[providerId];
          return (
            <div className="provider-row" key={providerId}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{providerId}</strong>
                {status && (
                  <span
                    className={`status-badge ${status.configured ? "configured" : "not-configured"}`}
                  >
                    {status.configured ? "Configured" : "Not configured"}
                  </span>
                )}
              </div>
              {status?.configured && !editing[providerId] ? (
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <input value={status.masked_preview ?? ""} readOnly />
                  <button
                    type="button"
                    onClick={() => setEditing((prev) => ({ ...prev, [providerId]: true }))}
                  >
                    Replace
                  </button>
                  <button type="button" onClick={() => handleRemove(providerId)}>
                    Remove
                  </button>
                </div>
              ) : (
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <input
                    type="password"
                    placeholder="Paste API key"
                    value={drafts[providerId] ?? ""}
                    onChange={(event) =>
                      setDrafts((prev) => ({ ...prev, [providerId]: event.target.value }))
                    }
                  />
                  <button type="button" onClick={() => handleSave(providerId)}>
                    Save key
                  </button>
                  {status?.configured && (
                    <button
                      type="button"
                      onClick={() => setEditing((prev) => ({ ...prev, [providerId]: false }))}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
