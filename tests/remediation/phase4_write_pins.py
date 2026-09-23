"""The reviewed text of every guard and invariant the Phase-4/5 statements carry.

Not a test module (no `test_` prefix): `test_phase4_write.py` compares what `write4.render_apply`,
`write4.render_rollback` and `revert4.render_revert` render against these blocks, byte for byte.

Why a pin and not the fake: the fake psql (`phase4_write_fixtures.FakeDb`) cannot evaluate PL/pgSQL,
so a predicate or a `RAISE` removed from a rendered guard would leave every behaviour test green. The
guards' semantics are reviewed here, as SQL; after that, any change to a predicate, a join, a
comparison or a `RAISE` - the one in-database protection against a row outside `ancient_nerds`, for
instance - changes this file in the same diff, where a reviewer reads it. The rehearsal
(`--rehearse`, ending in `ROLLBACK`) is what runs the reviewed statement against the live rows.

The P4 blocks are rendered from the one-site chunk of `phase4_write_fixtures` (batch `p4-0003`,
round 1, two rows); the reversal from `revert4.render_revert('phase5:%')`.
"""

P4_PLAN_TABLE = """\
CREATE TEMP TABLE _phase4_plan (
    site_id     UUID NOT NULL,
    table_name  TEXT NOT NULL,
    column_name TEXT NOT NULL,
    pk_column   TEXT NOT NULL,
    pk          TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    change_key  TEXT NOT NULL,
    test_id     TEXT NOT NULL,
    evidence    JSONB NOT NULL,
    -- one row per (table, column, site): two would be two writes of one transition
    PRIMARY KEY (table_name, column_name, site_id)
) ON COMMIT DROP;
"""

