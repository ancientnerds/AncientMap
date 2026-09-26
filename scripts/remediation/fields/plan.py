"""WD1 step 4: the decisions, written - journalled, in steps of at most 100 sites, each accepted.

The writer is the mechanical one (`mechanical/apply.py`): each step is a cell lane of its own,
`fields-wd1-<wave>-s<NNN>` (`mechanical/lane.py`, `fields_lane`), with its own run stamp, plan
directory and journal identity, writing `lat`, `lon`, `geom`, `period_start`, `period_name`,
`site_type` and `source_url` of `unified_sites` through `apply_remediation_change()` - every cell
conditioned on its old value (guard 3), the canonical types and the period buckets owned (guard 4),
and two site invariants checked inside the transaction after the loop: a planned site's `geom` is
its point, and its `period_name` is the bucket of its `period_start`.

    $P wave   --wave W                  the sites to write and their steps (WAVE.json), from
                                        DECISIONS.jsonl and CLASSIFIED.jsonl - files only
    $P step   --wave W --step N         the step's plan from a read-only production read:
                                        PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql
                                        (refused until step N-1 is accepted)
    apply.py --lane fields-wd1-W-sNNN --emit | --probe-guards | --rehearse | --rehearse-rollback
             | --apply | --verify
    $P accept --wave W --step N         the step read back from production, cell by cell, and its
                                        journal: ACCEPTED.json with 0 deviations, or refused

**What a site's cells are** (`site_cells`, first failure refuses the field and is recorded in
SKIPPED.jsonl; other fields of the site go on):

* the site is curated and not retired; the decision was made about the value the row still holds
  (`moved-since-classification` otherwise); the field's journal ends at the live value
  (`journal_break`, the period-name lane's rule);
* **coordinates** `replace` -> `lat`, `lon` (whichever change) and `geom` = `SRID=4326;POINT(lon lat)`
  of the new point, **all or none** (`point-incomplete`: a lone lat or lon would break the geom
  invariant inside the transaction and fail the whole step) - refused when the live `geom` is
  neither NULL nor the live point, and when the new point lies in another country than the stored
  one (`country-changes`: a country is the country lanes' question,
  `bcases.classify.country_after_move`). `unresolved` is held for the owner
  (`coordinates-unresolved`); the columns are NOT NULL;
* **period_start** `replace` -> the attested year - refused when the site's `period_end` lies before
  it; `clear` -> NULL; written only together with its label (`period-name-refused` when the
  label's cell is refused);
* **site_type**, **source_url** `replace` -> the value, `clear` -> NULL;
* a field **held** by the import (its last answer failed only on pages the checker could not
  read, `handoff.HELD`) is refused (`held-unreadable`): neither written nor cleared;
* **period_name** follows `period_start` on every site of the wave: the bucket of its final
  `period_start` (`categorize_period`, which must agree with the frontend's `categorizePeriod` -
  `mechanical/period_name.py`'s two-implementations check), NULL with no start. This also repairs
  the labels that disagree with an unchanged start.

`keep` writes nothing: the value stands, now with two quoted sources behind it (DECISIONS.jsonl).
Every held decision - `unresolved` and `held` - is listed in the wave's versioned HELD.jsonl,
whether or not its site has a cell to write.

    $P handoff --wave W                 after the last step is accepted: HANDOFF.json - the sites
                                        written (a card_stats wave recomputes their cards), every
                                        written source_url with the item its article names (a
                                        journalled site_external_ids pass re-derives the ids), and
                                        every written start (the scope check, WD2)

**Undo**: each step's ROLLBACK.sql (written before its APPLY.sql, pinned to its PLAN.jsonl) restores
every old value under the step's `-rollback` stamp - rehearse it with `apply.py --rehearse-rollback`
before the apply; run it deliberately with `psql < ROLLBACK.sql` (FIELD_CONTRACT: reversal is a
decision, never automatic).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import apply as MA  # noqa: E402
from mechanical.lane import FIELDS_ROOT, Lane, fields_lane, sql_literal  # noqa: E402
from mechanical.period_name import SITES_TS, frontend_rule  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    journal_break,
    load_journal,
    psql_json_reader,
    sql_ids,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)

from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from pipeline.utils.text import categorize_period  # noqa: E402

#: At most this many sites per step (PIECE6 section 7, the 100-step write rule).
STEP_SITES = 100
WAVE_FILE = "WAVE.json"
#: sha256 of WAVE.json's LF text, written with it: an edited WAVE.json is refused.
WAVE_PIN_FILE = "WAVE.sha256"
HELD_FILE = "HELD.jsonl"
HANDOFF_FILE = "HANDOFF.json"
ACCEPTED_FILE = "ACCEPTED.json"
NOTHING_FILE = "NOTHING_TO_WRITE.json"
WRITTEN_FIELDS = ("lat", "lon", "geom", "period_start", "period_name", "site_type", "source_url")

LIVE_SQL = """\
SELECT u.id::text AS site_id, u.name, u.source_id, u.scope_status, u.country,
       u.lat::text AS lat_text, u.lon::text AS lon_text, u.geom::text AS geom_text,
       (u.geom IS NOT DISTINCT FROM ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326)) AS geom_is_point,
       u.period_start, u.period_end, u.period_name, u.site_type, u.source_url
  FROM unified_sites u
 WHERE u.id IN ({ids})
 ORDER BY u.id"""


def wave_dir(wave: str) -> Path:
    return REPO / "output" / "remediation" / FIELDS_ROOT / wave


def step_dir(wave: str, step: int) -> Path:
    return MA.lane_dir(fields_lane(wave, step))


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------------------ the wave
def wants_write(decisions: Sequence[Mapping[str, Any]], line: Mapping[str, Any]) -> bool:
    """Whether a site may get a cell: a replace or clear decision, or a period label that is not
    the bucket of its start (as classified)."""
    if any(d["decision"] in (A.REPLACE, A.CLEAR) for d in decisions):
        return True
    return line["period_name"]["stored"] != line["period_name"]["bucket_of_stored_start"]


def build_wave(run: Path, wave: str) -> dict[str, Any]:
    """WAVE.json: the sites of this wave and their steps, from the decision files only."""
    target = wave_dir(wave)
    if (target / WAVE_FILE).exists():
        raise PlanError(f"{target / WAVE_FILE} exists: a wave is planned once")
    fields_fn = run / HO.DECISIONS_FILE
    decisions = HO._read_jsonl(fields_fn)
    if not decisions:
        raise PlanError(f"{fields_fn} holds no decision - import the handoff first")
    reask = json.loads((run / HO.REASK_FILE).read_text(encoding="utf-8"))
    if reask["fields"]:
        raise PlanError(
            f"{sum(len(v) for v in reask['fields'].values())} field(s) still wait for a re-ask: "
            "the wave is planned when every asked field is decided"
        )
    classified = HO.read_classified(run)
    by_site: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        by_site.setdefault(d["site_id"], []).append(d)
    sites = sorted(
        sid for sid, line in classified.items() if wants_write(by_site.get(sid, []), line)
    )
    steps = [sites[i : i + STEP_SITES] for i in range(0, len(sites), STEP_SITES)]
    held = [
        {
            key: d[key]
            for key in ("site_id", "name", "field", "decision", "via", "stored", "reasoning")
        }
        for d in sorted(decisions, key=lambda d: (d["site_id"], C.FIELDS.index(d["field"])))
        if d["decision"] in (A.UNRESOLVED, HO.HELD)
    ]
    record = {
        "wave": wave,
        "built_at": C.H.now(),
        "decisions_sha256": _sha256_text(fields_fn),
        "classified_sha256": _sha256_text(run / C.CLASSIFIED_FILE),
        "run": HO._shown(run),
        "sites": len(sites),
        "held": len(held),
        "steps": steps,
    }
    target.mkdir(parents=True, exist_ok=True)
    HO._write_jsonl(target / HELD_FILE, held)
    write_wave(wave, record)
    return {"wave": wave, "sites": len(sites), "steps": len(steps), "held": len(held)}


def write_wave(wave: str, record: Mapping[str, Any]) -> None:
    """WAVE.json and its pin (WAVE.sha256), written together."""
    target = wave_dir(wave)
    HO._write_json(target / WAVE_FILE, record)
    (target / WAVE_PIN_FILE).write_text(
        _sha256_text(target / WAVE_FILE) + "\n", encoding="utf-8", newline="\n"
    )


def read_wave(wave: str) -> dict[str, Any]:
    """WAVE.json - refused when it is not the file its pin names (an edit after `plan.py wave`)."""
    path = wave_dir(wave) / WAVE_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `plan.py wave` first")
    pin = (wave_dir(wave) / WAVE_PIN_FILE).read_text(encoding="utf-8").strip()
    if _sha256_text(path) != pin:
        raise PlanError(f"{path} is not the pinned wave ({WAVE_PIN_FILE}): it was edited")
    return json.loads(path.read_text(encoding="utf-8"))


def _step_size(sites: Sequence[str]) -> None:
    if len(sites) > STEP_SITES:
        raise PlanError(f"{len(sites)} sites: a step holds at most {STEP_SITES}")


# ------------------------------------------------------------------------------ one site
def _point_text(value: float) -> str:
    """A coordinate as the plan writes it: Python's shortest round-trip form, which is the form
    PostgreSQL prints a double in, so the journal's text is the stored value's."""
    return repr(float(value))


def ewkt(lat: float, lon: float) -> str:
    return f"SRID=4326;POINT({_point_text(lon)} {_point_text(lat)})"


def _verdict(
    live: Mapping[str, Any],
    column: str,
    *,
    ok: bool,
    old: str | None,
    new: str | None,
    rule: str,
    reason: str,
    note: str,
    evidence: Sequence[Mapping[str, Any]] = (),
) -> Verdict:
    return Verdict(
        site_id=str(live["site_id"]),
        site_name=str(live["name"]),
        ok=ok,
        old_value=old,
        new_value=new,
        rule=rule,
        reason=reason,
        note=note,
        phase3=False,
        finding_test_id=f"WD1/{column}",
        evidence=tuple(evidence),
        column=column,
    )


def _decision_evidence(decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The journal's evidence of a decided cell: each quote with its URL and its check's outcome,
    and the decision itself."""
    quoted = [
        {"source": q["source"], "url": q["source"], "quote": q["quote"], "outcome": q["outcome"]}
        for q in decision["quotes"]
    ]
    return [
        *quoted,
        {
            "source": f"WD1 decision ({decision['via']}, round {decision['round']}, "
            f"{decision['answered_by']})",
            "decision": decision["decision"],
            "status": decision["status"],
            "reasoning": decision["reasoning"],
            "value_page": decision["value_page"],
        },
    ]


