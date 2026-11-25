// Acceptance criterion 17: the preload script exposes only the seven
// operations to the renderer's global scope.
import { afterEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn().mockResolvedValue(undefined);
const exposeInMainWorld = vi.fn();

vi.mock("electron", () => ({
  contextBridge: { exposeInMainWorld },
  ipcRenderer: { invoke },
}));

afterEach(() => {
  vi.resetModules();
  invoke.mockClear();
  exposeInMainWorld.mockClear();
});

describe("preload bridge", () => {
  it("exposes exactly the seven established operations on window.atria", async () => {
    await import("./index");

    expect(exposeInMainWorld).toHaveBeenCalledTimes(1);
    const [name, bridge] = exposeInMainWorld.mock.calls[0];
    expect(name).toBe("atria");
    expect(Object.keys(bridge).sort()).toEqual(
      [
        "initiate",
        "get",
        "listByCycle",
        "listCycles",
        "setCredential",
        "getCredentialStatus",
        "removeCredential",
      ].sort(),
    );
  });

  it("forwards each call to ipcRenderer.invoke on its own channel", async () => {
    const { contextBridge } = (await import("electron")) as unknown as {
      contextBridge: { exposeInMainWorld: typeof exposeInMainWorld };
    };
    await import("./index");
    const bridge = contextBridge.exposeInMainWorld.mock.calls[0][1] as Record<
      string,
      (...args: unknown[]) => unknown
    >;

    await bridge.listCycles();

    expect(invoke).toHaveBeenCalledWith("atria:list-cycles");
  });
});
