-- 0022_remediation_change_by_key.sql
--
-- Make apply_remediation_change() find its row through the primary-key index.
--
-- WHY THIS FILE EXISTS
-- 0018 located the row with `WHERE %I::text = $2`. Casting the key COLUMN to text makes the
-- predicate unusable for the primary-key index, so every call scanned the whole table - twice,
-- once for the UPDATE and once for the re-read of the stored value. Measured on production
-- 2026-09-23 with EXPLAIN (read-only) on unified_sites (about 1.76M rows):
--
--     WHERE id::text = '99a98235-...'          -> Seq Scan,   cost 0.00..232500.22
--     WHERE id = '99a98235-...'::uuid          -> Index Scan using unified_sites_pkey,
--                                                  cost 0.43..8.45
--
-- It surfaced as a statement timeout: the period_name lane's 220-row rehearsal (BEGIN ...
-- ROLLBACK, nothing kept) did not finish inside its 120 s statement_timeout. Phase 3's 994
-- writes had paid the same price without a timeout to show it. Every later lane (search
-- corrections, sourced descriptions, card_stats) would pay it per row.
--
-- WHAT CHANGES: exactly the key lookup. The key column's type is read from the catalog like the
-- value column's already is, and both the UPDATE and the re-read compare `%I = $2::<key type>`.
-- The signature, the allow-list, the no-op refusal, the type-safe SET, the truncation-proof
-- re-read and the journal insert are 0018's, byte for byte (built from 0018's text by a script
-- that asserts each of its four edits matches exactly once).
--
-- A key value that is not a valid literal of the key type now raises while the statement is
-- built instead of matching zero rows; both ends in the function refusing the change, so no
-- caller can observe a different outcome.
--
-- Rehearsed on production inside BEGIN; ... ROLLBACK; before this file was committed: the
-- whole of scripts/remediation/0018_migration_selftest.sql passes against this body, and the
-- 220-row period_name rehearsal completes (evidence in AUDIT_LOG.md, 2026-09-23).

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
    -- The key column's own type (0022): the key is compared in it, so the primary-key
    -- index is used. `%I::text = $2` cast the COLUMN and scanned the whole table.
    v_pk_type TEXT;
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

    SELECT format_type(a.atttypid, NULL)
      INTO v_pk_type
      FROM pg_attribute a
     WHERE a.attrelid = p_table::regclass
       AND a.attname  = p_pk_col
       AND a.attnum   > 0
       AND NOT a.attisdropped;
    IF v_pk_type IS NULL THEN
        RAISE EXCEPTION
            'apply_remediation_change: table % has no key column % - refusing to build a '
            'statement against a key that does not exist', p_table, p_pk_col;
    END IF;
    IF v_type IS NULL THEN
        RAISE EXCEPTION
            'apply_remediation_change: table % has no column % - refusing to build a '
            'statement against a column that does not exist', p_table, p_column;
    END IF;
    -- The conditional WHERE, now type-safe. Since 0022 the key is compared in the key
    -- column's own type (`%I = $2::<key type>`), so the primary-key index is used. `IS NOT DISTINCT FROM` (not `=`) so that NULL
    -- counts as the old value it actually is: `col = NULL` is never true, which would make
    -- every correction of a NULL field silently match zero rows.
    --
    -- Both operands are cast to the column's own type. `$1::<type>` also keeps p_new = NULL
    -- meaning "clear the column", because NULL::anything is still NULL.
    EXECUTE format(
        'UPDATE %I SET %I = $1::%s WHERE %I = $2::%s AND %I IS NOT DISTINCT FROM $3::%s',
        p_table, p_column, v_type, p_pk_col, v_pk_type, p_column, v_type
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
        'SELECT %I IS NOT DISTINCT FROM $1::%s FROM %I WHERE %I = $2::%s',
        p_column, v_base_type, p_table, p_pk_col, v_pk_type
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
    'old value. Type-safe for every column type via the catalog (0018); finds its row through '
    'the key column''s own type, so the primary-key index is used (0022). Refuses a change '
    'whose value the column would silently truncate or coerce, so the journal never records '
    'a value the row does not hold, and refuses a no-op where p_old already equals p_new, so '
    'the journal holds only changes that actually happened. p_new = NULL clears the column (an '
    'empty field beats a wrong one).';

COMMIT;