def _journal_ok(
    column: str, links: Sequence[JournalLink], live: str | None
) -> tuple[str, str] | None:
    """`journal_break` in the column's own terms: a coordinate is compared as a number (the journal
    carries the text a writer gave, the database prints the double its own way). `geom` is not
    read: its journal carries EWKT and the database prints hex EWKB, and the live geom must be the
    live point anyway (`geom-not-point`) - its chain is the lat/lon chains."""
    if column == "geom":
        return None
    if column in ("lat", "lon") and links and live is not None:
        last = links[-1].new_value
        if last is not None and float(last) == float(live):
            live = last
    return journal_break(links, live)


def site_cells(
    live: Mapping[str, Any],
    line: Mapping[str, Any],
    decisions: Mapping[str, Mapping[str, Any]],
    journals: Mapping[str, Sequence[JournalLink]],
    *,
    country_check: Callable[[str, float, float], Mapping[str, Any]],
    derive: Callable[[int | None], str | None] = categorize_period,
    frontend: Callable[[int], str] | None = None,
) -> list[Verdict]:
    """Every cell of one site - writes (`ok`) and refusals. Pure: every input is given."""
    out: list[Verdict] = []

    def refusal(column: str, reason: str, note: str, old: Any = None, new: Any = None) -> Verdict:
        return _verdict(live, column, ok=False, old=old, new=new, rule="", reason=reason, note=note)

    def refuse(column: str, reason: str, note: str, old: Any = None, new: Any = None) -> None:
        out.append(refusal(column, reason, note, old, new))

    if live["source_id"] != CURATED_SOURCE or live["scope_status"] == "retired":
        refuse(
            "site", "not-a-curated-live-site", f"source {live['source_id']}, {live['scope_status']}"
        )
        return out

    def cell(column: str, old: str | None, new: str | None, rule: str, note: str,
             evidence: Sequence[Mapping[str, Any]]) -> Verdict:  # fmt: skip
        """The cell's write - or its refusal, when its journal does not end at the live value."""
        broken = _journal_ok(column, journals.get(column, ()), old)
        if broken is not None:
            return refusal(column, broken[0], broken[1], old, new)
        return _verdict(live, column, ok=True, old=old, new=new, rule=rule, reason="",
                        note=note, evidence=evidence)  # fmt: skip

    def write(column: str, old: str | None, new: str | None, rule: str, note: str,
              evidence: Sequence[Mapping[str, Any]]) -> None:  # fmt: skip
        out.append(cell(column, old, new, rule, note, evidence))

    start = live["period_start"]
    final_start: int | None = None if start is None else int(start)
    for field in C.FIELDS:
        decision = decisions.get(field)
        if decision is None or decision["decision"] == A.KEEP:
            continue
        stored = decision["stored"]
        if decision["decision"] == HO.HELD:
            column = "lat" if field == "coordinates" else field
            refuse(column, "held-unreadable", decision["reasoning"], None if stored is None
                   else str(stored))  # fmt: skip
            continue
        evidence = _decision_evidence(decision)
        if field == "coordinates":
            live_point = f"{float(live['lat_text'])}, {float(live['lon_text'])}"
            if stored != live_point:
                refuse(
                    "lat",
                    "moved-since-classification",
                    f"decided about {stored}, holds {live_point}",
                )
                continue
            if decision["decision"] == A.UNRESOLVED:
                refuse("lat", "coordinates-unresolved", decision["reasoning"], live_point)
                continue
            lat, lon = (float(x) for x in str(decision["value"]).split(","))
            if not (live["geom_text"] is None or live["geom_is_point"]):
                refuse("geom", "geom-not-point", "the live geom is neither NULL nor the live point")
                continue
            country = country_check(str(live["country"]), lat, lon)
            if not country["agrees"]:
                refuse(
                    "lat",
                    "country-changes",
                    f"the new point lies in {country['polygon']}, the site says {live['country']}",
                    live_point,
                    str(decision["value"]),
                )
                continue
            note = f"{live_point} -> {_point_text(lat)}, {_point_text(lon)}"
            group = []
            if float(live["lat_text"]) != lat:
                group.append(cell("lat", live["lat_text"], _point_text(lat), "wd1-replace", note,
                                  evidence))  # fmt: skip
            if float(live["lon_text"]) != lon:
                group.append(cell("lon", live["lon_text"], _point_text(lon), "wd1-replace", note,
                                  evidence))  # fmt: skip
            group.append(cell("geom", live["geom_text"], ewkt(lat, lon), "wd1-point", note,
                              evidence))  # fmt: skip
            broken = [v for v in group if not v.ok]
            if not broken:
                out.extend(group)
                continue
            first = broken[0]
            for v in group:
                if v.ok:
                    refuse(v.column, "point-incomplete",
                           f"the point is written whole: {first.column} is refused ({first.reason})",
                           v.old_value, v.new_value)  # fmt: skip
                else:
                    out.append(v)
            continue
        current = live[field]
        current_text = None if current is None else str(current)
        stored_text = None if stored is None else str(stored)
        if current_text != stored_text:
            refuse(
                field, "moved-since-classification", f"decided about {stored!r}, holds {current!r}"
            )
            continue
        new = None if decision["decision"] == A.CLEAR else str(decision["value"])
        if new == current_text:
            continue
        if field == "period_start":
            end = live["period_end"]
            if new is not None and end is not None and int(end) != 0 and int(new) > int(end):
                refuse(
                    field,
                    "period-end-precedes-start",
                    f"period_end {end} < {new}",
                    current_text,
                    new,
                )
                continue
        rule = "wd1-clear" if new is None else "wd1-replace"
        write(field, current_text, new, rule, f"{current_text!r} -> {new!r}", evidence)
        if field == "period_start" and out[-1].ok:
            final_start = None if new is None else int(new)
    unchained = [v for v in out if v.column == "period_start" and v.reason.startswith("journal-")]
    if unchained:
        refuse(
            "period_name",
            "period-start-journal",
            "the label follows a start written around the journal",
        )
        return out
    label = None if final_start is None else derive(final_start)
    started = [v for v in out if v.ok and v.column == "period_start"]
    named: Verdict | None = None
    if final_start is not None and frontend is not None and frontend(final_start) != label:
        named = refusal(
            "period_name", "implementations-disagree", f"categorize_period({final_start})"
        )
    elif label != live["period_name"]:
        evidence = [
            {
                "source": "pipeline/utils/text.py:categorize_period",
                "url": "pipeline/utils/text.py",
                "quote": f"categorize_period({final_start}) = {label!r}",
            },
            {
                "source": "output/remediation/gold_standard/GOLD_STANDARD.md:79",
                "url": "output/remediation/gold_standard/GOLD_STANDARD.md",
                "quote": "| `period_name` | equals `categorize_period(period_start)` |",
            },
        ]
        named = cell(
            "period_name",
            live["period_name"],
            label,
            "wd1-derive-period-name",
            f"period_start {final_start}{' (written in this step)' if started else ''}",
            evidence,
        )
    if named is None:
        return out
    if not named.ok and started:
        # a start without its label breaks the period invariant inside the transaction
        out = [v for v in out if v not in started]
        for v in started:
            refuse("period_start", "period-name-refused",
                   f"the start is written only with its label: period_name is refused "
                   f"({named.reason})", v.old_value, v.new_value)  # fmt: skip
    out.append(named)
    return out


