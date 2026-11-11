"""The write lanes of the identity package (final repair 2026-10-08): scope window, names, spoken names.

Six lane families, each a wave of at most 100 sites with a run stamp of its own (`<wave>` is a date
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
* `scope-unretire-<wave>` (D58, D50 and D57) - `scope_status` and `scope_reason` of a retired site,
  back to `in_scope` (`mechanical/scope_unretire.py` plans it): a date retirement the label rule no
  longer carries, a D50 mystery site once its description is a lane-E dispute enrichment, and a
  staged D57 insert once it holds a checked description and a confirmed picture (O12). The premise
  holds the description and the picture too, and an invariant checks in the transaction that every
  un-retired site carries one of the reasons and what that reason rests on;
* `country-d84-<wave>` (D84 and D149) - `country` of a site D84 leaves without one, emptied while
  the site is retired (`mechanical/country_d84.py` plans it). The premise holds the scope status,
  so the lane's apply and its `ROLLBACK.sql` both refuse a shown site: the un-retire shows such a
  site only without a country, and the country comes back only after the site is retired again.

`mechanical.lane.resolve_lane` reaches these lazily (`lane_of`), like the other wave families.
"""

from __future__ import annotations

import functools
import re

from mechanical.lane import (
    _CARD_COUNTRY,
    _CURATED_ROWS,
    _NAME_KEY_DIFFERS,
    _STATUS_WITHOUT_REASON,
    D50_NOT_RETIRED,
    D50_REASON_PREFIX,
    D57_STAGED_PREFIX,
    D84_NO_COUNTRY_SITES,
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
    _country_rows,
    _window_date_sql,
    d50_site_sql,
    d57_staged_sql,
    d84_site_sql,
    journal_readback,
    label_borderline_sql,
    label_cutoff_sql,
    name_journal_metrics,
    outside_label_window,
    scope_status_counts,
    sql_literal,
)
from pipeline.normalizers.dates import LABEL_CUTOFF_REST_OF_WORLD
from pipeline.utils.card_provenance import CARD_PROVENANCE_KEY
from pipeline.utils.public_sites import RETIRED, not_retired

IN_SCOPE = "in_scope"
WAVE = r"(\d{4}-\d{2}-\d{2}[a-z]?)"
SCOPE_WINDOW_LANE = re.compile(rf"^scope-window-{WAVE}\Z")
NAME_CLEAN_LANE = re.compile(rf"^name-clean-{WAVE}\Z")
RETARGET_NAME_LANE = re.compile(rf"^retarget-name-{WAVE}\Z")
SPOKEN_LANE = re.compile(rf"^spoken-{WAVE}\Z")
SCOPE_UNRETIRE_LANE = re.compile(rf"^scope-unretire-{WAVE}\Z")
COUNTRY_D84_LANE = re.compile(rf"^country-d84-{WAVE}\Z")
#: The lane families of this module, for `resolve_lane` and the read-back choice.
LANE_PATTERNS = (
    SCOPE_WINDOW_LANE,
    NAME_CLEAN_LANE,
    RETARGET_NAME_LANE,
    SPOKEN_LANE,
    SCOPE_UNRETIRE_LANE,
    COUNTRY_D84_LANE,
)

SCOPE_WINDOW_ROOT = "mechanical_scope_window"
NAME_ROOT = "mechanical_names"
SPOKEN_ROOT = "mechanical_spoken"
SCOPE_UNRETIRE_ROOT = "mechanical_scope_unretire"
COUNTRY_D84_ROOT = "mechanical_country_d84"
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


