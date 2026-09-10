import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiError } from "src/services/apiClient";
import type { Page, SeriesDetail, StudySummary } from "src/services/types";

export interface StudyFilters {
  modality: string | null;
  patientRef: string | null;
}

export interface StudiesApi {
  listStudies(
    query: Record<string, string | number | undefined>,
  ): Promise<Page<StudySummary>>;
  listSeries(studyId: string): Promise<SeriesDetail[]>;
}

export const useStudiesStore = defineStore("studies", () => {
  const studies = ref<StudySummary[]>([]);
  const series = ref<SeriesDetail[]>([]);
  const selectedStudyId = ref<string | null>(null);
  const selectedSeriesId = ref<string | null>(null);
  const nextCursor = ref<string | null>(null);
  const filters = ref<StudyFilters>({ modality: null, patientRef: null });
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  let api: StudiesApi | null = null;
  let requestSeq = 0;

  function useApi(client: StudiesApi): void {
    api = client;
  }

  const hasMore = computed(() => nextCursor.value !== null);
  const selectedStudy = computed(
    () => studies.value.find((s) => s.id === selectedStudyId.value) ?? null,
  );
  const selectedSeries = computed(
    () => series.value.find((s) => s.id === selectedSeriesId.value) ?? null,
  );
  const viewableSeries = computed(() =>
    series.value.filter((s) => s.hasVolume && !s.isQuarantined),
  );
  const quarantinedCount = computed(
    () => series.value.filter((s) => s.isQuarantined).length,
  );

  async function fetchStudies(
    options: { append?: boolean } = {},
  ): Promise<void> {
    if (!api) throw new Error("studies store has no API client");

    const seq = ++requestSeq;
    isLoading.value = true;
    error.value = null;

    try {
      const page = await api.listStudies({
        modality: filters.value.modality ?? undefined,
        patientRef: filters.value.patientRef ?? undefined,
        after: options.append ? (nextCursor.value ?? undefined) : undefined,
        limit: 50,
      });

      // A slower earlier request must not overwrite a newer result; filters
      // change faster than the network responds.
      if (seq !== requestSeq) return;

      studies.value = options.append
        ? [...studies.value, ...page.items]
        : page.items;
      nextCursor.value = page.nextCursor;
    } catch (caught) {
      if (seq !== requestSeq) return;
      error.value = describe(caught);
      if (!options.append) studies.value = [];
    } finally {
      if (seq === requestSeq) isLoading.value = false;
    }
  }

  async function selectStudy(studyId: string): Promise<void> {
    if (!api) throw new Error("studies store has no API client");

    selectedStudyId.value = studyId;
    selectedSeriesId.value = null;
    series.value = [];
    error.value = null;

    try {
      series.value = await api.listSeries(studyId);
      // Auto-select the first usable series so the viewer is never blank when
      // a study clearly has renderable data.
      const first = series.value.find((s) => s.hasVolume && !s.isQuarantined);
      if (first) selectedSeriesId.value = first.id;
    } catch (caught) {
      error.value = describe(caught);
    }
  }

  function selectSeries(seriesId: string): void {
    selectedSeriesId.value = seriesId;
  }

  function setFilters(next: Partial<StudyFilters>): void {
    filters.value = { ...filters.value, ...next };
    nextCursor.value = null;
  }

  function reset(): void {
    studies.value = [];
    series.value = [];
    selectedStudyId.value = null;
    selectedSeriesId.value = null;
    nextCursor.value = null;
    filters.value = { modality: null, patientRef: null };
    error.value = null;
  }

  return {
    studies,
    series,
    selectedStudyId,
    selectedSeriesId,
    nextCursor,
    filters,
    isLoading,
    error,
    hasMore,
    selectedStudy,
    selectedSeries,
    viewableSeries,
    quarantinedCount,
    useApi,
    fetchStudies,
    selectStudy,
    selectSeries,
    setFilters,
    reset,
  };
});

function describe(caught: unknown): string {
  if (caught instanceof ApiError) {
    return caught.isTransient
      ? "The service is temporarily unavailable. Retrying may succeed."
      : caught.problem.title;
  }
  return "Unable to reach the workstation service";
}
