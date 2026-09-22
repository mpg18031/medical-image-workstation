import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useViewportStore, type ViewportApi } from "src/stores/viewport";
import type { FramePayload, CameraState } from "src-electron/electron-preload";
import type { RenderSession } from "src/services/types";
import { bridge } from "../setup";

function fakeBitmap(): ImageBitmap {
  return { close: vi.fn(), width: 512, height: 512 } as unknown as ImageBitmap;
}

function renderSession(): RenderSession {
  return {
    id: "session-1",
    token: "session-token",
    seriesId: "series-1",
    websocketPath: "/ws/render/session-1",
    expiresAt: "2026-03-14T10:15:00Z",
  };
}

describe("viewport store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  describe("render session lifecycle", () => {
    it("opens a session, handles both frame codecs, and closes cleanly", async () => {
      const store = useViewportStore();
      const api: ViewportApi = {
        openSession: vi.fn().mockResolvedValue(renderSession()),
        closeSession: vi.fn().mockResolvedValue(undefined),
        attachSegmentation: vi.fn().mockResolvedValue(undefined),
      };
      store.useApi(api);

      let frameListener: ((frame: FramePayload) => void) | undefined;
      let errorListener: ((message: string) => void) | undefined;
      const detachFrame = vi.fn();
      const detachError = vi.fn();
      bridge.onFrame.mockImplementation(
        (callback: (frame: FramePayload) => void) => {
          frameListener = callback;
          return detachFrame;
        },
      );
      bridge.onStreamError.mockImplementation(
        (callback: (message: string) => void) => {
          errorListener = callback;
          return detachError;
        },
      );
      vi.stubGlobal(
        "ImageData",
        class {
          constructor(
            readonly data: Uint8ClampedArray,
            readonly width: number,
            readonly height: number,
          ) {}
        },
      );

      await store.connect("series-1", 640, 480);

      expect(api.openSession).toHaveBeenCalledWith("series-1", 640, 480);
      expect(bridge.connectRenderStream).toHaveBeenCalledWith("session-token");
      expect(store.sessionId).toBe("session-1");
      expect(store.connectionState).toBe("open");
      expect(bridge.sendCamera).toHaveBeenCalledOnce();

      const frame = {
        data: [0, 0, 0, 255],
        codec: "raw-rgba8",
        seq: 1,
        width: 1,
        height: 1,
        renderTimeUs: 8000,
      } satisfies FramePayload;
      frameListener?.(frame);
      await vi.waitFor(() => expect(store.currentSeq).toBe(1));
      expect(store.frameTimeMs).toBe(8);
      expect(store.isInteractive).toBe(true);

      frameListener?.({ ...frame, codec: "png", seq: 2 });
      await vi.waitFor(() => expect(store.currentSeq).toBe(2));
      expect(store.lastRenderTimeUs).toBe(8000);

      errorListener?.("stream interrupted");
      expect(store.streamError).toBe("stream interrupted");

      await store.attachSegmentation("run-1");
      expect(api.attachSegmentation).toHaveBeenCalledWith("session-1", "run-1");
      expect(store.segmentationActive).toBe(true);
      expect(bridge.sendLayers).toHaveBeenCalledWith(true, 0.45);

      await store.disconnect();
      expect(detachFrame).toHaveBeenCalledOnce();
      expect(detachError).toHaveBeenCalledOnce();
      expect(bridge.disconnectRenderStream).toHaveBeenCalledOnce();
      expect(api.closeSession).toHaveBeenCalledWith("session-1");
      expect(store.sessionId).toBeNull();
      expect(store.segmentationActive).toBe(false);
      expect(store.connectionState).toBe("closed");
    });

    it("surfaces connection errors and safely disconnects without a session", async () => {
      const store = useViewportStore();
      const api: ViewportApi = {
        openSession: vi.fn().mockRejectedValue(new Error("GPU unavailable")),
        closeSession: vi.fn().mockResolvedValue(undefined),
        attachSegmentation: vi.fn().mockResolvedValue(undefined),
      };
      store.useApi(api);

      await expect(store.connect("series-1")).rejects.toThrow(
        "GPU unavailable",
      );
      expect(store.connectionState).toBe("closed");
      expect(store.streamError).toBe("GPU unavailable");

      await store.disconnect();
      expect(bridge.disconnectRenderStream).toHaveBeenCalledOnce();
      expect(api.closeSession).not.toHaveBeenCalled();
      expect(store.sessionId).toBeNull();
    });

    it("uses a fallback message for non-Error connection failures", async () => {
      const store = useViewportStore();
      store.useApi({
        openSession: vi.fn().mockRejectedValue("unavailable"),
        closeSession: vi.fn().mockResolvedValue(undefined),
        attachSegmentation: vi.fn().mockResolvedValue(undefined),
      });

      await expect(store.connect("series-1")).rejects.toBe("unavailable");
      expect(store.streamError).toBe("Unable to open the render stream");
    });

    it("requires an API client before connecting or attaching segmentation", async () => {
      const store = useViewportStore();
      await expect(store.connect("series-1")).rejects.toThrow(
        "viewport store has no API client",
      );
      await expect(store.attachSegmentation("run-1")).rejects.toThrow(
        "viewport store has no API client",
      );
    });
  });

  describe("camera controls", () => {
    it("orbits around the target while preserving distance and clamps at a pole", () => {
      const store = useViewportStore();
      const initialRadius = Math.hypot(
        store.camera.eye[0] - store.camera.target[0],
        store.camera.eye[1] - store.camera.target[1],
        store.camera.eye[2] - store.camera.target[2],
      );

      store.orbit(25, 10_000);

      const offset = store.camera.eye.map(
        (value, index) => value - store.camera.target[index]!,
      );
      expect(Math.hypot(...offset)).toBeCloseTo(initialRadius);
      expect(store.camera.eye[1]).toBeLessThan(initialRadius);
      expect(bridge.sendCamera).toHaveBeenCalledOnce();
    });

    it("centres on a volume point without changing camera distance", () => {
      const store = useViewportStore();
      const offset = store.camera.eye.map(
        (value, index) => value - store.camera.target[index]!,
      );

      store.centerOn([10, 20, 30]);

      expect(store.camera.target).toEqual([10, 20, 30]);
      expect(store.camera.eye).toEqual([
        10 + offset[0]!,
        20 + offset[1]!,
        30 + offset[2]!,
      ]);
      expect(bridge.sendCamera).toHaveBeenCalledOnce();
    });

    it("ignores orbit when the eye is already at the target", () => {
      const store = useViewportStore();
      store.setCamera({
        eye: [0, 0, 0],
        target: [0, 0, 0],
        up: [0, 1, 0],
        fovDeg: 45,
      } satisfies CameraState);
      bridge.sendCamera.mockClear();

      store.orbit(10, 10);

      expect(bridge.sendCamera).not.toHaveBeenCalled();
    });

    it("does not close a bitmap twice when resetting an empty frame", () => {
      const store = useViewportStore();
      store.reset();
      expect(store.connectionState).toBe("idle");
      expect(store.currentSeq).toBe(0);
    });
  });

  describe("frame ordering", () => {
    it("accepts frames with increasing sequence numbers", () => {
      const store = useViewportStore();
      store.acceptFrame({ seq: 10, bitmap: fakeBitmap() });
      store.acceptFrame({ seq: 12, bitmap: fakeBitmap() });
      expect(store.currentSeq).toBe(12);
      expect(store.droppedFrames).toBe(0);
    });

    it("drops a late frame rather than showing a stale camera position", () => {
      const store = useViewportStore();
      store.acceptFrame({ seq: 12, bitmap: fakeBitmap() });

      const late = fakeBitmap();
      store.acceptFrame({ seq: 11, bitmap: late });

      expect(store.currentSeq).toBe(12);
      expect(store.droppedFrames).toBe(1);
      // Dropped bitmaps must be released or GPU memory leaks over a session.
      expect(late.close).toHaveBeenCalledOnce();
    });

    it("releases the superseded bitmap when a newer frame arrives", () => {
      const store = useViewportStore();
      const first = fakeBitmap();
      store.acceptFrame({ seq: 1, bitmap: first });
      store.acceptFrame({ seq: 2, bitmap: fakeBitmap() });
      expect(first.close).toHaveBeenCalledOnce();
    });
  });

  describe("window/level", () => {
    it("clamps a non-positive width to avoid a divide-by-zero in the shader", () => {
      const store = useViewportStore();
      store.setWindow({ center: 40, width: -100 });
      expect(store.window.width).toBeGreaterThan(0);
    });

    it("forwards the clamped value to the bridge, not the raw one", () => {
      const store = useViewportStore();
      store.setWindow({ center: 40, width: 0 });
      expect(bridge.sendWindowLevel).toHaveBeenCalledWith(
        40,
        expect.any(Number),
      );

      const [, forwardedWidth] = bridge.sendWindowLevel.mock.calls[0]!;
      expect(forwardedWidth).toBeGreaterThan(0);
    });
  });

  describe("interactivity", () => {
    it("reports non-interactive above the 16 ms budget", () => {
      const store = useViewportStore();
      store.recordFrameMetrics({ renderTimeUs: 25_000 });
      expect(store.isInteractive).toBe(false);
    });

    it("reports interactive within budget", () => {
      const store = useViewportStore();
      store.recordFrameMetrics({ renderTimeUs: 9_000 });
      expect(store.isInteractive).toBe(true);
    });
  });

  it("releases the current bitmap on reset", () => {
    const store = useViewportStore();
    const bitmap = fakeBitmap();
    store.acceptFrame({ seq: 1, bitmap });
    store.reset();
    expect(bitmap.close).toHaveBeenCalledOnce();
    expect(store.currentFrame).toBeNull();
  });
});
