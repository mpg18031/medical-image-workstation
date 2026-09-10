-- 0006_models_inference.sql
-- Pluggable ONNX model registry and inference provenance.

CREATE TABLE model (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    name            text NOT NULL,
    version         text NOT NULL,

    artifact_key    text NOT NULL,
    -- Verified before every load. Prevents artefact substitution.
    artifact_sha256 bytea NOT NULL,

    output_kind     model_output_kind NOT NULL,

    -- Declared input contract. A volume that does not satisfy it is rejected
    -- rather than silently resampled: a plausible-looking wrong result is the
    -- most dangerous failure mode in an imaging tool.
    input_spec      jsonb NOT NULL,
    label_map       jsonb NOT NULL DEFAULT '{}'::jsonb,

    description     text,
    is_enabled      boolean NOT NULL DEFAULT false,
    validated_at    timestamptz,
    created_by      uuid REFERENCES app_user(id),
    created_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (org_id, name, version),

    CONSTRAINT model_input_spec_shape CHECK (
        input_spec ? 'shape' AND input_spec ? 'spacingMm' AND input_spec ? 'orientation'
    ),
    CONSTRAINT model_digest_length CHECK (octet_length(artifact_sha256) = 32)
);

CREATE INDEX model_enabled_idx ON model (org_id, name) WHERE is_enabled;

CREATE TABLE inference_run (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    model_id            uuid NOT NULL REFERENCES model(id) ON DELETE RESTRICT,
    volume_asset_id     uuid NOT NULL REFERENCES volume_asset(id) ON DELETE CASCADE,

    -- Provenance: everything needed to reproduce or defend this result.
    input_sha256        bytea NOT NULL,
    model_sha256        bytea NOT NULL,
    engine_cache_key    text,
    gpu_name            text,
    driver_version      text,
    runtime_version     text,

    status              job_status NOT NULL DEFAULT 'queued',
    started_at          timestamptz,
    finished_at         timestamptz,
    metrics             jsonb NOT NULL DEFAULT '{}'::jsonb,
    error               jsonb,

    requested_by        uuid REFERENCES app_user(id),
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX inference_run_volume_idx ON inference_run (volume_asset_id, created_at DESC);

CREATE TABLE segmentation (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    inference_run_id    uuid NOT NULL REFERENCES inference_run(id) ON DELETE CASCADE,
    object_key          text NOT NULL,
    content_sha256      bytea NOT NULL,
    dims                integer[3] NOT NULL,
    label_stats         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- voxel counts, volumes in mL
    created_at          timestamptz NOT NULL DEFAULT now()
);
