-- 0010_service_role.sql
-- Login role the application connects as.
--
-- mivw_app (0002_roles.sql) is NOLOGIN by design: nothing should be able to
-- connect directly as the RLS-bound role and skip the SET ROLE step that
-- makes db.py's tenant/system transactions actually subject to RLS. This
-- login role exists only to authenticate; it is granted mivw_app membership
-- so `SET ROLE mivw_app` succeeds, but has no privileges of its own beyond
-- what that grant provides. Its password is set out-of-band and is never
-- committed here.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mivw_service') THEN
        CREATE ROLE mivw_service LOGIN NOBYPASSRLS;
    END IF;
END
$$;

GRANT mivw_app TO mivw_service;
