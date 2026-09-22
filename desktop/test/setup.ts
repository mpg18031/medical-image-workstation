import { afterEach, beforeEach, vi } from "vitest";
import { config } from "@vue/test-utils";
import { Quasar } from "quasar";

config.global.plugins = [Quasar];

// jsdom has no ImageBitmap, and the viewport code holds real bitmap handles.
class MockImageBitmap {
  width = 512;
  height = 512;
  close = vi.fn();
}

export interface MivwBridgeMock {
  connectRenderStream: ReturnType<typeof vi.fn>;
  disconnectRenderStream: ReturnType<typeof vi.fn>;
  sendCamera: ReturnType<typeof vi.fn>;
  sendWindowLevel: ReturnType<typeof vi.fn>;
  sendLayers: ReturnType<typeof vi.fn>;
  onFrame: ReturnType<typeof vi.fn>;
  onStreamError: ReturnType<typeof vi.fn>;
  pickFilesForIngest: ReturnType<typeof vi.fn>;
  getAppInfo: ReturnType<typeof vi.fn>;
}

function makeBridge(): MivwBridgeMock {
  return {
    connectRenderStream: vi.fn(async () => undefined),
    disconnectRenderStream: vi.fn(async () => undefined),
    sendCamera: vi.fn(),
    sendWindowLevel: vi.fn(),
    sendLayers: vi.fn(),
    onFrame: vi.fn(() => () => undefined),
    onStreamError: vi.fn(() => () => undefined),
    pickFilesForIngest: vi.fn(async () => []),
    getAppInfo: vi.fn(async () => ({
      version: "0.0.0-test",
      mode: "local" as const,
      platform: "linux" as NodeJS.Platform,
    })),
  };
}

/** The preload bridge mock for the current test. */
export let bridge: MivwBridgeMock = makeBridge();

beforeEach(() => {
  vi.stubGlobal("ImageBitmap", MockImageBitmap);
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(async () => new MockImageBitmap()),
  );

  // Assign onto the real jsdom window rather than replacing it. Quasar calls
  // window.addEventListener during install, so a plain-object stand-in breaks
  // every component mount.
  bridge = makeBridge();
  Object.defineProperty(globalThis.window, "mivw", {
    value: bridge,
    configurable: true,
    writable: true,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
