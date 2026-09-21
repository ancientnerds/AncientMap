-- 0018_remediation_change_log_boolean.sql
--
-- Make apply_remediation_change() type-safe, so the journal works for non-text columns.
--
-- WHY THIS FILE EXISTS
-- Migration 0017 built the conditional UPDATE with text parameters:
--
--     UPDATE %I SET %I = $1 WHERE %I::text = $2 AND %I IS NOT DISTINCT FROM $3
--
-- That is only valid for text columns. Measured against production on 2026-09-20, inside
-- BEGIN; ... ROLLBACK; (so nothing was written), on the boolean column wiki_images.is_hero:
--
--     ERROR:  operator does not exist: boolean = text
--     LINE 1: ... SET is_hero = $1 WHERE id::text = $2 AND is_hero IS NOT DISTINCT FROM $3
--     CONTEXT:  PL/pgSQL function apply_remediation_change(text,...,uuid) line 24 at EXECUTE
--
-- It dies while planning, before any row is considered: even a primary key that cannot
-- exist (id = -1) fails the same way. Fixing only the WHERE is not enough - the SET then
-- fails too, with 42804 ("column \"is_hero\" is of type boolean but expression is of type
-- text"), which is why this migration resolves the column's type from the catalog and casts
-- BOTH operands.
--
-- This is not a corner case. wiki_images.is_hero, wiki_images.is_lead and
-- wiki_images.is_excluded are all boolean, so the entire image half of the remediation
-- (Phase 2: the hero repair and the gallery audit's is_excluded writes) is blocked by it.
--
-- Found by the HERO lane of wave 3, which refused to work around it and reported instead.
-- The gap in 0017's own self-test is the reason it shipped: scripts/remediation/
-- 0017_migration_selftest.sql exercised a TEXT column only. Its replacement,
-- scripts/remediation/0018_migration_selftest.sql, exercises boolean, text, integer,
-- timestamp and NULL, and the truncation guard below.
--
-- SECOND FIX IN THE SAME BREATH: the journal may not lie.
-- A text value longer than the column's declared width is silently truncated by the
-- assignment, so the row would hold the truncated value while remediation_change_log
-- recorded the untruncated one - a reversal driven by the journal would then write back
-- something that was never there. After the UPDATE this function re-reads the column and
-- refuses the change unless the stored value is the value it was asked to store. Inside the
-- same implicit transaction, so a refused change leaves nothing behind.
--
-- Getting that check right took two attempts, and the first one is worth recording because
-- it looked correct and was not: it compared the stored value against `$1::<full column
-- type>`, and a cast to `character varying(200)` truncates just as silently as the
-- assignment does. Both sides were therefore truncated and always equal, so a 250-character
-- value was accepted into a varchar(200) column - a check that could not fail. It now
-- compares in the column's BASE type, read separately as format_type(atttypid, NULL).
--
-- Forward-only and idempotent: CREATE OR REPLACE only, so the deploy job re-applying this
-- file (or applying it after a manual application) is harmless.

BEGIN;

CREATE OR REPLACE FUNCTION apply_remediation_change(
    p_table      TEXT,
    p_column     TEXT,
    p_pk_col     TEXT,
    p_pk         TEXT,
    p_old        TEXT,
    p_new        TEXT,
    p_test_id    TEXT,
    p_run_stamp  TEXT,
    p_change_key TEXT,
    p_confidence TEXT,
    p_evidence   JSONB,
    p_site_id    UUID
) RETURNS INTEGER
LANGUAGE plpgsql
AS $fn$
DECLARE
    n INTEGER;
    v_type TEXT;
    -- The same type WITHOUT its length/precision modifier. The round-trip check below must
    -- compare against this, not against v_type: `$1::character varying(200)` truncates just
    -- as silently as the assignment does, so a check written with v_type compares two
    -- truncated values and always passes. Measured 2026-09-20 - the first version of this
    -- guard was written that way and accepted a 250-character value into varchar(200).
    v_base_type TEXT;
    v_stored_matches BOOLEAN;
    -- Only the tables this remediation is allowed to touch. A typo'd or over-broad table
    -- name must fail here rather than silently rewriting something no audit has looked at.
    allowed CONSTANT TEXT[] := ARRAY[
        'unified_sites', 'card_stats', 'wiki_images',
        'site_content_links', 'site_external_ids', 'unified_site_names'
    ];
BEGIN
    IF NOT (p_table = ANY (allowed)) THEN
        RAISE EXCEPTION
            'apply_remediation_change: % is not a remediation target (allowed: %)',
            p_table, array_to_string(allowed, ', ');
    END IF;

    IF p_run_stamp IS NULL OR p_run_stamp = '' THEN
        RAISE EXCEPTION 'apply_remediation_change: p_run_stamp is required';
    END IF;

    -- A no-op is not a change. Without this, p_old = p_new matches the conditional UPDATE,
    -- passes the round-trip check, and writes a journal row whose old_value equals its
    -- new_value: a correction the journal claims and the data never received. It is the same
    -- "the journal must not lie" reason the truncation check below exists - that one catches
    -- a value the row does not hold, this one catches a change the row never had.
    -- IS NOT DISTINCT FROM rather than `=`, so NULL -> NULL is refused too: `= NULL` is never
    -- true, and "set this NULL field to NULL" is exactly the no-op worth catching.
    IF p_old IS NOT DISTINCT FROM p_new THEN
        RAISE EXCEPTION
            'apply_remediation_change: %.% for %=% was given the same old and new value (%) - '
            'refusing to journal a change that is not one',
            p_table, p_column, p_pk_col, p_pk, coalesce(p_new, '<NULL>');
    END IF;

    -- The column's declared type, taken from the catalog rather than guessed. pg_attribute
    -- avoids information_schema's privilege filtering and its slow view, and attnum > 0
    -- excludes system columns while attisdropped excludes a column that was dropped (whose
    -- name can still linger in the catalog with a non-NULL format_type).
    -- Both the declared type and its base form are read in one pass. v_type keeps the
    -- original assignment semantics in the SET clause; v_base_type is what the round-trip
    -- check compares in, because an unbounded cast cannot truncate.
    SELECT format_type(a.atttypid, a.atttypmod), format_type(a.atttypid, NULL)
      INTO v_type, v_base_type
      FROM pg_attribute a
     WHERE a.attrelid = p_table::regclass
       AND a.attname  = p_column
       AND a.attnum   > 0
       AND NOT a.attisdropped;

    IF v_type IS NULL THEN
        RAISE EXCEPTION
            'apply_remediation_change: table % has no column % - refusing to build a '
            'statement against a column that does not exist', p_table, p_column;
    END IF;
    -- The conditional WHERE, now type-safe. `%I::text = $2` compares the primary key as
    -- text, which works for every key type. `IS NOT DISTINCT FROM` (not `=`) so that NULL
    -- counts as the old value it actually is: `col = NULL` is never true, which would make
    -- every correction of a NULL field silently match zero rows.
    --
    -- Both operands are cast to the column's own type. `$1::<type>` also keeps p_new = NULL
    -- meaning "clear the column", because NULL::anything is still NULL.
    EXECUTE format(
        'UPDATE %I SET %I = $1::%s WHERE %I::text = $2 AND %I IS NOT DISTINCT FROM $3::%s',
        p_table, p_column, v_type, p_pk_col, p_column, v_type
    ) USING p_new, p_pk, p_old;

    GET DIAGNOSTICS n = ROW_COUNT;

    -- NOTE ON PLACEHOLDERS: PostgreSQL's RAISE uses a BARE % as its placeholder. `%s`, `%I`
    -- and `%L` are not format specifiers there - each prints its argument followed by the
    -- literal letter, which is how 0017's messages shipped garbled ('card_statsI',
    -- '<NULL>L'). Measured 2026-09-20: RAISE NOTICE '%L' , '<NULL>' prints `<NULL>L`, and
    -- `%I` consumes an argument (RAISE ... '%I' with no argument raises "too few
    -- parameters"). Every placeholder below is therefore a bare %.
    IF n <> 1 THEN
        RAISE EXCEPTION
            'apply_remediation_change: %.% for %=% expected 1 row, matched % - the old '
            'value is % but the row holds something else (data changed underneath us?)',
            p_table, p_column, p_pk_col, p_pk, n,
            coalesce(p_old, '<NULL>');
    END IF;

    -- Did the column really take the value we were asked to write? A value too long for the
    -- declared width is truncated silently, and the journal would then record something the
    -- row does not hold - so a reversal read from the journal would write back a value that
    -- never existed. Caught here, before anything commits, so the caller can shorten the
    -- value and retry.
    --
    -- The comparison runs in the column's BASE type, unbounded, so that:
    --   * a truncated value fails - the requested value keeps its full length while the
    --     stored one does not, so they are not equal;
    --   * a value-preserving coercion passes - '2026-09-20' into a timestamp column, or
    --     '1.5' into numeric(10,2), compare equal in their own type rather than by text, so
    --     a legitimate write is not refused for spelling the value differently.
    EXECUTE format(
        'SELECT %I IS NOT DISTINCT FROM $1::%s FROM %I WHERE %I::text = $2',
        p_column, v_base_type, p_table, p_pk_col
    ) INTO v_stored_matches USING p_new, p_pk;

    IF v_stored_matches IS NOT TRUE THEN
        RAISE EXCEPTION
            'apply_remediation_change: %.% for %=% stored a different value than it was '
            'given (given %, column type %). Usually the value is longer than the column''s '
            'declared width; the journal must not record a value the row does not hold. '
            'Shorten the value and retry - a later generation step can widen the column, not '
            'this function.',
            p_table, p_column, p_pk_col, p_pk, p_new, v_type;
    END IF;

    INSERT INTO remediation_change_log (
        run_stamp, test_id, table_name, column_name, row_pk,
        old_value, new_value, change_key, confidence, evidence, site_id_ref
    ) VALUES (
        p_run_stamp, p_test_id, p_table, p_column, p_pk,
        p_old, p_new, p_change_key, p_confidence, p_evidence, p_site_id
    );

    RETURN n;
END
$fn$;

COMMENT ON FUNCTION apply_remediation_change IS
    'The only supported way to change remediation data. One statement, so the UPDATE and '
    'its journal row commit together; raises unless exactly one row matches the expected '
    'old value. Type-safe for every column type via the catalog (0018). Refuses a change '
    'whose value the column would silently truncate or coerce, so the journal never records '
    'a value the row does not hold, and refuses a no-op where p_old already equals p_new, so '
    'the journal holds only changes that actually happened. p_new = NULL clears the column (an '
    'empty field beats a wrong one).';

COMMIT;
