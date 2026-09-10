import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useModelsStore, type ModelsApi } from "src/stores/models";
import type { ModelDetail } from "src/services/types";

function model(overrides: Partial<ModelDetail> = {}): ModelDetail {
  return {
    id: "m1",
    name: "liver-seg",
    version: "1.4.0",
    outputKind: "segmentation",
    inputSpec: {
      shape: [1, 1, 128, 128, 128],
      spacingMm: [1, 1, 1],
      orientation: "RAS",
      spacingToleranceMm: 0.01,
    },
    labelMap: { "1": { name: "liver", color: "#d94f3d" } },
    description: null,
    isEnabled: true,
    validatedAt: "2026-03-01T00:00:00Z",
    ...overrides,
  };
}

describe("models store", () => {
  let api: Record<keyof ModelsApi, ReturnType<typeof vi.fn>>;

  beforeEach(() => {
    setActivePinia(createPinia());
    api = { list: vi.fn(), runInference: vi.fn() };
  });

  function storeWithApi() {
    const store = useModelsStore();
    store.useApi(api as unknown as ModelsApi);
    return store;
  }

  describe("input-spec pre-flight", () => {
    it("accepts a conforming volume", () => {
      const store = storeWithApi();
      expect(store.checkSpec(model(), [1, 1, 1])).toBeNull();
    });

    it("accepts spacing within the declared tolerance", () => {
      const store = storeWithApi();
      const m = model({
        inputSpec: { ...model().inputSpec, spacingToleranceMm: 0.05 },
      });
      expect(store.checkSpec(m, [1.02, 0.98, 1.01])).toBeNull();
    });

    it("rejects clinical anisotropic spacing rather than resampling it", () => {
      // 0.7x0.7x3.0 is typical clinical CT against a 1mm isotropic model.
      // Silently adapting would produce a plausible, confidently wrong result.
      const store = storeWithApi();
      const mismatch = store.checkSpec(model(), [0.7, 0.7, 3.0]);

      expect(mismatch).not.toBeNull();
      expect(mismatch!.expectedSpacing).toEqual([1, 1, 1]);
      expect(mismatch!.actualSpacing).toEqual([0.7, 0.7, 3.0]);
    });

    it("rejects spacing just outside the tolerance", () => {
      const store = storeWithApi();
      expect(store.checkSpec(model(), [1.02, 1, 1])).not.toBeNull();
    });
  });

  describe("registry filtering", () => {
    it("excludes disabled models from the runnable set", () => {
      const store = storeWithApi();
      store.models = [model({ id: "a" }), model({ id: "b", isEnabled: false })];

      expect(store.enabledModels.map((m) => m.id)).toEqual(["a"]);
    });

    it("separates segmentation models from other output kinds", () => {
      const store = storeWithApi();
      store.models = [
        model({ id: "seg" }),
        model({ id: "cls", outputKind: "classification" }),
      ];

      expect(store.segmentationModels.map((m) => m.id)).toEqual(["seg"]);
    });
  });

  describe("label visibility", () => {
    it("toggles a label without mutating the previous set", () => {
      const store = storeWithApi();
      const before = store.visibleLabels;

      store.setLabelVisible(1, true);
      expect(store.visibleLabels.has(1)).toBe(true);
      // Replacing rather than mutating keeps Vue's reactivity reliable.
      expect(store.visibleLabels).not.toBe(before);
    });

    it("shows every label of the selected model", () => {
      const store = storeWithApi();
      store.models = [
        model({
          labelMap: {
            "1": { name: "liver", color: "#a" },
            "2": { name: "tumour", color: "#b" },
          },
        }),
      ];
      store.selectedModelId = "m1";

      store.showAllLabels();
      expect([...store.visibleLabels].sort()).toEqual([1, 2]);
    });
  });

  describe("job tracking", () => {
    it("reports running for queued and running states", () => {
      const store = storeWithApi();
      store.activeJob = {
        id: "j1",
        kind: "inference",
        status: "queued",
        progress: 0,
        stage: null,
        createdAt: "",
        finishedAt: null,
        error: null,
      };
      expect(store.isRunning).toBe(true);

      store.updateJob({ ...store.activeJob, status: "succeeded", progress: 1 });
      expect(store.isRunning).toBe(false);
    });

    it("ignores progress for a job that is not the active one", () => {
      const store = storeWithApi();
      store.activeJob = {
        id: "j1",
        kind: "inference",
        status: "running",
        progress: 0.5,
        stage: null,
        createdAt: "",
        finishedAt: null,
        error: null,
      };

      store.updateJob({
        id: "other",
        kind: "ingest",
        status: "succeeded",
        progress: 1,
        stage: null,
        createdAt: "",
        finishedAt: null,
        error: null,
      });
      expect(store.activeJob.id).toBe("j1");
      expect(store.activeJob.progress).toBe(0.5);
    });
  });

  it("reports a registry load failure", async () => {
    api.list.mockRejectedValue(new Error("boom"));
    const store = storeWithApi();
    await store.load();

    expect(store.models).toEqual([]);
    expect(store.error).not.toBeNull();
  });
});
