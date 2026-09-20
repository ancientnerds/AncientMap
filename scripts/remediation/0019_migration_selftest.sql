-- 0019_migration_selftest.sql
--
-- End-to-end test of migration 0019 (wiki_images.image_kind) against the live database.
-- Everything that writes runs inside BEGIN ... ROLLBACK, so running this file changes nothing.
--
-- Why this file exists: 0017 shipped with a self-test that only exercised a TEXT column, and
-- the gap let a real defect through - apply_remediation_change() could not touch a boolean
-- column at all (fixed in 0018). The lesson taken was to test the shape of the thing, not just
-- one happy path. So this file checks the vocabulary in BOTH directions: every legal value must
-- be accepted, and an illegal value must be REFUSED. The second half is the part that can fail;
-- without it, a missing constraint would pass silently.
--
-- Usage (from the workstation):
--   ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" \
--       < scripts/remediation/0019_migration_selftest.sql
-- Note: `docker exec` needs -i, or stdin is empty and psql sees nothing.

\set ON_ERROR_STOP on

BEGIN;

CREATE TEMP TABLE _st (name TEXT, ok BOOLEAN) ON COMMIT DROP;

-- C1: the column exists, is TEXT, and is nullable.
INSERT INTO _st
SELECT 'C1 column exists, type text, nullable',
       EXISTS (
           SELECT 1 FROM information_schema.columns
            WHERE table_name = 'wiki_images'
              AND column_name = 'image_kind'
              AND data_type = 'text'
              AND is_nullable = 'YES'
       );

-- C2: the constraint exists and carries the intended name. Without this, the write tests below
-- could pass because some other constraint happened to reject the bad value.
INSERT INTO _st
SELECT 'C2 constraint wiki_images_image_kind_vocab exists',
       EXISTS (
           SELECT 1 FROM pg_constraint
            WHERE conrelid = 'wiki_images'::regclass
              AND conname  = 'wiki_images_image_kind_vocab'
              AND contype  = 'c'
       );

-- C3: NULL does not equal 'unknown'. This is the semantic the column depends on: NULL means
-- "never judged" and 'unknown' means "judged, undecidable". If these collapsed, the 49,691
-- unjudged rows would silently read as judged.
INSERT INTO _st
SELECT 'C3 NULL is distinct from unknown', (NULL::text IS DISTINCT FROM 'unknown');

DO $$
DECLARE
    v_id      BIGINT;
    v_site    UUID;
    v_kind    TEXT;
    v_ok      BOOLEAN;
    v_refused BOOLEAN;
    v_stored  TEXT;
    v_journal INT;
BEGIN
    SELECT id, site_id INTO v_id, v_site FROM wiki_images ORDER BY id LIMIT 1;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'SELFTEST FAILED: wiki_images is empty, nothing to test against';
    END IF;

    -- C4: every vocabulary value is accepted on a real row.
    FOREACH v_kind IN ARRAY ARRAY[
        'site_photo', 'artifact', 'map_or_document', 'painting_or_artwork',
        'people', 'other', 'unknown'
    ] LOOP
        v_ok := TRUE;
        BEGIN
            UPDATE wiki_images SET image_kind = v_kind WHERE id = v_id;
        EXCEPTION
            WHEN check_violation THEN v_ok := FALSE;
        END;
        INSERT INTO _st VALUES ('C4 accepts ' || v_kind, v_ok);
    END LOOP;

    -- C5: an out-of-vocabulary value is REFUSED. This is the case with teeth: if the CHECK
    -- constraint were absent or misspelled, v_refused would be FALSE and this row fails.
    v_refused := FALSE;
    BEGIN
        UPDATE wiki_images SET image_kind = 'site_photos' WHERE id = v_id;
    EXCEPTION
        WHEN check_violation THEN v_refused := TRUE;
    END;
    INSERT INTO _st VALUES ('C5 refuses a typo (site_photos)', v_refused);

    -- C6: NULL is still storable, so un-judged rows remain representable.
    v_ok := TRUE;
    BEGIN
        UPDATE wiki_images SET image_kind = NULL WHERE id = v_id;
    EXCEPTION
        WHEN others THEN v_ok := FALSE;
    END;
    INSERT INTO _st VALUES ('C6 NULL is storable', v_ok);

    -- C7: the whole point of the migration - a vision verdict can be written through the
    -- journalled primitive, and it lands both on the row and in the journal.
    PERFORM apply_remediation_change(
        'wiki_images', 'image_kind', 'id', v_id::text,
        NULL, 'map_or_document', 'T19/selftest', '2026-09-21_selftest',
        'selftest-0019-' || gen_random_uuid()::text, 'authoritative',
        '[{"src":"selftest:0019"}]'::jsonb, v_site
    );
    SELECT image_kind INTO v_stored FROM wiki_images WHERE id = v_id;
    SELECT count(*) INTO v_journal FROM remediation_change_log
     WHERE table_name = 'wiki_images' AND column_name = 'image_kind'
       AND row_pk = v_id::text AND new_value = 'map_or_document';
    INSERT INTO _st VALUES ('C7 row updated to map_or_document', v_stored = 'map_or_document');
    INSERT INTO _st VALUES ('C8 journal recorded the same change', v_journal = 1);

    -- C9: the primitive must have recorded the OLD value as NULL, not the string 'NULL' -
    -- otherwise a reversal would write the literal text into the column.
    SELECT count(*) INTO v_journal FROM remediation_change_log
     WHERE table_name = 'wiki_images' AND column_name = 'image_kind'
       AND row_pk = v_id::text AND old_value IS NULL;
    INSERT INTO _st VALUES ('C9 old_value is NULL, not the text NULL', v_journal = 1);
END
$$;

-- Report before rolling back, so a failure is visible with its name.
SELECT name, ok FROM _st ORDER BY name;
SELECT 'selftest done: '
       || count(*) FILTER (WHERE ok) || ' ok, '
       || count(*) FILTER (WHERE NOT ok) || ' failed' AS summary
  FROM _st;

DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM _st WHERE NOT ok;
    IF n > 0 THEN
        RAISE EXCEPTION 'SELFTEST FAILED: % case(s) - see the table above', n;
    END IF;
END
$$;

ROLLBACK;

-- Post-rollback proof, outside the transaction: nothing of the above survived.
-- The journal total is compared against the value recorded immediately before this file ran,
-- not against a hardcoded number - HERO contributed 5,438 rows and wave 4's MECHANICAL lane
-- added 35, so any literal here would rot.
SELECT 'change_log rows total (must be unchanged by this test)' AS check,
       count(*)::text AS value
  FROM remediation_change_log
UNION ALL
SELECT 'image_kind non-NULL rows (must be 0)',
       count(*)::text FROM wiki_images WHERE image_kind IS NOT NULL
UNION ALL
SELECT 'journal rows for image_kind (must be 0)',
       count(*)::text FROM remediation_change_log WHERE column_name = 'image_kind';
