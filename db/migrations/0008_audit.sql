-- 0008_audit.sql
-- Append-only audit trail. HIPAA 164.312(b) requires a record of PHI *access*,
-- not merely of mutation, so reads are logged too.

CREATE TABLE audit_log (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    org_id          uuid,
    actor_id        uuid,
    actor_subject   text,
    action          text NOT NULL,
    resource_type   text,
    resource_id     uuid,
    outcome         text NOT NULL CHECK (outcome IN ('success', 'denied', 'error')),
    -- Never contains PHI values: IP, user agent, trace id, role, reason codes only.
    context         jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

-- BRIN suits append-only, naturally time-ordered data at a fraction of B-tree cost.
CREATE INDEX audit_log_time_brin ON audit_log USING BRIN (occurred_at);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_id, occurred_at DESC);
CREATE INDEX audit_log_resource_idx ON audit_log (resource_type, resource_id);

-- Bootstrap partitions; scripts/rotate_audit_partitions.py maintains the rest.
CREATE TABLE audit_log_2026_01 PARTITION OF audit_log
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE audit_log_2026_02 PARTITION OF audit_log
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT;

-- Immutability: revoke the privilege *and* block it with a trigger, so a future
-- accidental GRANT does not silently reopen the hole.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM mivw_app, mivw_ingest, mivw_readonly;
GRANT INSERT, SELECT ON audit_log TO mivw_app, mivw_ingest;

CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$;

CREATE TRIGGER audit_log_no_mutation
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();
