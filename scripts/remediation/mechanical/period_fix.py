"""Owner decisions D121, D122, D124 and D136/D137 (2026-11-07) and D20 (2026-10-08): journalled
corrections of curated `period_start`.

## What is corrected

* **D121** - the 166 sites of `output/remediation/fields/D113_CONFLICT_LIST.jsonl`: a current year that
  came from a bare period word under the old fixed table, which the regional table
  (`pipeline/periods.py`, D101/D111/D113/D123) now answers differently. Each is recomputed from its
  stored word and the site's country: a year (`d121-regional`) or none (`d121-no-year`, Undated).
  Recomputation only, no model.
* **D122** - every curated site whose current `period_start` is still the one the old WD3 site_type
  rule wrote (`WD3 decision (derived, ...)`, evidence `status: RULE`; counted 301 on 2026-11-07, as
  the wave-4 checker counted them): no source dates it, so D12 ("unsourced -> Undated") applies
  (`d122-unsourced`). A site of the D113 list that is also such a row is D122's: a regional year
  recomputed from a word the site_type rule chose is still a year no source stands behind.
* **D124** - one cited start from a released re-ask (`--cited`): a decision file whose every line
  names the site, the year the answer cites and the quote it rests on (`d124-cited`).
* **D136/D137** - the predefined period bands (`--bands`, `output/remediation/fields/epoch_bands/
  CANDIDATES.jsonl` of `fields/epoch_bands.py`): an undated site whose own sources, Wikidata P2348 or
  name give an epoch takes the band that epoch begins in and stores the band's edge (`bucket_edge`,
  as the 511 `via: "band"` rows of 2026-10-04: `d136-band`); where the site's own source states a
  year or century for it, that year's band wins and its edge is stored (`d137-year`). Only `band`
  rows are written; a `scope-hold` row is read too, so the D58 precheck lists it as `d58-window`.
* **D138** - the `year-stated-only` rows of the same file (`--years`): a site with no epoch whose own
  source states a year takes the band of the earliest year it states and stores the band's edge
  (`d138-year`, the D137 year rule), with the sentence that states it as evidence. An obvious reading
  error (D137: a year that is not the site's own) is listed, not written (`D138_READING_ERRORS`).
* **D20** - the corrected starts of the scope window (`--d20`, the `PERIOD_WRONG.jsonl` a planned
  `scope-window-<wave>` hands over, `identity/scope_judge.py`): a site the web answer kept in scope
  on a sourced start other than the stored one takes that year (`d20-sourced`), with the D20
  decision, the answer's found quotes, its agent and its model as evidence. A row is written only
  where the scope wave's `in_scope` is in production (`d20-scope-not-written`: that write comes
  first, its premise is the stored period), the site still holds the start the answer judged
  (`moved-since-answer`) and one of the found quotes states the year itself as a date
  (`states_date`: `fields.answers.states_year`, the fields lanes' gate, read as the dating
  extractor reads a number - "300 metres", "Population 1200" and "Page 450" state no year:
  `d20-no-quote-states-year`). A start of 500-1500 in a label-borderline country is written where
  the answer was asked the label question (the row's `label_borderline`, D58: its subject is
  decided), and listed `d58-window` where not. The scope wave's `ROLLBACK.sql` is conditioned on
  the stored period as its write is (guard 5), so a D20 step is undone before the scope wave it
  follows (runbook WD2 1b).

Undated is the residue rung (`residue_period.py`): `period_start` NULL and `period_name` `Undated`.
The D58 window includes a record without a date (`pipeline.normalizers.dates.passes_date_cutoff`), so
making a site undated never retires it; a new year is refused when it would move the site out of the
window or make it a label borderline case (`fields.dating.scope_problem`, O1).

## How a site is decided (`derive`, then again per step)

1. The newest journal row of the site's `period_start` must end at the live value (`journal_break`).
2. D122: that row is the WD3 site_type rule's and the live value is its `new_value`.
3. D121: the list's `current` is the live value and its `journal_id` the newest journal row; the
   word recomputed now must give the list's `new_regional_start` (a table that moved since the
   list is refused, not followed).
4. A year must pass the D58 precheck; `period_end` must be empty (O1: all 5,004 are).

## The write

`period-fix-<wave>-sNNN`, a cell lane on `unified_sites` (`period_start`, `period_name`) of at most
100 sites a step (D8), under its own run stamp. Guard 3 holds the old values the step read; the
site invariant of the fields lanes holds `period_name` = the bucket of `period_start` (Undated with
none) inside the transaction.

    M=scripts/remediation/mechanical
    $M/period_fix.py wave   --wave W [--d113 FILE] [--cited FILE]   (read-only; WAVE.json, steps of 100)
    $M/period_fix.py wave   --wave W --no-d113 --bands CANDIDATES.jsonl                   (D136/D137)
    $M/period_fix.py wave   --wave W --no-d113 --years CANDIDATES.jsonl                   (D138)
    $M/period_fix.py wave   --wave W --no-d113 --d20 PERIOD_WRONG.jsonl                   (D20)
    $M/period_fix.py step   --wave W --step N                       (read-only; PLAN.jsonl, ROLLBACK.sql)
    $M/apply.py --lane period-fix-W-sNNN --emit | --verify | --rehearse | --probe-guards | --apply
    $M/apply.py --lane period-fix-W-sNNN --rehearse-rollback
    $M/period_fix.py accept --wave W --step N                       (read-only; 0 deviations)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import dates  # noqa: E402
from fields.answers import states_bp, states_year  # noqa: E402
from fields.dating import acceptable, scope_problem  # noqa: E402

from mechanical.field_prov import read_production, sha256_file, step_name  # noqa: E402
from mechanical.identity_lanes import IN_SCOPE  # noqa: E402
from mechanical.lane import (  # noqa: E402
    _CURATED_ROWS,
    _PERIOD_MISMATCH,
    FIELDS_CELLS_WD5,
    FIELDS_INVARIANTS,
    LOCK_TIMEOUT,
    PERIOD_FIX_LANE,
    STATEMENT_TIMEOUT,
    Lane,
    journal_readback,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    journal_break,
    parse_tagged_export,
    sql_ids,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline import periods as P  # noqa: E402
from pipeline.normalizers.dates import label_borderline  # noqa: E402
from pipeline.utils.text import UNDATED, bucket_edge, categorize_period  # noqa: E402

ROOT_NAME = "mechanical_period_fix"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
D113_LIST = REPO / "output" / "remediation" / "fields" / "D113_CONFLICT_LIST.jsonl"
MAX_SITES = 100
WAVE_FILE, WAVE_PIN_FILE, ACCEPTED_FILE = "WAVE.json", "WAVE.sha256", "ACCEPTED.json"
DECISIONS = "output/remediation/OWNER_DECISIONS_2026-10-08.md"
D121_QUOTE = (
    "| D121 | The 166 period-word years of D113_CONFLICT_LIST | **Correct them** (rec): 69 get the "
    "regional year, 97 become undated; recomputation only, journalled wave. |"
)
D122_QUOTE = (
    "| D122 | The 301 rule-made years without a source (old site_type rule, D12) | **Reset to "
    "undated** (rec), in the same journalled run as D121. |"
)
D124_QUOTE = (
    "| D124 | Dating of the remaining ~430 sites | **Stop here** (rec); only Eddisbury Hill Fort gets "
    "its cited radiocarbon start (12th c. BC) through a 1-2 answer re-ask. |"
)
#: The site_type rule's journal evidence: `WD3 decision (derived, round 0, rule:derived_rule.json)`.
_DERIVED = re.compile(r"^WD3 decision \(derived, ")
D136_QUOTE = (
    "| D136 | Sites whose only dating is an epoch word | **Use the predefined period bands**: every "
    "epoch maps to the band in which it begins (in the site's country where REGIONAL_STARTS has a "
    "value); the stored year is the band's edge (`bucket_edge`). |"
)
D137_QUOTE = (
    '| D137 | D136 details after the spot checks | **Write all bands now** (owner: "Egal, '
    'schreiben"). A century/year the site\'s own source states for the site wins over the epoch '
    "start (rec). A coarse word is read together with the site's own monument type. |"
)
D138_QUOTE = (
    "| D138 | (2026-11-07) The 60 year-stated-only sites of the D137 refine (year from the site's own "
    "source, mostly the stored description) and the 2 scope-hold sites | **Write the 60** as the band "
    'of their stated year (owner: "die 60 sites ja"); **retire Caus Castle and Ayazini Kaya Church** as '
    'medieval / out of scope (owner: "die 2 mittelalter deaktivieren"), through the journalled '
    "scope-retire lane. |"
)
D20_QUOTE = (
    "| D20 | Scope (116 after the window, 5 pending, Hadrian's Wall Path) | **Check and retire "
    "autonomously** (rec): a wrong period is corrected (sourced), a truly out-of-window site is "
    "retired (journalled); rule periods re-researched first. |"
)
RULES = (
    "d121-regional",
    "d121-no-year",
    "d122-unsourced",
    "d124-cited",
    "d136-band",
    "d137-year",
    "d138-year",
    "d20-sourced",
)
BAND_KEYS = frozenset(
    {"site_id", "name", "status", "band", "edge", "epoch", "band_from", "source_kind", "quote", "url"}
)
YEAR_KEYS = frozenset({"year", "year_quote", "year_url"})
#: The CANDIDATES.jsonl statuses the writer reads: `band` is written, `scope-hold` is read so that the
#: D58 precheck lists it (`year-stated-only` and `undated` carry no band).
BAND_STATUSES = ("band", "scope-hold")
#: The CANDIDATES.jsonl status D138 writes: a stated year and no epoch (`fields/epoch_bands.py`).
YEAR_ONLY_STATUS = "year-stated-only"
YEAR_ONLY_KEYS = frozenset({"site_id", "name", "status", "year_band", "year_sentences"})
#: D137 ("obvious reading errors ... are fixed before the write"), found reading the 60 sentences of
#: D138 before the write: a stated year that is not a date of the site. Listed for the owner, not written.
D138_READING_ERRORS = {
    "f6daed37-710f-4512-a494-bb4ecddd4d2c": (
        "Cave of El Soplao: the only year is the cave's geological formation ('Its formation dates back "
        "to the Mesozoic, in particular the Cretaceous period 240 million years ago'), not a date of "
        "human use of the site (D137: an obvious reading error is not written)"
    ),
}
CITED_KEYS = frozenset({"site_id", "start", "url", "quote", "answered_by", "model", "reason"})
#: A row of the scope window's `PERIOD_WRONG.jsonl` (`identity/scope_judge.py`, `build`): the D20
#: web answer that kept the site on a sourced start other than the stored one.
D20_KEYS = frozenset(
    {
        "site_id",
        "wave",
        "name",
        "stored_period_start",
        "stored_period_name",
        "period_start",
        "origin",
        "recheck_d10",
        "label_borderline",
        "why",
        "answered_by",
        "model",
        "answered_at",
        "quotes",
        "ask",
    }
)


# ------------------------------------------------------------------------------ the lane
def fix_lane(wave: str, step: int) -> Lane:
    """The lane of one step: the period pair of the wd5 cells (a start may be filled, replaced or
    cleared; the label is a bucket or Undated) under a stamp and directory of its own."""
    name = f"period-fix-{wave}-{step_name(step)}"
    if PERIOD_FIX_LANE.match(name) is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-11-07 or 2026-11-07b")
    return Lane(
        name=name,
        key_prefix=name,
        run_stamp=f"{wave}_mechanical-period-fix-{step_name(step)}",
        test_id="D121-D124/period-correction",
        # Derived from the owner's decisions and the cited table (D121/D122); the cited start of
        # D124 and the sourced start of D20 carry their own quote and answer in the evidence.
        confidence="authoritative",
        label="D121 period correction",
        plan_table="_period_fix_plan",
        out_dir_name=f"{ROOT_NAME}/{wave}/{step_name(step)}",
        post_commit_residual=_PERIOD_MISMATCH,
        rehearsal_residual=_PERIOD_MISMATCH,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        cells=tuple(c for c in FIELDS_CELLS_WD5 if c.name in ("period_start", "period_name")),
        site_invariants=(FIELDS_INVARIANTS[1],),
    )


def lane_of(name: str) -> Lane:
    match = PERIOD_FIX_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return fix_lane(match.group(1), int(match.group(2)))


def readback(lane: Lane) -> str:
    """The read-only verification of one step, before and after its write."""
    stamp = sql_literal(lane.run_stamp)
    journal = f"FROM remediation_change_log WHERE run_stamp = {stamp} AND "
    return journal_readback(
        lane,
        [
            (_PERIOD_MISMATCH.metric, _CURATED_ROWS + _PERIOD_MISMATCH.predicate),
            ("curated rows without a start", _CURATED_ROWS + "period_start IS NULL"),
            (
                "shown curated rows without a start",
                _CURATED_ROWS + "period_start IS NULL AND scope_status IS DISTINCT FROM 'retired'",
            ),
            ("journal rows for this run that clear a start", journal + "column_name = 'period_start' AND new_value IS NULL"),
        ],
    )


# ------------------------------------------------------------------------------ the read
def site_sql(site_ids: Iterable[str] | None = None) -> str:
    where = f" AND u.id::text IN ({sql_ids(site_ids)})" if site_ids is not None else ""
    return (
        "SELECT u.id::text AS site_id, u.name, u.country, u.source_id, u.scope_status, u.lat, "
        "u.lon, u.period_start, u.period_end, u.period_name FROM unified_sites u WHERE "
        f"u.source_id = {sql_literal(CURATED_SOURCE)}{where} ORDER BY u.id"
    )


def journal_sql(site_ids: Iterable[str] | None = None) -> str:
    where = f" AND l.row_pk IN ({sql_ids(site_ids)})" if site_ids is not None else ""
    return (
        "SELECT l.id, l.row_pk, l.run_stamp, coalesce(l.test_id, '') AS test_id, l.old_value, "
        "l.new_value, l.evidence FROM remediation_change_log l WHERE l.table_name = "
        f"'unified_sites' AND l.column_name = 'period_start'{where} ORDER BY l.id"
    )


@dataclass(frozen=True)
class Live:
    site_id: str
    name: str
    country: str | None
    source_id: str
    scope_status: str | None
    lat: float | None
    lon: float | None
    period_start: int | None
    period_end: int | None
    period_name: str | None


@dataclass(frozen=True)
class Link:
    """A journal row of `period_start`, with its evidence (the rule that made it)."""

    link: JournalLink
    evidence: tuple[Mapping[str, Any], ...]


def _int(value: Any) -> int | None:
    return None if value in (None, "") else int(str(value))


def parse_export(text: str) -> tuple[dict[str, Live], dict[str, list[Link]], str]:
    rows, at = parse_tagged_export(text, ("site", "journal"))
    live = {
        str(r["site_id"]): Live(
            str(r["site_id"]),
            str(r["name"]),
            r["country"],
            str(r["source_id"]),
            r["scope_status"],
            r["lat"],
            r["lon"],
            _int(r["period_start"]),
            _int(r["period_end"]),
            r["period_name"],
        )
        for r in rows["site"]
    }
    journal: dict[str, list[Link]] = {}
    for r in rows["journal"]:
        journal.setdefault(str(r["row_pk"]), []).append(
            Link(
                JournalLink(int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]),
                tuple(r["evidence"] or ()),
            )
        )
    return live, journal, at


def is_site_type_rule(link: Link) -> bool:
    """The row is the old WD3 site_type rule's write (D12's rule-made period without a source)."""
    return any(
        _DERIVED.match(str(e.get("source", ""))) and e.get("status") == "RULE" for e in link.evidence
    )


def _rule_reasoning(link: Link) -> str:
    for e in link.evidence:
        if _DERIVED.match(str(e.get("source", ""))):
            return str(e.get("reasoning") or "")
    return ""


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class Decision:
    """What the wave decided for one site, re-checked against production by every step."""

    site_id: str
    name: str
    rule: str
    live_start: int | None
    journal_id: int | None
    new_start: int | None
    note: str
    evidence: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "rule": self.rule,
            "live_start": self.live_start,
            "journal_id": self.journal_id,
            "new_start": self.new_start,
            "note": self.note,
            "evidence": [dict(e) for e in self.evidence],
        }

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> Decision:
        return Decision(
            str(d["site_id"]),
            str(d["name"]),
            str(d["rule"]),
            d["live_start"],
            d["journal_id"],
            d["new_start"],
            str(d["note"]),
            tuple(d["evidence"]),
        )


@dataclass(frozen=True)
class Refusal:
    site_id: str
    name: str
    reason: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {"site_id": self.site_id, "name": self.name, "reason": self.reason, "note": self.note}


def _site_checks(site: Live | None, links: Sequence[Link], site_id: str) -> Refusal | None:
    """The checks every rule shares: a curated row whose journal ends at its live start."""
    if site is None:
        return Refusal(site_id, "", "site-gone", "production has no curated row with this id")
    if site.source_id != CURATED_SOURCE:
        return Refusal(site_id, site.name, "row-not-in-curated-source", f"source_id={site.source_id!r}")
    live = None if site.period_start is None else str(site.period_start)
    broken = journal_break([link.link for link in links], live)
    if broken is not None:
        return Refusal(site_id, site.name, *broken)
    if site.period_end is not None:
        return Refusal(
            site_id, site.name, "period-end-set", f"period_end {site.period_end}: O1 writes a start only"
        )
    return None


def _scope(site: Live, start: int | None, *, label_asked: bool = False) -> str | None:
    """Why `start` is listed and not written (`scope_problem`), or None. `label_asked`: the D20
    answer the start comes from was asked the label question (D58), so a start that leaves the site
    label-borderline (inside the window: its region keeps it through 1500 AD) is a decided one -
    its subject was judged with it."""
    if start is None:
        return None
    record = {"site_id": site.site_id, "lat": site.lat, "lon": site.lon, "country": site.country}
    if label_asked and label_borderline({**record, "period_start": start, "period_end": None}):
        return None
    return scope_problem(record, start)


def _journal_quote(link: Link) -> dict[str, Any]:
    j = link.link
    return {
        "source": f"remediation_change_log:{j.id}",
        "url": "remediation_change_log",
        "quote": f"{j.run_stamp} ({j.test_id}): {j.old_value!r} -> {j.new_value!r}",
    }


def decide_d122(site: Live, links: Sequence[Link]) -> Decision | None:
    """D122, or None when the site's live start is not the site_type rule's."""
    if not links or site.period_start is None:
        return None
    last = links[-1]
    if not is_site_type_rule(last) or _int(last.link.new_value) != site.period_start:
        return None
    return Decision(
        site.site_id,
        site.name,
        "d122-unsourced",
        site.period_start,
        last.link.id,
        None,
        f"{site.period_start} was written by the WD3 site_type rule, no source dates it: Undated (D12, D122)",
        (
            {"source": "owner decision D122 (2026-11-07)", "url": DECISIONS, "quote": D122_QUOTE},
            _journal_quote(last),
            {
                "source": "the rule's own reasoning (journal evidence)",
                "url": "remediation_change_log",
                "quote": _rule_reasoning(last)[:400],
            },
        ),
    )


def decide_d121(
    site: Live, links: Sequence[Link], entry: Mapping[str, Any], *, list_sha: str
) -> Decision | Refusal:
    """D121 for one row of the D113 list."""
    if site.period_start != _int(entry["current"]):
        return Refusal(
            site.site_id,
            site.name,
            "moved-since-list",
            f"the list read {entry['current']}, production holds {site.period_start}",
        )
    if not links or links[-1].link.id != int(entry["journal_id"]):
        return Refusal(
            site.site_id,
            site.name,
            "journal-moved-since-list",
            f"the list's journal row is {entry['journal_id']}, the newest is "
            f"{links[-1].link.id if links else None}",
        )
    word = str(entry["period_word"])
    try:
        start: int | None = P.start_year(word, country=site.country)
        computed = f"start_year({word!r}, country={site.country!r}) = {start}"
    except P.PeriodError as exc:
        start, computed = None, f"start_year({word!r}, country={site.country!r}) refuses: {exc}"
    if start != _int(entry["new_regional_start"]):
        return Refusal(
            site.site_id,
            site.name,
            "table-moved-since-list",
            f"the list computed {entry['new_regional_start']}, the table now answers {start}",
        )
    rule = "d121-regional" if start is not None else "d121-no-year"
    note = (
        f"{site.period_start} came from the period word {word!r} under the old fixed table; the "
        f"regional table gives {start if start is not None else 'no year'} for {site.country!r} (D121)"
    )
    return Decision(
        site.site_id,
        site.name,
        rule,
        site.period_start,
        links[-1].link.id,
        start,
        note,
        (
            {"source": "owner decision D121 (2026-11-07)", "url": DECISIONS, "quote": D121_QUOTE},
            {"source": "pipeline/periods.py:start_year", "url": "pipeline/periods.py", "quote": computed},
            {
                "source": f"output/remediation/fields/D113_CONFLICT_LIST.jsonl (sha256 {list_sha})",
                "url": "output/remediation/fields/D113_CONFLICT_LIST.md",
                "quote": f"origin {entry['origin']}, run {entry['run_stamp']}, word {word!r}",
            },
            _journal_quote(links[-1]),
        ),
    )


def decide_cited(site: Live, links: Sequence[Link], cited: Mapping[str, Any]) -> Decision:
    """D124: a cited start a released re-ask returned, with its quote and its answer's stamp."""
    start = int(cited["start"])
    return Decision(
        site.site_id,
        site.name,
        "d124-cited",
        site.period_start,
        links[-1].link.id if links else None,
        start,
        f"the cited start {start} ({cited['reason']}) (D124)",
        (
            {"source": "owner decision D124 (2026-11-07)", "url": DECISIONS, "quote": D124_QUOTE},
            {"source": str(cited["url"]), "url": str(cited["url"]), "quote": str(cited["quote"])},
            {
                "source": f"D124 re-ask ({cited['answered_by']})",
                "model": str(cited["model"]),
                "reasoning": str(cited["reason"]),
            },
        ),
    )


