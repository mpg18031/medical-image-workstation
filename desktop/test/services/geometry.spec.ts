import { describe, expect, it } from "vitest";
import {
  MIN_WINDOW_WIDTH,
  SingularGeometryError,
  angleDegrees,
  applyWindow,
  distanceMm,
  ellipseAreaMm2,
  patientToVoxel,
  polygonAreaMm2,
  toHounsfield,
  voxelToPatient,
  voxelVolumeMl,
  type VolumeGeometry,
  type Vec3,
} from "src/services/geometry";

const anisotropic: VolumeGeometry = {
  origin: [10, -20, 30],
  spacingMm: [0.8, 0.8, 1.25],
};

describe("coordinate transforms", () => {
  it("round-trips voxel -> patient -> voxel", () => {
    const voxel: Vec3 = [12.5, 33, 7.25];
    const back = patientToVoxel(
      voxelToPatient(voxel, anisotropic),
      anisotropic,
    );
    back.forEach((value, index) => expect(value).toBeCloseTo(voxel[index]!, 9));
  });

  it("places voxel (0,0,0) at the geometry origin", () => {
    expect(voxelToPatient([0, 0, 0], anisotropic)).toEqual([10, -20, 30]);
  });

  it("scales by voxel spacing on each axis independently", () => {
    const p = voxelToPatient([1, 1, 1], anisotropic);
    expect(p[0]).toBeCloseTo(10.8);
    expect(p[1]).toBeCloseTo(-19.2);
    expect(p[2]).toBeCloseTo(31.25);
  });

  it("honours a non-identity direction matrix", () => {
    const lps: VolumeGeometry = {
      origin: [0, 0, 0],
      spacingMm: [1, 1, 1],
      direction: [-1, 0, 0, 0, -1, 0, 0, 0, 1],
    };
    expect(voxelToPatient([5, 5, 5], lps)).toEqual([-5, -5, 5]);
  });

  it("rejects a singular direction matrix rather than returning nonsense", () => {
    const corrupt: VolumeGeometry = {
      origin: [0, 0, 0],
      spacingMm: [1, 1, 1],
      direction: [0, 0, 0, 0, 0, 0, 0, 0, 0],
    };
    expect(() => patientToVoxel([1, 2, 3], corrupt)).toThrow(
      SingularGeometryError,
    );
  });
});

describe("measurements", () => {
  it("computes distance in millimetres", () => {
    expect(distanceMm([0, 0, 0], [3, 4, 0])).toBe(5);
  });

  it("measures a right angle", () => {
    expect(angleDegrees([1, 0, 0], [0, 0, 0], [0, 1, 0])).toBeCloseTo(90);
  });

  it("returns 180 degrees for collinear points without NaN from float error", () => {
    // acos of a value marginally outside [-1, 1] would otherwise yield NaN.
    expect(angleDegrees([1, 0, 0], [0, 0, 0], [-1, 0, 0])).toBeCloseTo(180);
  });

  it("returns NaN when a limb has zero length", () => {
    expect(angleDegrees([0, 0, 0], [0, 0, 0], [1, 0, 0])).toBeNaN();
  });

  it("computes ellipse area from semi-axis endpoints", () => {
    expect(ellipseAreaMm2([0, 0, 0], [2, 0, 0], [0, 3, 0])).toBeCloseTo(
      Math.PI * 6,
    );
  });

  it("computes polygon area via the shoelace formula", () => {
    expect(
      polygonAreaMm2([
        [0, 0, 0],
        [4, 0, 0],
        [4, 3, 0],
        [0, 3, 0],
      ]),
    ).toBeCloseTo(12);
  });

  it("treats a degenerate polygon as zero area", () => {
    expect(
      polygonAreaMm2([
        [0, 0, 0],
        [1, 1, 1],
      ]),
    ).toBe(0);
  });

  it("converts voxel counts to millilitres", () => {
    // 1000 voxels of 1 mm^3 = 1000 mm^3 = 1 mL
    expect(voxelVolumeMl(1000, [1, 1, 1])).toBeCloseTo(1);
    expect(voxelVolumeMl(1000, [0.5, 0.5, 2])).toBeCloseTo(0.5);
  });
});

describe("window/level", () => {
  it("maps the window centre to 0.5", () => {
    expect(applyWindow(40, { center: 40, width: 400 })).toBeCloseTo(0.5);
  });

  it("clamps values outside the window", () => {
    expect(applyWindow(-5000, { center: 40, width: 400 })).toBe(0);
    expect(applyWindow(5000, { center: 40, width: 400 })).toBe(1);
  });

  it("never divides by zero when width is degenerate", () => {
    for (const width of [0, -100, Number.EPSILON]) {
      const result = applyWindow(100, { center: 40, width });
      expect(Number.isFinite(result)).toBe(true);
      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThanOrEqual(1);
    }
    expect(MIN_WINDOW_WIDTH).toBeGreaterThan(0);
  });

  it("applies DICOM rescale to obtain Hounsfield units", () => {
    expect(toHounsfield(0, 1, -1024)).toBe(-1024);
    expect(toHounsfield(1000, 1, -1024)).toBe(-24);
  });
});
