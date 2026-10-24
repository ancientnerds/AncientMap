"""The write lanes of the identity package (final repair 2026-10-08): scope window, names, spoken names.

Four lane families, each a wave of at most 100 sites with a run stamp of its own (`<wave>` is a date
label like `2026-10-12` or `2026-10-12b`; a stamp is applied once):

* `scope-window-<wave>` (owner decision D20) - `scope_status` and `scope_reason` of one site in one
  transaction, the shape of `scope-review-<wave>`. The statuses it owns are `retired` and
  `in_scope`; the old value of a cell is whatever the site holds (NULL, `pending`, `in_scope`), so
  the transitions NULL -> retired, pending -> retired and in_scope -> retired are the same guarded
  write as NULL -> in_scope. Guard 3 conditions every cell on its old value and guard 5 on the
  entry the decision judged (name, type, point, country, dates);
* `name-clean-<wave>` (D23) and `retarget-name-<wave>` (D13) - `name` and its match key in one
  transaction, the key computed by Postgres from the new name (`name-l5`'s `NAME_CELLS` and write
  invariant). Both rest on the external ids the new name is attested by: a retargeted site's name is
  planned after its link step landed, so the premise makes the order a guard. The old name becomes
  an alias in `<kind>-alias-<wave>`, a chunk of the shared writer (`identity.name_write`);
* `spoken-<wave>` (D23) - `unified_sites.spoken_name` (migration 0029), filled where it is NULL, on
  the premise of the name it was derived from. A spoken name is never blank and never longer than
  `SPOKEN_MAX_CHARS`;
* `scope-unretire-<wave>` (D58 and D50) - `scope_status` and `scope_reason` of a retired site, back
  to `in_scope` (`mechanical/scope_unretire.py` plans it): a date retirement the label rule no
  longer carries, and a D50 mystery site once its description is a lane-E dispute enrichment. The
  premise holds the description too, and an invariant checks in the transaction that every
  un-retired site carries one of the two reasons and what that reason rests on.

`mechanical.lane.resolve_lane` reaches these lazily (`lane_of`), like the other wave families.
"""

from __future__ import annotations

import functools
import re

from mechanical.lane import (
    _CURATED_ROWS,
    _NAME_KEY_DIFFERS,
    _STATUS_WITHOUT_REASON,
    D50_NOT_RETIRED,
    D50_REASON_PREFIX,
    LOCK_TIMEOUT,
    NAME_CELLS,
    NAME_FIX_PREMISE_SQL,
    NON_SITE_TYPES,
    NOT_A_SITE_PREFIX,
    SCOPE_REVIEW_PREMISE_SQL,
    STATEMENT_TIMEOUT,
    UNDECIDED_OUTSIDE_LABEL_WINDOW,
    UNIFIED_SITES,
    Column,
    Lane,
    Residual,
    SiteInvariant,
    _window_date_sql,
    d50_site_sql,
    in_medieval_old_world_sql,
    journal_readback,
    label_borderline_sql,
    name_journal_metrics,
    outside_label_window,
    scope_status_counts,
    sql_literal,
)
from pipeline.utils.public_sites import RETIRED, not_retired

IN_SCOPE = "in_scope"
WAVE = r"(\d{4}-\d{2}-\d{2}[a-z]?)"
SCOPE_WINDOW_LANE = re.compile(rf"^scope-window-{WAVE}\Z")
NAME_CLEAN_LANE = re.compile(rf"^name-clean-{WAVE}\Z")
RETARGET_NAME_LANE = re.compile(rf"^retarget-name-{WAVE}\Z")
SPOKEN_LANE = re.compile(rf"^spoken-{WAVE}\Z")
SCOPE_UNRETIRE_LANE = re.compile(rf"^scope-unretire-{WAVE}\Z")
#: The lane families of this module, for `resolve_lane` and the read-back choice.
LANE_PATTERNS = (
    SCOPE_WINDOW_LANE,
    NAME_CLEAN_LANE,
    RETARGET_NAME_LANE,
    SPOKEN_LANE,
    SCOPE_UNRETIRE_LANE,
)

