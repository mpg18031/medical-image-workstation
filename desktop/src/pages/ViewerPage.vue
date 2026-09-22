<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import VolumeCanvas from "components/viewer/VolumeCanvas.vue";
import WindowLevelControl from "components/controls/WindowLevelControl.vue";
import LabelLegend from "components/controls/LabelLegend.vue";
import { useViewportStore } from "src/stores/viewport";
import { useAnnotationsStore } from "src/stores/annotations";
import { useModelsStore } from "src/stores/models";
import { useStudiesStore } from "src/stores/studies";
import { useAuthStore } from "src/stores/auth";
import { WINDOW_PRESETS, volumeCenterMm } from "src/services/geometry";

const props = defineProps<{ seriesId: string }>();

const viewport = useViewportStore();
const annotations = useAnnotationsStore();
const models = useModelsStore();
const auth = useAuthStore();

const {
  currentFrame,
  frameTimeMs,
  droppedFrames,
  connectionState,
  streamError,
  segmentationActive,
} = storeToRefs(viewport);
const { selectedModel, visibleLabels, isRunning, activeJob, segmentation } =
  storeToRefs(models);
const { selectedSeries } = storeToRefs(useStudiesStore());

const specWarning = ref<string | null>(null);
const inferenceError = ref<string | null>(null);

const presetNames = computed(() => Object.keys(WINDOW_PRESETS));
// `process` isn't available inside the compiled template's inline handlers.
const isE2E = process.env.MIVW_E2E === "1";

let e2eFrameTimer: ReturnType<typeof setInterval> | null = null;

// The render session's resolution is fixed at connect time, so the initial
// resolution is taken from the app window itself (not a sub-container), and
// the session is reconnected if the window is resized meaningfully.
const viewportWidth = ref(1024);
const viewportHeight = ref(1024);
let resizeReconnectTimer: ReturnType<typeof setTimeout> | null = null;
const RESIZE_RECONNECT_THRESHOLD_PX = 16;

function measuredSize(): { width: number; height: number } {
  return {
    width: Math.max(1, Math.round(globalThis.window.innerWidth)),
    height: Math.max(1, Math.round(globalThis.window.innerHeight)),
  };
}

function handleWindowResize(): void {
  const { width, height } = measuredSize();
  const changed =
    Math.abs(width - viewportWidth.value) > RESIZE_RECONNECT_THRESHOLD_PX ||
    Math.abs(height - viewportHeight.value) > RESIZE_RECONNECT_THRESHOLD_PX;
  viewportWidth.value = width;
  viewportHeight.value = height;
  if (!changed || isE2E || connectionState.value !== "open") return;

  if (resizeReconnectTimer !== null) clearTimeout(resizeReconnectTimer);
  resizeReconnectTimer = setTimeout(() => {
    resizeReconnectTimer = null;
    void viewport
      .disconnect()
      .then(() =>
        viewport.connect(
          props.seriesId,
          viewportWidth.value,
          viewportHeight.value,
        ),
      )
      .catch(() => undefined);
  }, 250);
}

// Re-centres the camera whenever a series (with usable geometry) becomes selected.
watch(
  selectedSeries,
  (series) => {
    if (!series?.hasVolume) return;
    viewport.centerOn(volumeCenterMm(series.geometry));
  },
  { immediate: true },
);

// Once the job resolves, fetch what it produced and composite it onto the
// still-open render session — the job itself carries no result payload.
watch(
  () => activeJob.value?.status,
  async (status) => {
    if (status !== "succeeded" || !activeJob.value) return;
    try {
      await models.fetchSegmentation(activeJob.value.id);
      await viewport.attachSegmentation(activeJob.value.id);
    } catch (caught) {
      inferenceError.value =
        caught instanceof Error
          ? caught.message
          : "Unable to load the segmentation result";
    }
  },
);

onMounted(async () => {
  const initial = measuredSize();
  viewportWidth.value = initial.width;
  viewportHeight.value = initial.height;
  globalThis.window.addEventListener("resize", handleWindowResize);

  const modelsLoad = models.load();
  await annotations.load(props.seriesId);
  await modelsLoad;
  if (!isE2E) {
    await viewport
      .connect(props.seriesId, viewportWidth.value, viewportHeight.value)
      .catch(() => undefined);
  }
  if (isE2E) {
    viewport.recordFrameMetrics({ renderTimeUs: 8500 });
    e2eFrameTimer = setInterval(
      () => viewport.recordFrameMetrics({ renderTimeUs: 9000 }),
      250,
    );
  }
});

onBeforeUnmount(async () => {
  if (e2eFrameTimer !== null) clearInterval(e2eFrameTimer);
  if (resizeReconnectTimer !== null) clearTimeout(resizeReconnectTimer);
  globalThis.window.removeEventListener("resize", handleWindowResize);
  await viewport.disconnect();
  viewport.reset();
});

function applyPreset(name: string): void {
  const preset = WINDOW_PRESETS[name];
  if (preset) viewport.setWindow(preset);
}

