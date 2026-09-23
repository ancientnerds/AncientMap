-- 0023_source_url_no_control_chars.sql
--
-- Keep control characters out of unified_sites.source_url:
--     CHECK (source_url !~ '[\x00-\x1f\x7f]')   (C0 controls and DEL; NULL stays allowed)
--
-- WHY THIS FILE EXISTS
-- Measured 2026-09-23 (read-only): 20 unified_sites rows - all curated, all from the 2026-03-04
-- import - held two URLs joined by a newline, and no other row of the table held a control
-- character in source_url. Every reader treats the column as one URL. The boot refresh of
-- site_external_ids (pipeline/lyra/prospector/external_ids.py) therefore never gave 19 of them an
-- id, and turned Petra's value into the enwiki_title 'Petra\nhttps://www.khanacademy.org/...'.
-- The data fix is output/remediation/qid_repair/wave4 (journalled in remediation_change_log);
-- pipeline/lyra/prospector/wiki.py now refuses such a URL. This constraint keeps the next import
-- from writing one.
--
-- ORDER - READ BEFORE THIS FILE REACHES main
-- The deploy applies this file AFTER the orchestrator has applied the data fix:
--     qid_repair.py check --wave 4, then wave4/APPLY.sql, then qid_repair.py verify --wave 4.
-- While any row still carries a control character in source_url, the first transaction below
-- raises, naming the count, and commits nothing - and a failing migration stops the deploy
-- (ON_ERROR_STOP). Rehearsed on production 2026-09-23 inside BEGIN; ... ROLLBACK;: it fails with
-- exactly the 20 rows, as it must until the data fix is in. Once this constraint is applied, the
-- source_url half of wave4/ROLLBACK.sql can no longer run: the CHECK refuses the two-URL values.
--
-- LOCKING (unified_sites is about 1.76M rows and the API reads it on every request) - the 0020
-- pattern:
--   * transaction 1 counts the offending rows with a plain read (no exclusive lock) and raises if
--     there is one. Then the CHECK is added NOT VALID: a catalog change that takes ACCESS
--     EXCLUSIVE only briefly and is enforced for every new write from then on.
--   * transaction 2 VALIDATEs it: SHARE UPDATE EXCLUSIVE, so readers and writers carry on during
--     the one full scan. A row written with a control character between the two transactions
--     fails the VALIDATE; the NOT VALID constraint already refuses any further one, and running
--     the file again after that row is fixed validates it.
--
-- Forward-only and idempotent: the constraint is added only when the catalog lacks it, and
-- VALIDATE of a validated constraint changes nothing.

BEGIN;

DO $$
DECLARE
    v_bad INTEGER;
BEGIN
    SELECT count(*) INTO v_bad FROM unified_sites WHERE source_url ~ '[\x00-\x1f\x7f]';
    IF v_bad > 0 THEN
        RAISE EXCEPTION
            '0023: % unified_sites row(s) carry a control character in source_url - apply the '
            'data fix (output/remediation/qid_repair/wave4) before this migration', v_bad;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'unified_sites'::regclass
           AND conname  = 'unified_sites_source_url_no_control_chars'
    ) THEN
        ALTER TABLE unified_sites
            ADD CONSTRAINT unified_sites_source_url_no_control_chars
            CHECK (source_url !~ '[\x00-\x1f\x7f]')
            NOT VALID;
        RAISE NOTICE '0023: unified_sites_source_url_no_control_chars added';
    ELSE
        RAISE NOTICE '0023: unified_sites_source_url_no_control_chars already exists - no ALTER';
    END IF;
END
$$;

COMMIT;

-- Own transaction: SHARE UPDATE EXCLUSIVE, readers and writers carry on during the scan.
ALTER TABLE unified_sites VALIDATE CONSTRAINT unified_sites_source_url_no_control_chars;

-- Prove the constraint is there, validated and the one this file means, from the catalog (the
-- 0020 selftest: no self-test write into a live 1.76M-row table).
DO $$
DECLARE
    v_def   TEXT;
    v_valid BOOLEAN;
BEGIN
    SELECT pg_get_constraintdef(oid), convalidated
      INTO v_def, v_valid
      FROM pg_constraint
     WHERE conrelid = 'unified_sites'::regclass
       AND conname  = 'unified_sites_source_url_no_control_chars';

    IF v_def IS NULL THEN
        RAISE EXCEPTION 'SELFTEST FAILED: unified_sites_source_url_no_control_chars does not exist';
    END IF;
    IF NOT v_valid THEN
        RAISE EXCEPTION 'SELFTEST FAILED: unified_sites_source_url_no_control_chars is not validated';
    END IF;
    -- strpos, not LIKE: LIKE reads the backslashes as its own escapes and would never match
    -- (measured 2026-09-23 on a temp table: the definition reads
    -- CHECK ((source_url !~ '[\x00-\x1f\x7f]'::text)), LIKE false, strpos 9).
    IF strpos(v_def, 'source_url !~ ''[\x00-\x1f\x7f]''') = 0 THEN
        RAISE EXCEPTION 'SELFTEST FAILED: unexpected definition: %', v_def;
    END IF;
    RAISE NOTICE '0023 selftest: %', v_def;
END
$$;