P4_APPLY_BODY = """\
DO $$
DECLARE
    bad        INTEGER;
    moved      INTEGER := 0;
    expected   INTEGER := 2;
    journalled INTEGER;
    r          RECORD;
BEGIN
    -- guard 1: every planned site is an existing curated site, and a card row has its
    -- card_stats row (apply_remediation_change only UPDATEs; a missing row matches 0).
    SELECT count(*) INTO bad
      FROM _phase4_plan p
      LEFT JOIN unified_sites u ON u.id = p.site_id
      LEFT JOIN card_stats c ON c.site_id = p.site_id
     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds'
        OR (p.table_name = 'card_stats' AND c.site_id IS NULL);
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % planned row(s) are not rows of % sites', bad, 'ancient_nerds';
    END IF;

    -- guard 2: table, column, key column and test_id are this group's allow-list, and the
    -- key is the site itself.
    SELECT count(*) INTO bad FROM _phase4_plan p
     WHERE (p.table_name, p.column_name, p.pk_column, p.test_id) NOT IN (VALUES ('unified_sites', 'description', 'id', 'P4/description'), ('unified_sites', 'raw_data', 'id', 'P4/raw_data'))
        OR p.pk <> p.site_id::text;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % planned row(s) are outside the allow-list', bad;
    END IF;

    -- guard 3: every row is a real change, in the column's own type: raw_data compares as
    -- jsonb, so a re-serialisation of the same object is refused as the no-op it is.
    SELECT count(*) INTO bad FROM _phase4_plan p
     WHERE p.new_value IS NOT DISTINCT FROM p.old_value OR p.new_value = ''
        OR (p.new_value IS NULL AND p.test_id <> 'P5/card-clear')
        OR CASE WHEN p.column_name = 'raw_data' THEN p.new_value::jsonb IS NOT DISTINCT FROM p.old_value::jsonb ELSE false END;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % planned row(s) are not real changes', bad;
    END IF;

    -- guard 4: every row still holds the old value the plan names (IS DISTINCT FROM in the
    -- column's type; unlike `=`, it is true for a NULL old value).
    SELECT count(*) INTO bad
      FROM _phase4_plan p
      LEFT JOIN unified_sites u ON u.id = p.site_id
      LEFT JOIN card_stats c ON c.site_id = p.site_id
     WHERE 1 = 0
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'description' THEN u.description IS DISTINCT FROM p.old_value ELSE false END
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'raw_data' THEN u.raw_data IS DISTINCT FROM p.old_value::jsonb ELSE false END
        OR CASE WHEN p.table_name = 'card_stats' AND p.column_name = 'card_description' THEN c.card_description IS DISTINCT FROM p.old_value ELSE false END
       ;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % planned row(s) no longer hold the planned old value', bad;
    END IF;

    -- the only writer: the conditional UPDATE and its journal row commit together
    FOR r IN SELECT * FROM _phase4_plan ORDER BY site_id, table_name, column_name LOOP
        moved := moved + apply_remediation_change(
            r.table_name, r.column_name, r.pk_column, r.pk, r.old_value, r.new_value,
            r.test_id, 'phase4:p4-0003:chunk-0001', r.change_key,
            'authoritative', r.evidence, r.site_id);
    END LOOP;
    IF moved <> expected THEN
        RAISE EXCEPTION 'p4 write: % row(s) changed, % planned', moved, expected;
    END IF;

    -- invariant 1: every planned row now holds the new value
    SELECT count(*) INTO bad
      FROM _phase4_plan p
      LEFT JOIN unified_sites u ON u.id = p.site_id
      LEFT JOIN card_stats c ON c.site_id = p.site_id
     WHERE 1 = 0
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'description' THEN u.description IS DISTINCT FROM p.new_value ELSE false END
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'raw_data' THEN u.raw_data IS DISTINCT FROM p.new_value::jsonb ELSE false END
        OR CASE WHEN p.table_name = 'card_stats' AND p.column_name = 'card_description' THEN c.card_description IS DISTINCT FROM p.new_value ELSE false END
       ;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % planned row(s) do not hold the new value', bad;
    END IF;

    -- invariant 2: the journal and the plan agree row for row, in both directions
    SELECT count(*) INTO bad
      FROM _phase4_plan p LEFT JOIN remediation_change_log l
        ON l.change_key = p.change_key AND l.run_stamp = 'phase4:p4-0003:chunk-0001'
     WHERE l.id IS NULL
        OR l.table_name IS DISTINCT FROM p.table_name
        OR l.column_name IS DISTINCT FROM p.column_name
        OR l.row_pk IS DISTINCT FROM p.pk
        OR l.old_value IS DISTINCT FROM p.old_value
        OR l.new_value IS DISTINCT FROM p.new_value
        OR l.test_id IS DISTINCT FROM p.test_id
        OR l.site_id_ref IS DISTINCT FROM p.site_id;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % planned row(s) have no matching journal row', bad;
    END IF;
    SELECT count(*) INTO journalled FROM remediation_change_log l
     WHERE l.run_stamp = 'phase4:p4-0003:chunk-0001';
    IF journalled <> expected THEN
        RAISE EXCEPTION 'p4 write: this run stamp journals % row(s), the plan has %', journalled, expected;
    END IF;

    -- invariant 3 (P4, L): the provenance's desc_sha256 is the sha256 of the description
    SELECT count(*) INTO bad
      FROM _phase4_plan p JOIN unified_sites u ON u.id = p.site_id
     WHERE p.column_name = 'raw_data'
       AND (u.raw_data -> '_description_provenance' ->> 'desc_sha256')
           IS DISTINCT FROM encode(sha256(convert_to(u.description, 'UTF8')), 'hex');
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % site(s) break the description sha256 invariant', bad;
    END IF;

    -- invariant 4 (P5): a written card's sha256 is its provenance's card.text_sha256
    SELECT count(*) INTO bad
      FROM _phase4_plan p JOIN unified_sites u ON u.id = p.site_id
      JOIN card_stats c ON c.site_id = p.site_id
     WHERE p.column_name = 'card_description' AND p.new_value IS NOT NULL
       AND encode(sha256(convert_to(c.card_description, 'UTF8')), 'hex')
           IS DISTINCT FROM (u.raw_data -> '_description_provenance' -> 'card' ->> 'text_sha256');
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 write: % card(s) break the card sha256 invariant', bad;
    END IF;

    RAISE NOTICE 'p4 write: % row(s) changed and journalled, % planned', moved, expected;
END $$;
"""

