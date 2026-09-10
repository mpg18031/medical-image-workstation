import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  angleDegrees,
  distanceMm,
  ellipseAreaMm2,
  type Vec3,
} from "src/services/geometry";
import type {
  Annotation,
  AnnotationKind,
  AnnotationPayload,
} from "src/services/types";

export interface AnnotationsApi {
  list(seriesId: string): Promise<Annotation[]>;
  create(
    seriesId: string,
    body: {
      kind: AnnotationKind;
      payload: AnnotationPayload;
      label?: string | null;
    },
  ): Promise<Annotation>;
  update(
    id: string,
    body: { payload?: AnnotationPayload; label?: string },
  ): Promise<Annotation>;
  remove(id: string): Promise<void>;
}

export interface DraftAnnotation {
  kind: AnnotationKind;
  points: Vec3[];
}

/** Points required before a draft of each kind can be committed. */
const REQUIRED_POINTS: Record<AnnotationKind, number> = {
  measurement: 2,
  roi: 3,
  note: 1,
  label_edit: 1,
};

export const useAnnotationsStore = defineStore("annotations", () => {
  const items = ref<Annotation[]>([]);
  const draft = ref<DraftAnnotation | null>(null);
  const selectedId = ref<string | null>(null);
  const isSaving = ref(false);
  const error = ref<string | null>(null);

  let api: AnnotationsApi | null = null;

  function useApi(client: AnnotationsApi): void {
    api = client;
  }

  const selected = computed(
    () => items.value.find((a) => a.id === selectedId.value) ?? null,
  );
  const measurements = computed(() =>
    items.value.filter((a) => a.kind === "measurement"),
  );
  const draftIsComplete = computed(() => {
    if (!draft.value) return false;
    return draft.value.points.length >= REQUIRED_POINTS[draft.value.kind];
  });

  function beginDraft(kind: AnnotationKind): void {
    draft.value = { kind, points: [] };
  }

  function addDraftPoint(point: Vec3): void {
    if (!draft.value) return;
    draft.value = { ...draft.value, points: [...draft.value.points, point] };
  }

  function undoDraftPoint(): void {
    if (!draft.value || draft.value.points.length === 0) return;
    draft.value = { ...draft.value, points: draft.value.points.slice(0, -1) };
  }

  function cancelDraft(): void {
    draft.value = null;
  }

  async function commitDraft(
    seriesId: string,
    label?: string,
  ): Promise<Annotation | null> {
    if (!api) throw new Error("annotations store has no API client");
    if (!draft.value || !draftIsComplete.value) return null;

    isSaving.value = true;
    error.value = null;

    try {
      // Units are pinned to mm at the boundary: the API rejects pixel indices,
      // and so should we, before a round trip.
      const created = await api.create(seriesId, {
        kind: draft.value.kind,
        payload: {
          units: "mm",
          points: draft.value.points.map(
            (p) => [...p] as [number, number, number],
          ),
        },
        label: label ?? null,
      });
      items.value = [...items.value, created];
      draft.value = null;
      return created;
    } catch {
      error.value = "Could not save the annotation";
      return null;
    } finally {
      isSaving.value = false;
    }
  }

  async function load(seriesId: string): Promise<void> {
    if (!api) throw new Error("annotations store has no API client");
    error.value = null;
    try {
      items.value = await api.list(seriesId);
    } catch {
      error.value = "Could not load annotations";
      items.value = [];
    }
  }

  async function remove(id: string): Promise<boolean> {
    if (!api) throw new Error("annotations store has no API client");
    const previous = items.value;
    // Optimistic removal, reverted on failure: a lingering annotation the user
    // believes they deleted is worse than a brief flicker.
    items.value = items.value.filter((a) => a.id !== id);

    try {
      await api.remove(id);
      if (selectedId.value === id) selectedId.value = null;
      return true;
    } catch {
      items.value = previous;
      error.value = "Could not delete the annotation";
      return false;
    }
  }

  function measurementValue(annotation: Annotation): number | null {
    const points = annotation.payload.points as Vec3[];
    switch (annotation.kind) {
      case "measurement":
        if (points.length === 2) return distanceMm(points[0]!, points[1]!);
        if (points.length === 3)
          return angleDegrees(points[0]!, points[1]!, points[2]!);
        return null;
      case "roi":
        if (points.length === 3)
          return ellipseAreaMm2(points[0]!, points[1]!, points[2]!);
        return null;
      default:
        return null;
    }
  }

  function reset(): void {
    items.value = [];
    draft.value = null;
    selectedId.value = null;
    error.value = null;
  }

  return {
    items,
    draft,
    selectedId,
    isSaving,
    error,
    selected,
    measurements,
    draftIsComplete,
    useApi,
    beginDraft,
    addDraftPoint,
    undoDraftPoint,
    cancelDraft,
    commitDraft,
    load,
    remove,
    measurementValue,
    reset,
  };
});
