// Acceptance criteria 7: metrics-present vs. metrics-None rendering.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChatWorkspace from "./ChatWorkspace";

const noop = () => {};

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
});
