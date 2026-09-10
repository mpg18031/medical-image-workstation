#!/usr/bin/env python3
"""Generate synthetic DICOM fixtures.

No real patient data may ever enter this repository. Everything here is
procedurally generated; the "PHI" injected into some fixtures is fabricated so
that de-identification tests have something to strip.

A CI check rejects any .dcm file this script did not produce.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

GENERATOR_TAG = "MIVW-SYNTHETIC-FIXTURE"

FAKE_IDENTIFIERS = {
    "PatientName": "SYNTHETIC^TESTCASE^NOTAREALPERSON",
    "PatientID": "FAKE-MRN-000123",
    "PatientBirthDate": "19700615",
    "PatientAddress": "1 Fictional Street, Nowhere",
    "PatientTelephoneNumbers": "+00 000 0000000",
    "ReferringPhysicianName": "FICTIONAL^REFERRER",
    "InstitutionName": "Nonexistent General Hospital",
    "OperatorsName": "FICTIONAL^OPERATOR",
    "DeviceSerialNumber": "SN-FAKE-0001",
    "AccessionNumber": "FAKEACC0001",
}


def shepp_logan(shape: tuple[int, int, int]) -> np.ndarray:
    """Classic 3D phantom, scaled into a plausible Hounsfield range."""
    nz, ny, nx = shape
    z, y, x = np.mgrid[-1 : 1 : nz * 1j, -1 : 1 : ny * 1j, -1 : 1 : nx * 1j]

    volume = np.zeros(shape, dtype=np.float32)
    ellipsoids = [
        # (intensity, centre z/y/x, radii z/y/x)
        (1.0, (0.0, 0.0, 0.0), (0.9, 0.92, 0.69)),
        (-0.8, (0.0, -0.0184, 0.0), (0.88, 0.874, 0.6624)),
        (-0.2, (0.0, 0.0, 0.22), (0.21, 0.16, 0.11)),
        (-0.2, (0.0, 0.0, -0.22), (0.22, 0.16, 0.11)),
        (0.1, (0.0, 0.35, 0.0), (0.5, 0.25, 0.21)),
        (0.1, (0.0, 0.1, 0.0), (0.046, 0.046, 0.046)),
    ]
    for intensity, (cz, cy, cx), (rz, ry, rx) in ellipsoids:
        mask = ((z - cz) / rz) ** 2 + ((y - cy) / ry) ** 2 + ((x - cx) / rx) ** 2 <= 1.0
        volume[mask] += intensity

    return (volume * 1000.0 - 1000.0).astype(np.int16)


def sphere(shape: tuple[int, int, int], radius_fraction: float = 0.6) -> np.ndarray:
    nz, ny, nx = shape
    z, y, x = np.mgrid[-1 : 1 : nz * 1j, -1 : 1 : ny * 1j, -1 : 1 : nx * 1j]
    inside = (x**2 + y**2 + z**2) <= radius_fraction**2
    return np.where(inside, 300, -1000).astype(np.int16)


def base_dataset(*, modality: str, with_phi: bool) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.Modality = modality
    ds.StudyDate = date(2026, 3, 14).strftime("%Y%m%d")
    ds.StudyTime = "101500"

    # Marks provenance so CI can distinguish generated fixtures from anything
    # that might have been dropped in by accident.
    ds.ImageComments = GENERATOR_TAG

    if with_phi:
        for keyword, value in FAKE_IDENTIFIERS.items():
            setattr(ds, keyword, value)
    else:
        ds.PatientName = "ANON^ANON"
        ds.PatientID = "ANON"

    return ds


def write_slice(
    path: Path,
    pixels: np.ndarray,
    *,
    study_uid: str,
    series_uid: str,
    frame_uid: str,
    instance_number: int,
    slice_position: float,
    spacing: tuple[float, float],
    thickness: float,
    modality: str = "CT",
    with_phi: bool = False,
    burned_in: str | None = None,
    private_tags: bool = False,
    sop_class_uid: str | None = None,
) -> None:
    ds = base_dataset(modality=modality, with_phi=with_phi)
    if sop_class_uid is not None:
        ds.SOPClassUID = sop_class_uid
        ds.file_meta.MediaStorageSOPClassUID = sop_class_uid

    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.FrameOfReferenceUID = frame_uid
    ds.InstanceNumber = instance_number
    ds.SliceLocation = slice_position

    ds.Rows, ds.Columns = pixels.shape
    ds.PixelSpacing = list(spacing)
    ds.SliceThickness = thickness
    ds.ImagePositionPatient = [0.0, 0.0, slice_position]
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = -1024.0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1

    if burned_in is not None:
        ds.BurnedInAnnotation = burned_in

    if private_tags:
        # Vendors habitually stash identifiers in private blocks; the
        # de-identifier must strip the whole odd-group space.
        block = ds.private_block(0x0009, "MIVW SYNTHETIC", create=True)
        block.add_new(0x01, "LO", "FAKE-PRIVATE-IDENTIFIER")
        block.add_new(0x02, "LO", FAKE_IDENTIFIERS["PatientID"])

    ds.PixelData = (pixels.astype(np.int16) + 1024).tobytes()

    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(path, enforce_file_format=True)


def generate(output: Path) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}

    study_uid, series_uid, frame_uid = generate_uid(), generate_uid(), generate_uid()
    volume = shepp_logan((16, 128, 128))

    write_slice(
        output / "synthetic_ct_with_phi.dcm",
        volume[0],
        study_uid=study_uid,
        series_uid=series_uid,
        frame_uid=frame_uid,
        instance_number=1,
        slice_position=0.0,
        spacing=(1.0, 1.0),
        thickness=1.0,
        with_phi=True,
    )
    write_slice(
        output / "synthetic_ct_private_tags.dcm",
        volume[0],
        study_uid=study_uid,
        series_uid=series_uid,
        frame_uid=frame_uid,
        instance_number=1,
        slice_position=0.0,
        spacing=(1.0, 1.0),
        thickness=1.0,
        with_phi=True,
        private_tags=True,
    )

    for i in (1, 2):
        write_slice(
            output / f"synthetic_ct_slice_{i:03d}.dcm",
            volume[i],
            study_uid=study_uid,
            series_uid=series_uid,
            frame_uid=frame_uid,
            instance_number=i,
            slice_position=float(i),
            spacing=(1.0, 1.0),
            thickness=1.0,
            with_phi=True,
        )

    write_slice(
        output / "synthetic_us_burned_in.dcm",
        sphere((1, 128, 128))[0],
        study_uid=generate_uid(),
        series_uid=generate_uid(),
        frame_uid=generate_uid(),
        instance_number=1,
        slice_position=0.0,
        spacing=(0.3, 0.3),
        thickness=1.0,
        modality="US",
        with_phi=True,
        burned_in="YES",
    )
    write_slice(
        output / "synthetic_xa_no_burnin_flag.dcm",
        sphere((1, 128, 128))[0],
        study_uid=generate_uid(),
        series_uid=generate_uid(),
        frame_uid=generate_uid(),
        instance_number=1,
        slice_position=0.0,
        spacing=(0.3, 0.3),
        thickness=1.0,
        modality="XA",
        with_phi=True,
    )

    write_slice(
        # RT Structure Set Storage: not a SOP class this workstation reconstructs.
        output / "synthetic_unsupported_sop.dcm",
        sphere((1, 128, 128))[0],
        study_uid=generate_uid(),
        series_uid=generate_uid(),
        frame_uid=generate_uid(),
        instance_number=1,
        slice_position=0.0,
        spacing=(1.0, 1.0),
        thickness=1.0,
        modality="OT",
        with_phi=True,
        sop_class_uid="1.2.840.10008.5.1.4.1.1.481.3",
    )

    for path in sorted(output.glob("*.dcm")):
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify(output: Path) -> int:
    """CI guard: every .dcm present must be one we generated."""
    manifest_path = output / "MANIFEST.json"
    if not manifest_path.exists():
        print("MANIFEST.json missing; run without --verify to generate fixtures")
        return 1

    manifest = json.loads(manifest_path.read_text())
    failures = 0
    for path in sorted(output.glob("*.dcm")):
        if path.name not in manifest:
            print(f"UNKNOWN FIXTURE: {path.name} was not produced by this generator")
            failures += 1
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != manifest[path.name]:
            print(f"MODIFIED FIXTURE: {path.name}")
            failures += 1

    ds_tagged = 0
    for path in sorted(output.glob("*.dcm")):
        ds = pydicom.dcmread(path, stop_before_pixels=True)
        if getattr(ds, "ImageComments", "") == GENERATOR_TAG:
            ds_tagged += 1
        else:
            print(f"UNTAGGED FIXTURE: {path.name}")
            failures += 1

    print(f"verified {ds_tagged} synthetic fixture(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        return verify(args.output)

    manifest = generate(args.output)
    print(f"generated {len(manifest)} synthetic fixture(s) in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
