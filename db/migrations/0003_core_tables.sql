-- 0003_core_tables.sql
-- Tenancy and identity.

CREATE TABLE organisation (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organisation(id) ON DELETE RESTRICT,
    -- OIDC subject claim. Authentication is fully delegated: no password material
    -- is ever stored by this application.
    subject     text NOT NULL UNIQUE,
    email       text NOT NULL,
    display_name text NOT NULL,
    role        mivw_role NOT NULL DEFAULT 'viewer',
    is_active   boolean NOT NULL DEFAULT true,
    last_seen_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX app_user_org_idx ON app_user (org_id) WHERE is_active;

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

CREATE TRIGGER organisation_touch BEFORE UPDATE ON organisation
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER app_user_touch BEFORE UPDATE ON app_user
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
