"""The scope lane's un-retire (owner decisions D58 of 2026-10-24 and D50 of 2026-10-19).

Two decisions bring retired curated sites back, written as every scope lane writes - `scope_status`
and `scope_reason` of one site in one transaction, journalled (`identity_lanes.scope_unretire_lane`,
`apply.py --lane scope-unretire-<wave>`). The one transition is `retired` -> `in_scope` with a new
reason, guarded by the old values, the entry's premise (name, type, point, country, dates and the
md5 of the description) and an invariant inside the transaction; the rollback retires the site
again with the reason it had.

**D58, the label rule.** "Only the medieval Old World of Europe, Byzantium and the Vikings is out;
non-European sites of 500-1500 stay in; the sites retired under the numeric cut come back through
the scope lane, journalled." A site comes back when

* its retirement is journalled and was the numeric cut's: its latest `scope_status` journal row
  wrote `retired` under one of `identity_lanes.NUMERIC_CUT_STAMPS` (scope-e4) - a D20 scope-window
  wave writes the same `E3: period_start N` reason, but under the label window, and is skipped
  `not-the-numeric-cut` - for its date (the reason `E3: period_start N ...` of scope-e4 rule (a)),
  and the label rule now keeps both the year the retirement named and the stored date:
  `passes_date_cutoff` (`pipeline/normalizers/dates.py`, `scope_region`) and not
  `label_borderline`. A borderline site (Anatolia, the Levant, Egypt, Byzantine Africa, the
  Caucasus, Greenland, dated 500-1500) is skipped `label-borderline`: whether its subject is
  Byzantine, Crusader or Norse is a scope verdict's question, not this lane's. A site whose Wikidata
  item is a Viking subject (`VIKING_SUBJECT_QIDS`, L'Anse aux Meadows) stays out, and so does a
  site of a type that asks the scope review's not-a-site question first (`lane.NON_SITE_TYPES`:
  `not-a-site-question-first` - an un-retired natural feature would be the next round's candidate
  and its URL would flip 410 -> 200 -> 410);
* or it is one of the museums scope-e4 retired by the museum rule for exhibits dated past 500 AD
  (`MUSEUM_EXHIBITS`, pinned by id with the exhibits the reason names) whose country is not of
  the medieval Old World, so the label rule keeps its exhibits.

**D50, the disputed sites.** "All return as disputed sites: un-retire them through the scope lane,
journalled; each description states the scholarly position and the claim, both sourced; no card or
page asserts the claim." The six sites of `lane.D50_DISPUTED_SITES` come back only when their
description as it stands is a lane-E dispute enrichment (`wc/disputes.py` -> `wc/cli.py export
--enrich --disputes`, D21): the journal row that wrote the current description carries an
enrichment's evidence (`wc4.EVIDENCE_DECISION_ENRICH`) with a well-formed adjudicated brief of this
site (`wc.enrich.dispute_record_problems`) and appended a sentence of each position (`dispute_a`,
`dispute_b`). Until then each is skipped `d50-no-dispute-text`, with what is missing. Its card
must not assert the claim either: a D50 site with a card text comes back only once the latest
journal row of its `card_stats.card_description` is later than the one of its dispute text (the
card lane wrote the card in the knowledge of the dispute, D21); until then it is skipped
`d50-card-not-cleared`. Premise and invariant hold the card's md5 and the same test.

**Waves.** A write lands at most `MAX_SITES` sites and a run stamp is applied once: `write --wave
<label>` plans the first `MAX_SITES` sites (by id) of a fresh export into
`mechanical_scope_unretire/<label>/`; a wave is refused when an earlier wave was planned from the
same export, and a delivered plan is never replaced. The D50 sites come in a later wave, after lane
E wrote their texts.

Files per wave: `PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md`, `ROLLBACK.sql`, `SOURCE.json`; the export
is `export/export.jsonl` (read-only, one repeatable-read snapshot). The runbook is
`docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` section 4.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from phase4 import wc4  # noqa: E402
from served_image.state import StateError, json_text, sha256_text, write_text_once  # noqa: E402
from wc import enrich as E  # noqa: E402

from mechanical.identity_lanes import (  # noqa: E402
    D50_REASON_PREFIX,
    D58_MUSEUM_REASON_PREFIX,
    D58_REASON_PREFIX,
    DATE_RETIRED_PREFIX,
    IN_SCOPE,
    NUMERIC_CUT_STAMPS,
    SCOPE_UNRETIRE_LANE,
    SCOPE_UNRETIRE_PREMISE_SQL,
    SCOPE_UNRETIRE_ROOT,
    scope_unretire_lane,
)
from mechanical.lane import (  # noqa: E402
    D50_DISPUTED_SITES,
    NON_SITE_TYPES,
    NOT_A_SITE_PREFIX,
    Lane,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    Plan,
    PlanError,
    Verdict,
    _now,
    parse_tagged_export,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
    write_tagged_export,
)
from pipeline.normalizers.dates import (  # noqa: E402
    LABEL_CUTOFFS,
    MEDIEVAL_OLD_WORLD,
    UNPLACED_OLD_WORLD,
    VIKING_SUBJECT_QIDS,
    label_borderline,
    passes_date_cutoff,
    scope_region,
    window_date,
)
from pipeline.utils.public_sites import RETIRED  # noqa: E402

DEFAULT_OUT = REPO / "output" / "remediation" / SCOPE_UNRETIRE_ROOT
MAX_SITES = 100
TEST_ID = "D58/scope-unretire"
MUSEUM_PREFIX = "E3 museum rule"
#: The museums scope-e4 retired by the museum rule (plan section 8.2: "the 3 Museum rows that
#: leave") for exhibits dated past 500 AD, by id, with the exhibits their reason names (read on
#: production 2026-10-24). A museum comes back when its stored reason still names these exhibits and
#: it lies outside the medieval Old World; Gross Raden (Germany, a Slavic temple of the 9th/10th
#: century) and the King Richard III Visitor Centre (England, the grave of 1485) stay out.
MUSEUM_EXHIBITS: Mapping[str, str] = {
    "71d8e2bc-7406-4c4a-b68d-2ff1b71800e8": "Gokturk Orkhon stelae, 8th century",
    "9bbea428-26aa-4cb9-a9c8-d3f8f059972d": "Slavic settlement and temple, 9th/10th century",
    "aa56465b-1a9e-45b2-abec-b50be3796d8f": "the 1485 grave of Richard III",
}


class UnretireError(PlanError):
    """The step must not run on this state. Nothing was written by it."""


# ------------------------------------------------------------------------------ the export
_SITE_COLUMNS = (
    "u.id::text AS id, u.name, u.country, u.site_type, u.lat, u.lon, u.period_start, "
    "u.period_end, u.scope_status, u.scope_reason, "
    "(SELECT coalesce(json_agg(e.value ORDER BY e.value), '[]'::json) FROM site_external_ids e "
    "WHERE e.site_id = u.id AND e.kind = 'wikidata_qid') AS qids, "
    "EXISTS (SELECT 1 FROM card_stats cs WHERE cs.site_id = u.id "
    "AND cs.card_description IS NOT NULL) AS has_card, "
    "(SELECT max(c.id) FROM remediation_change_log c WHERE c.table_name = 'card_stats' "
    "AND c.column_name = 'card_description' AND c.row_pk = u.id::text) AS card_journal_id, "
    f"{SCOPE_UNRETIRE_PREMISE_SQL} AS premise"
)
#: Every retired curated site: the population the planner decides over.
EXPORT_SITES_SQL = (
    f"SELECT {_SITE_COLUMNS} FROM unified_sites u WHERE u.source_id = "
    f"{sql_literal(CURATED_SOURCE)} AND u.scope_status = {sql_literal(RETIRED)} ORDER BY u.id"
)
#: The `scope_status` journal rows of those sites, every stamp: whose retirement stands.
EXPORT_JOURNAL_SQL = (
    "SELECT l.id, l.row_pk, l.old_value, l.new_value, l.run_stamp FROM remediation_change_log l "
    "JOIN unified_sites u ON u.id::text = l.row_pk WHERE l.table_name = 'unified_sites' AND "
    f"l.column_name = 'scope_status' AND u.source_id = {sql_literal(CURATED_SOURCE)} AND "
    f"u.scope_status = {sql_literal(RETIRED)} ORDER BY l.id"
)
_D50_IDS = ", ".join(sql_literal(site_id) for site_id in sorted(D50_DISPUTED_SITES))
#: The journal rows that wrote the description a D50 site holds now, with what their evidence says
#: of a dispute (`wc4`'s enrichment block): the D50 gate's input.
EXPORT_DISPUTE_SQL = (
    "SELECT l.id, l.row_pk, l.run_stamp, l.evidence->>'decision' AS decision, "
    f"l.evidence->{sql_literal(wc4.ENRICH_EVIDENCE_KEY)}->'dispute' AS dispute, "
    f"l.evidence->{sql_literal(wc4.ENRICH_EVIDENCE_KEY)}->'classes' AS classes "
    "FROM remediation_change_log l JOIN unified_sites u ON u.id::text = l.row_pk "
    "WHERE l.table_name = 'unified_sites' AND l.column_name = 'description' "
    f"AND l.new_value = u.description AND u.id::text IN ({_D50_IDS}) ORDER BY l.id"
)
EXPORT_PARTS = (
    ("site", EXPORT_SITES_SQL),
    ("journal", EXPORT_JOURNAL_SQL),
    ("dispute", EXPORT_DISPUTE_SQL),
)


@dataclass(frozen=True)
class Export:
    sites: tuple[dict[str, Any], ...]
    journal: tuple[dict[str, Any], ...]
    disputes: tuple[dict[str, Any], ...]
    exported_at: str
    sha256: str


def parse_export(text: str) -> Export:
    rows, exported_at = parse_tagged_export(text, (kind for kind, _sql in EXPORT_PARTS))
    return Export(
        tuple(rows["site"]),
        tuple(rows["journal"]),
        tuple(rows["dispute"]),
        exported_at,
        sha256_text(text),
    )


def export_path(out: Path) -> Path:
    return out / "export" / "export.jsonl"


def read_export(path: Path) -> Export:
    if not path.is_file():
        raise UnretireError(f"{path} does not exist - run `export` first")
    return parse_export(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------ the decisions
def latest_retirement(
    site_id: str, journal: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """The site's latest `scope_status` journal row when it wrote `retired`, else None: a retirement
    the journal does not hold (or one a later row moved on from) is not this lane's to take back."""
    rows = [entry for entry in journal if str(entry["row_pk"]) == site_id]
    if not rows:
        return None
    last = max(rows, key=lambda entry: int(entry["id"]))
    return last if last["new_value"] == RETIRED else None