P4_ROLLBACK_BODY = """\
DO $$
DECLARE
    bad      INTEGER;
    moved    INTEGER := 0;
    expected INTEGER := 2;
    r        RECORD;
BEGIN
    -- guard: every row still holds the value the write left (the reversal's old value)
    SELECT count(*) INTO bad
      FROM _phase4_plan p
      LEFT JOIN unified_sites u ON u.id = p.site_id
      LEFT JOIN card_stats c ON c.site_id = p.site_id
     WHERE 1 = 0
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'description' THEN u.description IS DISTINCT FROM p.old_value ELSE false END
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'raw_data' THEN u.raw_data IS DISTINCT FROM p.old_value::jsonb ELSE false END
        OR CASE WHEN p.table_name = 'card_stats' AND p.column_name = 'card_description' THEN c.card_description IS DISTINCT FROM p.old_value ELSE false END
       ;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 rollback: % planned row(s) do not hold the written value', bad;
    END IF;

    FOR r IN SELECT * FROM _phase4_plan ORDER BY site_id, table_name, column_name LOOP
        moved := moved + apply_remediation_change(
            r.table_name, r.column_name, r.pk_column, r.pk, r.old_value, r.new_value,
            r.test_id, 'phase4:p4-0003:chunk-0001-rollback', r.change_key,
            'authoritative', r.evidence, r.site_id);
    END LOOP;
    IF moved <> expected THEN
        RAISE EXCEPTION 'p4 rollback: % row(s) changed, % planned', moved, expected;
    END IF;

    -- the inverse, asserted inside the transaction: every row is back at the old value
    SELECT count(*) INTO bad
      FROM _phase4_plan p
      LEFT JOIN unified_sites u ON u.id = p.site_id
      LEFT JOIN card_stats c ON c.site_id = p.site_id
     WHERE 1 = 0
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'description' THEN u.description IS DISTINCT FROM p.new_value ELSE false END
        OR CASE WHEN p.table_name = 'unified_sites' AND p.column_name = 'raw_data' THEN u.raw_data IS DISTINCT FROM p.new_value::jsonb ELSE false END
        OR CASE WHEN p.table_name = 'card_stats' AND p.column_name = 'card_description' THEN c.card_description IS DISTINCT FROM p.new_value ELSE false END
       ;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 rollback: % row(s) are not back at the old value', bad;
    END IF;

    -- the reversal is journalled row for row, under the rollback stamp
    SELECT count(*) INTO bad
      FROM _phase4_plan p LEFT JOIN remediation_change_log l
        ON l.change_key = p.change_key AND l.run_stamp = 'phase4:p4-0003:chunk-0001-rollback'
     WHERE l.id IS NULL
        OR l.old_value IS DISTINCT FROM p.old_value
        OR l.new_value IS DISTINCT FROM p.new_value;
    IF bad > 0 THEN
        RAISE EXCEPTION 'p4 rollback: % planned row(s) have no matching journal row', bad;
    END IF;

    RAISE NOTICE 'p4 rollback: % row(s) reversed inside a transaction about to be rolled back',
        moved;
END $$;
"""

