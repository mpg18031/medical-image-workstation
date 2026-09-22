import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { Job, ModelDetail, SegmentationResult } from "src/services/types";

export interface ModelsApi {
  list(): Promise<ModelDetail[]>;
  runInference(
    body: { modelId: string; volumeAssetId: string },
    key: string,
  ): Promise<Job>;
  getSegmentation(inferenceRunId: string): Promise<SegmentationResult>;
}

export interface SpecMismatch {
  expectedSpacing: [number, number, number];
  actualSpacing: [number, number, number];
  toleranceMm: number;
}

export const useModelsStore = defineStore("models", () => {
  const models = ref<ModelDetail[]>([]);
  const selectedModelId = ref<string | null>(null);
  const activeJob = ref<Job | null>(null);
  const segmentation = ref<SegmentationResult | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const visibleLabels = ref<Set<number>>(new Set());

  let api: ModelsApi | null = null;

  function useApi(client: ModelsApi): void {
    api = client;
  }

  const selectedModel = computed(
    () => models.value.find((m) => m.id === selectedModelId.value) ?? null,
  );
  const enabledModels = computed(() => models.value.filter((m) => m.isEnabled));
  const segmentationModels = computed(() =>
    enabledModels.value.filter((m) => m.outputKind === "segmentation"),
  );
  const isRunning = computed(
    () =>
      activeJob.value?.status === "queued" ||
      activeJob.value?.status === "running",
  );

  /**
   * Local pre-flight against the model's declared input spec.
   *
   * The server enforces this authoritatively; checking here means the user
   * learns why before waiting on a queued job. Never silently resample.
   */
  function checkSpec(
    model: ModelDetail,
    volumeSpacing: [number, number, number],
  ): SpecMismatch | null {
    const expected = model.inputSpec.spacingMm;
    const tolerance = model.inputSpec.spacingToleranceMm;

    const conforms = expected.every(
      (value, index) => Math.abs(value - volumeSpacing[index]!) <= tolerance,
    );

    return conforms
      ? null
      : {
          expectedSpacing: expected,
          actualSpacing: volumeSpacing,
          toleranceMm: tolerance,
        };
  }

  async function load(): Promise<void> {
    if (!api) throw new Error("models store has no API client");
    isLoading.value = true;
    error.value = null;
    try {
      models.value = await api.list();
    } catch (caught) {
      error.value =
        caught instanceof Error
          ? caught.message
          : "Could not load the model registry";
      models.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  async function runInference(
    body: { modelId: string; volumeAssetId: string },
    key: string,
  ): Promise<Job> {
    if (!api) throw new Error("models store has no API client");
    segmentation.value = null;
    const job = await api.runInference(body, key);
    activeJob.value = job;
    return job;
  }

  async function fetchSegmentation(
    inferenceRunId: string,
  ): Promise<SegmentationResult> {
    if (!api) throw new Error("models store has no API client");
    const result = await api.getSegmentation(inferenceRunId);
    segmentation.value = result;
    showAllLabels();
    return result;
  }

  function setLabelVisible(index: number, visible: boolean): void {
    const next = new Set(visibleLabels.value);
    if (visible) next.add(index);
    else next.delete(index);
    visibleLabels.value = next;
  }

  function showAllLabels(): void {
    const model = selectedModel.value;
    if (!model) return;
    visibleLabels.value = new Set(Object.keys(model.labelMap).map(Number));
  }

  function updateJob(job: Job): void {
    if (activeJob.value && activeJob.value.id !== job.id) return;
    activeJob.value = job;
  }

  function reset(): void {
    selectedModelId.value = null;
    activeJob.value = null;
    segmentation.value = null;
    visibleLabels.value = new Set();
    error.value = null;
  }

  return {
    models,
    selectedModelId,
    activeJob,
    segmentation,
    isLoading,
    error,
    visibleLabels,
    selectedModel,
    enabledModels,
    segmentationModels,
    isRunning,
    useApi,
    checkSpec,
    load,
    runInference,
    fetchSegmentation,
    setLabelVisible,
    showAllLabels,
    updateJob,
    reset,
  };
});