SCOPE_WINDOW_ROOT = "mechanical_scope_window"
NAME_ROOT = "mechanical_names"
SPOKEN_ROOT = "mechanical_spoken"
SCOPE_UNRETIRE_ROOT = "mechanical_scope_unretire"
#: The reason prefix of a retirement for the date (`E3: period_start N is past the cutoff; <quote>`).
DATE_RETIRED_PREFIX = "E3: period_start"
#: The reason prefix of a retirement by the label (D58: a borderline entry whose subject is
#: Byzantine, Crusader or Norse; `identity.scope_judge.MEDIEVAL_SUBJECT`).
LABEL_RETIRED_PREFIX = "D58: a medieval Old World subject"
#: A spoken name is a few words the narrator says in one breath; the triage's own bound
#: (`identity.names_triage.SPOKEN_MAX_CHARS`) is the same 40 characters, the lane allows a little
#: more because a model may keep a long attested form the rule would have flagged.
SPOKEN_MAX_CHARS = 60


def scope_window_lane(wave: str) -> Lane:
    """The scope window's write of one wave: its own stamp, key prefix and directory."""
    if SCOPE_WINDOW_LANE.match(f"scope-window-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-12 or 2026-10-12b")
    return Lane(
        name=f"scope-window-{wave}",
        key_prefix=f"scope-window-{wave}",
        run_stamp=f"{wave}_mechanical-scope-window",
        test_id="D20/scope-window",
        confidence="authoritative",
        label="D20 scope window",
        plan_table="_scope_window_plan",
        out_dir_name=f"{SCOPE_WINDOW_ROOT}/{wave}",
        post_commit_residual=UNDECIDED_OUTSIDE_LABEL_WINDOW,
        rehearsal_residual=UNDECIDED_OUTSIDE_LABEL_WINDOW,
        premise_sql=SCOPE_REVIEW_PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(
            Column("scope_status", "text", allowed_new_values=(RETIRED, IN_SCOPE), fills_null=True),
            Column("scope_reason", "text", fills_null=True),
        ),
        site_invariants=(D50_NOT_RETIRED,),
    )


@functools.cache
def scope_window_readback(lane: Lane) -> str:
    """The read-only verification of a scope-window wave, before and after its write."""
    stamp = sql_literal(lane.run_stamp)
    return journal_readback(
        lane,
        [
            *scope_status_counts(),
            (
                UNDECIDED_OUTSIDE_LABEL_WINDOW.metric,
                _CURATED_ROWS + UNDECIDED_OUTSIDE_LABEL_WINDOW.predicate,
            ),
            (
                "curated rows retired for their date",
                _CURATED_ROWS
                + f"scope_status = 'retired' AND scope_reason LIKE {sql_literal(DATE_RETIRED_PREFIX + '%')}",
            ),
            (
                "curated rows retired as no archaeological site",
                _CURATED_ROWS
                + f"scope_status = 'retired' AND scope_reason LIKE {sql_literal(NOT_A_SITE_PREFIX + '%')}",
            ),
            (
                "curated rows retired as a medieval Old World subject",
                _CURATED_ROWS
                + f"scope_status = 'retired' AND scope_reason LIKE {sql_literal(LABEL_RETIRED_PREFIX + '%')}",
            ),
            _STATUS_WITHOUT_REASON,
            (
                "journal rows for this run that write a status outside retired and in_scope",
                f"FROM remediation_change_log WHERE run_stamp = {stamp} AND "
                "column_name = 'scope_status' AND new_value NOT IN ('retired', 'in_scope')",
            ),
        ],
    )


def name_lane(kind: str, wave: str) -> Lane:
    """`name-clean-<wave>` (D23) or `retarget-name-<wave>` (D13): a rename and its match key."""
    pattern, test_id, label = {
        "name-clean": (NAME_CLEAN_LANE, "D23/name-clean", "D23 name clean"),
        "retarget-name": (RETARGET_NAME_LANE, "D13/retarget-name", "D13 retarget name"),
    }[kind]
    if pattern.match(f"{kind}-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-12 or 2026-10-12b")
    return Lane(
        name=f"{kind}-{wave}",
        key_prefix=f"{kind}-{wave}",
        run_stamp=f"{wave}_mechanical-{kind}",
        test_id=test_id,
        confidence="authoritative",
        label=label,
        plan_table=f"_{kind.replace('-', '_')}_plan",
        out_dir_name=f"{NAME_ROOT}/{kind}/{wave}",
        post_commit_residual=_NAME_KEY_DIFFERS,
        rehearsal_residual=_NAME_KEY_DIFFERS,
        premise_sql=NAME_FIX_PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=NAME_CELLS,
        write_invariant=_NAME_KEY_DIFFERS,
    )