# ---------------------------------------------------------- the un-retire (D58, D50 and D57)
#: The reason prefixes of an un-retirement (`scope_unretire.py` writes the texts): a date
#: retirement the label rule no longer carries, a museum whose exhibits the label rule keeps, a D50
#: mystery site shown as disputed, a staged D57 insert shown with its text and its picture.
D58_REASON_PREFIX = "D58 label rule (owner, 2026-10-24): "
D58_MUSEUM_REASON_PREFIX = "D58 label rule (owner, 2026-10-24), museum rule: "
#: Owner decision D143 and orchestrator decision O12 (2026-11-10): a site of the D57 insert is
#: created hidden and shown only with a description and a confirmed picture. It does not begin
#: with `D57_STAGED_PREFIX`: a shown site is no staged one for any lane.
D57_REASON_PREFIX = "D57 new site (owner D143, O12 of 2026-11-10): "
#: The wave delivered before the D57 class existed (applied 2026-10-24). Its committed APPLY.sql
#: and ROLLBACK.sql must stay what its plan renders - `apply.py --rehearse-rollback` and the
#: rollback itself verify the file against the lane - so it keeps the premise and the invariant it
#: was applied with (`scope_unretire_lane`).
WAVES_BEFORE_D57 = frozenset({"2026-10-24"})
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
#: the card the plan checked (none, or one the card lane judged against that text), and a text
#: rewritten or a cleared card put back between plan and apply is refused by guard 5.
#: This is the premise of the wave delivered before the D57 class (`WAVES_BEFORE_D57`).
_PREMISE_BEFORE_D57 = (
    SCOPE_REVIEW_PREMISE_SQL.removesuffix(")")
    + ", md5(coalesce(u.description, '')), md5(coalesce((SELECT cs.card_description FROM "
    "card_stats cs WHERE cs.site_id = u.id), '')))"
)


def live_hero_sql(alias: str = "u") -> str:
    """SQL condition on an image row `w`: it is a live hero row of the site - the hero flag on a
    row that is not excluded (`import_hero.verify.live_heroes`)."""
    return f"w.site_id = {alias}.id AND w.is_hero IS TRUE AND w.is_excluded IS NOT TRUE"


