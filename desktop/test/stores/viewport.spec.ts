import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useViewportStore } from "src/stores/viewport";
import { bridge } from "../setup";

function fakeBitmap(): ImageBitmap {
  return { close: vi.fn(), width: 512, height: 512 } as unknown as ImageBitmap;
}

describe("viewport store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
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
