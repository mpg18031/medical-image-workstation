<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    frame: ImageBitmap | null;
    width?: number;
    height?: number;
    frameTimeMs?: number;
    droppedFrames?: number;
    showOverlay?: boolean;
    segmentationActive?: boolean;
    connectionState?:
      "idle" | "connecting" | "open" | "reconnecting" | "closed";
  }>(),
  {
    width: 1024,
    height: 1024,
    frameTimeMs: 0,
    droppedFrames: 0,
    showOverlay: true,
    segmentationActive: false,
    connectionState: "idle",
  },
);

const emit = defineEmits<{
  orbit: [dx: number, dy: number];
  zoom: [delta: number];
  windowLevel: [dCenter: number, dWidth: number];
  canvasClick: [x: number, y: number];
}>();

const canvas = ref<HTMLCanvasElement | null>(null);
let context: ImageBitmapRenderingContext | null = null;
let dragButton: number | null = null;
let lastX = 0;
let lastY = 0;

watch(
  () => props.frame,
  (bitmap) => {
    if (!bitmap || !canvas.value) return;
    context ??= canvas.value.getContext("bitmaprenderer");
    // transferFromImageBitmap hands ownership to the canvas, avoiding a copy
    // through the JS heap on every frame.
    context?.transferFromImageBitmap(bitmap);
  },
);

function onPointerDown(event: PointerEvent): void {
  dragButton = event.button;
  lastX = event.clientX;
  lastY = event.clientY;
  (event.target as HTMLElement).setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent): void {
  if (dragButton === null) return;

  const dx = event.clientX - lastX;
  const dy = event.clientY - lastY;
  lastX = event.clientX;
  lastY = event.clientY;

  // Right drag adjusts window/level, matching every clinical viewer.
  if (dragButton === 2) emit("windowLevel", dy, dx);
  else emit("orbit", dx, dy);
}

function onPointerUp(event: PointerEvent): void {
  dragButton = null;
  (event.target as HTMLElement).releasePointerCapture(event.pointerId);
}

function onWheel(event: WheelEvent): void {
  event.preventDefault();
  emit("zoom", Math.sign(event.deltaY));
}

function onKeydown(event: KeyboardEvent): void {
  const step = event.shiftKey ? 10 : 2;
  switch (event.key) {
    case "ArrowLeft":
      emit("orbit", -step, 0);
      break;
    case "ArrowRight":
      emit("orbit", step, 0);
      break;
    case "ArrowUp":
      emit("orbit", 0, -step);
      break;
    case "ArrowDown":
      emit("orbit", 0, step);
      break;
    case "+":
    case "=":
      emit("zoom", -1);
      break;
    case "-":
      emit("zoom", 1);
      break;
    default:
      return;
  }
  event.preventDefault();
}

function onCanvasClick(event: MouseEvent): void {
  const target = event.currentTarget as HTMLCanvasElement;
  const bounds = target.getBoundingClientRect();
  emit(
    "canvasClick",
    ((event.clientX - bounds.left) / bounds.width - 0.5) * 256,
    ((event.clientY - bounds.top) / bounds.height - 0.5) * 256,
  );
}

onBeforeUnmount(() => {
  context = null;
});
</script>

<template>
  <div class="volume-canvas">
    <canvas
      ref="canvas"
      :width="width"
      :height="height"
      class="volume-canvas__surface"
      tabindex="0"
      role="img"
      aria-label="Volume rendering. Use arrow keys to rotate and plus or minus to zoom."
      data-testid="volume-canvas"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @wheel="onWheel"
      @keydown="onKeydown"
      @click="onCanvasClick"
      @contextmenu.prevent
    />

    <div
      v-if="connectionState === 'reconnecting'"
      class="volume-canvas__banner"
      role="status"
      data-testid="volume-canvas-reconnecting"
    >
      <q-spinner size="18px" />
      <span class="q-ml-sm">Reconnecting to the render stream…</span>
    </div>

    <div
      v-if="segmentationActive"
      class="volume-canvas__banner volume-canvas__banner--top-left"
      role="status"
      data-testid="segmentation-overlay"
    >
      Segmentation overlay
    </div>

    <div
      v-if="showOverlay"
      class="volume-canvas__stats"
      data-testid="volume-canvas-stats"
      aria-live="off"
    >
      <span :class="{ 'text-warning': frameTimeMs > 16 }">
        {{ frameTimeMs.toFixed(1) }} ms
      </span>
      <span v-if="droppedFrames > 0" class="q-ml-sm"
        >{{ droppedFrames }} dropped</span
      >
    </div>
  </div>
</template>

<style scoped lang="scss">
.volume-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
}

.volume-canvas__surface {
  width: 100%;
  height: 100%;
  display: block;
  touch-action: none;
  cursor: grab;

  &:focus-visible {
    outline: 2px solid #1976d2;
    outline-offset: -2px;
  }
}

.volume-canvas__stats {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.6);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}

.volume-canvas__banner {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 12px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;

  &--top-left {
    left: 8px;
    transform: none;
  }
}
</style>
