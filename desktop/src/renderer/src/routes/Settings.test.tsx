// Acceptance criteria 13, 14, 15: credential status/removal round trips in the UI.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { atria } from "../api";
import Settings from "./Settings";

vi.mock("../api", () => ({
  atria: {
    getCredentialStatus: vi.fn(),
    setCredential: vi.fn(),
    removeCredential: vi.fn(),
  },
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("Settings", () => {
  it("shows 'Configured' (not 'Connected') when a provider has a stored credential", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: true,
      status: "configured",
      masked_preview: "test-***1234",
    });

    render(<Settings onBackToChat={() => {}} />);

    expect(await screen.findAllByText("Configured")).toHaveLength(3);
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("shows 'Not configured' and a Save-key form when no credential is stored", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: false,
      status: "not_configured",
      masked_preview: null,
    });

    render(<Settings onBackToChat={() => {}} />);

    expect(await screen.findAllByText("Not configured")).toHaveLength(3);
    expect(screen.getAllByText("Save key")).toHaveLength(3);
  });

  it("submitting a credential calls setCredential and never displays the secret back", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: false,
      status: "not_configured",
      masked_preview: null,
    });
    vi.mocked(atria.setCredential).mockResolvedValue({ success: true });

    render(<Settings onBackToChat={() => {}} />);
    await screen.findAllByText("Not configured");

    const [input] = screen.getAllByPlaceholderText("Paste API key");
    fireEvent.change(input, { target: { value: "test-super-secret" } });
    const [saveButton] = screen.getAllByText("Save key");
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(atria.setCredential).toHaveBeenCalledWith("anthropic", "test-super-secret"),
    );
    expect(screen.queryByDisplayValue("test-super-secret")).not.toBeInTheDocument();
  });

  it("Replace reveals a Save-key form without removing the existing credential first", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: true,
      status: "configured",
      masked_preview: "test-***1234",
    });
    vi.mocked(atria.setCredential).mockResolvedValue({ success: true });

    render(<Settings onBackToChat={() => {}} />);
    const [replaceButton] = await screen.findAllByText("Replace");
    fireEvent.click(replaceButton);

    const [input] = screen.getAllByPlaceholderText("Paste API key");
    fireEvent.change(input, { target: { value: "test-new-secret" } });
    const [saveButton] = screen.getAllByText("Save key");
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(atria.setCredential).toHaveBeenCalledWith("anthropic", "test-new-secret"),
    );
    expect(atria.removeCredential).not.toHaveBeenCalled();
  });

  it("a failed setCredential call surfaces an error banner instead of an unhandled rejection", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: false,
      status: "not_configured",
      masked_preview: null,
    });
    vi.mocked(atria.setCredential).mockRejectedValue(new Error("credential operation failed"));

    render(<Settings onBackToChat={() => {}} />);
    await screen.findAllByText("Not configured");

    const [input] = screen.getAllByPlaceholderText("Paste API key");
    fireEvent.change(input, { target: { value: "test-secret" } });
    const [saveButton] = screen.getAllByText("Save key");
    fireEvent.click(saveButton);

    expect(await screen.findByText("credential operation failed")).toBeInTheDocument();
  });

  it("the API key input is masked (type=password), not plain text", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: false,
      status: "not_configured",
      masked_preview: null,
    });

    render(<Settings onBackToChat={() => {}} />);
    const [input] = await screen.findAllByPlaceholderText("Paste API key");

    expect(input).toHaveAttribute("type", "password");
  });

  it("removing a credential calls removeCredential", async () => {
    vi.mocked(atria.getCredentialStatus).mockResolvedValue({
      configured: true,
      status: "configured",
      masked_preview: "test-***1234",
    });
    vi.mocked(atria.removeCredential).mockResolvedValue({ success: true });

    render(<Settings onBackToChat={() => {}} />);
    const [removeButton] = await screen.findAllByText("Remove");
    fireEvent.click(removeButton);

    await waitFor(() => expect(atria.removeCredential).toHaveBeenCalledWith("anthropic"));
  });
});