@functools.cache
def name_readback(lane: Lane) -> str:
    """The read-only verification of a name wave: keys, the name journal and the shared keys."""
    return journal_readback(
        lane,
        [
            (_NAME_KEY_DIFFERS.metric, _CURATED_ROWS + _NAME_KEY_DIFFERS.predicate),
            *name_journal_metrics(lane),
            (
                "visible curated rows sharing their name key with another visible curated row",
                f"FROM unified_sites a WHERE a.source_id = 'ancient_nerds' AND {not_retired('a')} "
                "AND EXISTS (SELECT 1 FROM unified_sites b WHERE b.source_id = 'ancient_nerds' AND "
                f"{not_retired('b')} AND b.id <> a.id AND b.name_normalized = a.name_normalized)",
            ),
        ],
    )


_SPOKEN_BROKEN = Residual(
    "curated rows whose spoken_name is blank or longer than the bound",
    f"spoken_name IS NOT NULL AND (length(btrim(spoken_name)) = 0 OR length(spoken_name) > "
    f"{SPOKEN_MAX_CHARS})",
)


def spoken_lane(wave: str) -> Lane:
    """The spoken names of one wave: `spoken_name`, filled where it is NULL."""
    if SPOKEN_LANE.match(f"spoken-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-12 or 2026-10-12b")
    return Lane(
        name=f"spoken-{wave}",
        key_prefix=f"spoken-{wave}",
        run_stamp=f"{wave}_mechanical-spoken",
        test_id="D23/spoken-name",
        confidence="authoritative",
        label="D23 spoken name",
        plan_table="_spoken_plan",
        out_dir_name=f"{SPOKEN_ROOT}/{wave}",
        post_commit_residual=_SPOKEN_BROKEN,
        rehearsal_residual=_SPOKEN_BROKEN,
        premise_sql="u.name",
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(Column("spoken_name", "text", fills_null=True),),
        site_invariants=(
            SiteInvariant(
                says="planned site(s) hold a spoken_name that is blank or too long",
                predicate=(
                    "u.spoken_name IS NULL OR length(btrim(u.spoken_name)) = 0 OR "
                    f"length(u.spoken_name) > {SPOKEN_MAX_CHARS}"
                ),
                probe_column="spoken_name",
                probe_values=(
                    "x" * (SPOKEN_MAX_CHARS + 1),
                    "y" * (SPOKEN_MAX_CHARS + 2),
                    "z" * (SPOKEN_MAX_CHARS + 3),
                ),
            ),
        ),
    )


@functools.cache
def spoken_readback(lane: Lane) -> str:
    """The read-only verification of a spoken-name wave."""
    return journal_readback(
        lane,
        [
            ("curated rows with a spoken_name", _CURATED_ROWS + "spoken_name IS NOT NULL"),
            (_SPOKEN_BROKEN.metric, _CURATED_ROWS + _SPOKEN_BROKEN.predicate),
            (
                "journal rows for this run that overwrite a spoken_name",
                f"FROM remediation_change_log WHERE run_stamp = {sql_literal(lane.run_stamp)} "
                "AND column_name = 'spoken_name' AND old_value IS NOT NULL",
            ),
        ],
    )


