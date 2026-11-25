import { useEffect, useState } from "react";

import { atria } from "../api";
import type { InteractionRecord } from "../../../shared/types";

interface Props {
  cycles: string[];
  activeCycleId: string;
  records: InteractionRecord[];
  onNewInteraction(): void;
  onSelectCycle(cycleId: string): void;
  onOpenSettings(): void;
  onSubmit(input: string, providerId: string, modelId: string): Promise<void>;
  onViewDetails(recordId: string): void;
}

interface HistoryEntry {
  cycleId: string;
  title: string;
  mostRecentAt: Date;
}

type HistoryGroup = "Today" | "Yesterday" | "Previous 7 Days" | "Older";

function groupLabel(date: Date): HistoryGroup {
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays <= 7) return "Previous 7 Days";
  // A cycle older than 7 days was previously mislabeled "Previous 7 Days" —
  // every entry older than yesterday landed there regardless of actual age.
  return "Older";
}

export default function ChatWorkspace({
  cycles,
  activeCycleId,
  records,
  onNewInteraction,
  onSelectCycle,
  onOpenSettings,
  onSubmit,
  onViewDetails,
}: Props) {
  const [history, setHistory] = useState<Record<string, HistoryEntry>>({});
  const [input, setInput] = useState("");
  const [providerId] = useState("openai");
  const [modelId] = useState("gpt-4o-mini");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (const cycleId of cycles) {
        if (history[cycleId]) continue;
        const cycleRecords = await atria.listByCycle(cycleId);
        if (cancelled || cycleRecords.length === 0) continue;
        const first = cycleRecords[0];
        setHistory((prev) => ({
          ...prev,
          [cycleId]: {
            cycleId,
            title: first.request.input.slice(0, 48),
            mostRecentAt: new Date(cycleRecords[cycleRecords.length - 1].created_at),
          },
        }));
      }
    })();
    return () => {
      cancelled = true;
    };
    // history is intentionally omitted from the dependency list: this effect
    // only needs to fill in entries missing from it, not re-run when it changes.
  }, [cycles]);

  const grouped: Record<HistoryGroup, HistoryEntry[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    Older: [],
  };
  for (const cycleId of cycles) {
    const entry = history[cycleId];
    if (!entry) continue;
    grouped[groupLabel(entry.mostRecentAt)].push(entry);
  }

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    setSending(true);
    const toSend = input;
    setInput("");
    await onSubmit(toSend, providerId, modelId);
    setSending(false);
  };

  return (
    <>
      <aside className="sidebar">
        <h1>Atria</h1>
        <button className="new-interaction-button" onClick={onNewInteraction} type="button">
          + New interaction
        </button>
        {(["Today", "Yesterday", "Previous 7 Days", "Older"] as const).map((label) =>
          grouped[label].length > 0 ? (
            <div key={label}>
              <div className="history-group-label">{label.toUpperCase()}</div>
              {grouped[label].map((entry) => (
                <div
                  key={entry.cycleId}
                  className={`history-entry${entry.cycleId === activeCycleId ? " active" : ""}`}
                  onClick={() => onSelectCycle(entry.cycleId)}
                >
                  {entry.title || entry.cycleId}
                </div>
              ))}
            </div>
          ) : null,
        )}
        <div className="settings-link" onClick={onOpenSettings}>
          ⚙ Settings
        </div>
      </aside>
      <main className="main-panel">
        <div className="thread">
          {records.map((record) => (
            <div className="exchange" key={record.id}>
              <div className="user-bubble">{record.request.input}</div>
              {record.result && (
                <div className="assistant-response">
                  <div>{record.result.output}</div>
                  {record.result.metrics && (
                    <>
                      <span className="metric-chip">{record.result.metrics.duration.toFixed(2)} s</span>
                      <span className="metric-chip">
                        {record.result.metrics.input_tokens + record.result.metrics.output_tokens}{" "}
                        tokens
                      </span>
                    </>
                  )}
                  <span className="view-details-link" onClick={() => onViewDetails(record.id)}>
                    View details
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="composer">
          <textarea
            rows={2}
            placeholder="Message Atria..."
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
          />
        </div>
      </main>
    </>
  );
}
