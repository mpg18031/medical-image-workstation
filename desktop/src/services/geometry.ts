/**
 * Coordinate transforms and measurement maths.
 *
 * Annotations are always stored in patient millimetres. Pixel indices would
 * silently become wrong the moment a volume is resampled or reoriented, so
 * conversion happens here at the edges and nowhere else.
 */

export type Vec3 = readonly [number, number, number];
export type Mat3 = readonly [
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
];

export interface VolumeGeometry {
  /** Patient-space position of the centre of voxel (0, 0, 0), in mm. */
  origin: Vec3;
  spacingMm: Vec3;
  /** Row-major direction cosines. Defaults to identity (LPS-aligned). */
  direction?: Mat3;
}

const IDENTITY: Mat3 = [1, 0, 0, 0, 1, 0, 0, 0, 1];

export function voxelToPatient(voxel: Vec3, geometry: VolumeGeometry): Vec3 {
  const m = geometry.direction ?? IDENTITY;
  const s: Vec3 = [
    voxel[0] * geometry.spacingMm[0],
    voxel[1] * geometry.spacingMm[1],
    voxel[2] * geometry.spacingMm[2],
  ];

  return [
    geometry.origin[0] + m[0] * s[0] + m[1] * s[1] + m[2] * s[2],
    geometry.origin[1] + m[3] * s[0] + m[4] * s[1] + m[5] * s[2],
    geometry.origin[2] + m[6] * s[0] + m[7] * s[1] + m[8] * s[2],
  ];
}

export class SingularGeometryError extends Error {
  constructor() {
    super("Volume direction matrix is singular; DICOM geometry is unusable");
    this.name = "SingularGeometryError";
  }
}

export function patientToVoxel(
  patientMm: Vec3,
  geometry: VolumeGeometry,
): Vec3 {
  const m = geometry.direction ?? IDENTITY;

  const det =
    m[0] * (m[4] * m[8] - m[5] * m[7]) -
    m[1] * (m[3] * m[8] - m[5] * m[6]) +
    m[2] * (m[3] * m[7] - m[4] * m[6]);

  // Refuse rather than emit nonsense coordinates a user might measure against.
  if (Math.abs(det) < 1e-12) throw new SingularGeometryError();

  const inv = 1 / det;
  const adj: Mat3 = [
    (m[4] * m[8] - m[5] * m[7]) * inv,
    (m[2] * m[7] - m[1] * m[8]) * inv,
    (m[1] * m[5] - m[2] * m[4]) * inv,
    (m[5] * m[6] - m[3] * m[8]) * inv,
    (m[0] * m[8] - m[2] * m[6]) * inv,
    (m[2] * m[3] - m[0] * m[5]) * inv,
    (m[3] * m[7] - m[4] * m[6]) * inv,
    (m[1] * m[6] - m[0] * m[7]) * inv,
    (m[0] * m[4] - m[1] * m[3]) * inv,
  ];

  const d: Vec3 = [
    patientMm[0] - geometry.origin[0],
    patientMm[1] - geometry.origin[1],
    patientMm[2] - geometry.origin[2],
  ];

  return [
    (adj[0] * d[0] + adj[1] * d[1] + adj[2] * d[2]) / geometry.spacingMm[0],
    (adj[3] * d[0] + adj[4] * d[1] + adj[5] * d[2]) / geometry.spacingMm[1],
    (adj[6] * d[0] + adj[7] * d[1] + adj[8] * d[2]) / geometry.spacingMm[2],
  ];
}

export function distanceMm(a: Vec3, b: Vec3): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
}

export interface VolumeExtent {
  rows: number;
  columns: number;
  sliceCount: number;
  pixelSpacingMm: [number, number];
  sliceThicknessMm: number | null;
  imageOrientation: [number, number, number, number, number, number] | null;
  imagePosition: [number, number, number] | null;
}