async function runModel(): Promise<void> {
  const model = selectedModel.value;
  const series = selectedSeries.value;
  if (!model || !series?.volumeAssetId) return;

  // Pre-flight locally so the user learns *why* before waiting on a queued job.
  const mismatch = models.checkSpec(model, [
    series.geometry.pixelSpacingMm[0],
    series.geometry.pixelSpacingMm[1],
    series.geometry.sliceThicknessMm ?? 0,
  ]);
  specWarning.value = mismatch
    ? `This model requires ${mismatch.expectedSpacing.join(" × ")} mm spacing within ` +
      `${mismatch.toleranceMm} mm. This series is ${mismatch.actualSpacing.join(" × ")} mm.`
    : null;
  inferenceError.value = null;
  if (mismatch) return;

  try {
    await models.runInference(
      { modelId: model.id, volumeAssetId: series.volumeAssetId },
      crypto.randomUUID(),
    );
  } catch (caught) {
    inferenceError.value =
      caught instanceof Error ? caught.message : "Unable to queue inference";
  }
}

async function addMeasurementPoint(x: number, y: number): Promise<void> {
  if (!annotations.draft) return;
  annotations.addDraftPoint([x, y, 0]);
  if (annotations.draftIsComplete)
    await annotations.commitDraft(props.seriesId);
}
</script>

<template>
  <q-page class="row no-wrap">
    <div class="col viewer-surface">
      <VolumeCanvas
        :frame="currentFrame"
        :width="viewportWidth"
        :height="viewportHeight"
        :frame-time-ms="frameTimeMs"
        :dropped-frames="droppedFrames"
        :connection-state="connectionState"
        :segmentation-active="segmentationActive"
        @orbit="
          (dx, dy) => {
            viewport.orbit(dx, dy);
            if (isE2E)
              viewport.recordFrameMetrics({
                renderTimeUs: 10000 + Math.abs(dx) * 100,
              });
          }
        "
        @canvas-click="addMeasurementPoint"
        @window-level="
          (dc, dw) =>
            viewport.setWindow({
              center: viewport.window.center + dc,
              width: viewport.window.width + dw,
            })
        "
      />
    </div>

    <aside class="viewer-sidebar column q-pa-md q-gutter-md">
      <q-banner
        v-if="streamError"
        dense
        class="bg-negative text-white"
        role="alert"
      >
        {{ streamError }}
      </q-banner>

      <section>
        <h3 class="text-subtitle2 q-mt-none">Window / Level</h3>
        <WindowLevelControl
          :center="viewport.window.center"
          :width="viewport.window.width"
          @change="viewport.setWindow"
        />
        <div class="row q-gutter-xs q-mt-sm">
          <q-btn
            v-for="name in presetNames"
            :key="name"
            flat
            dense
            size="sm"
            no-caps
            :label="name.replace('ct-', '')"
            @click="applyPreset(name)"
          />
        </div>
      </section>

      <q-separator />

      <section>
        <h3 class="text-subtitle2 q-mt-none">AI model</h3>
        <q-select
          v-model="models.selectedModelId"
          :options="
            models.segmentationModels.map((m) => ({
              label: `${m.name} ${m.version}`,
              value: m.id,
            }))
          "
          emit-value
          map-options
          dense
          outlined
          label="Model"
          aria-label="Select a model"
        />
        <q-btn
          class="q-mt-sm full-width"
          color="primary"
          no-caps
          label="Run model"
          :disable="
            !auth.canRunInference || !models.selectedModelId || isRunning
          "
          :loading="isRunning"
          data-testid="run-model"
          @click="runModel"
        />
        <q-linear-progress
          v-if="isRunning && activeJob"
          class="q-mt-sm"
          :value="activeJob.progress"
          role="progressbar"
        />
        <q-banner
          v-if="specWarning"
          dense
          class="bg-negative text-white q-mt-sm"
          role="alert"
        >
          {{ specWarning }}
        </q-banner>
        <q-banner
          v-if="inferenceError"
          dense
          class="bg-negative text-white q-mt-sm"
          role="alert"
        >
          {{ inferenceError }}
        </q-banner>
      </section>

      <q-separator />

      <LabelLegend
        :labels="selectedModel?.labelMap ?? {}"
        :visible="visibleLabels"
        :stats="segmentation?.labelStats ?? {}"
        @toggle="models.setLabelVisible"
        @show-all="models.showAllLabels"
      />

      <q-separator />

      <section>
        <h3 class="text-subtitle2 q-mt-none">Annotations</h3>
        <q-btn
          flat
          dense
          no-caps
          icon="straighten"
          label="Measure"
          :disable="!auth.canAnnotate"
          @click="annotations.beginDraft('measurement')"
        />
        <ul class="q-pl-md">
          <li v-for="item in annotations.measurements" :key="item.id">
            {{ annotations.measurementValue(item)?.toFixed(1) }} mm
          </li>
        </ul>
      </section>
    </aside>
  </q-page>
</template>

<style scoped lang="scss">
.viewer-surface {
  background: #000;
  min-height: calc(100vh - 100px);
}

.viewer-sidebar {
  width: 320px;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  overflow-y: auto;
}
</style>
