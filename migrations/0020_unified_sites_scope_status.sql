-- 0020_unified_sites_scope_status.sql
--
-- Add unified_sites.scope_status and unified_sites.scope_reason: owner decision E4
-- ("flag it AND hide it platform-wide"), plan docs/procedures/SITES_DB_REMEDIATION_2026-09.md
-- section 8.4. The column was approved for the implementation phase; this is it.
--
-- VOCABULARY
--     NULL       never assessed - counts as IN SCOPE. This is why no backfill is needed and
--                why nothing disappears on the deploy that adds the column.
--     in_scope   assessed and kept
--     pending    assessment open; still shown until decided
--     retired    assessed and hidden everywhere (API, SSR pages, sitemap, IndexNow, static
--                export, Qdrant, shorts batch, card draws, public API). The row is NOT
--                deleted (E1): matching and prospector dedup keep seeing it, so a retired
--                site is never proposed again.
-- scope_reason carries the evidence-backed reason in words ("dated 1537, outside the E3
-- window"). It is free text on purpose: the reason is for a human reviewer, the status is
-- for the code.
--
-- The consumers read the status through pipeline/utils/public_sites.py:not_retired(), which is
-- `scope_status IS DISTINCT FROM 'retired'` - NOT `<> 'retired'`, which is NULL for the NULL
-- rows and would hide every site nobody has assessed.
--
-- Writes go through apply_remediation_change() (migration 0017): its allowlist is a list of
-- TABLE names and already contains unified_sites, so no allowlist change is needed. The one
-- other writer is a founder's snapshot restore, and only from a snapshot that recorded the
-- column (taken after this migration); its preview lists the scope change before it runs.
--
-- Restart behaviour: survives. No boot-time writer touches these columns (FIELD_CONTRACT
-- section 2 names exactly three: unified_sites.site_type, unified_sites.name_normalized,
-- card_stats.card_description).
--
-- LOCKING (unified_sites is 1.76M rows / 2.1 GB, and the API reads it on every request)
--   * ADD COLUMN without a DEFAULT is a catalog change - no table rewrite - but takes ACCESS
--     EXCLUSIVE briefly. It runs only when the catalog says the column is absent.
--   * The CHECK is added NOT VALID (instant, and already enforced for every new write), then
--     VALIDATEd in its own transaction: VALIDATE takes SHARE UPDATE EXCLUSIVE, which does not
--     block reads or writes, while the one full scan runs. Every existing row is NULL, so the
--     validation cannot fail.
--
-- Forward-only and idempotent: re-running the file changes nothing.

BEGIN;

DO $$
DECLARE
    v_fresh boolean;
BEGIN
    -- attisdropped: a dropped column keeps its name in pg_attribute.
    SELECT NOT EXISTS (
        SELECT 1
          FROM pg_attribute a
         WHERE a.attrelid = 'unified_sites'::regclass
           AND a.attname  = 'scope_status'
           AND a.attnum > 0
           AND NOT a.attisdropped
    ) INTO v_fresh;

    IF v_fresh THEN
        EXECUTE 'ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS scope_status TEXT';
        EXECUTE 'ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS scope_reason TEXT';
        RAISE NOTICE '0020: scope_status and scope_reason added';
    ELSE
        RAISE NOTICE '0020: scope_status already exists - no ALTER';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'unified_sites'::regclass
           AND conname  = 'unified_sites_scope_status_vocab'
    ) THEN
        ALTER TABLE unified_sites
            ADD CONSTRAINT unified_sites_scope_status_vocab
            CHECK (scope_status IS NULL OR scope_status IN ('in_scope', 'retired', 'pending'))
            NOT VALID;
    END IF;
END
$$;

COMMENT ON COLUMN unified_sites.scope_status IS
    'E4 scope decision. NULL = never assessed (shown); in_scope; pending (shown); retired = '
    'hidden platform-wide but kept for matching. Read through '
    'pipeline/utils/public_sites.not_retired(); written through apply_remediation_change() '
    '(and by a snapshot restore, from a snapshot that recorded it).';
COMMENT ON COLUMN unified_sites.scope_reason IS
    'Why the scope_status was set, in words, for the human reviewer. Free text.';

COMMIT;

-- Own transaction: SHARE UPDATE EXCLUSIVE, readers and writers carry on during the scan.
ALTER TABLE unified_sites VALIDATE CONSTRAINT unified_sites_scope_status_vocab;

-- Prove the constraint is really there before trusting it (the 0019 lesson: a check that cannot
-- fail is not a check). This reads the catalog instead of writing an invalid value into a live
-- row: a self-test UPDATE on a 1.76M-row table the API and Lyra write to can wait on a row lock
-- and fail the deploy for a reason that has nothing to do with this migration. The catalog
-- is what Postgres enforces, so asserting it is equivalent - and it fails loudly if the
-- constraint is missing, unvalidated, or carries a different vocabulary.
DO $$
DECLARE
    v_def   TEXT;
    v_valid BOOLEAN;
BEGIN
    SELECT pg_get_constraintdef(oid), convalidated
      INTO v_def, v_valid
      FROM pg_constraint
     WHERE conrelid = 'unified_sites'::regclass
       AND conname  = 'unified_sites_scope_status_vocab';

    IF v_def IS NULL THEN
        RAISE EXCEPTION 'SELFTEST FAILED: unified_sites_scope_status_vocab does not exist';
    END IF;
    IF NOT v_valid THEN
        RAISE EXCEPTION 'SELFTEST FAILED: unified_sites_scope_status_vocab is not validated';
    END IF;
    IF v_def NOT LIKE '%''in_scope''%' OR v_def NOT LIKE '%''retired''%'
       OR v_def NOT LIKE '%''pending''%' THEN
        RAISE EXCEPTION 'SELFTEST FAILED: unexpected scope vocabulary: %', v_def;
    END IF;
    RAISE NOTICE '0020 selftest: %', v_def;
END
$$;