# ---------------------------------------------------------------- the un-retire (D58 and D50)
#: The reason prefixes of an un-retirement (`scope_unretire.py` writes the texts): a date
#: retirement the label rule no longer carries, a museum whose exhibits the label rule keeps, a D50
#: mystery site shown as disputed.
D58_REASON_PREFIX = "D58 label rule (owner, 2026-10-24): "
D58_MUSEUM_REASON_PREFIX = "D58 label rule (owner, 2026-10-24), museum rule: "
#: The retirements "under the numeric cut" (D58): the stamps that retired a site by E3's 500 AD for
#: the rest of the world - scope-e4 alone (read on production 2026-10-24: the only stamps that ever
#: wrote `scope_status = retired` are scope-e4, chiapa-hide, scope-review and dup-retire). A D20
#: scope-window wave writes the same `E3: period_start` reason for an OUT_OF_WINDOW verdict, but it
#: judges the source's date under the label window: its retirement is not the numeric cut's, and
#: the un-retire never takes it back.
NUMERIC_CUT_STAMPS = ("2026-09-23_mechanical-scope-e4",)
#: What an un-retirement rests on, as the database prints it: the entry's name, type, point,
#: country and dates (`SCOPE_REVIEW_PREMISE_SQL`'s, which the label rule reads), the md5 of its
#: description and the md5 of its card text - a D50 site is shown only with the dispute text and
#: the card the plan checked, and a text rewritten between plan and apply is refused by guard 5.
SCOPE_UNRETIRE_PREMISE_SQL = (
    SCOPE_REVIEW_PREMISE_SQL.removesuffix(")")
    + ", md5(coalesce(u.description, '')), md5(coalesce((SELECT cs.card_description FROM "
    "card_stats cs WHERE cs.site_id = u.id), '')))"
)


def latest_retirement_stamp_sql(alias: str = "u") -> str:
    """SQL: the run stamp of the latest journal row that wrote `scope_status = retired` for the
    site (NULL when none did)."""
    return (
        "(SELECT l.run_stamp FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
        f"AND l.column_name = 'scope_status' AND l.row_pk = CAST({alias}.id AS text) "
        "AND l.new_value = 'retired' ORDER BY l.id DESC LIMIT 1)"
    )


def numeric_cut_sql(alias: str = "u") -> str:
    """SQL: the site's latest retirement was written under one of `NUMERIC_CUT_STAMPS`."""
    stamps = ", ".join(sql_literal(stamp) for stamp in NUMERIC_CUT_STAMPS)
    return f"coalesce({latest_retirement_stamp_sql(alias)} IN ({stamps}), false)"


def viking_subject_sql(alias: str = "u") -> str:
    """SQL: the site holds a Wikidata item of `dates.VIKING_SUBJECT_QIDS`."""
    from pipeline.normalizers.dates import VIKING_SUBJECT_QIDS

    qids = ", ".join(sql_literal(qid) for qid in sorted(VIKING_SUBJECT_QIDS))
    return (
        f"EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = {alias}.id "
        f"AND e.kind = 'wikidata_qid' AND e.value IN ({qids}))"
    )


def card_cleared_sql(alias: str = "u") -> str:
    """SQL: the site's card asserts nothing the card lane has not judged against the dispute text
    (D50: "no card or page asserts the claim") - it has no card text, or the latest journal row
    that wrote its `card_stats.card_description` comes after the latest journal row that wrote the
    description it holds now."""
    a = alias
    card = (
        "(SELECT max(c.id) FROM remediation_change_log c WHERE c.table_name = 'card_stats' "
        f"AND c.column_name = 'card_description' AND c.row_pk = CAST({a}.id AS text))"
    )
    text = (
        "(SELECT max(d.id) FROM remediation_change_log d WHERE d.table_name = 'unified_sites' "
        f"AND d.column_name = 'description' AND d.row_pk = CAST({a}.id AS text) "
        f"AND d.new_value = {a}.description)"
    )
    no_card = (
        f"NOT EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = {a}.id "
        "AND cs.card_description IS NOT NULL)"
    )
    return f"({no_card} OR coalesce({card} > {text}, false))"


