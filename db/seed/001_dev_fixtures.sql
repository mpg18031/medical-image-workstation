-- Synthetic development fixtures. Every identifier here is fabricated.
-- No real patient data may ever be added to this file.

INSERT INTO organisation (id, name, slug) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Demo Research Group', 'demo-research'),
    ('22222222-2222-2222-2222-222222222222', 'Second Tenant', 'second-tenant')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    slug = EXCLUDED.slug;

INSERT INTO app_user (id, org_id, subject, email, display_name, role) VALUES
    ('aaaa1111-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111',
     'dev|researcher', 'researcher@example.invalid', 'Dev Researcher', 'researcher'),
    ('aaaa1111-0000-0000-0000-000000000002',
     '11111111-1111-1111-1111-111111111111',
     'dev|admin', 'admin@example.invalid', 'Dev Admin', 'admin'),
    ('aaaa1111-0000-0000-0000-000000000003',
     '11111111-1111-1111-1111-111111111111',
     'dev|viewer', 'viewer@example.invalid', 'Dev Viewer', 'viewer'),
    ('bbbb2222-0000-0000-0000-000000000001',
     '22222222-2222-2222-2222-222222222222',
     'dev|other-tenant', 'other@example.invalid', 'Other Tenant User', 'researcher')
ON CONFLICT (id) DO NOTHING;

INSERT INTO patient (id, org_id, pseudonym, key_id, birth_year, sex) VALUES
    ('cccc3333-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111', 'PHANTOM-001', 'dev-key', 1970, 'O'),
    ('cccc3333-0000-0000-0000-000000000002',
     '11111111-1111-1111-1111-111111111111', 'PHANTOM-ANISOTROPIC', 'dev-key', 1965, 'O'),
    ('cccc3333-0000-0000-0000-000000000003',
     '22222222-2222-2222-2222-222222222222', 'OTHER-TENANT-001', 'dev-key', 1980, 'O'),
    ('cccc3333-0000-0000-0000-000000000004',
     '11111111-1111-1111-1111-111111111111', 'PHANTOM-COLOR', 'dev-key', 1975, 'O')
ON CONFLICT (id) DO NOTHING;

INSERT INTO study (id, org_id, patient_id, study_uid, study_datetime, description, modalities) VALUES
    ('dddd4444-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111',
     'cccc3333-0000-0000-0000-000000000001',
     '1.2.826.0.1.DEV.STUDY.1', '2026-03-14 10:15:00+00',
     'Shepp-Logan phantom, isotropic', ARRAY['CT']),
    ('dddd4444-0000-0000-0000-000000000002',
     '11111111-1111-1111-1111-111111111111',
     'cccc3333-0000-0000-0000-000000000002',
     '1.2.826.0.1.DEV.STUDY.2', '2026-03-15 09:00:00+00',
     'Phantom with clinical anisotropic spacing', ARRAY['CT']),
    ('dddd4444-0000-0000-0000-000000000003',
     '22222222-2222-2222-2222-222222222222',
     'cccc3333-0000-0000-0000-000000000003',
     '1.2.826.0.1.DEV.STUDY.3', '2026-03-16 14:30:00+00',
    'Other tenant study - must never be visible to demo-research', ARRAY['MR']),
    ('dddd4444-0000-0000-0000-000000000004',
    '11111111-1111-1111-1111-111111111111',
    'cccc3333-0000-0000-0000-000000000004',
    '1.2.826.0.1.DEV.STUDY.4', '2026-03-17 11:30:00+00',
    'High-contrast multi-intensity phantom', ARRAY['CT'])
ON CONFLICT (id) DO NOTHING;

-- Isotropic: satisfies the demo model's input spec.
INSERT INTO series (id, org_id, study_id, series_uid, frame_of_reference_uid,
                    series_number, modality, description,
                    rows, columns, slice_count, pixel_spacing_mm, slice_thickness_mm,
                    image_orientation, image_position)
