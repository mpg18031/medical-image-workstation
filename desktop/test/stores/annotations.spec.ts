import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import {
  useAnnotationsStore,
  type AnnotationsApi,
} from "src/stores/annotations";
import type { Annotation } from "src/services/types";

function annotation(overrides: Partial<Annotation> = {}): Annotation {
  return {
    id: "a1",
    seriesId: "s1",
    authorId: "u1",
    authorName: "Test User",
    kind: "measurement",
    payload: {
      units: "mm",
      points: [
        [0, 0, 0],
        [10, 0, 0],
      ],
    },
    label: null,
    frameOfReferenceUid: "for-1",
    createdAt: "2026-03-14T10:00:00Z",
    updatedAt: "2026-03-14T10:00:00Z",
    ...overrides,
  };
}

describe("annotations store", () => {
  let api: Record<keyof AnnotationsApi, ReturnType<typeof vi.fn>>;

  beforeEach(() => {
    setActivePinia(createPinia());
    api = { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() };
  });

  function storeWithApi() {
    const store = useAnnotationsStore();
    store.useApi(api as unknown as AnnotationsApi);
    return store;
  }

  describe("drafting", () => {
    it("is incomplete until a measurement has two points", () => {
      const store = storeWithApi();
      store.beginDraft("measurement");
      expect(store.draftIsComplete).toBe(false);

      store.addDraftPoint([0, 0, 0]);
      expect(store.draftIsComplete).toBe(false);

      store.addDraftPoint([10, 0, 0]);
      expect(store.draftIsComplete).toBe(true);
    });

    it("requires three points for an ROI", () => {
      const store = storeWithApi();
      store.beginDraft("roi");
      store.addDraftPoint([0, 0, 0]);
      store.addDraftPoint([1, 0, 0]);
      expect(store.draftIsComplete).toBe(false);

      store.addDraftPoint([0, 1, 0]);
      expect(store.draftIsComplete).toBe(true);
    });

    it("undoes the last point", () => {
      const store = storeWithApi();
      store.beginDraft("measurement");
      store.addDraftPoint([0, 0, 0]);
      store.addDraftPoint([5, 0, 0]);
      store.undoDraftPoint();

      expect(store.draft?.points).toHaveLength(1);
    });

    it("ignores undo on an empty draft", () => {
      const store = storeWithApi();
      store.beginDraft("measurement");
      expect(() => store.undoDraftPoint()).not.toThrow();
      expect(store.draft?.points).toHaveLength(0);
    });

    it("refuses to commit an incomplete draft", async () => {
      const store = storeWithApi();
      store.beginDraft("measurement");
      store.addDraftPoint([0, 0, 0]);

      expect(await store.commitDraft("s1")).toBeNull();
      expect(api.create).not.toHaveBeenCalled();
    });

    it("always submits geometry in millimetres", async () => {
      // The API rejects pixel indices; catching it here avoids a round trip
      // and, more importantly, prevents pixel geometry ever being constructed.
      api.create.mockResolvedValue(annotation());
      const store = storeWithApi();

      store.beginDraft("measurement");
      store.addDraftPoint([0, 0, 0]);
      store.addDraftPoint([10, 0, 0]);
      await store.commitDraft("s1");

      expect(api.create).toHaveBeenCalledWith(
        "s1",
        expect.objectContaining({
          payload: expect.objectContaining({ units: "mm" }),
        }),
      );
    });

    it("clears the draft after a successful commit", async () => {
      api.create.mockResolvedValue(annotation());
      const store = storeWithApi();

      store.beginDraft("measurement");
      store.addDraftPoint([0, 0, 0]);
      store.addDraftPoint([10, 0, 0]);
      await store.commitDraft("s1");

      expect(store.draft).toBeNull();
      expect(store.items).toHaveLength(1);
    });

    it("keeps the draft when the save fails so work is not lost", async () => {
      api.create.mockRejectedValue(new Error("network"));
      const store = storeWithApi();

      store.beginDraft("measurement");
      store.addDraftPoint([0, 0, 0]);
      store.addDraftPoint([10, 0, 0]);
      const result = await store.commitDraft("s1");

      expect(result).toBeNull();
      expect(store.draft).not.toBeNull();
      expect(store.error).not.toBeNull();
    });
  });

  describe("deletion", () => {
    it("removes optimistically", async () => {
      api.remove.mockResolvedValue(undefined);
      const store = storeWithApi();
      store.items = [annotation({ id: "a1" }), annotation({ id: "a2" })];

      await store.remove("a1");
      expect(store.items.map((a) => a.id)).toEqual(["a2"]);
    });

    it("restores the annotation when deletion fails", async () => {
      // A lingering annotation the user believes they deleted is worse than a
      // brief flicker, so the optimistic removal must be reverted.
      api.remove.mockRejectedValue(new Error("conflict"));
      const store = storeWithApi();
      store.items = [annotation({ id: "a1" })];

      expect(await store.remove("a1")).toBe(false);
      expect(store.items).toHaveLength(1);
      expect(store.error).not.toBeNull();
    });
  });

  describe("derived values", () => {
    it("computes a distance for a two-point measurement", () => {
      const store = storeWithApi();
      const value = store.measurementValue(
        annotation({
          payload: {
            units: "mm",
            points: [
              [0, 0, 0],
              [3, 4, 0],
            ],
          },
        }),
      );
      expect(value).toBeCloseTo(5);
    });

    it("computes an angle for a three-point measurement", () => {
      const store = storeWithApi();
      const value = store.measurementValue(
        annotation({
          payload: {
            units: "mm",
            points: [
              [1, 0, 0],
              [0, 0, 0],
              [0, 1, 0],
            ],
          },
        }),
      );
      expect(value).toBeCloseTo(90);
    });

    it("returns null for kinds without a numeric value", () => {
      const store = storeWithApi();
      expect(store.measurementValue(annotation({ kind: "note" }))).toBeNull();
    });
  });

  it("reports a load failure and leaves no partial state", async () => {
    api.list.mockRejectedValue(new Error("boom"));
    const store = storeWithApi();
    await store.load("s1");

    expect(store.items).toEqual([]);
    expect(store.error).not.toBeNull();
  });
});