def dispute_text_problems(site_id: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Why the description a D50 site holds now is no dispute enrichment, or nothing: the journal
    row that wrote it (the latest such row) is an enrichment's, carries a well-formed adjudicated
    brief of this site and appended a sentence of each position."""
    mine = [row for row in rows if str(row["row_pk"]) == site_id]
    if not mine:
        return ["no journal row wrote the description the site holds now"]
    row = max(mine, key=lambda r: int(r["id"]))
    if row["decision"] != wc4.EVIDENCE_DECISION_ENRICH:
        return [f"journal row {row['id']} is no lane-E enrichment ({row['decision']!r})"]
    brief = row["dispute"]
    if brief is None:
        return [f"journal row {row['id']} is an enrichment without a dispute brief"]
    problems = list(E.dispute_record_problems(brief))
    if not problems and brief["site_id"] != site_id:
        problems.append(f"the dispute brief is of {brief['site_id']}, not of this site")
    classes = set((row["classes"] or {}).values())
    for needed in (wc4.DISPUTE_A, wc4.DISPUTE_B):
        if needed not in classes:
            problems.append(f"journal row {row['id']} appended no {needed} sentence")
    return problems


def card_problem(site: Mapping[str, Any], written_id: int) -> str | None:
    """Why a D50 site's card may still assert the claim, or None: it has a card text and no
    journal row wrote that card after the journal row `written_id` that wrote its dispute text
    (`identity_lanes.card_cleared_sql`, the invariant's form of the same test)."""
    if not site["has_card"]:
        return None
    card = site["card_journal_id"]
    if card is not None and int(card) > written_id:
        return None
    when = (
        "by no journalled lane, so not after"
        if card is None
        else f"last by remediation_change_log:{card}, before"
    )
    return (
        f"its card was written {when} the dispute text (remediation_change_log:{written_id}): D50 "
        "shows it only once no card asserts the claim - the card lane (D21) rewrites the card first"
    )


#: The year a numeric-cut retirement names: `E3: period_start N is K years past the ... cutoff`.
_RETIRED_YEAR = re.compile(r"^E3: period_start (-?\d+) ")


def retired_year(reason: str) -> int | None:
    """The year `N` of an `E3: period_start N ...` reason, or None for a reason without one."""
    found = _RETIRED_YEAR.match(reason)
    return int(found.group(1)) if found else None


def _cells(
    site: Mapping[str, Any], reason: str, rule: str, evidence: Sequence[dict[str, Any]]
) -> list[Verdict]:
    return [
        Verdict(
            site_id=str(site["id"]),
            site_name=str(site["name"]),
            ok=True,
            old_value=site[column],
            new_value=value,
            rule=rule,
            reason="",
            note=f"{column} {site[column]!r} -> {value!r}",
            phase3=False,
            finding_test_id=TEST_ID,
            evidence=tuple(evidence),
            premise=str(site["premise"]),
            column=column,
        )
        for column, value in (("scope_status", IN_SCOPE), ("scope_reason", reason))
    ]


def _skip(site: Mapping[str, Any], rule: str, note: str) -> Verdict:
    return Verdict(
        site_id=str(site["id"]),
        site_name=str(site["name"]),
        ok=False,
        old_value=site["scope_status"],
        new_value=None,
        rule="",
        reason=rule,
        note=note,
        phase3=False,
        finding_test_id=TEST_ID,
        column="scope_status",
    )


def _journal_evidence(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": f"remediation_change_log:{entry['id']}",
        "url": "remediation_change_log",
        "quote": f"{entry['run_stamp']}: scope_status {entry['old_value']} -> retired",
    }


def _date_decision(
    site: Mapping[str, Any], entry: Mapping[str, Any]
) -> tuple[str, str, list[dict[str, Any]]] | Verdict:
    """A date retirement under the label rule: the cells' reason and evidence, or a skip."""
    vikings = sorted(set(site["qids"] or ()) & set(VIKING_SUBJECT_QIDS))
    if vikings:
        names = ", ".join(f"{q} {VIKING_SUBJECT_QIDS[q]}" for q in vikings)
        return _skip(site, "viking-subject", f"D58 keeps a Viking subject out: {names}")
    region = scope_region(site)
    if region is None or window_date(site) is None:
        return _skip(
            site,
            "label-rule-cannot-tell",
            "no longitude or no date: the label rule cannot place it, the retirement stands",
        )
    if not passes_date_cutoff(site):
        return _skip(
            site,
            "outside-label-window",
            f"date {window_date(site)} is past the {region} cutoff of {LABEL_CUTOFFS[region]} AD: "
            "the retirement stands",
        )
    year = retired_year(str(site["scope_reason"]))
    if year is None:
        return _skip(
            site, "retired-year-unread", "the reason names no year the label rule could test"
        )
    if not passes_date_cutoff({**site, "period_start": year, "period_end": None}):
        return _skip(
            site,
            "retired-year-outside-label-window",
            f"the retirement named period_start {year}, past the {region} cutoff of "
            f"{LABEL_CUTOFFS[region]} AD: the retirement stands",
        )
    if site["site_type"] in NON_SITE_TYPES:
        return _skip(
            site,
            "not-a-site-question-first",
            f"site_type {site['site_type']!r} asks the scope review's not-a-site question first: "
            "the retirement stands until it is answered",
        )
    if label_borderline(site):
        return _skip(
            site,
            "label-borderline",
            f"{site['country']}, date {window_date(site)}: the label decides (a Byzantine, "
            "Crusader or Norse subject is out) - a scope verdict, not this lane",
        )
    reason = (
        f"{D58_REASON_PREFIX}{region}, period_start {site['period_start']} lies inside its window "
        f"through {LABEL_CUTOFFS[region]} AD; the E3 retirement no longer holds"
    )
    evidence = [
        _journal_evidence(entry),
        {"source": "pipeline/normalizers/dates.py", "url": "scope_region", "quote": region},
    ]
    return reason, "d58-label-rule", evidence


def _museum_decision(
    site: Mapping[str, Any], entry: Mapping[str, Any]
) -> tuple[str, str, list[dict[str, Any]]] | Verdict:
    """A museum-rule retirement under the label rule: kept when its exhibits lie outside the
    medieval Old World."""
    exhibits = MUSEUM_EXHIBITS.get(str(site["id"]))
    if exhibits is None:
        return _skip(site, "museum-not-pinned", "no exhibits of this museum are pinned")
    if exhibits not in str(site["scope_reason"]):
        return _skip(
            site,
            "museum-reason-moved",
            f"the stored reason no longer names the pinned exhibits ({exhibits})",
        )
    if site["site_type"] != "Museum":
        return _skip(site, "museum-type-moved", f"site_type is {site['site_type']!r} now")
    region = scope_region(site)
    if region is None:
        return _skip(site, "label-rule-cannot-tell", "no longitude: the label rule cannot place it")
    if region in (MEDIEVAL_OLD_WORLD, UNPLACED_OLD_WORLD):
        return _skip(
            site,
            "museum-exhibits-out",
            f"its exhibits ({exhibits}) are of the medieval Old World: the retirement stands",
        )
    reason = (
        f"{D58_MUSEUM_REASON_PREFIX}its exhibits ({exhibits}) lie in the {region}, inside the "
        f"window through {LABEL_CUTOFFS[region]} AD; the E3 retirement no longer holds"
    )
    evidence = [
        _journal_evidence(entry),
        {"source": "unified_sites.scope_reason", "url": "scope-e4", "quote": exhibits},
        {"source": "pipeline/normalizers/dates.py", "url": "scope_region", "quote": region},
    ]
    return reason, "d58-museum", evidence


def _dispute_decision(
    site: Mapping[str, Any], entry: Mapping[str, Any], disputes: Sequence[Mapping[str, Any]]
) -> tuple[str, str, list[dict[str, Any]]] | Verdict:
    """A D50 site: shown again once its description is a dispute enrichment."""
    sid = str(site["id"])
    if not str(site["scope_reason"] or "").startswith(NOT_A_SITE_PREFIX):
        return _skip(
            site,
            "d50-reason-moved",
            f"retired as {site['scope_reason']!r}, not as no archaeological site: D50 names the "
            "scope review's retirement",
        )
    problems = dispute_text_problems(sid, disputes)
    if problems:
        return _skip(
            site,
            "d50-no-dispute-text",
            "D50 shows it only with a sourced dispute text (lane E, `wc/disputes.py`): "
            + "; ".join(problems),
        )
    written = max(
        (row for row in disputes if str(row["row_pk"]) == sid), key=lambda r: int(r["id"])
    )
    card = card_problem(site, int(written["id"]))
    if card is not None:
        return _skip(site, "d50-card-not-cleared", card)
    brief = written["dispute"]
    reason = (
        f"{D50_REASON_PREFIX}shown as disputed; its description states the scholarly position "
        f"and the claim, both sourced (remediation_change_log:{written['id']})"
    )
    evidence = [
        _journal_evidence(entry),
        {
            "source": f"remediation_change_log:{written['id']}",
            "url": "remediation_change_log",
            "quote": f"{written['run_stamp']}: description, a lane-E dispute enrichment",
        },
        *(
            {"source": s["url"], "url": s["url"], "quote": s["quote"]}
            for side in ("position_a", "position_b")
            for s in brief[side]["sources"]
        ),
    ]
    return reason, "d50-disputed", evidence


def build_plan(export: Export, *, built_at: str, lane: Lane) -> Plan:
    """Every un-retirement the export allows, as the lane's cells - all of them; a wave is its
    first `MAX_SITES` sites (`first_wave`). A pure function of the export."""
    changes: list[Verdict] = []
    skipped: list[Verdict] = []
    for site in sorted(export.sites, key=lambda s: str(s["id"])):
        sid = str(site["id"])
        reason_now = str(site["scope_reason"] or "")
        d50 = sid in D50_DISPUTED_SITES
        if site["scope_status"] != RETIRED:
            raise UnretireError(f"{sid}: the export's site part holds a site that is not retired")
        if not d50 and not reason_now.startswith((DATE_RETIRED_PREFIX, MUSEUM_PREFIX)):
            continue  # duplicates, non-sites and the rest: no decision of D58 or D50 names them
        entry = latest_retirement(sid, export.journal)
        if entry is None:
            skipped.append(
                _skip(site, "retirement-not-journalled", "no journal row of its retirement stands")
            )
            continue
        if d50:
            decided = _dispute_decision(site, entry, export.disputes)
        elif entry["run_stamp"] not in NUMERIC_CUT_STAMPS:
            decided = _skip(
                site,
                "not-the-numeric-cut",
                f"retired by {entry['run_stamp']}, not by the numeric cut "
                f"({', '.join(NUMERIC_CUT_STAMPS)}): D58 takes back only the numeric cut's "
                "retirements",
            )
        elif reason_now.startswith(DATE_RETIRED_PREFIX):
            decided = _date_decision(site, entry)
        else:
            decided = _museum_decision(site, entry)
        if isinstance(decided, Verdict):
            skipped.append(decided)
            continue
        reason, rule, evidence = decided
        changes += _cells(site, reason, rule, evidence)
    rules = [c.rule for c in changes if c.column == "scope_status"]
    counters = {
        "sites": len(rules),
        "cells": len(changes),
        "d58_date": rules.count("d58-label-rule"),
        "d58_museum": rules.count("d58-museum"),
        "d50_disputed": rules.count("d50-disputed"),
        "skipped": len(skipped),
    }
    for verdict in skipped:
        key = f"skipped_{verdict.reason}"
        counters[key] = counters.get(key, 0) + 1
    return Plan(tuple(changes), tuple(skipped), built_at=built_at, counters=counters, lane=lane)


def first_wave(plan: Plan) -> Plan:
    """The plan's first `MAX_SITES` sites (by id), whole sites only."""
    chosen = set(sorted({c.site_id for c in plan.changes})[:MAX_SITES])
    return Plan(
        tuple(c for c in plan.changes if c.site_id in chosen),
        plan.skipped,
        built_at=plan.built_at,
        counters=dict(plan.counters)
        | {"wave_sites": len(chosen), "left_for_later_waves": plan.counters["sites"] - len(chosen)},
        lane=plan.lane,
    )


SOURCE = "SOURCE.json"


def write_wave(out: Path, wave: str, *, built_at: str) -> dict[str, Any]:
    """The next wave from the current export, into `out/<wave>/` (with the default `out` the lane's
    own directory, where `apply.py --lane scope-unretire-<wave>` reads it). Refused when the export
    already planned a wave, the wave has a plan, or there is nothing to write."""
    lane = scope_unretire_lane(wave)
    target = out / wave
    export = read_export(export_path(out))
    for earlier in sorted(out.glob(f"*/{SOURCE}")):
        if json.loads(earlier.read_text(encoding="utf-8"))["export_sha256"] == export.sha256:
            raise UnretireError(
                f"{earlier.parent.name} was planned from this export - run `export` again first"
            )
    if (target / "PLAN.jsonl").exists():
        raise UnretireError(f"{target} holds a plan already - a delivered plan is never replaced")
    plan = first_wave(build_plan(export, built_at=built_at, lane=lane))
    if not plan.changes:
        raise UnretireError(
            "the export leaves nothing to un-retire - SKIPPED reasons: "
            + json.dumps({k: v for k, v in plan.counters.items() if k.startswith("skipped_")})
        )
    target.mkdir(parents=True, exist_ok=True)
    write_plan_jsonl(plan, target / "PLAN.jsonl")
    write_skipped_jsonl(plan, target / "SKIPPED.jsonl")
    write_rollback_sql(plan, target / "ROLLBACK.sql", plan_path=target / "PLAN.jsonl")
    lines = [
        f"# Scope un-retire (D58, D50) - wave {wave}",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/scope_unretire.py` from the "
        f"export of {export.exported_at}. Lane `{lane.name}`, run stamp `{lane.run_stamp}`, test "
        f"id `{lane.test_id}`.",
        "",
        "```json",
        json.dumps(dict(plan.counters), indent=1, sort_keys=True),
        "```",
        "",
        "## Un-retired",
        "",
    ]
    for change in plan.changes:
        if change.column == "scope_reason":
            lines.append(f"* **{change.site_name}** (`{change.site_id}`): {change.new_value}")
            lines += [f"  * {e['source']}: {e['quote']}" for e in change.evidence]
    lines += ["", "## Not un-retired", ""]
    lines += [f"* **{v.site_name}** (`{v.site_id}`): `{v.reason}` - {v.note}" for v in plan.skipped]
    (target / "PLAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    source = {"export_sha256": export.sha256, "exported_at": export.exported_at, "wave": wave}
    write_text_once(target / SOURCE, json_text(source))
    return dict(plan.counters) | {"lane": lane.name, "dir": str(target)}


# ------------------------------------------------------------------------------------- CLI
def _wave(label: str) -> str:
    """`--wave`: a label `apply.py --lane scope-unretire-<label>` resolves, else argparse's error."""
    if SCOPE_UNRETIRE_LANE.match(f"scope-unretire-{label}") is None:
        raise argparse.ArgumentTypeError(f"{label!r} is not a wave label like 2026-10-24")
    return label


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    cmds = {
        name: sub.add_parser(name, help=helps)
        for name, helps in (
            ("export", "read production (read-only) into export/export.jsonl"),
            ("write", "the next wave's plan: PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql"),
        )
    }
    for cmd in cmds.values():
        cmd.add_argument("--out", type=Path, default=DEFAULT_OUT)
    cmds["write"].add_argument(
        "--wave", required=True, type=_wave, help="the wave's date label (2026-10-24, ...)"
    )
    args = ap.parse_args(argv)
    out: Path = args.out
    try:
        if args.command == "export":
            path = write_tagged_export(tagged_export_script(EXPORT_PARTS), export_path(out))
            export = read_export(path)
            print(json.dumps({"export": str(path), "retired_sites": len(export.sites)}))
        else:
            print(json.dumps(write_wave(out, args.wave, built_at=_now()), indent=1, sort_keys=True))
    except (PlanError, StateError, FileNotFoundError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
