/**
 * Domain types mirroring the API schemas.
 *
 * Generated types land in `src/services/generated/`; these are the hand-written
 * aliases the UI actually consumes.
 */

export interface PatientSummary {
  id: string;
  pseudonym: string;
  birthYear: number | null;
  sex: "M" | "F" | "O" | "U" | null;
}

export interface StudySummary {
  id: string;
  patient: PatientSummary;
  studyDatetime: string | null;
  description: string | null;
  modalities: string[];
  seriesCount: number;
}

export interface SeriesGeometry {
  rows: number;
  columns: number;
  sliceCount: number;
  pixelSpacingMm: [number, number];
  sliceThicknessMm: number | null;
  imageOrientation: [number, number, number, number, number, number] | null;
  imagePosition: [number, number, number] | null;
  rescaleSlope: number;
  rescaleIntercept: number;
}

export interface SeriesDetail {
  id: string;
  studyId: string;
  volumeAssetId?: string | null;
  seriesNumber: number | null;
  modality: string;
  description: string | null;
  frameOfReferenceUid: string | null;
  geometry: SeriesGeometry;
  isQuarantined: boolean;
  hasVolume: boolean;
}

export type AnnotationKind = "measurement" | "roi" | "note" | "label_edit";

export interface AnnotationPayload {
  units: "mm";
  points: Array<[number, number, number]>;
  text?: string | null;
  radiusMm?: number | null;
  labelIndex?: number | null;
}

export interface Annotation {
  id: string;
  seriesId: string;
  authorId: string;
  authorName: string | null;
  kind: AnnotationKind;
  payload: AnnotationPayload;
  label: string | null;
  frameOfReferenceUid: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface LabelInfo {
  name: string;
  color: string;
}

export interface ModelDetail {
  id: string;
  name: string;
  version: string;
  outputKind: "segmentation" | "classification" | "heatmap" | "landmarks";
  inputSpec: {
    shape: number[];
    spacingMm: [number, number, number];
    orientation: string;
    spacingToleranceMm: number;
  };
  labelMap: Record<string, LabelInfo>;
  description: string | null;
  isEnabled: boolean;
  validatedAt: string | null;
}

export interface Page<T> {
  items: T[];
  nextCursor: string | null;
}

export type Role = "viewer" | "annotator" | "researcher" | "admin";

export interface RenderSession {
  id: string;
  token: string;
  seriesId: string;
  websocketPath: string;
  expiresAt: string;
}

export type JobStatus =
  "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  kind: "ingest" | "inference" | "export" | "erasure";
  status: JobStatus;
  progress: number;
  stage: string | null;
  createdAt: string;
  finishedAt: string | null;
  error: Record<string, unknown> | null;
}
