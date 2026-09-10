-- 0005_volume_assets.sql
-- Resampled volumes (pointer only; bytes live in the object store) and the
-- encrypted de-identification mapping.

CREATE TABLE volume_asset (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    series_id       uuid NOT NULL UNIQUE REFERENCES series(id) ON DELETE CASCADE,

    object_key      text NOT NULL,
    content_sha256  bytea NOT NULL,             -- integrity check on every read
    size_bytes      bigint NOT NULL CHECK (size_bytes > 0),

    dims            integer[3] NOT NULL,
    spacing_mm      double precision[3] NOT NULL,
    origin_mm       double precision[3] NOT NULL,
    direction       double precision[9] NOT NULL,
    dtype           text NOT NULL CHECK (dtype IN ('int16', 'uint16', 'float32')),
    compression     text NOT NULL DEFAULT 'zstd',

    value_min       double precision,
    value_max       double precision,

    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX volume_asset_hash_idx ON volume_asset (content_sha256);

-- Mapping from pseudonyms back to original identifiers.
--
-- Readable only by mivw_reidentify (granted in 0009). Deleting a row here makes
-- the retained imaging data irreversibly anonymous, which is how GDPR Art. 17
-- erasure is satisfied without destroying research datasets.
CREATE TABLE deid_map (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    pseudonym       text NOT NULL,
    original_enc    bytea NOT NULL,
    entity_kind     text NOT NULL CHECK (entity_kind IN
                        ('patient', 'study_uid', 'series_uid', 'sop_uid',
                         'frame_of_reference_uid', 'accession')),
    key_id          text NOT NULL,
    date_shift_days integer,                    -- consistent per patient
    created_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (org_id, entity_kind, pseudonym)
);
