-- 0002_roles.sql
-- Least-privilege database roles. None of these may create or alter schema objects,
-- and none has BYPASSRLS.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mivw_app') THEN
        CREATE ROLE mivw_app NOLOGIN NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mivw_readonly') THEN
        CREATE ROLE mivw_readonly NOLOGIN NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mivw_ingest') THEN
        CREATE ROLE mivw_ingest NOLOGIN NOBYPASSRLS;
    END IF;
    -- Re-identification is a separate, deliberately awkward role. The application
    -- never assumes it; use requires an out-of-band, audited action.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mivw_reidentify') THEN
        CREATE ROLE mivw_reidentify NOLOGIN NOBYPASSRLS;
    END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO mivw_app, mivw_readonly, mivw_ingest, mivw_reidentify;

-- No role may create objects in the application schema.
REVOKE CREATE ON SCHEMA public FROM mivw_app, mivw_readonly, mivw_ingest, mivw_reidentify;

-- Default privileges for tables created by later migrations.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mivw_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO mivw_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO mivw_app, mivw_ingest;
