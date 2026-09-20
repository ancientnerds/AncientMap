-- 0017_migration_selftest.sql
--
-- Functional test for migrations/0017_remediation_change_log.sql.
--
-- Run against a SCRATCH database, never production. It creates a minimal stand-in for
-- unified_sites (the only columns apply_remediation_change touches are the id and the
-- column being changed) and exercises the safety properties the journal is supposed to
-- have. Any failure raises, and the caller runs this with ON_ERROR_STOP=1, so a broken
-- safety primitive stops the run instead of quietly permitting unjournalled writes.
--
-- Usage (on the VPS, with the file already inside the container):
--   docker exec -i ancient_nerds_db psql -U ancient_map -d <scratch> -v ON_ERROR_STOP=1 -f /tmp/x.sql

\set ON_ERROR_STOP on
\pset pager off

\echo '--- setup'
DROP TABLE IF EXISTS unified_sites;
CREATE TABLE unified_sites (id UUID PRIMARY KEY, country TEXT);

INSERT INTO unified_sites (id, country) VALUES
  ('00000000-0000-0000-0000-000000000001', 'Georgia (country)'),
  ('00000000-0000-0000-0000-000000000002', NULL),
  ('00000000-0000-0000-0000-000000000003', 'Baltic Sea');

DELETE FROM remediation_change_log;

-- ------------------------------------------------------------------ 1. the happy path
\echo '--- T1 a matched change writes the value AND journals it'
SELECT apply_remediation_change(
  'unified_sites', 'country', 'id', '00000000-0000-0000-0000-000000000001',
  'Georgia (country)', 'Georgia', 'T05/country-disambiguation', 'selftest',
  'key-disambig', 'authoritative', '[{"source":"test"}]'::jsonb,
  '00000000-0000-0000-0000-000000000001');

DO $$
BEGIN
  IF (SELECT country FROM unified_sites WHERE id='00000000-0000-0000-0000-000000000001') <> 'Georgia' THEN
    RAISE EXCEPTION 'T1 FAIL: the value was not changed';
  END IF;
  IF (SELECT count(*) FROM remediation_change_log WHERE change_key='key-disambig') <> 1 THEN
    RAISE EXCEPTION 'T1 FAIL: no journal row was written';
  END IF;
  IF (SELECT old_value FROM remediation_change_log WHERE change_key='key-disambig') <> 'Georgia (country)' THEN
    RAISE EXCEPTION 'T1 FAIL: old_value is not the value that was replaced, so the change is not reversible';
  END IF;
  RAISE NOTICE 'T1 PASS';
END $$;

-- ------------------------------------------------- 2. NULL is a value, not "no match"
-- This is the case a naive `WHERE col = :old` silently fails: `col = NULL` is never true,
-- so correcting a field that is currently empty would match zero rows. IS NOT DISTINCT FROM
-- is what makes it work, and this test is what keeps it that way.
\echo '--- T2 correcting a NULL field works (IS NOT DISTINCT FROM, not =)'
SELECT apply_remediation_change(
  'unified_sites', 'country', 'id', '00000000-0000-0000-0000-000000000002',
  NULL, 'Chile', 'T05/country-compound', 'selftest',
  'key-nullfill', 'authoritative', '[]'::jsonb,
  '00000000-0000-0000-0000-000000000002');

DO $$
BEGIN
  IF (SELECT country FROM unified_sites WHERE id='00000000-0000-0000-0000-000000000002') IS DISTINCT FROM 'Chile' THEN
    RAISE EXCEPTION 'T2 FAIL: a NULL field could not be corrected';
  END IF;
  IF (SELECT count(*) FROM remediation_change_log WHERE change_key='key-nullfill') <> 1 THEN
    RAISE EXCEPTION 'T2 FAIL: the NULL correction was not journalled';
  END IF;
  RAISE NOTICE 'T2 PASS';
END $$;

-- --------------------------------------------- 3. a stale old value must abort, not guess
-- If the row no longer holds the value our Finding was based on, the data moved underneath
-- us. Writing anyway would apply a correction to something nobody reviewed.
\echo '--- T3 a stale old value raises and writes nothing'
DO $$
DECLARE
  before_n INTEGER;
  before_v TEXT;
