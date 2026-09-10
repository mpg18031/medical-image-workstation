import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useStudiesStore, type StudiesApi } from "src/stores/studies";
import { ApiError } from "src/services/apiClient";
import type { Page, SeriesDetail, StudySummary } from "src/services/types";

function study(id: string, modality = "CT"): StudySummary {
  return {
    id,
    patient: {
      id: `p-${id}`,
      pseudonym: `PT-${id}`,
      birthYear: 1970,
      sex: "O",
    },
    studyDatetime: "2026-03-14T10:15:00Z",
    description: "Synthetic phantom",
    modalities: [modality],
    seriesCount: 1,
  };
}

function series(
  id: string,
  overrides: Partial<SeriesDetail> = {},
): SeriesDetail {
  return {
    id,
    studyId: "study-1",
    seriesNumber: 1,
    modality: "CT",
    description: "Axial",
    frameOfReferenceUid: "for-1",
    geometry: {
      rows: 512,
      columns: 512,
      sliceCount: 120,
      pixelSpacingMm: [0.7, 0.7],
      sliceThicknessMm: 3,
      imageOrientation: null,
      imagePosition: null,
      rescaleSlope: 1,
      rescaleIntercept: -1024,
    },
    isQuarantined: false,
    hasVolume: true,
    ...overrides,
  };
}

function page(
  items: StudySummary[],
  nextCursor: string | null = null,
): Page<StudySummary> {
  return { items, nextCursor };
}

describe("studies store", () => {
  let api: {
    listStudies: ReturnType<typeof vi.fn>;
    listSeries: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    setActivePinia(createPinia());
    api = { listStudies: vi.fn(), listSeries: vi.fn() };
  });

  function storeWithApi() {
    const store = useStudiesStore();
    store.useApi(api as unknown as StudiesApi);
    return store;
  }

  it("loads the first page and records the cursor", async () => {
    api.listStudies.mockResolvedValue(
      page([study("a"), study("b")], "cursor-1"),
    );
    const store = storeWithApi();

    await store.fetchStudies();

    expect(store.studies).toHaveLength(2);
    expect(store.hasMore).toBe(true);
    expect(store.isLoading).toBe(false);
  });

  it("appends the next page rather than replacing it", async () => {
    api.listStudies.mockResolvedValueOnce(page([study("a")], "cursor-1"));
    const store = storeWithApi();
    await store.fetchStudies();

    api.listStudies.mockResolvedValueOnce(page([study("b")], null));
    await store.fetchStudies({ append: true });

    expect(store.studies.map((s) => s.id)).toEqual(["a", "b"]);
    expect(store.hasMore).toBe(false);
  });

  it("discards a stale response that resolves after a newer one", async () => {
    // Filters change faster than the network responds; a slow first request
    // must not clobber the result the user is actually looking at.
    let resolveSlow: (value: Page<StudySummary>) => void = () => {};
    api.listStudies.mockImplementationOnce(
      () =>
        new Promise<Page<StudySummary>>((resolve) => {
          resolveSlow = resolve;
        }),
    );
    const store = storeWithApi();
    const slow = store.fetchStudies();

    api.listStudies.mockResolvedValueOnce(page([study("fresh")]));
    await store.fetchStudies();

    resolveSlow(page([study("stale")]));
    await slow;

    expect(store.studies.map((s) => s.id)).toEqual(["fresh"]);
  });

  it("reports a transient failure distinctly from a hard one", async () => {
    api.listStudies.mockRejectedValue(
      new ApiError({ type: "t", title: "Service unavailable", status: 503 }),
    );
    const store = storeWithApi();
    await store.fetchStudies();

    expect(store.error).toMatch(/temporarily unavailable/i);
    expect(store.studies).toEqual([]);
  });

  it("keeps already-loaded studies when an append fails", async () => {
    api.listStudies.mockResolvedValueOnce(page([study("a")], "c1"));
    const store = storeWithApi();
    await store.fetchStudies();

    api.listStudies.mockRejectedValueOnce(new Error("network"));
    await store.fetchStudies({ append: true });

    expect(store.studies).toHaveLength(1);
    expect(store.error).not.toBeNull();
  });

  describe("series selection", () => {
    it("auto-selects the first renderable series", async () => {
      api.listSeries.mockResolvedValue([
        series("s1", { hasVolume: false }),
        series("s2"),
      ]);
      const store = storeWithApi();

      await store.selectStudy("study-1");
      expect(store.selectedSeriesId).toBe("s2");
    });

    it("skips quarantined series when auto-selecting", async () => {
      // Quarantined series may carry burned-in PHI; never open one by default.
      api.listSeries.mockResolvedValue([
        series("s1", { isQuarantined: true }),
        series("s2"),
      ]);
      const store = storeWithApi();

      await store.selectStudy("study-1");
      expect(store.selectedSeriesId).toBe("s2");
      expect(store.quarantinedCount).toBe(1);
    });

    it("selects nothing when no series is renderable", async () => {
      api.listSeries.mockResolvedValue([series("s1", { hasVolume: false })]);
      const store = storeWithApi();

      await store.selectStudy("study-1");
      expect(store.selectedSeriesId).toBeNull();
      expect(store.viewableSeries).toHaveLength(0);
    });

    it("clears the previous study series before loading new ones", async () => {
      api.listSeries.mockResolvedValueOnce([series("s1")]);
      const store = storeWithApi();
      await store.selectStudy("study-1");

      api.listSeries.mockRejectedValueOnce(new Error("boom"));
      await store.selectStudy("study-2");

      expect(store.series).toEqual([]);
      expect(store.selectedSeriesId).toBeNull();
    });
  });

  it("resets the cursor when filters change", async () => {
    api.listStudies.mockResolvedValue(page([study("a")], "cursor-1"));
    const store = storeWithApi();
    await store.fetchStudies();

    store.setFilters({ modality: "MR" });
    expect(store.nextCursor).toBeNull();
    expect(store.filters.modality).toBe("MR");
  });
});
