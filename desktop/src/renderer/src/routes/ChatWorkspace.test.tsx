// Acceptance criteria 7: metrics-present vs. metrics-None rendering.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { atria } from "../api";
import ChatWorkspace from "./ChatWorkspace";

vi.mock("../api", () => ({
  atria: { listByCycle: vi.fn() },
}));

afterEach(() => {
  vi.clearAllMocks();
});

const noop = () => {};

function recordAt(cycleId: string, isoDate: string) {
  return {
    id: `rec-${cycleId}`,
    cycle_id: cycleId,
    sequence: 1,
    request: { input: `message for ${cycleId}`, provider_id: "openai", model_id: "gpt-4o-mini", parameters: {} },
    result: null,
    created_at: isoDate,
  };
}

describe("ChatWorkspace", () => {
  it("displays metrics when result.metrics is present", () => {
    render(
      <ChatWorkspace
        cycles={[]}
        activeCycleId="cycle-1"
        records={[
          {
            id: "rec-1",
            cycle_id: "cycle-1",
            sequence: 1,
            request: { input: "hi", provider_id: "openai", model_id: "gpt-4o-mini", parameters: {} },
            result: {
              output: "hello back",
              status: "success",
              metrics: { input_tokens: 3, output_tokens: 5, duration: 1.2345, cost: "0.01" },
            },
            created_at: new Date().toISOString(),
          },
        ]}
        onNewInteraction={noop}
        onSelectCycle={noop}
        onOpenSettings={noop}
        onSubmit={async () => {}}
        onViewDetails={noop}
      />,
    );

    expect(screen.getByText("hello back")).toBeInTheDocument();
    expect(screen.getByText("1.23 s")).toBeInTheDocument();
    expect(screen.getByText("8 tokens")).toBeInTheDocument();
  });

  it("does not render synthetic metrics when result.metrics is None", () => {
    render(
      <ChatWorkspace
        cycles={[]}
        activeCycleId="cycle-1"
        records={[
          {
            id: "rec-1",
            cycle_id: "cycle-1",
            sequence: 1,
            request: { input: "hi", provider_id: "openai", model_id: "gpt-4o-mini", parameters: {} },
            result: { output: "hello back", status: "success", metrics: null },
            created_at: new Date().toISOString(),
          },
        ]}
        onNewInteraction={noop}
        onSelectCycle={noop}
        onOpenSettings={noop}
        onSubmit={async () => {}}
        onViewDetails={noop}
      />,
    );

    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument();
  });

  it("submits on Enter and clears the composer", () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <ChatWorkspace
        cycles={[]}
        activeCycleId="cycle-1"
        records={[]}
        onNewInteraction={noop}
        onSelectCycle={noop}
        onOpenSettings={noop}
        onSubmit={onSubmit}
        onViewDetails={noop}
      />,
    );

    const textarea = screen.getByPlaceholderText("Message Atria...");
    fireEvent.change(textarea, { target: { value: "hello" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(onSubmit).toHaveBeenCalledWith("hello", "openai", "gpt-4o-mini");
  });

  it("groups a cycle older than 7 days under 'Older', not 'Previous 7 Days'", async () => {
    const tenDaysAgo = new Date(Date.now() - 10 * 86_400_000).toISOString();
    const threeDaysAgo = new Date(Date.now() - 3 * 86_400_000).toISOString();
    vi.mocked(atria.listByCycle).mockImplementation(async (cycleId: string) =>
      cycleId === "old-cycle"
        ? [recordAt("old-cycle", tenDaysAgo)]
        : [recordAt("recent-cycle", threeDaysAgo)],
    );

    render(
      <ChatWorkspace
        cycles={["old-cycle", "recent-cycle"]}
        activeCycleId="recent-cycle"
        records={[]}
        onNewInteraction={noop}
        onSelectCycle={noop}
        onOpenSettings={noop}
        onSubmit={async () => {}}
        onViewDetails={noop}
      />,
    );

    expect(await screen.findByText("OLDER")).toBeInTheDocument();
    expect(screen.getByText("PREVIOUS 7 DAYS")).toBeInTheDocument();
  });
});