def dispute_enriched_sql(alias: str = "u") -> str:
    """SQL: the site's description is a lane-E dispute enrichment (D21 written for D50): a journal
    row of `unified_sites.description` of this site whose new value is the description as it stands,
    whose evidence is an enrichment's (`wc4.EVIDENCE_DECISION_ENRICH`), carries the adjudicated
    dispute brief and appended a sentence of each position (`wc4.DISPUTE_A`, `wc4.DISPUTE_B`).
    Postgres' `->`/`->>` on the jsonb evidence; SQLite reads the same operators on JSON text, which
    is where the tests evaluate it."""
    from phase4 import wc4

    a = alias
    classes = f"l.evidence->{sql_literal(wc4.ENRICH_EVIDENCE_KEY)}->>'classes'"
    return (
        "EXISTS (SELECT 1 FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
        f"AND l.column_name = 'description' AND l.row_pk = CAST({a}.id AS text) "
        f"AND l.new_value = {a}.description "
        f"AND l.evidence->>'decision' = {sql_literal(wc4.EVIDENCE_DECISION_ENRICH)} "
        f"AND l.evidence->{sql_literal(wc4.ENRICH_EVIDENCE_KEY)}->>'dispute' IS NOT NULL "
        f"AND {classes} LIKE {sql_literal(f'%{chr(34)}{wc4.DISPUTE_A}{chr(34)}%')} "
        f"AND {classes} LIKE {sql_literal(f'%{chr(34)}{wc4.DISPUTE_B}{chr(34)}%')})"
    )


def unretire_violation_sql() -> str:
    """SQL over the written site `u`, TRUE for an un-retired site that rests on nothing: every
    planned site carries one of the three reasons, and what that reason says holds in the same
    transaction -

    * `D58_REASON_PREFIX`: no D50 site, retired by the numeric cut (`numeric_cut_sql`), placed and
      dated, inside the label window, not label-borderline, no Viking subject and of no type that
      asks the not-a-site question first (`NON_SITE_TYPES`);
    * `D58_MUSEUM_REASON_PREFIX`: no D50 site, retired by the numeric cut, a placed Museum whose
      country is not of the medieval Old World;
    * `D50_REASON_PREFIX`: a D50 site whose description is a dispute enrichment and whose card
      was written after it (`card_cleared_sql`)."""
    d50 = d50_site_sql("u")
    non_site = ", ".join(sql_literal(kind) for kind in sorted(NON_SITE_TYPES))
    date_kept = (
        f"(u.scope_reason LIKE {sql_literal(D58_REASON_PREFIX + '%')} AND NOT {d50} "
        f"AND {numeric_cut_sql('u')} AND u.lon IS NOT NULL "
        f"AND {_window_date_sql('u.')} IS NOT NULL "
        f"AND NOT {outside_label_window('u.')} AND NOT {label_borderline_sql('u.')} "
        f"AND NOT {viking_subject_sql('u')} AND coalesce(u.site_type, '') NOT IN ({non_site}))"
    )
    museum_kept = (
        f"(u.scope_reason LIKE {sql_literal(D58_MUSEUM_REASON_PREFIX + '%')} AND NOT {d50} "
        f"AND {numeric_cut_sql('u')} AND u.site_type = 'Museum' AND u.country IS NOT NULL "
        f"AND u.lon IS NOT NULL AND NOT {in_medieval_old_world_sql('u.')})"
    )
    disputed = (
        f"(u.scope_reason LIKE {sql_literal(D50_REASON_PREFIX + '%')} AND {d50} "
        f"AND {dispute_enriched_sql('u')} AND {card_cleared_sql('u')})"
    )
    return f"NOT ({date_kept} OR {museum_kept} OR {disputed})"


def scope_unretire_lane(wave: str) -> Lane:
    """The un-retire's write of one wave (D58, D50): its own stamp, key prefix and directory. The
    one transition is `retired` -> `in_scope` with a new reason; its rollback retires the site
    again with the reason it had."""
    if SCOPE_UNRETIRE_LANE.match(f"scope-unretire-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-24 or 2026-10-24b")
    return Lane(
        name=f"scope-unretire-{wave}",
        key_prefix=f"scope-unretire-{wave}",
        run_stamp=f"{wave}_mechanical-scope-unretire",
        test_id="D58/scope-unretire",
        confidence="authoritative",
        label="D58 D50 scope unretire",
        plan_table="_scope_unretire_plan",
        out_dir_name=f"{SCOPE_UNRETIRE_ROOT}/{wave}",
        post_commit_residual=UNDECIDED_OUTSIDE_LABEL_WINDOW,
        rehearsal_residual=UNDECIDED_OUTSIDE_LABEL_WINDOW,
        premise_sql=SCOPE_UNRETIRE_PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(
            Column("scope_status", "text", allowed_new_values=(IN_SCOPE,)),
            Column("scope_reason", "text"),
        ),
        site_invariants=(
            SiteInvariant(
                says="planned site(s) leave retired without the reason D58 or D50 gives them",
                predicate=unretire_violation_sql(),
                probe_column="scope_reason",
                probe_values=(
                    "a reason that names no rule",
                    "D58 label rule probe",
                    D50_REASON_PREFIX + "a probe on a site without a dispute text",
                ),
            ),
        ),
    )


