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
  an alias in `name-alias-<wave>`, a chunk of the shared writer (`identity.name_write`);
* `spoken-<wave>` (D23) - `unified_sites.spoken_name` (migration 0029), filled where it is NULL, on
  the premise of the name it was derived from. A spoken name is never blank and never longer than
  `SPOKEN_MAX_CHARS`.

`mechanical.lane.resolve_lane` reaches these lazily (`lane_of`), like the other wave families.
"""

from __future__ import annotations

import functools
import re

from mechanical.lane import (
    _CURATED_ROWS,
    _NAME_KEY_DIFFERS,
    _STATUS_WITHOUT_REASON,
    _UNDECIDED_OUT_OF_WINDOW_O7,
    LOCK_TIMEOUT,
    NAME_CELLS,
    NAME_FIX_PREMISE_SQL,
    NOT_A_SITE_PREFIX,
    SCOPE_REVIEW_PREMISE_SQL,
    STATEMENT_TIMEOUT,
    UNIFIED_SITES,
    Column,
    Lane,
    Residual,
    SiteInvariant,
    journal_readback,
    name_journal_metrics,
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
#: The lane families of this module, for `resolve_lane` and the read-back choice.
LANE_PATTERNS = (SCOPE_WINDOW_LANE, NAME_CLEAN_LANE, RETARGET_NAME_LANE, SPOKEN_LANE)

SCOPE_WINDOW_ROOT = "mechanical_scope_window"
NAME_ROOT = "mechanical_names"
SPOKEN_ROOT = "mechanical_spoken"
#: The reason prefix of a retirement for the date (`E3: period_start N is past the cutoff; <quote>`).
DATE_RETIRED_PREFIX = "E3: period_start"
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
        post_commit_residual=_UNDECIDED_OUT_OF_WINDOW_O7,
        rehearsal_residual=_UNDECIDED_OUT_OF_WINDOW_O7,
        premise_sql=SCOPE_REVIEW_PREMISE_SQL,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        cells=(
            Column("scope_status", "text", allowed_new_values=(RETIRED, IN_SCOPE), fills_null=True),
            Column("scope_reason", "text", fills_null=True),
        ),
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
                _UNDECIDED_OUT_OF_WINDOW_O7.metric,
                _CURATED_ROWS + _UNDECIDED_OUT_OF_WINDOW_O7.predicate,
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


def lane_of(name: str) -> Lane:
    """`scope-window-2026-10-12`, `name-clean-...`, `retarget-name-...` or `spoken-...` -> the
    lane; `KeyError` for any other name."""
    for pattern, build in (
        (SCOPE_WINDOW_LANE, scope_window_lane),
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
    if SPOKEN_LANE.match(lane.name):
        return spoken_readback(lane)
    if NAME_CLEAN_LANE.match(lane.name) or RETARGET_NAME_LANE.match(lane.name):
        return name_readback(lane)
    raise KeyError(lane.name)
