-- 0009_rls_policies.sql
-- Row-Level Security is the authorisation boundary. API-layer role checks exist
-- for good error messages; this is what actually holds if that layer has a bug.
--
-- FORCE is essential: without it the table owner bypasses its own policies.

DO $$
DECLARE
    t text;
    tenant_tables text[] := ARRAY[
        'patient', 'study', 'series', 'instance', 'volume_asset',
        'model', 'inference_run', 'segmentation', 'annotation', 'job', 'app_user'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);

        -- Fails closed: mivw_current_org() returns NULL when context is unset,
        -- and NULL = NULL is not true, so no rows are visible.
        EXECUTE format($p$
            CREATE POLICY %1$I_tenant_read ON %1$I
                FOR SELECT USING (org_id = mivw_current_org())
        $p$, t);

        EXECUTE format($p$
            CREATE POLICY %1$I_tenant_write ON %1$I
                FOR INSERT WITH CHECK (org_id = mivw_current_org())
        $p$, t);

        EXECUTE format($p$
            CREATE POLICY %1$I_tenant_update ON %1$I
                FOR UPDATE USING (org_id = mivw_current_org())
                          WITH CHECK (org_id = mivw_current_org())
        $p$, t);

        EXECUTE format($p$
            CREATE POLICY %1$I_tenant_delete ON %1$I
                FOR DELETE USING (org_id = mivw_current_org())
        $p$, t);
    END LOOP;
END
$$;

-- Annotations: authors may modify their own; admins may modify any within the tenant.
DROP POLICY annotation_tenant_update ON annotation;
CREATE POLICY annotation_author_or_admin_update ON annotation
    FOR UPDATE
    USING (org_id = mivw_current_org()
           AND (author_id = mivw_current_user_id() OR mivw_current_role() = 'admin'))
    WITH CHECK (org_id = mivw_current_org());

DROP POLICY annotation_tenant_write ON annotation;
CREATE POLICY annotation_write_requires_role ON annotation
    FOR INSERT WITH CHECK (
        org_id = mivw_current_org()
        AND author_id = mivw_current_user_id()
        AND mivw_current_role() IN ('annotator', 'researcher', 'admin')
    );

-- Model registry is administrative.
DROP POLICY model_tenant_write ON model;
CREATE POLICY model_admin_write ON model
    FOR INSERT WITH CHECK (
        org_id = mivw_current_org() AND mivw_current_role() = 'admin'
    );

-- deid_map is reachable only by the dedicated re-identification role. The
-- application never assumes this role.
ALTER TABLE deid_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE deid_map FORCE ROW LEVEL SECURITY;
REVOKE ALL ON deid_map FROM mivw_app, mivw_readonly;
GRANT INSERT ON deid_map TO mivw_ingest;
GRANT SELECT ON deid_map TO mivw_reidentify;

CREATE POLICY deid_map_reidentify_only ON deid_map
    FOR SELECT TO mivw_reidentify
    USING (org_id = mivw_current_org());

CREATE POLICY deid_map_ingest_insert ON deid_map
    FOR INSERT TO mivw_ingest
    WITH CHECK (org_id = mivw_current_org());

-- Session context is established per transaction with SET LOCAL, never SET:
--     SET LOCAL mivw.org_id  = '...';
--     SET LOCAL mivw.user_id = '...';
--     SET LOCAL mivw.role    = '...';
-- SET LOCAL dies with the transaction and therefore cannot leak to the next
-- borrower of a pooled connection.
