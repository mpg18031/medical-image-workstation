-- db/tests/030_rls_isolation.sql
-- Verifies that Row-Level Security actually isolates tenants, including across a
-- reused pooled connection. Run with pg_prove or the pytest wrapper.

BEGIN;
SELECT plan(9);

-- Schema-level assertions -----------------------------------------------------
SELECT ok(
    (SELECT bool_and(relrowsecurity AND relforcerowsecurity)
     FROM pg_class
     WHERE relname IN ('patient', 'study', 'series', 'volume_asset', 'annotation')),
    'PHI tables have RLS both ENABLED and FORCED'
);

SELECT ok(
    NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'mivw_app'),
    'mivw_app cannot bypass RLS'
);

-- Fixtures --------------------------------------------------------------------
INSERT INTO organisation (id, name, slug) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Org A', 'org-a'),
    ('22222222-2222-2222-2222-222222222222', 'Org B', 'org-b');

INSERT INTO patient (id, org_id, pseudonym, key_id) VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001',
     '11111111-1111-1111-1111-111111111111', 'PT-A-001', 'test-key'),
    ('bbbbbbbb-0000-0000-0000-000000000001',
     '22222222-2222-2222-2222-222222222222', 'PT-B-001', 'test-key');

INSERT INTO study (id, org_id, patient_id, study_uid) VALUES
    ('aaaaaaaa-0000-0000-0000-000000000010',
     '11111111-1111-1111-1111-111111111111',
     'aaaaaaaa-0000-0000-0000-000000000001', '1.2.826.0.1.A'),
    ('bbbbbbbb-0000-0000-0000-000000000010',
     '22222222-2222-2222-2222-222222222222',
     'bbbbbbbb-0000-0000-0000-000000000001', '1.2.826.0.1.B');

-- Tenant A --------------------------------------------------------------------
SET LOCAL ROLE mivw_app;
SET LOCAL mivw.org_id = '11111111-1111-1111-1111-111111111111';

SELECT is((SELECT count(*) FROM study), 1::bigint,
          'tenant A sees exactly its own study');

SELECT is((SELECT count(*) FROM study
           WHERE id = 'bbbbbbbb-0000-0000-0000-000000000010'), 0::bigint,
          'direct lookup of tenant B study returns zero rows');

SELECT is((SELECT count(*) FROM patient), 1::bigint,
          'patient table is isolated');

-- Simulating a pooled connection handed to another tenant ---------------------
SET LOCAL mivw.org_id = '22222222-2222-2222-2222-222222222222';

SELECT is((SELECT count(*) FROM study
           WHERE id = 'aaaaaaaa-0000-0000-0000-000000000010'), 0::bigint,
          'context switch does not leak tenant A rows to tenant B');

-- Fail closed when context is missing entirely --------------------------------
RESET mivw.org_id;

SELECT is((SELECT count(*) FROM study), 0::bigint,
          'missing session context yields zero rows, not all rows');

-- Cross-tenant write must be rejected -----------------------------------------
SET LOCAL mivw.org_id = '11111111-1111-1111-1111-111111111111';

SELECT throws_ok(
    $$ INSERT INTO patient (org_id, pseudonym, key_id)
       VALUES ('22222222-2222-2222-2222-222222222222', 'PT-X', 'k') $$,
    '42501',
    NULL,
    'insert into another tenant is rejected by WITH CHECK'
);

-- Audit immutability -----------------------------------------------------------
RESET ROLE;
INSERT INTO audit_log (org_id, action, outcome)
VALUES ('11111111-1111-1111-1111-111111111111', 'test.write', 'success');

SELECT throws_ok(
    $$ DELETE FROM audit_log WHERE action = 'test.write' $$,
    NULL, NULL,
    'audit_log rejects deletion even for the owner'
);

SELECT * FROM finish();
ROLLBACK;