#: The premise in force: the same, and the picture a staged D57 site is shown with - its
#: `thumbnail_url` and the files of its live hero rows. A picture moved between plan and apply is
#: refused by guard 5 like a rewritten text (for a site of any class: a lane has one premise).
SCOPE_UNRETIRE_PREMISE_SQL = (
    _PREMISE_BEFORE_D57.removesuffix(")")
    + ", coalesce(u.thumbnail_url, 'NULL'), coalesce((SELECT string_agg(w.filename, ' ; ' "
    f"ORDER BY w.filename) FROM wiki_images w WHERE {live_hero_sql('u')}), 'NULL'))"
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


def card_judged_sql(alias: str = "u") -> str:
    """SQL: the card lane judged the card text the site holds against the description it holds -
    the site's teaser provenance (`raw_data._card_provenance`, which lane WB writes beside every
    card it writes: `pipeline.utils.card_provenance`) hashes the live card (`text_sha256`) and the
    live description (`desc_sha256`, "the description the card was written from and checked
    against"). The order of the journal rows proves nothing of that: the reversal of a card clear
    is a later row than the dispute text and puts back the card of before it (review of
    2026-11-11) - a card no teaser run wrote has no provenance, and one a teaser run wrote before
    the dispute text has a provenance that hashes the description of before. A site without a
    card text, or without a provenance, answers FALSE, never NULL."""
    a = alias
    provenance = f"{a}.raw_data->{sql_literal(CARD_PROVENANCE_KEY)}"
    return (
        f"EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = {a}.id "
        "AND encode(sha256(convert_to(cs.card_description, 'UTF8')), 'hex') = "
        f"{provenance}->>'text_sha256' "
        f"AND encode(sha256(convert_to(coalesce({a}.description, ''), 'UTF8')), 'hex') = "
        f"{provenance}->>'desc_sha256')"
    )


def card_cleared_sql(alias: str = "u") -> str:
    """SQL: no card of the site asserts the claim (D50: "no card or page asserts the claim") - it
    holds no card text (O17: the six cards are cleared the D47 way, `teaser.py d50-clear`), or the
    card lane judged the card it holds against the description it holds (`card_judged_sql`),
    which the D50 gate beside this test proves to be the dispute text (`dispute_enriched_sql`):
    a card judged against the description of before that text passes only until the text is
    written (Richat's teaser card, read 2026-11-11, hashes the description the site holds today,
    which is no dispute text yet). No card run asks a retired site, so once the six hold their
    dispute text the second leg is a shown site's - the card a later run writes for it. A cleared
    card that an undo put back passes neither leg."""
    no_card = (
        f"NOT EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = {alias}.id "
        "AND cs.card_description IS NOT NULL)"
    )
    return f"({no_card} OR {card_judged_sql(alias)})"


def dispute_enriched_sql(alias: str = "u") -> str:
    """SQL: the site's description is a lane-E dispute enrichment (D21 written for D50) that names
    both positions: a journal row of `unified_sites.description` of this site whose new value is
    the description as it stands, whose evidence is an enrichment's
    (`wc4.EVIDENCE_DECISION_ENRICH`) and carries the adjudicated dispute brief; and the public
    record that run left on the site (`raw_data._description_enrichment`, tied to the journal row
    by its `run`) **kept** a sentence of each position (`wc4.DISPUTE_A`, `wc4.DISPUTE_B`). Kept, not
    written: the import and each verifier drop sentence by sentence, and a text that names one
    position is none D21 allows. The record holds class and verdict of every appended sentence
    side by side, so it is read by position, up to the most an enrichment appends
    (`enrich.MAX_APPENDED`; a sentence beyond it would not count, which refuses). Every test
    stands in the one WHERE, so a site without a record answers FALSE, never NULL. Postgres'
    `->`/`->>` on jsonb; SQLite reads the same operators on JSON text, which is where the tests
    evaluate it."""
    from phase4 import wc4
    from wc import enrich

    a = alias
    record = f"{a}.raw_data->{sql_literal(wc4.ENRICH_KEY)}"
    keep = sql_literal(wc4.Verdict.KEEP.value)

    def kept(position: str) -> str:
        return (
            "("
            + " OR ".join(
                f"({record}->'sentences'->{index}->>'class' = {sql_literal(position)} "
                f"AND {record}->'sentences'->{index}->>'verdict' = {keep})"
                for index in range(enrich.MAX_APPENDED)
            )
            + ")"
        )

    return (
        "EXISTS (SELECT 1 FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
        f"AND l.column_name = 'description' AND l.row_pk = CAST({a}.id AS text) "
        f"AND l.new_value = {a}.description "
        f"AND l.evidence->>'decision' = {sql_literal(wc4.EVIDENCE_DECISION_ENRICH)} "
        f"AND l.evidence->{sql_literal(wc4.ENRICH_EVIDENCE_KEY)}->>'dispute' IS NOT NULL "
        f"AND l.evidence->>'run' = {record}->>'run' "
        f"AND {kept(wc4.DISPUTE_A)} "
        f"AND {kept(wc4.DISPUTE_B)})"
    )


def description_checked_sql(alias: str = "u") -> str:
    """SQL: the site holds a description that is not blank and that its check record
    (`wc4.CHECK_KEY`) or its provenance (`model4.PROVENANCE_KEY`) hashes - the text a lane wrote
    and checked, not one edited since (`desc_sha256`, the sha256 of the UTF-8 text). `trim` and the
    `->`/`->>` operators read the same in SQLite, where the tests evaluate it over JSON text."""
    from phase4 import wc4

    a = alias
    sha = f"encode(sha256(convert_to({a}.description, 'UTF8')), 'hex')"
    recorded = " OR ".join(
        f"({a}.raw_data -> {sql_literal(key)} ->> 'desc_sha256') = {sha}"
        for key in (wc4.CHECK_KEY, wc4.M.PROVENANCE_KEY)
    )
    return f"(trim(coalesce({a}.description, '')) <> '' AND coalesce({recorded}, false))"


def picture_confirmed_sql(alias: str = "u") -> str:
    """SQL: the site has exactly one live hero row (`live_hero_sql`) and its `thumbnail_url` names
    that row's local file (`hero_repair.thumbnail.local_path`: the directory is the first eight
    characters of the site id) - the picture the image lane wrote, on the page and on the globe."""
    a = alias
    live = f"FROM wiki_images w WHERE {live_hero_sql(a)}"
    path = f"'/data/images/wiki/' || substr(CAST({a}.id AS text), 1, 8) || '/' || w.filename"
    return (
        f"((SELECT count(*) {live}) = 1 "
        f"AND EXISTS (SELECT 1 {live} AND {a}.thumbnail_url = {path}))"
    )


def staged_before_sql(alias: str = "u") -> str:
    """SQL: the reason the site holds was written over a staged one - the latest journal row of its
    `scope_reason` wrote the reason it holds now and replaced one that begins `D57_STAGED_PREFIX`
    (the un-retirement's own row: the invariant reads it inside the write's transaction)."""
    a = alias
    return (
        f"coalesce((SELECT r.new_value = {a}.scope_reason AND r.old_value LIKE "
        f"{sql_literal(D57_STAGED_PREFIX + '%')} FROM remediation_change_log r "
        "WHERE r.table_name = 'unified_sites' AND r.column_name = 'scope_reason' "
        f"AND r.row_pk = CAST({a}.id AS text) ORDER BY r.id DESC LIMIT 1), false)"
    )


def _disputed_as_applied_before_d57(d50: str) -> str:
    """The D50 leg of the invariant exactly as the wave of `WAVES_BEFORE_D57` was applied with it
    (2026-10-24): the card test by journal order and the dispute test by the journal row's
    classes, as `card_cleared_sql` and `dispute_enriched_sql` read until the D50 review of
    2026-11-11, and no D84 gate. Frozen text, never edited: that wave's committed `APPLY.sql` and
    `ROLLBACK.sql` are verified against what the lane renders (`--rehearse-rollback`); a wave planned
    since uses the tests of today (`unretire_violation_sql`)."""
    from phase4 import wc4

    card = (
        "(SELECT max(c.id) FROM remediation_change_log c WHERE c.table_name = 'card_stats' "
        "AND c.column_name = 'card_description' AND c.row_pk = CAST(u.id AS text))"
    )
    text = (
        "(SELECT max(d.id) FROM remediation_change_log d WHERE d.table_name = 'unified_sites' "
        "AND d.column_name = 'description' AND d.row_pk = CAST(u.id AS text) "
        "AND d.new_value = u.description)"
    )
    no_card = (
        "NOT EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = u.id "
        "AND cs.card_description IS NOT NULL)"
    )
    cleared = f"({no_card} OR coalesce({card} > {text}, false))"
    key = sql_literal(wc4.ENRICH_EVIDENCE_KEY)
    classes = f"l.evidence->{key}->>'classes'"
    enriched = (
        "EXISTS (SELECT 1 FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
        "AND l.column_name = 'description' AND l.row_pk = CAST(u.id AS text) "
        "AND l.new_value = u.description AND l.evidence->>'decision' = "
        f"{sql_literal(wc4.EVIDENCE_DECISION_ENRICH)} AND l.evidence->{key}->>'dispute' IS NOT NULL "
        f"AND {classes} LIKE {sql_literal(f'%{chr(34)}{wc4.DISPUTE_A}{chr(34)}%')} "
        f"AND {classes} LIKE {sql_literal(f'%{chr(34)}{wc4.DISPUTE_B}{chr(34)}%')})"
    )
    return (
        f"(u.scope_reason LIKE {sql_literal(D50_REASON_PREFIX + '%')} AND {d50} "
        f"AND {enriched} AND {cleared})"
    )


def unretire_violation_sql(*, d57: bool = True) -> str:
    """SQL over the written site `u`, TRUE for an un-retired site that rests on nothing: every
    planned site carries one of the reasons, and what that reason says holds in the same
    transaction -

    * `D58_REASON_PREFIX`: no D50 site, retired by the numeric cut (`numeric_cut_sql`), placed and
      dated, inside the label window, not label-borderline, no Viking subject and of no type that
      asks the not-a-site question first (`NON_SITE_TYPES`);
    * `D58_MUSEUM_REASON_PREFIX`: no D50 site, retired by the numeric cut, a placed Museum whose
      region has the 1500 AD cutoff (Oceania, the Americas or a recognised country of the rest of
      the world - never the medieval Old World or a country no list recognises);
    * `D50_REASON_PREFIX`: a D50 site whose description is a dispute enrichment and which holds
      no card text, or one the card lane judged against that description (`card_cleared_sql`) -
      and, for a site D84 leaves without a country (`lane.D84_NO_COUNTRY_SITES`, the Baltic Sea
      Anomaly), no country: shown with one it would get a country page and a `/sites/` route,
      which D149 rules out;
    * `D57_REASON_PREFIX` (`d57`; not in the text of a wave of `WAVES_BEFORE_D57`): no D50 site,
      staged until this write (`staged_before_sql`), with a checked description
      (`description_checked_sql`) and a confirmed picture (`picture_confirmed_sql`)."""
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
        f"AND {numeric_cut_sql('u')} AND u.site_type = 'Museum' AND u.lon IS NOT NULL "
        f"AND {label_cutoff_sql('u.')} = {LABEL_CUTOFF_REST_OF_WORLD})"
    )
    disputed = (
        f"(u.scope_reason LIKE {sql_literal(D50_REASON_PREFIX + '%')} AND {d50} "
        f"AND (u.country IS NULL OR NOT {d84_site_sql('u')}) "
        f"AND {dispute_enriched_sql('u')} AND {card_cleared_sql('u')})"
    )
    if not d57:
        return f"NOT ({date_kept} OR {museum_kept} OR {_disputed_as_applied_before_d57(d50)})"
    shown = (
        f"(u.scope_reason LIKE {sql_literal(D57_REASON_PREFIX + '%')} AND NOT {d50} "
        f"AND {staged_before_sql('u')} "
        f"AND {description_checked_sql('u')} "
        f"AND {picture_confirmed_sql('u')})"
    )
    return f"NOT ({date_kept} OR {museum_kept} OR {disputed} OR {shown})"