P5_REVERT = """\
BEGIN;
DO $$
DECLARE
    bad      INTEGER;
    matched  INTEGER;
    expected INTEGER;
    ids      BIGINT[];
    moved    INTEGER := 0;
    r        RECORD;
BEGIN
    SELECT count(*) INTO matched FROM remediation_change_log l WHERE l.run_stamp LIKE 'phase5:%' AND l.run_stamp NOT LIKE '%-rollback';
    IF matched = 0 THEN
        RAISE EXCEPTION 'revert: no journalled write matches %', 'phase5:%';
    END IF;

    -- the set, fixed before anything moves: every matched write whose own reversal (its key
    -- and its stamp plus -rollback) is not journalled; a reverted write is never reverted again
    ids := ARRAY(SELECT l.id FROM remediation_change_log l
                  WHERE l.run_stamp LIKE 'phase5:%' AND l.run_stamp NOT LIKE '%-rollback'
                    AND NOT EXISTS (SELECT 1 FROM remediation_change_log k
                          WHERE k.change_key = l.change_key || '-rollback'
                            AND k.run_stamp = l.run_stamp || '-rollback')
                  ORDER BY l.id);
    expected := cardinality(ids);
    IF expected = 0 THEN
        RAISE EXCEPTION 'revert: all % matched write(s) were reverted already', matched;
    END IF;

    -- guard: only the three written columns, only curated sites, the key is the site
    SELECT count(*) INTO bad
      FROM remediation_change_log l LEFT JOIN unified_sites u ON u.id = l.site_id_ref
     WHERE l.id = ANY(ids)
       AND ((l.table_name, l.column_name) NOT IN (VALUES ('unified_sites', 'description'), ('unified_sites', 'raw_data'), ('card_stats', 'card_description'))
            OR u.id IS NULL OR u.source_id <> 'ancient_nerds'
            OR l.row_pk <> l.site_id_ref::text);
    IF bad > 0 THEN
        RAISE EXCEPTION 'revert: % journal row(s) are outside the phase-4/5 targets', bad;
    END IF;

    -- newest first; each row's conditional WHERE needs it to hold its written value
    FOR r IN SELECT * FROM remediation_change_log l
              WHERE l.id = ANY(ids) ORDER BY l.id DESC LOOP
        moved := moved + apply_remediation_change(
            r.table_name, r.column_name, CASE r.table_name WHEN 'card_stats' THEN 'site_id' WHEN 'unified_sites' THEN 'id' END, r.row_pk,
            r.new_value, r.old_value, r.test_id,
            r.run_stamp || '-rollback', r.change_key || '-rollback',
            r.confidence, r.evidence, r.site_id_ref);
    END LOOP;
    IF moved <> expected THEN
        RAISE EXCEPTION 'revert: % row(s) changed, % journalled', moved, expected;
    END IF;

    -- invariant: every reverted field holds the old value of its oldest reverted link
    SELECT count(*) INTO bad FROM (
        SELECT DISTINCT ON (l.table_name, l.column_name, l.row_pk) l.*
          FROM remediation_change_log l WHERE l.id = ANY(ids)
         ORDER BY l.table_name, l.column_name, l.row_pk, l.id
    ) o
      LEFT JOIN unified_sites u ON o.table_name = 'unified_sites' AND u.id = o.row_pk::uuid
      LEFT JOIN card_stats c ON o.table_name = 'card_stats' AND c.site_id = o.row_pk::uuid
     WHERE CASE WHEN o.table_name = 'unified_sites' AND o.column_name = 'description' THEN u.description IS DISTINCT FROM o.old_value ELSE false END
        OR CASE WHEN o.table_name = 'unified_sites' AND o.column_name = 'raw_data' THEN u.raw_data IS DISTINCT FROM o.old_value::jsonb ELSE false END
        OR CASE WHEN o.table_name = 'card_stats' AND o.column_name = 'card_description' THEN c.card_description IS DISTINCT FROM o.old_value ELSE false END;
    IF bad > 0 THEN
        RAISE EXCEPTION 'revert: % field(s) are not back at their old value', bad;
    END IF;

    -- invariant: each reversal is journalled once, with the values swapped
    SELECT count(*) INTO bad FROM remediation_change_log l
      LEFT JOIN remediation_change_log k
        ON k.change_key = l.change_key || '-rollback' AND k.run_stamp = l.run_stamp || '-rollback'
     WHERE l.id = ANY(ids)
       AND (k.id IS NULL OR k.old_value IS DISTINCT FROM l.new_value
            OR k.new_value IS DISTINCT FROM l.old_value);
    IF bad > 0 THEN
        RAISE EXCEPTION 'revert: % row(s) have no matching reversal journal row', bad;
    END IF;

    RAISE NOTICE 'revert: % row(s) reverted', moved;
END $$;

COMMIT;

-- after the transaction:
-- the write rows matched, and those with their own reversal kept (read-only)
SELECT 'journalled writes matched' AS metric, count(*)::text AS value
  FROM remediation_change_log l WHERE l.run_stamp LIKE 'phase5:%' AND l.run_stamp NOT LIKE '%-rollback'
UNION ALL
SELECT 'reversals kept', count(*)::text FROM remediation_change_log l
 WHERE l.run_stamp LIKE 'phase5:%' AND l.run_stamp NOT LIKE '%-rollback'
   AND EXISTS (SELECT 1 FROM remediation_change_log k
                          WHERE k.change_key = l.change_key || '-rollback'
                            AND k.run_stamp = l.run_stamp || '-rollback');
"""
