-- 0004_dicom_hierarchy.sql
-- Patient / Study / Series / Instance. All UIDs stored here are PSEUDONYMISED;
-- the mapping to originals lives encrypted in deid_map (0005).

CREATE TABLE patient (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,

    -- Stable, non-reversible display identifier shown in the UI.
    pseudonym   text NOT NULL,

    -- Direct identifiers, encrypted with pgp_sym_encrypt. The key lives outside
    -- the database, so a dump alone does not disclose PHI.
    mrn_enc     bytea,
    name_enc    bytea,
    key_id      text NOT NULL,

    -- Keyed HMAC of the MRN. Enables exact-match lookup without decryption and
    -- without the frequency leakage of deterministic encryption.
    mrn_hmac    bytea,

    -- Full DOB is a direct identifier under HIPAA Safe Harbor; store the year only.
    birth_year  smallint CHECK (birth_year BETWEEN 1900 AND 2200),
    sex         text CHECK (sex IN ('M', 'F', 'O', 'U')),

    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    UNIQUE (org_id, pseudonym)
);

CREATE INDEX patient_mrn_hmac_idx ON patient (org_id, mrn_hmac) WHERE mrn_hmac IS NOT NULL;

CREATE TABLE study (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    patient_id          uuid NOT NULL REFERENCES patient(id) ON DELETE CASCADE,
    study_uid           text NOT NULL,          -- pseudonymised
    study_datetime      timestamptz,            -- date-shifted, consistent per patient
    accession_pseudonym text,
    description         text,
    modalities          text[] NOT NULL DEFAULT '{}',
    deleted_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    UNIQUE (org_id, study_uid)
);

-- org_id leads so the index also serves the RLS predicate.
CREATE INDEX study_worklist_idx ON study (org_id, study_datetime DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE series (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    study_id            uuid NOT NULL REFERENCES study(id) ON DELETE CASCADE,
    series_uid          text NOT NULL,          -- pseudonymised
    frame_of_reference_uid text,                -- pseudonymised; anchors annotations
    series_number       integer,
    modality            text NOT NULL,
    description         text,

    -- Geometry required by the renderer.
    rows                integer NOT NULL CHECK (rows > 0),
    columns             integer NOT NULL CHECK (columns > 0),
    slice_count         integer NOT NULL CHECK (slice_count > 0),
    pixel_spacing_mm    double precision[2] NOT NULL,
    slice_thickness_mm  double precision,
    image_orientation   double precision[6],    -- direction cosines
    image_position      double precision[3],    -- first slice, patient coords
    rescale_slope       double precision NOT NULL DEFAULT 1.0,
    rescale_intercept   double precision NOT NULL DEFAULT 0.0,

    -- Burned-in text is PHI that header scrubbing cannot remove. Series flagged
    -- here are quarantined until a human reviews them.
    burned_in_annotation boolean,
    is_quarantined      boolean NOT NULL DEFAULT false,

    created_at          timestamptz NOT NULL DEFAULT now(),

    UNIQUE (org_id, series_uid)
);

CREATE INDEX series_study_idx ON series (study_id, series_number);

CREATE TABLE instance (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    series_id       uuid NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    sop_instance_uid text NOT NULL,             -- pseudonymised
    instance_number integer,
    slice_location  double precision,
    object_key      text NOT NULL,
    content_sha256  bytea NOT NULL,

    UNIQUE (org_id, sop_instance_uid)
);

CREATE INDEX instance_series_idx ON instance (series_id, instance_number);

CREATE TRIGGER patient_touch BEFORE UPDATE ON patient
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER study_touch BEFORE UPDATE ON study
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
