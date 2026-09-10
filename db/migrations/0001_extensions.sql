-- 0001_extensions.sql
-- Extensions required across the schema. Installed by a superuser at provisioning time.

CREATE EXTENSION IF NOT EXISTS pgcrypto;              -- column-level PHI encryption + HMAC
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;    -- query performance visibility

-- Enum types used throughout the schema.
CREATE TYPE mivw_role AS ENUM ('viewer', 'annotator', 'researcher', 'admin');

CREATE TYPE model_output_kind AS ENUM (
    'segmentation', 'classification', 'heatmap', 'landmarks'
);

CREATE TYPE job_kind   AS ENUM ('ingest', 'inference', 'export', 'erasure');
CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'cancelled');
CREATE TYPE annotation_kind AS ENUM ('measurement', 'roi', 'note', 'label_edit');

-- Helper: the current request's tenant, taken from transaction-local session context.
-- Returns NULL when unset so RLS policies fail closed rather than open.
CREATE OR REPLACE FUNCTION mivw_current_org() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('mivw.org_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION mivw_current_user_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('mivw.user_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION mivw_current_role() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('mivw.role', true), '')
$$;
