-- 0007_annotations_jobs.sql

CREATE TABLE annotation (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    series_id               uuid NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    author_id               uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
    kind                    annotation_kind NOT NULL,

    -- Geometry is stored in patient coordinates (mm) against an explicit frame of
    -- reference, so annotations survive resampling and reorientation. Pixel-index
    -- geometry is rejected at the API boundary.
    frame_of_reference_uid  text,
    payload                 jsonb NOT NULL,

    label                   text,
    deleted_at              timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT annotation_payload_units CHECK (payload ->> 'units' = 'mm')
);

CREATE INDEX annotation_series_idx ON annotation (series_id) WHERE deleted_at IS NULL;
CREATE INDEX annotation_payload_idx ON annotation USING GIN (payload jsonb_path_ops);

CREATE TRIGGER annotation_touch BEFORE UPDATE ON annotation
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TABLE job (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    kind            job_kind NOT NULL,
    status          job_status NOT NULL DEFAULT 'queued',
    progress        double precision NOT NULL DEFAULT 0
                        CHECK (progress BETWEEN 0 AND 1),
    stage           text,
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
    error           jsonb,
    attempts        smallint NOT NULL DEFAULT 0,
    max_attempts    smallint NOT NULL DEFAULT 3,
    idempotency_key text,
    submitted_by    uuid REFERENCES app_user(id),
    claimed_at      timestamptz,
    finished_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),

    UNIQUE (org_id, idempotency_key)
);

-- Partial index: the queue is small even when the table is large.
CREATE INDEX job_queue_idx ON job (kind, created_at)
    WHERE status IN ('queued', 'running');

-- Workers claim with SELECT ... FOR UPDATE SKIP LOCKED so a job is never
-- processed twice, even with many concurrent workers.