function crossVec3(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/** Centre of the volume in patient mm, so a viewer can orbit around it instead of a corner. */
export function volumeCenterMm(geometry: VolumeExtent): Vec3 {
  const origin = geometry.imagePosition ?? [0, 0, 0];
  const rowCosine: Vec3 = geometry.imageOrientation
    ? [
        geometry.imageOrientation[0],
        geometry.imageOrientation[1],
        geometry.imageOrientation[2],
      ]
    : [1, 0, 0];
  const colCosine: Vec3 = geometry.imageOrientation
    ? [
        geometry.imageOrientation[3],
        geometry.imageOrientation[4],
        geometry.imageOrientation[5],
      ]
    : [0, 1, 0];
  const sliceCosine = crossVec3(rowCosine, colCosine);

  const halfExtentMm: Vec3 = [
    ((geometry.columns - 1) / 2) * geometry.pixelSpacingMm[0],
    ((geometry.rows - 1) / 2) * geometry.pixelSpacingMm[1],
    ((geometry.sliceCount - 1) / 2) * (geometry.sliceThicknessMm ?? 0),
  ];

  return [
    origin[0] +
      rowCosine[0] * halfExtentMm[0] +
      colCosine[0] * halfExtentMm[1] +
      sliceCosine[0] * halfExtentMm[2],
    origin[1] +
      rowCosine[1] * halfExtentMm[0] +
      colCosine[1] * halfExtentMm[1] +
      sliceCosine[1] * halfExtentMm[2],
    origin[2] +
      rowCosine[2] * halfExtentMm[0] +
      colCosine[2] * halfExtentMm[1] +
      sliceCosine[2] * halfExtentMm[2],
  ];
}

/** Angle at vertex `b`, in degrees. Returns NaN when a limb has zero length. */
export function angleDegrees(a: Vec3, b: Vec3, c: Vec3): number {
  const u: Vec3 = [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const v: Vec3 = [c[0] - b[0], c[1] - b[1], c[2] - b[2]];

  const lenU = Math.hypot(...u);
  const lenV = Math.hypot(...v);
  if (lenU === 0 || lenV === 0) return Number.NaN;

  const dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
  // Clamp: floating error can push the quotient just outside [-1, 1] and make
  // acos return NaN for legitimately collinear points.
  const cosine = Math.min(1, Math.max(-1, dot / (lenU * lenV)));
  return (Math.acos(cosine) * 180) / Math.PI;
}

/** Area of an ellipse defined by its two semi-axis endpoints, in mm². */
export function ellipseAreaMm2(
  centre: Vec3,
  majorEnd: Vec3,
  minorEnd: Vec3,
): number {
  return Math.PI * distanceMm(centre, majorEnd) * distanceMm(centre, minorEnd);
}

/** Polygon area via the shoelace formula, projected onto its own plane. */
export function polygonAreaMm2(points: readonly Vec3[]): number {
  if (points.length < 3) return 0;

  let cross: Vec3 = [0, 0, 0];
  for (let i = 0; i < points.length; i += 1) {
    const p = points[i]!;
    const q = points[(i + 1) % points.length]!;
    cross = [
      cross[0] + (p[1] * q[2] - p[2] * q[1]),
      cross[1] + (p[2] * q[0] - p[0] * q[2]),
      cross[2] + (p[0] * q[1] - p[1] * q[0]),
    ];
  }
  return Math.hypot(...cross) / 2;
}

/** Voxel count to millilitres. 1 mL = 1000 mm³. */
export function voxelVolumeMl(voxelCount: number, spacingMm: Vec3): number {
  return (voxelCount * spacingMm[0] * spacingMm[1] * spacingMm[2]) / 1000;
}

export interface WindowLevel {
  center: number;
  width: number;
}

export const MIN_WINDOW_WIDTH = 1;

/** Maps a stored value into [0, 1]. Width is clamped to avoid /0 in the shader. */
export function applyWindow(value: number, window: WindowLevel): number {
  const width = Math.max(window.width, MIN_WINDOW_WIDTH);
  const low = window.center - width / 2;
  return Math.min(1, Math.max(0, (value - low) / width));
}

export function toHounsfield(
  stored: number,
  slope: number,
  intercept: number,
): number {
  return stored * slope + intercept;
}

export const WINDOW_PRESETS: Record<string, WindowLevel> = {
  "ct-soft-tissue": { center: 40, width: 400 },
  "ct-lung": { center: -600, width: 1500 },
  "ct-bone": { center: 300, width: 1500 },
  "ct-brain": { center: 40, width: 80 },
  "ct-liver": { center: 60, width: 160 },
};

export function formatMm(value: number, digits = 1): string {
  return `${value.toFixed(digits)} mm`;
}

export function formatArea(value: number, digits = 1): string {
  return `${value.toFixed(digits)} mm²`;
}
