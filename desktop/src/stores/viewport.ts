import { defineStore } from "pinia";
import { computed, ref, shallowRef } from "vue";
import type { CameraState, FramePayload } from "src-electron/electron-preload";
import type { RenderSession } from "src/services/types";

export interface WindowLevel {
  center: number;
  width: number;
}

export interface ViewportApi {
  openSession(
    seriesId: string,
    width: number,
    height: number,
  ): Promise<RenderSession>;
  closeSession(sessionId: string): Promise<void>;
}

const MIN_WINDOW_WIDTH = 1;

export const useViewportStore = defineStore("viewport", () => {
  // shallowRef: an ImageBitmap must not be made deeply reactive.
  const currentFrame = shallowRef<ImageBitmap | null>(null);
  const currentSeq = ref(0);
  const droppedFrames = ref(0);
  const lastRenderTimeUs = ref(0);
  const camera = ref<CameraState>({
    eye: [0, 0, -500],
    target: [0, 0, 0],
    up: [0, 1, 0],
    fovDeg: 45,
  });
  const window = ref<WindowLevel>({ center: 40, width: 400 });
  const streamError = ref<string | null>(null);
  const connectionState = ref<
    "idle" | "connecting" | "open" | "reconnecting" | "closed"
  >("idle");
  const sessionId = ref<string | null>(null);

  let api: ViewportApi | null = null;
  let detachFrame: (() => void) | null = null;
  let detachError: (() => void) | null = null;

  function useApi(client: ViewportApi): void {
    api = client;
  }

  /** Opens a render session, connects the stream, and starts listening for frames. */
  async function connect(
    seriesId_: string,
    width = 1024,
    height = 1024,
  ): Promise<void> {
    if (!api) throw new Error("viewport store has no API client");

    connectionState.value = "connecting";
    streamError.value = null;

    try {
      const session = await api.openSession(seriesId_, width, height);
      sessionId.value = session.id;
      await globalThis.window.mivw.connectRenderStream(session.token);

      detachFrame = globalThis.window.mivw.onFrame(async (frame) => {
        const bitmap =
          frame.codec === "raw-rgba8"
            ? await createImageBitmap(
                new ImageData(
                  new Uint8ClampedArray(frame.data),
                  frame.width,
                  frame.height,
                ),
              )
            : await createImageBitmap(new Blob([new Uint8Array(frame.data)]));
        acceptFrame({ seq: frame.seq, bitmap });
        recordFrameMetrics({ renderTimeUs: frame.renderTimeUs });
      });
      detachError = globalThis.window.mivw.onStreamError((message) => {
        streamError.value = message;
      });

      connectionState.value = "open";
      setCamera(camera.value);
    } catch (caught) {
      connectionState.value = "closed";
      streamError.value =
        caught instanceof Error
          ? caught.message
          : "Unable to open the render stream";
      throw caught;
    }
  }

  /** Tears down the stream and releases the pinned GPU session. */
  async function disconnect(): Promise<void> {
    detachFrame?.();
    detachError?.();
    detachFrame = null;
    detachError = null;

    await globalThis.window.mivw?.disconnectRenderStream();
    if (api && sessionId.value) {
      await api.closeSession(sessionId.value).catch(() => undefined);
    }
    sessionId.value = null;
    connectionState.value = "closed";
  }

  const frameTimeMs = computed(() => lastRenderTimeUs.value / 1000);
  const isInteractive = computed(() => frameTimeMs.value <= 16);

  /**
   * Accept a decoded frame.
   *
   * The server drops superseded renders under load, so sequence numbers arrive
   * with gaps and occasionally out of order. Rendering a stale frame after a
   * newer one would show the user a camera position they have already left, so
   * late frames are discarded.
   */
  function acceptFrame(frame: { seq: number; bitmap: ImageBitmap }): void {
    if (frame.seq <= currentSeq.value) {
      droppedFrames.value += 1;
      frame.bitmap.close();
      return;
    }
    currentFrame.value?.close();
    currentFrame.value = frame.bitmap;
    currentSeq.value = frame.seq;
  }

  function recordFrameMetrics(
    payload: Pick<FramePayload, "renderTimeUs">,
  ): void {
    lastRenderTimeUs.value = payload.renderTimeUs;
  }

  function setCamera(next: CameraState): void {
    const normalized: CameraState = {
      eye: next.eye.map(Number) as CameraState["eye"],
      target: next.target.map(Number) as CameraState["target"],
      up: next.up.map(Number) as CameraState["up"],
      fovDeg: Number(next.fovDeg),
    };
    camera.value = normalized;
    globalThis.window.mivw.sendCamera(normalized);
  }

  const ORBIT_RADIANS_PER_PX = 0.01;
  const POLE_EPSILON = 0.001;

  /**
   * Rotates the eye around the current target on an arcball, keeping the
   * distance to the target fixed so the volume stays centred while spinning.
   */
  function orbit(dxPx: number, dyPx: number): void {
    const { eye, target, up, fovDeg } = camera.value;
    const offset: [number, number, number] = [
      eye[0] - target[0],
      eye[1] - target[1],
      eye[2] - target[2],
    ];
    const radius = Math.hypot(...offset);
    if (radius < 1e-6) return;

    let azimuth = Math.atan2(offset[0], offset[2]);
    let polar = Math.acos(Math.min(1, Math.max(-1, offset[1] / radius)));

    azimuth -= dxPx * ORBIT_RADIANS_PER_PX;
    polar = Math.min(
      Math.PI - POLE_EPSILON,
      Math.max(POLE_EPSILON, polar - dyPx * ORBIT_RADIANS_PER_PX),
    );

    setCamera({
      eye: [
        target[0] + radius * Math.sin(polar) * Math.sin(azimuth),
        target[1] + radius * Math.cos(polar),
        target[2] + radius * Math.sin(polar) * Math.cos(azimuth),
      ],
      target,
      up,
      fovDeg,
    });
  }

  /** Points the camera at `targetMm`, preserving the current viewing distance and direction. */
  function centerOn(targetMm: readonly [number, number, number]): void {
    const { eye, target, up, fovDeg } = camera.value;
    const offset: [number, number, number] = [
      eye[0] - target[0],
      eye[1] - target[1],
      eye[2] - target[2],
    ];
    setCamera({
      eye: [
        targetMm[0] + offset[0],
        targetMm[1] + offset[1],
        targetMm[2] + offset[2],
      ],
      target: [targetMm[0], targetMm[1], targetMm[2]],
      up,
      fovDeg,
    });
  }

  function setWindow(next: WindowLevel): void {
    // A non-positive width divides by zero in the shader's window transform.
    const width = Math.max(next.width, MIN_WINDOW_WIDTH);
    window.value = { center: next.center, width };
    globalThis.window.mivw.sendWindowLevel(next.center, width);
  }

  function reset(): void {
    currentFrame.value?.close();
    currentFrame.value = null;
    currentSeq.value = 0;
    droppedFrames.value = 0;
    streamError.value = null;
    connectionState.value = "idle";
  }

  return {
    currentFrame,
    currentSeq,
    droppedFrames,
    lastRenderTimeUs,
    camera,
    window,
    streamError,
    connectionState,
    sessionId,
    frameTimeMs,
    isInteractive,
    useApi,
    connect,
    disconnect,
    acceptFrame,
    recordFrameMetrics,
    setCamera,
    orbit,
    centerOn,
    setWindow,
    reset,
  };
});
