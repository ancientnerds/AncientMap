-- 0018_migration_selftest.sql
--
-- Proves apply_remediation_change() is type-safe and refuses to journal a lie.
--
-- READ-ONLY: every case runs inside one BEGIN; ... ROLLBACK;, so production cannot change
-- even if an assertion is wrong. Run it with
--     docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map < <this file>
-- and read the NOTICE lines; a non-empty "FAILED" count is the failure signal.
--
-- Why it exists: 0017_migration_selftest.sql exercised a TEXT column only, which is exactly
-- how the boolean defect reached production. Every case below is one that file could not see.

BEGIN;

DO $selftest$
DECLARE
    ok        INTEGER := 0;
    failed    INTEGER := 0;
    v_id      TEXT;
    v_other   TEXT;
    v_card    TEXT;
    v_old_text TEXT;
    v_int     INTEGER;
    v_bool    BOOLEAN;
    v_text    TEXT;
    v_journal INTEGER;
    v_long    TEXT := repeat('x', 250);   -- card_stats.card_description is varchar(200)
BEGIN
    -- ---- fixtures, read-only ------------------------------------------------
    SELECT id::text INTO v_id    FROM wiki_images WHERE is_hero IS FALSE LIMIT 1;
    SELECT id::text INTO v_other FROM wiki_images WHERE is_hero IS TRUE  LIMIT 1;

    IF v_id IS NULL OR v_other IS NULL THEN
        RAISE EXCEPTION 'selftest fixture missing: need one hero and one non-hero row';
    END IF;

    -- ---- C1: a BOOLEAN column, the defect 0017 shipped ----------------------
    BEGIN
        PERFORM apply_remediation_change(
            'wiki_images', 'is_hero', 'id', v_id, 'false', 'true',
            'T09/selftest-boolean', 'selftest', 'selftest-c1', 'authoritative',
            NULL::jsonb, NULL::uuid);
        SELECT is_hero INTO v_bool FROM wiki_images WHERE id::text = v_id;
        IF v_bool IS TRUE THEN
            ok := ok + 1;  RAISE NOTICE 'C1 OK   boolean column flips (false -> true)';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C1 FAILED boolean column did not change';
        END IF;
    EXCEPTION WHEN others THEN
        failed := failed + 1; RAISE NOTICE 'C1 FAILED raised: %', SQLERRM;
    END;

    -- ---- C2: the journal row is written in the same transaction -------------
    SELECT count(*) INTO v_journal
      FROM remediation_change_log WHERE change_key = 'selftest-c1';
    IF v_journal = 1 THEN
        ok := ok + 1;  RAISE NOTICE 'C2 OK   journal row written for the change';
    ELSE
        failed := failed + 1; RAISE NOTICE 'C2 FAILED journal rows = % (want 1)', v_journal;
    END IF;

    -- ---- C3: a TEXT column still works (no regression from 0017) ------------
    -- card_stats has no `id` column: its primary key is site_id (uuid). The first draft of
    -- this test assumed `id` and crashed here, which is why the fixture is spelled out.
    SELECT site_id::text, card_description
      INTO v_card, v_old_text
      FROM card_stats WHERE card_description IS NOT NULL LIMIT 1;
    IF v_card IS NOT NULL THEN
        BEGIN
            PERFORM apply_remediation_change(
                'card_stats', 'card_description', 'site_id', v_card, v_old_text, 'selftest text',
                'T03/selftest-text', 'selftest', 'selftest-c3', 'authoritative',
                NULL::jsonb, NULL::uuid);
            SELECT card_description INTO v_text FROM card_stats WHERE site_id::text = v_card;
            IF v_text = 'selftest text' THEN
                ok := ok + 1;  RAISE NOTICE 'C3 OK   text column writes';
            ELSE
                failed := failed + 1; RAISE NOTICE 'C3 FAILED text column holds %', v_text;
            END IF;
        EXCEPTION WHEN others THEN
            failed := failed + 1; RAISE NOTICE 'C3 FAILED raised: %', SQLERRM;
        END;
    ELSE
        RAISE NOTICE 'C3 SKIP no card_stats row with text';
    END IF;

    -- ---- C4: an INTEGER column ---------------------------------------------
    -- thumb_width, not sort_order: sort_order is NOT NULL, so it cannot serve C5 below.
    BEGIN
        PERFORM apply_remediation_change(
            'wiki_images', 'thumb_width', 'id', v_id, NULL, '1234',
            'T09/selftest-int', 'selftest', 'selftest-c4', 'authoritative',
            NULL::jsonb, NULL::uuid);
        SELECT thumb_width INTO v_int FROM wiki_images WHERE id::text = v_id;
        IF v_int = 1234 THEN
            ok := ok + 1;  RAISE NOTICE 'C4 OK   integer column writes';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C4 FAILED integer column holds %', v_int;
        END IF;
    EXCEPTION WHEN others THEN
        failed := failed + 1; RAISE NOTICE 'C4 FAILED raised: %', SQLERRM;
    END;

    -- ---- C5: clearing a column with NULL -----------------------------------
    BEGIN
        PERFORM apply_remediation_change(
            'wiki_images', 'thumb_width', 'id', v_id, '1234', NULL,
            'T09/selftest-null', 'selftest', 'selftest-c5', 'authoritative',
            NULL::jsonb, NULL::uuid);
        SELECT thumb_width INTO v_int FROM wiki_images WHERE id::text = v_id;
        IF v_int IS NULL THEN
            ok := ok + 1;  RAISE NOTICE 'C5 OK   NULL clears the column';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C5 FAILED thumb_width = % after clearing', v_int;
        END IF;
    EXCEPTION WHEN others THEN
        failed := failed + 1; RAISE NOTICE 'C5 FAILED raised: %', SQLERRM;
    END;

    -- ---- C6: the truncation guard - the journal must not lie ---------------
    IF v_card IS NOT NULL THEN
        -- C3 already wrote to this row inside this transaction, so the value it started
        -- with is gone. Re-read before using it as the expected old value.
        SELECT card_description INTO v_old_text FROM card_stats WHERE site_id::text = v_card;
        BEGIN
            PERFORM apply_remediation_change(
                'card_stats', 'card_description', 'site_id', v_card, v_old_text, v_long,
                'T03/selftest-long', 'selftest', 'selftest-c6', 'authoritative',
                NULL::jsonb, NULL::uuid);
            failed := failed + 1;
            RAISE NOTICE 'C6 FAILED a 250-char value into varchar(200) was accepted';
        EXCEPTION WHEN others THEN
            IF SQLERRM LIKE '%stored a different value%' THEN
                ok := ok + 1;  RAISE NOTICE 'C6 OK   truncation refused (journal cannot lie)';
            ELSE
                failed := failed + 1; RAISE NOTICE 'C6 FAILED wrong error: %', SQLERRM;
            END IF;
        END;
    ELSE
        RAISE NOTICE 'C6 SKIP no card_stats fixture';
    END IF;

    -- ---- C7: a wrong old value matches nothing and must raise --------------
    BEGIN
        PERFORM apply_remediation_change(
            'wiki_images', 'is_hero', 'id', v_other, 'false', 'true',
            'T09/selftest-wrongold', 'selftest', 'selftest-c7', 'authoritative',
            NULL::jsonb, NULL::uuid);
        failed := failed + 1; RAISE NOTICE 'C7 FAILED wrong old value was accepted';
    EXCEPTION WHEN others THEN
        IF SQLERRM LIKE '%expected 1 row, matched 0%' THEN
            ok := ok + 1;  RAISE NOTICE 'C7 OK   wrong old value raises (0 rows)';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C7 FAILED wrong error: %', SQLERRM;
        END IF;
    END;

    -- ---- C8: a primary key that does not exist ------------------------------
    BEGIN
        PERFORM apply_remediation_change(
            'wiki_images', 'is_hero', 'id', '-1', 'false', 'true',
            'T09/selftest-nopk', 'selftest', 'selftest-c8', 'authoritative',
            NULL::jsonb, NULL::uuid);
        failed := failed + 1; RAISE NOTICE 'C8 FAILED nonexistent pk was accepted';
    EXCEPTION WHEN others THEN
        IF SQLERRM LIKE '%expected 1 row, matched 0%' THEN
            ok := ok + 1;  RAISE NOTICE 'C8 OK   nonexistent pk raises';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C8 FAILED wrong error: %', SQLERRM;
        END IF;
    END;

    -- ---- C9: a table outside the allowlist ----------------------------------
    BEGIN
        PERFORM apply_remediation_change(
            'pg_class', 'relname', 'oid', '1', NULL, 'x',
            'X/selftest', 'selftest', 'selftest-c9', 'authoritative',
            NULL::jsonb, NULL::uuid);
        failed := failed + 1; RAISE NOTICE 'C9 FAILED a non-target table was accepted';
    EXCEPTION WHEN others THEN
        IF SQLERRM LIKE '%not a remediation target%' THEN
            ok := ok + 1;  RAISE NOTICE 'C9 OK   table allowlist holds';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C9 FAILED wrong error: %', SQLERRM;
        END IF;
    END;

    -- ---- C10: a column that does not exist ---------------------------------
    BEGIN
        PERFORM apply_remediation_change(
            'wiki_images', 'no_such_column', 'id', v_id, NULL, 'x',
            'X/selftest', 'selftest', 'selftest-c10', 'authoritative',
            NULL::jsonb, NULL::uuid);
        failed := failed + 1; RAISE NOTICE 'C10 FAILED a nonexistent column was accepted';
    EXCEPTION WHEN others THEN
        IF SQLERRM LIKE '%has no column%' THEN
            ok := ok + 1;  RAISE NOTICE 'C10 OK  unknown column refused from the catalog';
        ELSE
            failed := failed + 1; RAISE NOTICE 'C10 FAILED wrong error: %', SQLERRM;
        END IF;
    END;

    RAISE NOTICE 'selftest done: % ok, % failed', ok, failed;
    IF failed > 0 THEN
        RAISE EXCEPTION 'SELFTEST FAILED: % of % cases', failed, ok + failed;
    END IF;
END
$selftest$;

-- Nothing the selftest did may survive.
ROLLBACK;

-- After the rollback the journal must be exactly as empty as before.
SELECT count(*) AS change_log_rows_must_be_0 FROM remediation_change_log;