def load_cited(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        if set(r) != CITED_KEYS:
            raise PlanError(f"{path}: a cited start has exactly the keys {sorted(CITED_KEYS)}, not {sorted(r)}")
        if not str(r["quote"]).strip() or not str(r["url"]).startswith("http"):
            raise PlanError(f"{path}: {r['site_id']} has no quote or no URL")
        if not str(r["model"]).startswith("anthropic/claude-"):
            raise PlanError(f"{path}: {r['site_id']} was not answered by a Claude model ({r['model']!r})")
    return rows


def load_d20(path: Path) -> list[dict[str, Any]]:
    """The rows of a scope-window wave's `PERIOD_WRONG.jsonl`, each in the shape `scope_judge.build`
    writes: a year, the answer's found quotes and the stamp of the Claude answer they come from."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        if set(r) != D20_KEYS:
            raise PlanError(
                f"{path}: a D20 start has exactly the keys {sorted(D20_KEYS)}, not {sorted(r)} (a "
                "file planned before the hand-off carried the answer's stamp is not read)"
            )
        start = r["period_start"]
        if isinstance(start, bool) or not isinstance(start, int):
            raise PlanError(f"{path}: {r['site_id']} period_start {start!r} is not a year")
        quotes = r["quotes"]
        if not quotes or not all(
            q["outcome"] == "found" and str(q["quote"]).strip() and str(q["url"]).startswith("http")
            for q in quotes
        ):
            raise PlanError(f"{path}: {r['site_id']} has no quote, or one that was not found on its page")
        if not str(r["model"]).startswith("anthropic/claude-") or not str(r["answered_by"]).strip():
            raise PlanError(
                f"{path}: {r['site_id']} was not answered by a Claude model ({r['model']!r}, "
                f"{r['answered_by']!r})"
            )
    return rows


def states_date(quote: str, year: int) -> bool:
    """Whether a found quote states `year` as a date: `fields.answers.states_year` (the fields
    lanes' gate), by a statement the dating extractor reads as a date (`fields.dating.acceptable`).
    `states_year` reads every unmarked number as an AD year; here "300 metres" (a unit after it),
    "Population 1200" and "Page 450" (an unmarked number with no date preposition before it) state
    none. Years before the present are `states_bp`'s."""
    if not states_year(quote, year):
        return False
    if states_bp(quote, year):
        return True
    low = dates.reading_text(quote).casefold()
    return any(
        item.statement.lo <= year <= item.statement.hi and acceptable(item, low) is None
        for item in dates.located(quote)
    )


def decide_d20(site: Live, links: Sequence[Link], row: Mapping[str, Any]) -> Decision | Refusal:
    """D20: the sourced start of a site the scope window kept, where a found quote states it as a
    date (`states_date`). The gate proves the year stands on a page the answer quoted, not that the
    sentence dates the beginning of this site: that is the answer's judgement, read again in the
    step's PLAN.md before the write."""
    start, stored = int(row["period_start"]), row["stored_period_start"]
    if site.scope_status != IN_SCOPE:
        return Refusal(
            site.site_id,
            site.name,
            "d20-scope-not-written",
            f"scope wave {row['wave']} keeps the site in scope, production holds scope_status "
            f"{site.scope_status!r}: that wave's write comes first",
        )
    if site.period_start != stored:
        return Refusal(
            site.site_id,
            site.name,
            "moved-since-answer",
            f"the answer judged a stored start of {stored}, production holds {site.period_start}",
        )
    if not any(states_date(str(q["quote"]), start) for q in row["quotes"]):
        return Refusal(
            site.site_id,
            site.name,
            "d20-no-quote-states-year",
            f"none of the answer's {len(row['quotes'])} found quote(s) states {start} itself as a "
            "date (its year, or its century or millennium; a measure, a count or a bare number is "
            "none): the year is the answer's reading, not a source's",
        )
    return Decision(
        site.site_id,
        site.name,
        "d20-sourced",
        site.period_start,
        links[-1].link.id if links else None,
        start,
        f"a source dates the start at {start}, the stored start was {stored} ({row['origin']}): "
        f"corrected (D20, scope wave {row['wave']})",
        (
            {"source": "owner decision D20 (2026-10-08)", "url": DECISIONS, "quote": D20_QUOTE},
            *({"source": str(q["url"]), "url": str(q["url"]), "quote": str(q["quote"])} for q in row["quotes"]),
            {
                "source": f"D20 scope-window answer ({row['answered_by']}, {row['answered_at']})",
                "model": str(row["model"]),
                "reasoning": str(row["why"]),
            },
        ),
    )


def load_bands(path: Path) -> list[dict[str, Any]]:
    """The band rows of an epoch_bands CANDIDATES.jsonl, each checked against the band rule."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") not in BAND_STATUSES:
            continue
        missing = BAND_KEYS - set(r)
        if missing:
            raise PlanError(f"{path}: {r.get('site_id')} lacks {sorted(missing)}")
        if not str(r["quote"]).strip() or not str(r["url"]).strip():
            raise PlanError(f"{path}: {r['site_id']} has no quote or no URL")
        if int(r["edge"]) != bucket_edge(str(r["band"])):
            raise PlanError(f"{path}: {r['site_id']} edge {r['edge']} is not the edge of {r['band']!r}")
        if r["band_from"] == "year":
            if YEAR_KEYS - set(r) or not str(r["year_quote"]).strip():
                raise PlanError(f"{path}: {r['site_id']} is read from a year but carries no year quote")
            if categorize_period(int(r["year"])) != r["band"]:
                raise PlanError(f"{path}: {r['site_id']} year {r['year']} does not lie in {r['band']!r}")
        elif r["band_from"] != "epoch":
            raise PlanError(f"{path}: {r['site_id']} band_from {r['band_from']!r} is neither epoch nor year")
        rows.append(r)
    return rows


def stated_year(row: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
    """The earliest year a `year-stated-only` row's sentences state, and the first sentence stating it."""
    year = min(int(y) for s in row["year_sentences"] for y in s["years"])
    return year, next(s for s in row["year_sentences"] if year in s["years"])


def load_years(path: Path) -> list[dict[str, Any]]:
    """The `year-stated-only` rows of an epoch_bands CANDIDATES.jsonl (D138), each checked: its band is
    the band of the earliest year its own sentences state, and that sentence has a quote and a URL."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") != YEAR_ONLY_STATUS:
            continue
        missing = YEAR_ONLY_KEYS - set(r)
        if missing:
            raise PlanError(f"{path}: {r.get('site_id')} lacks {sorted(missing)}")
        if not r["year_sentences"] or not all(s.get("years") for s in r["year_sentences"]):
            raise PlanError(f"{path}: {r['site_id']} states no year")
        year, sentence = stated_year(r)
        if categorize_period(year) != r["year_band"]:
            raise PlanError(
                f"{path}: {r['site_id']} year_band {r['year_band']!r} is not the band of its earliest "
                f"quoted year {year} (a year outside the kept sentences?)"
            )
        if not str(sentence.get("sentence") or "").strip() or not str(sentence.get("url") or "").strip():
            raise PlanError(f"{path}: {r['site_id']} has no quote or no URL for its year {year}")
        rows.append(r)
    return rows


def decide_year(site: Live, links: Sequence[Link], row: Mapping[str, Any]) -> Decision | Refusal:
    """D138: an undated site whose own source states a year takes the edge of that year's band."""
    if site.period_start is not None:
        return Refusal(
            site.site_id,
            site.name,
            "dated-since-candidates",
            f"the candidates read the site undated, production holds {site.period_start}",
        )
    year, sentence = stated_year(row)
    band = str(row["year_band"])
    edge = bucket_edge(band)
    quoted_by = f" ({sentence['quoted_by']})" if sentence.get("quoted_by") else ""
    note = f"the site's own source states {year}: the band {band!r}, its edge {edge} (D137 year rule, D138)"
    return Decision(
        site.site_id,
        site.name,
        "d138-year",
        None,
        links[-1].link.id if links else None,
        edge,
        note,
        (
            {"source": "owner decision D138 (2026-11-07)", "url": DECISIONS, "quote": D138_QUOTE},
            {"source": "owner decision D137 (2026-11-07)", "url": DECISIONS, "quote": D137_QUOTE},
            {
                "source": f"the year the site's own source states (D138): {year}, {sentence['file']}{quoted_by}",
                "url": str(sentence["url"]),
                "quote": str(sentence["sentence"]),
            },
            {"source": "pipeline/utils/text.py:categorize_period", "url": "pipeline/utils/text.py", "quote": note},
        ),
    )


def decide_band(site: Live, links: Sequence[Link], row: Mapping[str, Any]) -> Decision | Refusal:
    """D136/D137: an undated site takes the edge of its band (the epoch's, or a stated year's)."""
    if site.period_start is not None:
        return Refusal(
            site.site_id,
            site.name,
            "dated-since-candidates",
            f"the candidates read the site undated, production holds {site.period_start}",
        )
    by_year = row["band_from"] == "year"
    edge = int(row["edge"])
    quoted_by = f" ({row['quoted_by']})" if row.get("quoted_by") else ""
    evidence: list[Mapping[str, Any]] = [
        {"source": "owner decisions D136/D137 (2026-11-07)", "url": DECISIONS, "quote": f"{D136_QUOTE} {D137_QUOTE}"},
        {
            "source": f"{row['source_kind']}: epoch {row['epoch']!r}{quoted_by}",
            "url": str(row["url"]),
            "quote": str(row["quote"]),
        },
    ]
    if by_year:
        evidence.append(
            {
                "source": f"the year the site's own source states (D137): {row['year']}",
                "url": str(row["year_url"]),
                "quote": str(row["year_quote"]),
            }
        )
        note = (
            f"the site's own source states {row['year']} ({row['band']!r}, over the epoch "
            f"{row['epoch']!r}'s {row.get('epoch_band')!r}): the band's edge {edge} (D137)"
        )
    else:
        note = f"the epoch {row['epoch']!r} begins in {row['band']!r}: the band's edge {edge} (D136/D137)"
    evidence.append({"source": "pipeline/periods.py:epoch_band", "url": "pipeline/periods.py", "quote": note})
    return Decision(
        site.site_id,
        site.name,
        "d137-year" if by_year else "d136-band",
        None,
        links[-1].link.id if links else None,
        edge,
        note,
        tuple(evidence),
    )


def build_decisions(
    live: Mapping[str, Live],
    journal: Mapping[str, Sequence[Link]],
    d113: Sequence[Mapping[str, Any]],
    *,
    list_sha: str,
    cited: Sequence[Mapping[str, Any]] = (),
    bands: Sequence[Mapping[str, Any]] = (),
    years: Sequence[Mapping[str, Any]] = (),
    d20: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[Decision], list[Refusal], dict[str, int]]:
    """Every decision of a wave and every refusal, from one production read. Pure."""
    decided: dict[str, Decision] = {}
    refused: list[Refusal] = []
    label_asked: set[str] = set()
    counters: Counter[str] = Counter()
    for site_id, site in live.items():
        d = decide_d122(site, journal.get(site_id, ()))
        if d is not None:
            decided[site_id] = d
    counters["d122-candidates"] = len(decided)
    listed = set()
    for entry in d113:
        sid = str(entry["site_id"])
        if sid in listed:
            raise PlanError(f"the D113 list names {sid} twice")
        listed.add(sid)
        if sid in decided:
            counters["d121-covered-by-d122"] += 1
            continue
        site = live.get(sid)
        refusal = _site_checks(site, journal.get(sid, ()), sid)
        if refusal is not None:
            refused.append(refusal)
            continue
        assert site is not None
        out = decide_d121(site, journal.get(sid, ()), entry, list_sha=list_sha)
        if isinstance(out, Refusal):
            refused.append(out)
        else:
            decided[sid] = out
    for c in cited:
        sid = str(c["site_id"])
        if sid in decided:
            raise PlanError(f"{sid}: a cited start for a site another rule already decides")
        site = live.get(sid)
        refusal = _site_checks(site, journal.get(sid, ()), sid)
        if refusal is not None:
            refused.append(refusal)
            continue
        assert site is not None
        decided[sid] = decide_cited(site, journal.get(sid, ()), c)
    for row in bands:
        sid = str(row["site_id"])
        if sid in decided:
            raise PlanError(f"{sid}: a band for a site another rule already decides")
        site = live.get(sid)
        refusal = _site_checks(site, journal.get(sid, ()), sid)
        if refusal is not None:
            refused.append(refusal)
            continue
        assert site is not None
        out = decide_band(site, journal.get(sid, ()), row)
        if isinstance(out, Refusal):
            refused.append(out)
        else:
            decided[sid] = out
    for row in years:
        sid = str(row["site_id"])
        if sid in decided:
            raise PlanError(f"{sid}: a stated year for a site another rule already decides")
        if sid in D138_READING_ERRORS:
            refused.append(Refusal(sid, str(row["name"]), "d137-reading-error", D138_READING_ERRORS[sid]))
            continue
        site = live.get(sid)
        refusal = _site_checks(site, journal.get(sid, ()), sid)
        if refusal is not None:
            refused.append(refusal)
            continue
        assert site is not None
        out = decide_year(site, journal.get(sid, ()), row)
        if isinstance(out, Refusal):
            refused.append(out)
        else:
            decided[sid] = out
    for row in d20:
        sid = str(row["site_id"])
        if sid in decided:
            raise PlanError(f"{sid}: a D20 start for a site another rule already decides")
        site = live.get(sid)
        refusal = _site_checks(site, journal.get(sid, ()), sid)
        if refusal is not None:
            refused.append(refusal)
            continue
        assert site is not None
        out = decide_d20(site, journal.get(sid, ()), row)
        if isinstance(out, Refusal):
            refused.append(out)
        else:
            decided[sid] = out
            if row["label_borderline"]:
                label_asked.add(sid)
    final: list[Decision] = []
    for sid in sorted(decided):
        d = decided[sid]
        site = live[sid]
        if d.rule == "d122-unsourced":
            refusal = _site_checks(site, journal.get(sid, ()), sid)
            if refusal is not None:
                refused.append(refusal)
                continue
        problem = _scope(site, d.new_start, label_asked=sid in label_asked)
        if problem is not None:
            refused.append(Refusal(sid, site.name, "d58-window", problem))
            continue
        final.append(d)
    counters.update(f"rule:{d.rule}" for d in final)
    counters.update(f"skip:{r.reason}" for r in refused)
    counters["sites"] = len(final)
    return final, refused, dict(sorted(counters.items()))


# ------------------------------------------------------------------------------ the wave
def wave_dir(wave: str, root: Path = ROOT) -> Path:
    return root / wave


def build_wave(
    wave: str,
    *,
    d113_path: Path | None = D113_LIST,
    cited_path: Path | None = None,
    bands_path: Path | None = None,
    years_path: Path | None = None,
    d20_path: Path | None = None,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> dict[str, Any]:
    """WAVE.json: every decision in steps of 100, from one read-only production read."""
    fix_lane(wave, 1)
    target = wave_dir(wave, root)
    if (target / WAVE_FILE).exists():
        raise PlanError(f"{target / WAVE_FILE} exists: a wave is planned once")
    d113 = (
        [json.loads(line) for line in d113_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if d113_path is not None
        else []
    )
    list_sha = sha256_file(d113_path) if d113_path is not None else ""
    cited = load_cited(cited_path) if cited_path is not None else []
    bands = load_bands(bands_path) if bands_path is not None else []
    years = load_years(years_path) if years_path is not None else []
    d20 = load_d20(d20_path) if d20_path is not None else []
    text = read(tagged_export_script([("site", site_sql()), ("journal", journal_sql())]))
    live, journal, at = parse_export(text)
    if d113_path is None:
        # a wave without the list (D124, D136/D137, D138 or D20 alone) decides no D122 row either:
        # those are one run's
        named = [str(c["site_id"]) for c in (*cited, *bands, *years, *d20)]
        live_scope = {sid: live[sid] for sid in named if sid in live}
    else:
        live_scope = live
    decisions, refused, counters = build_decisions(
        live_scope, journal, d113, list_sha=list_sha, cited=cited, bands=bands, years=years, d20=d20
    )
    ids = [d.site_id for d in decisions]
    record = {
        "wave": wave,
        "read_at": at,
        "d113_sha256": list_sha,
        "cited_sha256": sha256_file(cited_path) if cited_path is not None else "",
        "bands_sha256": sha256_file(bands_path) if bands_path is not None else "",
        "years_sha256": sha256_file(years_path) if years_path is not None else "",
        "d20_sha256": sha256_file(d20_path) if d20_path is not None else "",
        "counters": counters,
        "steps": [ids[i : i + MAX_SITES] for i in range(0, len(ids), MAX_SITES)],
        "decisions": [d.as_dict() for d in decisions],
        "refused": [r.as_dict() for r in refused],
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / WAVE_FILE).write_text(
        json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    (target / WAVE_PIN_FILE).write_text(sha256_file(target / WAVE_FILE) + "\n", encoding="utf-8", newline="\n")
    return {"wave": wave, "read_at": at, "steps": len(record["steps"]), **counters}


def read_wave(wave: str, root: Path = ROOT) -> dict[str, Any]:
    target = wave_dir(wave, root)
    path = target / WAVE_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `period_fix.py wave` first")
    if sha256_file(path) != (target / WAVE_PIN_FILE).read_text(encoding="utf-8").strip():
        raise PlanError(f"{path} is not the pinned wave: it was edited")
    return json.loads(path.read_text(encoding="utf-8"))


def label_of(start: int | None) -> str:
    return UNDATED if start is None else str(categorize_period(start))


def step_verdicts(
    decision: Decision, site: Live | None, links: Sequence[Link]
) -> list[Verdict]:
    """The cells of one decided site, re-checked against the step's own read. Pure."""

    def verdict(ok: bool, column: str, old: Any, new: Any, reason: str, note: str, rule: str = "") -> Verdict:
        return Verdict(
            site_id=decision.site_id,
            site_name=decision.name,
            ok=ok,
            old_value=None if old is None else str(old),
            new_value=None if new is None else str(new),
            rule=rule,
            reason=reason,
            note=note,
            phase3=any(link.link.run_stamp.startswith("phase3:") for link in links),
            finding_test_id=f"{decision.rule.split('-')[0].upper()}/{column}",
            evidence=decision.evidence if ok else (),
            column=column,
        )

    refusal = _site_checks(site, links, decision.site_id)
    if refusal is None and site is not None:
        newest = links[-1].link.id if links else None
        if site.period_start != decision.live_start or newest != decision.journal_id:
            refusal = Refusal(
                decision.site_id,
                site.name,
                "moved-since-wave",
                f"the wave read {decision.live_start} (journal {decision.journal_id}), production "
                f"holds {site.period_start} (journal {newest})",
            )
    if refusal is not None:
        return [verdict(False, "period_start", decision.live_start, decision.new_start, refusal.reason, refusal.note)]
    assert site is not None
    out = []
    if site.period_start != decision.new_start:
        out.append(
            verdict(True, "period_start", site.period_start, decision.new_start, "", decision.note, decision.rule)
        )
    label = label_of(decision.new_start)
    if site.period_name != label:
        out.append(
            verdict(
                True,
                "period_name",
                site.period_name,
                label,
                "",
                f"the label of {decision.new_start if decision.new_start is not None else 'no start'}: {label!r}",
                f"{decision.rule}-label",
            )
        )
    return out


def _step_dir(wave: str, step: int, root: Path) -> Path:
    return wave_dir(wave, root) / step_name(step)


def write_plan_md(plan: Plan, path: Path, decisions: Sequence[Decision]) -> None:
    lane = plan.lane
    by_rule = Counter(d.rule for d in decisions if d.site_id in plan.sites)
    lines = [
        f"# D121/D122/D124/D136/D137/D138/D20 period correction - {lane.name}",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/period_fix.py`. Run stamp "
        f"`{lane.run_stamp}`, test id `{lane.test_id}`, change keys `{lane.key_prefix}:<site_id>:<column>`.",
        "",
        f"**{len(plan.sites)} site(s), {len(plan.changes)} cell(s); {len(plan.skipped)} refused** (`SKIPPED.jsonl`).",
        "",
        "| rule | sites |",
        "|---|---|",
        *(f"| {k} | {n} |" for k, n in sorted(by_rule.items())),
        "",
        "| site | rule | period_start | period_name |",
        "|---|---|---|---|",
    ]
    cells: dict[str, dict[str, Verdict]] = {}
    for c in plan.changes:
        cells.setdefault(c.site_id, {})[str(c.column)] = c
    for d in decisions:
        if d.site_id not in cells:
            continue
        s, n = cells[d.site_id].get("period_start"), cells[d.site_id].get("period_name")
        lines.append(
            f"| {d.name} (`{d.site_id}`) | {d.rule} | "
            f"{f'{s.old_value} -> {s.new_value}' if s else 'unchanged'} | "
            f"{f'{n.old_value} -> {n.new_value}' if n else 'unchanged'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def plan_step(
    wave: str, step: int, *, read: Callable[[str], str] = read_production, root: Path = ROOT
) -> dict[str, Any]:
    record = read_wave(wave, root)
    if not 1 <= step <= len(record["steps"]):
        raise PlanError(f"wave {wave} has steps 1..{len(record['steps'])}, not {step}")
    if step > 1 and not (_step_dir(wave, step - 1, root) / ACCEPTED_FILE).exists():
        raise PlanError(f"step {step - 1} is not accepted: `period_fix.py accept --step {step - 1}`")
    out = _step_dir(wave, step, root)
    if out.exists():
        raise PlanError(f"{out} exists: a step is planned once")
    sites = record["steps"][step - 1]
    by_id = {d["site_id"]: Decision.from_dict(d) for d in record["decisions"]}
    text = read(tagged_export_script([("site", site_sql(sites)), ("journal", journal_sql(sites))]))
    live, journal, _at = parse_export(text)
    decisions = [by_id[s] for s in sorted(sites)]
    verdicts = [v for d in decisions for v in step_verdicts(d, live.get(d.site_id), journal.get(d.site_id, ()))]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    lane = fix_lane(wave, step)
    plan = Plan(
        changes=changes,
        skipped=skipped,
        built_at=datetime.now(UTC).isoformat(),
        counters={
            "cells": len(changes),
            **{f"skip:{k}": n for k, n in sorted(Counter(v.reason for v in skipped).items())},
        },
        lane=lane,
    )
    out.mkdir(parents=True)
    (out / "export.jsonl").write_text(text, encoding="utf-8", newline="\n")
    write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
    write_plan_md(plan, out / "PLAN.md", decisions)
    if plan.changes:
        write_plan_jsonl(plan, out / "PLAN.jsonl")
        write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    return {"step": step, "lane": lane.name, "sites": len(plan.sites), **plan.counters}


# ------------------------------------------------------------------------------ the acceptance
def deviations(
    lane: Lane,
    rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    written = [j for j in journal if j["run_stamp"] == lane.run_stamp]
    undone = [j for j in journal if j["run_stamp"] == lane.rollback_run_stamp]
    if undone:
        found.append(f"{lane.name}: {len(undone)} rollback journal row(s)")
    by_cell = {(j["row_pk"], j["column_name"]): j for j in written}
    planned = {(r["site_id"], r["column"]) for r in rows}
    if len(by_cell) != len(written) or set(by_cell) != planned:
        found.append(f"{lane.name}: {len(written)} journal row(s) for {len(rows)} planned cell(s)")
    for row in rows:
        site = live.get(row["site_id"])
        held = None if site is None else getattr(site, row["column"])
        if site is None or (None if held is None else str(held)) != row["new_value"]:
            found.append(f"{row['site_id']}: {row['column']} does not hold the planned value")
        entry = by_cell.get((row["site_id"], row["column"]))
        if entry is None or (entry["old_value"], entry["new_value"]) != (row["old_value"], row["new_value"]):
            found.append(f"{row['site_id']}: the {row['column']} journal row is not the plan's")
    for site in live.values():
        if site.period_name != label_of(site.period_start):
            found.append(f"{site.site_id}: period_name {site.period_name!r} is not the label of {site.period_start}")
    return found


def accept_step(
    wave: str, step: int, *, read: Callable[[str], str] = read_production, root: Path = ROOT
) -> tuple[int, list[str]]:
    lane = fix_lane(wave, step)
    out = _step_dir(wave, step, root)
    plan_path = out / "PLAN.jsonl"
    rows = (
        [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines() if line]
        if plan_path.exists()
        else []
    )
    stamps = ", ".join(sql_literal(s) for s in (lane.run_stamp, lane.rollback_run_stamp))
    parts = [
        (
            "journal",
            "SELECT l.row_pk, l.column_name, l.run_stamp, l.old_value, l.new_value FROM "
            f"remediation_change_log l WHERE l.run_stamp IN ({stamps}) ORDER BY l.id",
        ),
    ]
    if rows:
        parts.insert(0, ("site", site_sql(sorted({r["site_id"] for r in rows}))))
    parsed, at = parse_tagged_export(read(tagged_export_script(parts)), ("site", "journal"))
    live, _journal, _at = parse_export(
        "\n".join(
            [json.dumps({"kind": "site", "row": r}) for r in parsed["site"]]
            + [json.dumps({"kind": "snapshot", "row": {"exported_at": at}})]
        )
    )
    found = deviations(lane, rows, live, parsed["journal"])
    accepted = out / ACCEPTED_FILE
    if not found and not accepted.exists():
        accepted.write_text(
            json.dumps(
                {
                    "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "read_at": at,
                    "cells": len(rows),
                    "sites": len({r["site_id"] for r in rows}),
                    "deviations": 0,
                    "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest() if rows else None,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return (0 if not found else 1), found


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("wave", "step", "accept"):
        command = sub.add_parser(name)
        command.add_argument("--wave", required=True, help="a date label: 2026-11-07 or 2026-11-07b")
        if name == "wave":
            command.add_argument("--d113", type=Path, default=D113_LIST, help="the D113 list")
            command.add_argument("--no-d113", action="store_true", help="a wave of cited starts only")
            command.add_argument("--cited", type=Path, help="D124: cited starts of a released re-ask")
            command.add_argument("--bands", type=Path, help="D136/D137: the epoch_bands CANDIDATES.jsonl")
            command.add_argument("--years", type=Path, help="D138: its year-stated-only rows")
            command.add_argument("--d20", type=Path, help="D20: a scope-window wave's PERIOD_WRONG.jsonl")
        else:
            command.add_argument("--step", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "wave":
            _print(
                build_wave(
                    args.wave,
                    d113_path=None if args.no_d113 else args.d113,
                    cited_path=args.cited,
                    bands_path=args.bands,
                    years_path=args.years,
                    d20_path=args.d20,
                )
            )
        elif args.command == "step":
            _print(plan_step(args.wave, args.step))
        else:
            code, found = accept_step(args.wave, args.step)
            _print({"deviations": found})
            print(f"ACCEPT_EXIT={code}")
            return code
    except (PlanError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
