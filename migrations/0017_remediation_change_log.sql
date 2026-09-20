-- 0017_remediation_change_log.sql
--
-- The change journal for the 2026-09 site remediation.
--
-- Owner decision E1 (docs/procedures/SITES_DB_REMEDIATION_2026-09.md, section 1.2) allows
-- the remediation to write to production under four conditions: a conditional WHERE, a
-- change journal, no DELETE, and a verified backup beforehand. This migration supplies the
-- journal and, with it, the only supported way to make a remediation write.
--
-- Why a function and not just a table:
--   A conditional UPDATE plus a journal INSERT issued as two statements from a script can
--   half-succeed - the value changes and the journal entry does not, or the journal records
--   a write whose WHERE clause matched nothing. Either way the audit trail lies, which is
--   worse than having none. apply_remediation_change() does both in one statement, so the
--   caller gets a single implicit transaction: it either changes exactly one row AND
--   journals it, or it raises.
--
--   It also refuses to write when the WHERE clause does not match exactly one row. That is
--   the difference between "I changed the value" and "I believe I changed the value": if
--   the old value moved underneath us, the row count is 0 and the call fails loudly instead
--   of silently applying a correction to data that has since changed.
--
-- Forward-only and idempotent: CREATE IF NOT EXISTS / CREATE OR REPLACE only. The deploy
-- job in .github/workflows/ci.yml applies every migrations/*.sql not yet present in
-- applied_migrations, with ON_ERROR_STOP=1, so re-running this file is harmless.

BEGIN;

CREATE TABLE IF NOT EXISTS remediation_change_log (
    id           BIGSERIAL PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_stamp    TEXT        NOT NULL,          -- e.g. '2026-09-20_remediation'
    test_id      TEXT,                          -- e.g. 'T05/country-compound'
    table_name   TEXT        NOT NULL,
    column_name  TEXT        NOT NULL,
    row_pk       TEXT        NOT NULL,          -- primary key value, as text
    old_value    TEXT,                          -- what was there, for reversal
    new_value    TEXT,                          -- what we wrote (NULL = cleared)
    change_key   TEXT,                          -- Finding.change_key, groups duplicates
    confidence   TEXT,                          -- authoritative|two_source|weak|unverifiable
    evidence     JSONB,                         -- the Finding's evidence array
    applied_by   TEXT        NOT NULL DEFAULT current_user,
    -- The bare row_pk is not enough to join back: a UUID identifies a row in unified_sites,
    -- but the same UUID in wiki_images means nothing. site_id_ref carries the owning site
    -- wherever it is known, so "what did we change on this site" is one indexed lookup.
    site_id_ref  UUID
);

COMMENT ON TABLE remediation_change_log IS
    'Journal of every value the 2026-09 remediation changed. Written only by '
    'apply_remediation_change(). old_value makes each write reversible by hand.';

-- Idempotent safety for a database where an earlier partial version of this file created
-- the table without the column. Must come BEFORE the index on it, or the migration fails
-- on a fresh database with "column site_id_ref does not exist".
ALTER TABLE remediation_change_log
    ADD COLUMN IF NOT EXISTS site_id_ref UUID;

CREATE INDEX IF NOT EXISTS idx_rcl_site  ON remediation_change_log (site_id_ref);
CREATE INDEX IF NOT EXISTS idx_rcl_stamp ON remediation_change_log (run_stamp);
CREATE INDEX IF NOT EXISTS idx_rcl_key   ON remediation_change_log (change_key);
CREATE INDEX IF NOT EXISTS idx_rcl_table ON remediation_change_log (table_name, column_name);

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

    -- The conditional WHERE. `IS NOT DISTINCT FROM` (not `=`) so that NULL counts as the
    -- old value it actually is: `col = NULL` is never true, which would make every
    -- correction of a NULL field silently match zero rows.
    EXECUTE format(
        'UPDATE %I SET %I = $1 WHERE %I::text = $2 AND %I IS NOT DISTINCT FROM $3',
        p_table, p_column, p_pk_col, p_column
    ) USING p_new, p_pk, p_old;

    GET DIAGNOSTICS n = ROW_COUNT;

    IF n <> 1 THEN
        RAISE EXCEPTION
            'apply_remediation_change: %I.%I for %I=%s expected 1 row, matched % - '
            'the old value is %L but the row holds something else (data changed underneath us?)',
            p_table, p_column, p_pk_col, p_pk, n,
            coalesce(p_old, '<NULL>');
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
    'old value. p_new = NULL clears the column (an empty field beats a wrong one).';

-- Undo helper: the previous value for one row/column, newest first. Reversal is then a
-- deliberate, reviewable call to apply_remediation_change() - not an automatic rollback.
CREATE OR REPLACE VIEW remediation_change_history AS
SELECT
    l.applied_at,
    l.run_stamp,
    l.test_id,
    l.table_name,
    l.column_name,
    l.row_pk,
    l.old_value,
    l.new_value,
    l.applied_by,
    LAG(l.old_value) OVER (
        PARTITION BY l.table_name, l.column_name, l.row_pk
        ORDER BY l.applied_at, l.id
    ) AS value_before_previous
FROM remediation_change_log l;

COMMENT ON VIEW remediation_change_history IS
    'Newest-first audit of remediation writes per row, with the preceding value so a change '
    'can be reverted deliberately.';

COMMIT;