# ------------------------------------------------------------------------------ one step
def _previous_accepted(wave: str, step: int) -> None:
    if step == 1:
        return
    before = step_dir(wave, step - 1)
    accepted = before / ACCEPTED_FILE
    if not accepted.exists():
        raise PlanError(f"step {step - 1} is not accepted ({accepted} is missing)")
    if json.loads(accepted.read_text(encoding="utf-8"))["deviations"] != 0:
        raise PlanError(f"step {step - 1} was accepted with deviations")


def build_step(
    wave: str,
    step: int,
    *,
    reader: Callable[[str], list[dict[str, Any]]],
    country_check: Callable[[str, float, float], Mapping[str, Any]],
    frontend: Callable[[int], str],
) -> dict[str, Any]:
    """The plan of one step, from a read-only read of its sites - never a step before the one
    before it is accepted."""
    record = read_wave(wave)
    if not 1 <= step <= len(record["steps"]):
        raise PlanError(f"wave {wave} has steps 1..{len(record['steps'])}, not {step}")
    _previous_accepted(wave, step)
    lane = fields_lane(wave, step)
    out = MA.lane_dir(lane)
    if (out / "APPLY.sql").exists() or (out / ACCEPTED_FILE).exists():
        raise PlanError(f"{out} holds an emitted or accepted step: it is not planned again")
    run = HO._resolve(Path(record["run"]))
    if _sha256_text(run / HO.DECISIONS_FILE) != record["decisions_sha256"]:
        raise PlanError("DECISIONS.jsonl is not the one the wave was built from")
    classified = HO.read_classified(run)
    decisions: dict[str, dict[str, Mapping[str, Any]]] = {}
    for d in HO._read_jsonl(run / HO.DECISIONS_FILE):
        decisions.setdefault(d["site_id"], {})[d["field"]] = d
    sites = record["steps"][step - 1]
    _step_size(sites)
    rows = {str(r["site_id"]): r for r in reader(LIVE_SQL.format(ids=sql_ids(sites)))}
    missing = sorted(set(sites) - set(rows))
    if missing:
        raise PlanError(f"{len(missing)} site(s) of the step no longer exist: {missing[:3]}")
    journals = {column: load_journal(reader, column, sites) for column in WRITTEN_FIELDS}
    verdicts: list[Verdict] = []
    for sid in sites:
        verdicts.extend(
            site_cells(
                rows[sid],
                classified[sid],
                decisions.get(sid, {}),
                {column: journals[column].get(sid, ()) for column in WRITTEN_FIELDS},
                country_check=country_check,
                frontend=frontend,
            )
        )
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters = {
        "sites": len(sites),
        "cells": len(changes),
        "sites_written": len({v.site_id for v in changes}),
        "refused": len(skipped),
        **{f"cells:{k}": n for k, n in sorted(Counter(v.column for v in changes).items())},
        **{f"refused:{k}": n for k, n in sorted(Counter(v.reason for v in skipped).items())},
    }
    plan = Plan(changes=changes, skipped=skipped, built_at=C.H.now(), counters=counters, lane=lane)
    out.mkdir(parents=True, exist_ok=True)
    write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
    if not changes:
        HO._write_json(out / NOTHING_FILE, {"built_at": plan.built_at, **counters})
        return {"step": step, **counters}
    MA.validate_records(MA.load_records(_plan_file(plan, out)), lane=lane)
    write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    write_plan_md(plan, out / "PLAN.md")
    return {"step": step, **counters}