def scope_unretire_lane(wave: str) -> Lane:
    """The un-retire's write of one wave (D58, D50, D57): its own stamp, key prefix and directory.
    The one transition is `retired` -> `in_scope` with a new reason; its rollback retires the site
    again with the reason it had. A wave of `WAVES_BEFORE_D57` keeps the text it was applied
    with."""
    if SCOPE_UNRETIRE_LANE.match(f"scope-unretire-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-24 or 2026-10-24b")
    d57 = wave not in WAVES_BEFORE_D57
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
        premise_sql=SCOPE_UNRETIRE_PREMISE_SQL if d57 else _PREMISE_BEFORE_D57,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(
            Column("scope_status", "text", allowed_new_values=(IN_SCOPE,)),
            Column("scope_reason", "text"),
        ),
        site_invariants=(
            SiteInvariant(
                says=(
                    "planned site(s) leave retired without the reason D58, D50 or D57 gives them"
                    if d57
                    else "planned site(s) leave retired without the reason D58 or D50 gives them"
                ),
                predicate=unretire_violation_sql(d57=d57),
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
    text, with a card the card lane did not judge against it or with a country D84 takes from
    them (0, always), the D57 sites still staged, those shown and those shown without a checked
    description or a confirmed picture, and the statuses the run wrote."""
    stamp = sql_literal(lane.run_stamp)
    d50 = d50_site_sql("u")
    d57_shown = f"{not_retired('u')} AND u.scope_reason LIKE {sql_literal(D57_REASON_PREFIX + '%')}"
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
                "curated D50 sites shown with a card not judged against their dispute text",
                _CURATED_U + f"{d50} AND {not_retired('u')} AND NOT {card_cleared_sql('u')}",
            ),
            ("curated D57 sites staged, not shown yet", _CURATED_U + d57_staged_sql("u")),
            ("curated D57 sites shown by the un-retire", _CURATED_U + d57_shown),
            (
                "curated D57 sites shown without a checked description",
                _CURATED_U + f"{d57_shown} AND NOT {description_checked_sql('u')}",
            ),
            (
                "curated D57 sites shown without a confirmed picture",
                _CURATED_U + f"{d57_shown} AND NOT {picture_confirmed_sql('u')}",
            ),
            (
                "curated sites D84 leaves without a country shown with one",
                _CURATED_U
                + f"{d84_site_sql('u')} AND {not_retired('u')} AND u.country IS NOT NULL",
            ),
            _STATUS_WITHOUT_REASON,
            (
                "journal rows for this run that write a status other than in_scope",
                f"FROM remediation_change_log WHERE run_stamp = {stamp} AND "
                "column_name = 'scope_status' AND new_value IS DISTINCT FROM 'in_scope'",
            ),
        ],
    )


# ------------------------------------------------- the D84 country lane (D84 and D149, 2026-11-11)
COUNTRY_D84_TEST_ID = "D84/country"
_D84_COUNTRY_HELD = Residual(
    "curated rows D84 leaves without a country that still hold one",
    f"({d84_site_sql('unified_sites')} AND country IS NOT NULL)",
)
#: What the D84 write rests on, as the database prints it: the row is the site the owner named,
#: where it lies - and it is retired. The scope status makes the order a guard (guard 5, on the
#: apply and on the reversal alike): the cell is emptied while the site is retired, and
#: `ROLLBACK.sql` gives the country back only to a site that is retired again - run before the
#: un-retire wave's own `ROLLBACK.sql` it is refused, so no file of the lane leaves a D84 site
#: shown with a country (review of 2026-11-11). `concat_ws` and the `coalesce`s keep the premise
#: from ever being NULL.
COUNTRY_D84_PREMISE_SQL = (
    "concat_ws(' | ', u.name, coalesce(u.lat::text, 'NULL'), coalesce(u.lon::text, 'NULL'), "
    "coalesce(u.scope_status, 'NULL'))"
)


def country_d84_lane(wave: str) -> Lane:
    """The D84 country lane of one wave (`country_d84.py --write --wave <wave>`): a cell lane,
    because it empties its column (`Column.clears`) - a column lane owns values and never writes
    NULL. It owns no value: the one thing it writes is "no country", onto the sites of
    `D84_NO_COUNTRY_SITES` and no other, which its invariant checks inside the transaction (a NULL
    is nothing guard 4 could own). A wave like every lane of this module: a stamp is applied once
    and a lane that has written is never re-planned, so a write that was undone (the un-retire
    wave's `ROLLBACK.sql`, then this lane's) is made again under the next label - one fixed stamp
    would leave D84 unwritable after its first undo (review of 2026-11-11)."""
    if COUNTRY_D84_LANE.match(f"country-d84-{wave}") is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-11-11 or 2026-11-11b")
    return Lane(
        name=f"country-d84-{wave}",
        key_prefix=f"country-d84-{wave}",
        run_stamp=f"{wave}_mechanical-country-d84",
        test_id=COUNTRY_D84_TEST_ID,
        confidence="authoritative",
        label="D84 country emptied",
        plan_table="_country_d84_plan",
        out_dir_name=f"{COUNTRY_D84_ROOT}/{wave}",
        post_commit_residual=_D84_COUNTRY_HELD,
        rehearsal_residual=_D84_COUNTRY_HELD,
        premise_sql=COUNTRY_D84_PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(Column("country", "character varying", max_chars=100, clears=True),),
        site_invariants=(
            SiteInvariant(
                says="planned site(s) keep a country, or are none D84 leaves without one",
                predicate=f"u.country IS NOT NULL OR NOT {d84_site_sql('u')}",
                probe_column="country",
                probe_values=("Sweden", "Finland", "International waters"),
            ),
        ),
    )


@functools.cache
def country_d84_readback(lane: Lane) -> str:
    """The read-only verification of a D84 country wave, before and after its write: the D84 rows
    that still hold a country, the curated rows without one, the shown ones D84 does not name,
    the rows of the country it empties and the cards whose civilization differs."""
    return journal_readback(
        lane,
        [
            (_D84_COUNTRY_HELD.metric, _CURATED_ROWS + _D84_COUNTRY_HELD.predicate),
            ("curated rows without a country", _CURATED_ROWS + "country IS NULL"),
            (
                "curated shown rows without a country that D84 does not name",
                _CURATED_ROWS
                + f"country IS NULL AND {not_retired('unified_sites')} "
                + f"AND NOT {d84_site_sql('unified_sites')}",
            ),
            *_country_rows(sorted({held for _name, held in D84_NO_COUNTRY_SITES.values()})),
            _CARD_COUNTRY,
        ],
    )


def lane_of(name: str) -> Lane:
    """`scope-window-2026-10-12`, `scope-unretire-...`, `country-d84-...`, `name-clean-...`,
    `retarget-name-...` or `spoken-...` -> the lane; `KeyError` for any other name."""
    for pattern, build in (
        (SCOPE_WINDOW_LANE, scope_window_lane),
        (SCOPE_UNRETIRE_LANE, scope_unretire_lane),
        (COUNTRY_D84_LANE, country_d84_lane),
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
    if COUNTRY_D84_LANE.match(lane.name):
        return country_d84_readback(lane)
    if SPOKEN_LANE.match(lane.name):
        return spoken_readback(lane)
    if NAME_CLEAN_LANE.match(lane.name) or RETARGET_NAME_LANE.match(lane.name):
        return name_readback(lane)
    raise KeyError(lane.name)