BEGIN
  SELECT count(*) INTO before_n FROM remediation_change_log;
  SELECT country INTO before_v FROM unified_sites WHERE id='00000000-0000-0000-0000-000000000003';

  BEGIN
    PERFORM apply_remediation_change(
      'unified_sites', 'country', 'id', '00000000-0000-0000-0000-000000000003',
      'France', 'Chile', 'T05/stale', 'selftest', 'key-stale', 'authoritative',
      '[]'::jsonb, '00000000-0000-0000-0000-000000000003');
    RAISE EXCEPTION 'T3 FAIL: a stale old value was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM LIKE 'T3 FAIL%' THEN RAISE; END IF;   -- our own failure, propagate
      IF SQLERRM NOT LIKE '%expected 1 row%' THEN
        RAISE EXCEPTION 'T3 FAIL: raised, but for the wrong reason: %', SQLERRM;
      END IF;
  END;

  IF (SELECT country FROM unified_sites WHERE id='00000000-0000-0000-0000-000000000003')
       IS DISTINCT FROM before_v THEN
    RAISE EXCEPTION 'T3 FAIL: the value changed despite the mismatch';
  END IF;
  IF (SELECT count(*) FROM remediation_change_log) <> before_n THEN
    RAISE EXCEPTION 'T3 FAIL: a journal row was written for a change that did not happen';
  END IF;
  RAISE NOTICE 'T3 PASS';
END $$;

-- ------------------------------------------------- 4. a missing row is not a silent no-op
\echo '--- T4 an unknown row raises'
DO $$
BEGIN
  BEGIN
    PERFORM apply_remediation_change(
      'unified_sites', 'country', 'id', '00000000-0000-0000-0000-0000000000ff',
      'Georgia', 'X', 'T05', 'selftest', 'key-ghost', 'authoritative', '[]'::jsonb, NULL);
    RAISE EXCEPTION 'T4 FAIL: a non-existent row was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM LIKE 'T4 FAIL%' THEN RAISE; END IF;
      IF SQLERRM NOT LIKE '%expected 1 row%' THEN
        RAISE EXCEPTION 'T4 FAIL: raised for the wrong reason: %', SQLERRM;
      END IF;
  END;
  RAISE NOTICE 'T4 PASS';
END $$;

-- ------------------------------------------------- 5. the table allowlist is a real gate
\echo '--- T5 a table outside the allowlist is refused'
DO $$
BEGIN
  BEGIN
    PERFORM apply_remediation_change(
      'applied_migrations', 'filename', 'filename', 'x', 'x', 'y',
      'T00', 'selftest', 'key-bad-table', 'authoritative', '[]'::jsonb, NULL);
    RAISE EXCEPTION 'T5 FAIL: a table outside the allowlist was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM LIKE 'T5 FAIL%' THEN RAISE; END IF;
      IF SQLERRM NOT LIKE '%not a remediation target%' THEN
        RAISE EXCEPTION 'T5 FAIL: raised for the wrong reason: %', SQLERRM;
      END IF;
  END;
  RAISE NOTICE 'T5 PASS';
END $$;

-- ---------------------------------------------------- 6. a run stamp is mandatory
\echo '--- T6 an empty run stamp is refused'
DO $$
BEGIN
  BEGIN
    PERFORM apply_remediation_change(
      'unified_sites', 'country', 'id', '00000000-0000-0000-0000-000000000001',
      'Georgia', 'Z', 'T05', '', 'key-nostamp', 'authoritative', '[]'::jsonb, NULL);
    RAISE EXCEPTION 'T6 FAIL: an empty run_stamp was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM LIKE 'T6 FAIL%' THEN RAISE; END IF;
      IF SQLERRM NOT LIKE '%p_run_stamp is required%' THEN
        RAISE EXCEPTION 'T6 FAIL: raised for the wrong reason: %', SQLERRM;
      END IF;
  END;
  RAISE NOTICE 'T6 PASS';
END $$;

-- --------------------------------------------------------- 7. clearing is expressible
\echo '--- T7 p_new = NULL clears the field and records the old value'
SELECT apply_remediation_change(
  'unified_sites', 'country', 'id', '00000000-0000-0000-0000-000000000003',
  'Baltic Sea', NULL, 'T05/non-country', 'selftest', 'key-clear', 'unverifiable',
  '[{"source":"review"}]'::jsonb, '00000000-0000-0000-0000-000000000003');

DO $$
BEGIN
  IF (SELECT country FROM unified_sites WHERE id='00000000-0000-0000-0000-000000000003') IS NOT NULL THEN
    RAISE EXCEPTION 'T7 FAIL: the field was not cleared';
  END IF;
  IF (SELECT old_value FROM remediation_change_log WHERE change_key='key-clear') <> 'Baltic Sea' THEN
    RAISE EXCEPTION 'T7 FAIL: clearing did not record what it replaced';
  END IF;
  RAISE NOTICE 'T7 PASS';
END $$;

-- ------------------------------------------------------------------ 8. the view is usable
\echo '--- T8 remediation_change_history exposes the previous value'
SELECT count(*) AS history_rows,
       count(*) FILTER (WHERE test_id = 'T05/country-disambiguation') AS t1_rows
FROM remediation_change_history;

\echo '--- ALL 0017 SELFTESTS PASSED'