def _plan_file(plan: Plan, out: Path) -> Path:
    write_plan_jsonl(plan, out / "PLAN.jsonl")
    return out / "PLAN.jsonl"


def write_plan_md(plan: Plan, path: Path) -> None:
    lane = plan.lane
    lines = [
        f"# WD1 {lane.name}: plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/fields/plan.py`. Run stamp "
        f"`{lane.run_stamp}`, test id `{lane.test_id}`, change keys `{lane.key_prefix}:<site>:<column>`.",
        "",
        "| counter | value |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in plan.counters.items()),
        "",
        "## Cells",
        "",
        "| site | column | old | new | rule |",
        "|---|---|---|---|---|",
    ]
    for v in sorted(plan.changes, key=lambda v: (v.site_name, str(v.column))):
        old = "NULL" if v.old_value is None else v.old_value[:60]
        new = "NULL" if v.new_value is None else v.new_value[:60]
        lines.append(f"| {v.site_name} | {v.column} | `{old}` | `{new}` | {v.rule} |")
    if plan.skipped:
        lines += ["", "## Refused", "", "| site | column | reason | note |", "|---|---|---|---|"]
        lines += [
            f"| {v.site_name} | {v.column} | `{v.reason}` | {v.note[:120]} |" for v in plan.skipped
        ]
    lines += [
        "",
        "## Undo",
        "",
        "`ROLLBACK.sql` restores every old value under the stamp "
        f"`{lane.rollback_run_stamp}`; rehearse it with `apply.py --lane {lane.name} "
        "--rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------ the acceptance
ACCEPT_SQL = """\
WITH planned(site_id, column_name, old_value, new_value) AS (VALUES {values})
SELECT 'planned cells holding their new value' AS metric, count(*)::text AS value
  FROM planned p JOIN unified_sites u ON u.id = p.site_id
 WHERE {holds}
UNION ALL
SELECT 'journal rows for the stamp', count(*)::text
  FROM remediation_change_log WHERE run_stamp = {stamp}
UNION ALL
SELECT 'journal rows matching a planned cell exactly', count(*)::text
  FROM remediation_change_log l JOIN planned p
    ON l.row_pk = p.site_id::text AND l.column_name = p.column_name
   AND l.old_value IS NOT DISTINCT FROM p.old_value AND l.new_value IS NOT DISTINCT FROM p.new_value
 WHERE l.run_stamp = {stamp} AND l.table_name = 'unified_sites'
UNION ALL
SELECT 'journal rows of another stamp on a planned cell since', count(*)::text
  FROM remediation_change_log l JOIN planned p
    ON l.row_pk = p.site_id::text AND l.column_name = p.column_name
 WHERE l.run_stamp <> {stamp} AND l.id > (SELECT coalesce(min(id), 0) FROM remediation_change_log
                                          WHERE run_stamp = {stamp})
{invariants}"""


def accept_sql(lane: Lane, records: Sequence[MA.ChangeRecord]) -> str:
    values = ", ".join(
        f"({sql_literal(r.site_id)}::uuid, {sql_literal(r.column)}, {sql_literal(r.old_value)}, "
        f"{sql_literal(r.new_value)})"
        for r in records
    )
    holds = MA.cell_case(lane, "p.new_value", alias="u", compare="IS NOT DISTINCT FROM",
                         otherwise="false")  # fmt: skip
    invariants = "".join(
        f"UNION ALL\nSELECT {sql_literal('planned sites breaking: ' + i.says)}, count(*)::text\n"
        f"  FROM (SELECT DISTINCT site_id FROM planned) p JOIN unified_sites u ON u.id = p.site_id\n"
        f" WHERE {i.predicate.format(plan='planned')}\n"
        for i in lane.site_invariants
    )
    return ACCEPT_SQL.format(
        values=values, holds=holds, stamp=sql_literal(lane.run_stamp), invariants=invariants
    )


def deviations(counts: Mapping[str, int], planned: int) -> list[str]:
    """Every way the read-back differs from the plan."""
    wanted = {
        "planned cells holding their new value": planned,
        "journal rows for the stamp": planned,
        "journal rows matching a planned cell exactly": planned,
        "journal rows of another stamp on a planned cell since": 0,
    }
    out = [f"{k} = {counts.get(k)}, expected {v}" for k, v in wanted.items() if counts.get(k) != v]
    out += [
        f"{k} = {n}, expected 0"
        for k, n in counts.items()
        if k.startswith("planned sites breaking") and n
    ]
    return out


def accept(
    wave: str, step: int, *, read_rows: Callable[[str], list[list[str]]] = MA.read_rows
) -> dict[str, Any]:
    """The step's independent acceptance, read-only: ACCEPTED.json, or refused."""
    lane = fields_lane(wave, step)
    out = MA.lane_dir(lane)
    if (out / ACCEPTED_FILE).exists():
        raise PlanError(f"{out / ACCEPTED_FILE} exists: a step is accepted once")
    if (out / NOTHING_FILE).exists():
        result = {"step": step, "planned": 0, "deviations": 0, "note": "nothing to write",
                  "accepted_at": C.H.now()}  # fmt: skip
        HO._write_json(out / ACCEPTED_FILE, result)
        return result
    records = MA.load_records(out / "PLAN.jsonl")
    _step_size(sorted({r.site_id for r in records}))
    MA.verify_pinned(out / "APPLY.sql", plan_path=out / "PLAN.jsonl",
                     expected=MA.apply_statement(records, lane))  # fmt: skip
    counts = {name.strip(): int(value) for name, value in read_rows(accept_sql(lane, records))}
    found = deviations(counts, len(records))
    result = {
        "step": step,
        "run_stamp": lane.run_stamp,
        "planned": len(records),
        "sites": len({r.site_id for r in records}),
        "counts": counts,
        "deviations": len(found),
        "found": found,
        "accepted_at": C.H.now(),
    }
    if found:
        raise PlanError(f"step {step}: {len(found)} deviation(s): {found}")
    HO._write_json(out / ACCEPTED_FILE, result)
    return result


# ------------------------------------------------------------------------------ the hand-off
def _value_page_of(record: MA.ChangeRecord) -> Mapping[str, Any] | None:
    """The value page the source_url cell's decision recorded (its evidence's decision entry)."""
    entries = [e for e in record.evidence if str(e.get("source", "")).startswith("WD1 decision")]
    if len(entries) != 1:
        raise PlanError(f"{record.site_id}/{record.column}: not one WD1 decision in its evidence")
    return entries[0]["value_page"]


def handoff(wave: str) -> dict[str, Any]:
    """HANDOFF.json, once every step is accepted with 0 deviations: what the wave wrote that
    derived stores must follow. `sites_written` - their cards (`card_stats`: category group,
    antiquity, mystery, rarity, empires) are recomputed by a card_stats wave; `source_urls` - each
    written source_url with the item its new article names, from which a journalled
    site_external_ids pass (the qid_repair / L5 tool) re-derives the site's `wikidata_qid` and
    `enwiki_title` (a cleared URL: the ids derived from the old one are stale); `starts` - each
    written or cleared period_start, which the scope check (WD2) reads against the E3 window."""
    record = read_wave(wave)
    written: list[MA.ChangeRecord] = []
    for number in range(1, len(record["steps"]) + 1):
        out = step_dir(wave, number)
        accepted = out / ACCEPTED_FILE
        if not accepted.exists():
            raise PlanError(f"step {number} is not accepted ({accepted} is missing)")
        if json.loads(accepted.read_text(encoding="utf-8"))["deviations"] != 0:
            raise PlanError(f"step {number} was accepted with deviations")
        if (out / NOTHING_FILE).exists():
            continue
        written.extend(MA.load_records(out / "PLAN.jsonl"))
    source_urls = []
    for r in sorted((r for r in written if r.column == "source_url"), key=lambda r: r.site_id):
        page = _value_page_of(r) or {}
        source_urls.append(
            {
                "site_id": r.site_id,
                "name": r.site_name,
                "old": r.old_value,
                "new": r.new_value,
                "lang": page.get("lang"),
                "resolved_title": page.get("resolved_title"),
                "wikibase_item": page.get("wikibase_item"),
            }
        )
    result = {
        "wave": wave,
        "built_at": C.H.now(),
        "sites_written": sorted({r.site_id for r in written}),
        "source_urls": source_urls,
        "starts": [
            {"site_id": r.site_id, "name": r.site_name, "old": r.old_value, "new": r.new_value}
            for r in sorted(written, key=lambda r: r.site_id)
            if r.column == "period_start"
        ],
    }
    HO._write_json(wave_dir(wave) / HANDOFF_FILE, result)
    return result


# ------------------------------------------------------------------------------ the CLI
def _country_check() -> Callable[[str, float, float], Mapping[str, Any]]:
    """`bcases.classify.country_after_move` over the boundary file, loaded once."""
    from bcases.classify import country_after_move

    tools = REPO / "output" / "remediation" / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import country_census as CC  # noqa: PLC0415 - the boundary file and its spelling rules

    atlas = CC.load_countries()
    return lambda country, lat, lon: country_after_move(country, lat, lon, atlas)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        name: sub.add_parser(name) for name in ("wave", "step", "accept", "handoff", "status")
    }
    for command in commands.values():
        command.add_argument(
            "--wave", required=True, help="a date label: 2026-09-27 or 2026-09-27b"
        )
    commands["wave"].add_argument("--run", type=Path, default=C.DEFAULT_OUT)
    for name in ("step", "accept"):
        commands[name].add_argument("--step", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "wave":
            fields_lane(args.wave, 1)
            result: Any = build_wave(HO._resolve(args.run), args.wave)
        elif args.command == "step":
            result = build_step(
                args.wave,
                args.step,
                reader=psql_json_reader(),
                country_check=_country_check(),
                frontend=frontend_rule(SITES_TS.read_text(encoding="utf-8")),
            )
        elif args.command == "accept":
            result = accept(args.wave, args.step)
        elif args.command == "handoff":
            result = handoff(args.wave)
        else:
            record = read_wave(args.wave)
            result = {
                "sites": record["sites"],
                "steps": [
                    {
                        "step": n,
                        "planned": (step_dir(args.wave, n) / "PLAN.jsonl").exists(),
                        "applied": (step_dir(args.wave, n) / "APPLY.sql").exists(),
                        "accepted": (step_dir(args.wave, n) / ACCEPTED_FILE).exists(),
                    }
                    for n in range(1, len(record["steps"]) + 1)
                ],
            }
    except (PlanError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