VALUES
    ('eeee5555-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111',
     'dddd4444-0000-0000-0000-000000000001',
     '1.2.826.0.2.DEV.SERIES.1', '1.2.826.0.3.DEV.FOR.1',
     1, 'CT', 'Axial 1mm isotropic',
     256, 256, 128, ARRAY[1.0, 1.0], 1.0,
     ARRAY[1.0, 0.0, 0.0, 0.0, 1.0, 0.0], ARRAY[-128.0, -128.0, 0.0]),

    -- Anisotropic: exercises the spec-mismatch rejection path in E2E.
    ('eeee5555-0000-0000-0000-000000000002',
     '11111111-1111-1111-1111-111111111111',
     'dddd4444-0000-0000-0000-000000000002',
     '1.2.826.0.2.DEV.SERIES.2', '1.2.826.0.3.DEV.FOR.2',
     1, 'CT', 'Axial 0.7x0.7x3.0mm',
     512, 512, 120, ARRAY[0.7, 0.7], 3.0,
    ARRAY[1.0, 0.0, 0.0, 0.0, 1.0, 0.0], ARRAY[-179.2, -179.2, 0.0]),
    ('eeee5555-0000-0000-0000-000000000003',
    '11111111-1111-1111-1111-111111111111',
    'dddd4444-0000-0000-0000-000000000004',
    '1.2.826.0.2.DEV.SERIES.3', '1.2.826.0.3.DEV.FOR.3',
    1, 'CT', 'Axial high-contrast phantom',
    256, 256, 128, ARRAY[1.0, 1.0], 1.0,
    ARRAY[1.0, 0.0, 0.0, 0.0, 1.0, 0.0], ARRAY[-128.0, -128.0, 0.0])
ON CONFLICT (id) DO NOTHING;

-- Synthetic reconstructed-volume metadata lets the desktop E2E journeys open
-- the viewer without requiring a real object-store payload.
INSERT INTO volume_asset (
    id, org_id, series_id, object_key, content_sha256, size_bytes,
    dims, spacing_mm, origin_mm, direction, dtype, value_min, value_max
) VALUES
    ('aaaa7777-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111',
     'eeee5555-0000-0000-0000-000000000001',
     'volumes/phantom-001.raw',
    decode('080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e', 'hex'),
     1, ARRAY[128, 256, 256], ARRAY[1.0, 1.0, 1.0], ARRAY[0.0, 0.0, 0.0],
     ARRAY[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], 'int16', -1000, 1000),
    ('aaaa7777-0000-0000-0000-000000000002',
     '11111111-1111-1111-1111-111111111111',
     'eeee5555-0000-0000-0000-000000000002',
     'volumes/phantom-anisotropic.raw',
    decode('cf5ac69ca412f9b3b1a8b8de27d368c5c05ed4b1b6aa40e6c38d9cbf23711342', 'hex'),
     1, ARRAY[120, 512, 512], ARRAY[0.7, 0.7, 3.0], ARRAY[0.0, 0.0, 0.0],
    ARRAY[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], 'int16', -1000, 1000),
    ('aaaa7777-0000-0000-0000-000000000003',
    '11111111-1111-1111-1111-111111111111',
    'eeee5555-0000-0000-0000-000000000003',
    'volumes/phantom-color.raw',
    decode('bf1bb8481f7e6e27d70b6645f12175bdf5db1733cd54a9f83338349fea560c3b', 'hex'),
    16777216, ARRAY[128, 256, 256], ARRAY[1.0, 1.0, 1.0], ARRAY[0.0, 0.0, 0.0],
    ARRAY[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], 'int16', -1000, 1000)
ON CONFLICT (id) DO UPDATE SET
    object_key = EXCLUDED.object_key,
    content_sha256 = EXCLUDED.content_sha256,
    size_bytes = EXCLUDED.size_bytes,
    dims = EXCLUDED.dims,
    spacing_mm = EXCLUDED.spacing_mm,
    origin_mm = EXCLUDED.origin_mm,
    direction = EXCLUDED.direction,
    dtype = EXCLUDED.dtype,
    value_min = EXCLUDED.value_min,
    value_max = EXCLUDED.value_max;

INSERT INTO model (id, org_id, name, version, artifact_key, artifact_sha256,
                   output_kind, input_spec, label_map, description, is_enabled, created_by)
VALUES (
    'ffff6666-0000-0000-0000-000000000001',
    '11111111-1111-1111-1111-111111111111',
    'liver-seg', '1.4.0',
    'models/liver-seg-1.4.0.onnx',
    decode('9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08', 'hex'),
    'segmentation',
    '{"shape": [1, 1, 128, 128, 128],
      "spacingMm": [1.0, 1.0, 1.0],
      "orientation": "RAS",
      "normalisation": {"kind": "zscore", "clipHu": [-200, 300]}}'::jsonb,
    '{"1": {"name": "liver", "color": "#d94f3d"}}'::jsonb,
    'Demo segmentation model for local development',
    true,
    'aaaa1111-0000-0000-0000-000000000002'
)
ON CONFLICT (id) DO NOTHING;
