import { useCallback, useEffect, useState } from "react";

import { atria } from "./api";
import InteractionDetailsPanel from "./components/InteractionDetailsPanel";
import ChatWorkspace from "./routes/ChatWorkspace";
import Settings from "./routes/Settings";
import type { InteractionRecord } from "../../shared/types";

type Route = "chat" | "settings";

export default function App() {
  const [route, setRoute] = useState<Route>("chat");
  const [cycles, setCycles] = useState<string[]>([]);
  const [activeCycleId, setActiveCycleId] = useState<string>(() => crypto.randomUUID());
  const [records, setRecords] = useState<InteractionRecord[]>([]);
  const [detailsRecordId, setDetailsRecordId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshCycles = useCallback(async () => {
    try {
      setCycles(await atria.listCycles());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const refreshRecords = useCallback(async (cycleId: string) => {
    try {
      setRecords(await atria.listByCycle(cycleId));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refreshCycles();
  }, [refreshCycles]);

  useEffect(() => {
    void refreshRecords(activeCycleId);
  }, [activeCycleId, refreshRecords]);

  const handleNewInteraction = useCallback(() => {
    // The renderer assigns a fresh cycle_id locally (crypto.randomUUID()); no
    // persistence write happens until the first submitted request for it is
    // saved — this increment introduces no eighth "create cycle" operation.
    setActiveCycleId(crypto.randomUUID());
    setRecords([]);
    setRoute("chat");
  }, []);

  const handleSelectCycle = useCallback((cycleId: string) => {
    setActiveCycleId(cycleId);
    setRoute("chat");
  }, []);

  const handleSubmit = useCallback(
    async (input: string, providerId: string, modelId: string) => {
      try {
        setError(null);
        await atria.initiate(
          { input, provider_id: providerId, model_id: modelId, parameters: {} },
          activeCycleId,
        );
        await refreshRecords(activeCycleId);
        await refreshCycles();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [activeCycleId, refreshCycles, refreshRecords],
  );

  const detailsRecord = records.find((record) => record.id === detailsRecordId) ?? null;

  return (
    <div className="app-shell">
      {error && <div className="error-banner">{error}</div>}
      {route === "chat" ? (
        <ChatWorkspace
          cycles={cycles}
          activeCycleId={activeCycleId}
          records={records}
          onNewInteraction={handleNewInteraction}
          onSelectCycle={handleSelectCycle}
          onOpenSettings={() => setRoute("settings")}
          onSubmit={handleSubmit}
          onViewDetails={setDetailsRecordId}
        />
      ) : (
        <Settings onBackToChat={() => setRoute("chat")} />
      )}
      {detailsRecord && (
        <InteractionDetailsPanel
          record={detailsRecord}
          onClose={() => setDetailsRecordId(null)}
        />
      )}
    </div>
  );
}