#: The un-retire's read-back metrics over `unified_sites u`.
_CURATED_U = "FROM unified_sites u WHERE u.source_id = 'ancient_nerds' AND "


@functools.cache
def scope_unretire_readback(lane: Lane) -> str:
    """The read-only verification of an un-retire wave, before and after its write: the scope
    counts, the D58 residual, the date retirements the label window keeps (the wave's own
    population, borderline ones apart), the D50 sites shown and those shown without their dispute
    text (0, always), and the statuses the run wrote."""
    stamp = sql_literal(lane.run_stamp)
    d50 = d50_site_sql("u")
    return journal_readback(
        lane,
        [
            *scope_status_counts(),
            (
                UNDECIDED_OUTSIDE_LABEL_WINDOW.metric,
                _CURATED_ROWS + UNDECIDED_OUTSIDE_LABEL_WINDOW.predicate,
            ),
            (
                "curated rows retired for their date inside the D58 window, not borderline",
                _CURATED_U
                + "u.scope_status = 'retired' AND u.scope_reason LIKE "
                + f"{sql_literal(DATE_RETIRED_PREFIX + '%')} AND NOT {outside_label_window('u.')} "
                + f"AND NOT {label_borderline_sql('u.')}",
            ),
            (
                "curated rows retired for their date that are D58 borderline",
                _CURATED_U
                + "u.scope_status = 'retired' AND u.scope_reason LIKE "
                + f"{sql_literal(DATE_RETIRED_PREFIX + '%')} AND {label_borderline_sql('u.')}",
            ),
            ("curated D50 sites shown", _CURATED_U + f"{d50} AND {not_retired('u')}"),
            (
                "curated D50 sites shown without a dispute-enriched description",
                _CURATED_U + f"{d50} AND {not_retired('u')} AND NOT {dispute_enriched_sql('u')}",
            ),
            (
                "curated D50 sites shown with a card not written after their dispute text",
                _CURATED_U + f"{d50} AND {not_retired('u')} AND NOT {card_cleared_sql('u')}",
            ),
            _STATUS_WITHOUT_REASON,
            (
                "journal rows for this run that write a status other than in_scope",
                f"FROM remediation_change_log WHERE run_stamp = {stamp} AND "
                "column_name = 'scope_status' AND new_value IS DISTINCT FROM 'in_scope'",
            ),
        ],
    )


def lane_of(name: str) -> Lane:
    """`scope-window-2026-10-12`, `scope-unretire-...`, `name-clean-...`, `retarget-name-...` or
    `spoken-...` -> the lane; `KeyError` for any other name."""
    for pattern, build in (
        (SCOPE_WINDOW_LANE, scope_window_lane),
        (SCOPE_UNRETIRE_LANE, scope_unretire_lane),
        (SPOKEN_LANE, spoken_lane),
        (NAME_CLEAN_LANE, lambda wave: name_lane("name-clean", wave)),
        (RETARGET_NAME_LANE, lambda wave: name_lane("retarget-name", wave)),
    ):
        found = pattern.match(name)
        if found is not None:
            return build(found.group(1))
    raise KeyError(name)


def readback(lane: Lane) -> str:
    """The read-only verification text of any lane of this module."""
    if SCOPE_WINDOW_LANE.match(lane.name):
        return scope_window_readback(lane)
    if SCOPE_UNRETIRE_LANE.match(lane.name):
        return scope_unretire_readback(lane)
    if SPOKEN_LANE.match(lane.name):
        return spoken_readback(lane)
    if NAME_CLEAN_LANE.match(lane.name) or RETARGET_NAME_LANE.match(lane.name):
        return name_readback(lane)
    raise KeyError(lane.name)
