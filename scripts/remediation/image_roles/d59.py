"""D59 (owner decision of 2026-10-24): the shown sites whose only picture is a hotlinked thumbnail.

"Replace the third-party ones, credit the Commons ones: the 9 third-party hotlinks join the D17
research (a checked Commons picture with credit, else the thumbnail goes NULL); the 131 Commons
thumbnails get a credited gallery row of the same file through the INSERT lane after a Sonnet depicts
check. Lifts the 2026-10-05 thumbnail-only rule for these sites."

Two populations, two paths, no new writer:

* **The 131 Commons thumbnails** (`candidates`): a candidate run directory whose population is the
  sites with no live row and a hotlinked Commons file as `thumbnail_url`
  (`candidate_search.population.population_sql(kind=COMMONS_THUMBNAIL)`), and whose only candidate
  per site is **that file** - asked of Commons for its rendering, its MIME type and its size, exactly
  as the search asks (`served_image.commons`). From there the image roles' chain runs unchanged
  except for the prefilter: `pictures`, then `depicts-export` - the Sonnet depicts check D59 names,
  over every fetched candidate, because the run carries the `D59.json` marker
  (`image_roles.flow.skips_prefilter`: a Haiku cut must not decide a picture the owner sent to the
  depicts role) -, `recheck-export` and `write-targets`. The adversarial re-check stays: the INSERT
  lane takes only a confirmed target, the second look every picture of the lanes gets before it
  goes on a page (D17), so D59 does not lower that bar. Then `judge_run.py insert-claims`, which
  words the claim as a D59 first row and marks it (`candidate_search.judge.d59_wording`), and the
  INSERT lane, whose plan lifts the thumbnail-only rule only for such a claim and only while the read
  still shows that very thumbnail and the fetched file is that very file
  (`import_hero.insert.d59_refusal`).
* **The 9 third-party thumbnails** are in the D17 population itself (`population_sql` of kind
  `research`). Where the research confirms a Commons picture, the INSERT wave replaces the
  thumbnail. `null-plan` sets the `thumbnail_url` to NULL through the shared image writer (lane
  `d59-thumb`) for every site the research found nothing for - only once every candidate of the site
  was judged, so a site still waiting for a round is never emptied - and for every site whose
  confirmed picture the INSERT lane refused for good (`--insert-run`: a credit the file lacks, a
  failed fetch, a file an excluded row already holds), each with the measured reason as evidence.
  A confirmed site no INSERT run covers, one whose INSERT is planned but not in production, and one
  whose INSERT run was planned from another state of the site are refused by name: D59 knows two
  ends, a credited Commons picture or NULL, and no third that waits.

A candidate the Commons answer refuses - a file Commons no longer holds, one that is no still picture,
one renamed since (a redirect: "the same file" would no longer hold), one below the floor, one an
excluded row of the site already holds (unhiding it needs a judgement of its own) - is named in
`CANDIDATE_REFUSALS.jsonl`, never skipped. `outcomes` states per site of a D59 run where it stands
(`D59_OUTCOMES.jsonl`) and lists every site that keeps its uncredited hotlink with the reason
(`D59_OWNER_LIST.jsonl`; the floor refusals are the owner question of the runbook).

    d59.py candidates     --run-dir C [--min-width 800 --min-height 300]
    d59.py outcomes       --run-dir C [--insert-run I ...]
    d59.py null-read      --run-dir N          (N = output/remediation/d59/d59-thumb-<date>)
    d59.py null-plan      --run-dir N --research-run C [C ...] [--insert-run I ...]
    chunk_writer.py N/chunks/chunk-NNN --check | --rehearse | --apply | --readback | --rehearse-rollback
    d59.py null-accept    --run-dir N --chunk N/chunks/chunk-NNN
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import research_web  # noqa: E402
from candidate_search import judge as CJ  # noqa: E402
from candidate_search import population as PP  # noqa: E402
from candidate_search import search as CS  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from served_image import commons as CM  # noqa: E402
from served_image import plan as SP  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import flow as FL  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402

#: The route a D59 candidate carries: the site's own thumbnail, not a search hit.
ROUTE = "d59_thumbnail"
MARKER = FL.D59_MARKER

LANE_NAME = "d59-thumb"
TEST_ID = "D59/thumbnail-null"
LABEL = "third-party thumbnail"
RULE_NULL = "d59-thumb-null"
RUN_RE = re.compile(r"d59-thumb-(\d{4}-\d{2}-\d{2}[a-z]?)")
CLEARED = "thumbnail cleared"
READ_FILE = "READ.json"
CHUNKS = "chunks"
EXPECTED = "EXPECTED.jsonl"
SUMMARY = "PLAN_SUMMARY.json"
OUTCOMES = "D59_OUTCOMES.jsonl"
OWNER_LIST = "D59_OWNER_LIST.jsonl"

#: The research outcomes `research_outcome` names.
TARGET, NO_CANDIDATE, NONE_CONFIRMED = "target", "no_candidate", "none_confirmed"
#: What an INSERT run did with a confirmed target (`insert_state`).
NOT_CLAIMED, NOT_PLANNED, PLANNED, REFUSED = "not_claimed", "not_planned", "planned", "refused"
#: INSERT refusals that speak of another state of the site than the one read now: the INSERT is
#: planned again from a fresh read, the thumbnail is not emptied on them.
STALE_INSERT_REASONS = frozenset({"retired", "d59_thumbnail_moved"})
#: The INSERT lane's record files (`import_hero/run.py`).
INSERT_CLAIMS = "IMPORT_CLAIMS.json"
INSERT_SEEDS = "IMPORT_HERO_REFUSALS.jsonl"
INSERT_REFUSALS = "INSERT_REFUSALS.jsonl"
FETCH_FAILURES = "FETCH_FAILURES.jsonl"


class D59Error(ST.StateError):
    """D59's inputs do not allow the step. Nothing was written."""


def _refuse_existing(paths: Iterable[Path], what: str) -> None:
    """Every write-once target is checked before the first write (and before any network call),
    so a refused step leaves no half of its files behind."""
    found = [p for p in paths if p.exists()]
    if found:
        raise D59Error(f"{found[0]} exists - {what} is written once and never replaced")


# ----------------------------------------------------------------------- the 131 Commons files
def commons_candidates(
    sites: Sequence[Mapping[str, Any]], commons: Any, *, floor: tuple[int, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(CANDIDATES lines, refusals)`: per site the one candidate D59 allows - its own thumbnail's
    Commons file - in the shape `candidate_search/search.py` writes."""
    files = {}
    for site in sites:
        thumb = site.get("thumbnail_url")
        if not PP.is_commons_thumbnail(thumb):
            raise D59Error(f"{site['site_id']}: {thumb!r} is no hotlinked Commons file")
        name = ST.file_of_url(str(thumb))
        if name is None:
            raise D59Error(f"{site['site_id']}: {thumb!r} names no Commons file")
        files[str(site["site_id"])] = name
    info = commons.imageinfo(files.values())
    boxes = commons.sizes(files.values())
    lines: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []

    def refuse(sid: str, reason: str, detail: str) -> None:
        refusals.append({"site_id": sid, "reason": reason, "detail": detail, "notes": []})

    for site in sites:
        sid = str(site["site_id"])
        file = files[sid]
        entry = info.get(file) or {}
        if entry.get("status") != CM.OK:
            refuse(sid, "missing_on_commons", f"Commons does not hold {file!r}")
            continue
        if entry.get("title") != file:
            refuse(
                sid,
                "renamed_on_commons",
                f"{file!r} redirects to {entry.get('title')!r}: the thumbnail names another title",
            )
            continue
        shown = CM.picture_url(entry)
        if shown is None:
            refuse(sid, "not_a_still_picture", f"{file!r} is {entry.get('mime')!r}")
            continue
        if file in (site.get("held_files") or ()):
            refuse(
                sid,
                "an_excluded_row_holds_the_file",
                f"an excluded row of the site holds {file!r}: unhiding it needs a judgement and a "
                "lane of its own, the INSERT lane creates no second copy",
            )
            continue
        width, height = boxes.get(file, (0, 0))
        if width < floor[0] or height < floor[1]:
            refuse(
                sid,
                CS.ALL_TOO_SMALL,
                f"{file!r} is {width}x{height}, below {floor[0]}x{floor[1]}",
            )
            continue
        lines.append(
            {
                "site_id": sid,
                "name": str(site.get("name") or ""),
                "country": str(site.get("country") or ""),
                "floor": {"min_width": floor[0], "min_height": floor[1]},
                "candidates": [
                    {
                        "file": file,
                        "why": "D59: the site's own hotlinked thumbnail, shown without a credit",
                        "route": ROUTE,
                        "picture_url": shown,
                        "original_url": entry.get("url"),
                        "width": width,
                        "height": height,
                    }
                ],
                "notes": [],
                "capped": [],
            }
        )
    return lines, refusals


def write_candidates(
    run: Path, rows: Sequence[Mapping[str, Any]], commons: Any, *, floor: tuple[int, int]
) -> dict[str, Any]:
    """The D59 candidate run directory: `POPULATION.jsonl`, `CANDIDATES.jsonl`, the refusals and
    the `D59.json` marker - each written once, all after the Commons answers are in, the marker
    last."""
    names = (PP.POPULATION_FILE, CS.CANDIDATES, CS.REFUSALS, MARKER)
    _refuse_existing((run / name for name in names), "a candidate run's record")
    sites = PP.build(rows)
    lines, refusals = commons_candidates(sites, commons, floor=floor)
    population_sha = PP.write_population(run / PP.POPULATION_FILE, sites)
    ST.write_text_once(run / CS.CANDIDATES, ST.jsonl_text(lines))
    ST.write_text_once(run / CS.REFUSALS, ST.jsonl_text(refusals))
    counts: dict[str, int] = {}
    for refusal in refusals:
        counts[refusal["reason"]] = counts.get(refusal["reason"], 0) + 1
    summary = {
        "decision": "D59",
        "made_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "population_sha256": population_sha,
        "sites": len(sites),
        "candidates": len(lines),
        "refused": counts,
        "floor": {"min_width": floor[0], "min_height": floor[1]},
    }
    ST.write_text_once(run / MARKER, ST.json_text(summary))
    return summary


# ----------------------------------------------------------------- the 9 third-party thumbnails
THIRD_PARTY_SQL = f"""SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.name, u.thumbnail_url, u.source_id FROM unified_sites u
   WHERE u.source_id = '{ST.CURATED_SOURCE}' AND u.scope_status IS DISTINCT FROM 'retired'
     AND NOT EXISTS (SELECT 1 FROM wiki_images w WHERE w.site_id = u.id AND NOT w.is_excluded)
     AND {PP.third_party_thumbnail_sql()}
   ORDER BY u.id
) t;"""


def lane_for(run: Path) -> CW.Lane:
    match = RUN_RE.fullmatch(run.name)
    if match is None:
        raise D59Error(f"{run} is not a run directory (d59-thumb-YYYY-MM-DD[a-z])")
    return CW.Lane(LANE_NAME, TEST_ID, f"{LANE_NAME}-{match.group(1)}", "authoritative", LABEL)


def _jsonl_or_empty(path: Path) -> list[dict[str, Any]]:
    return FL._jsonl(path) if path.is_file() else []


def research_outcome(run: Path, site_id: str) -> tuple[str, str]:
    """What the research run `run` found for one site: `(TARGET, file)`, `(NO_CANDIDATE, why)` or
    `(NONE_CONFIRMED, counts)`. Refused while the run has not written its targets, does not hold the
    site, or left a candidate of it unjudged - an empty thumbnail must rest on a finished search. A
    D59 run has no prefilter (`flow.skips_prefilter`): every fetched candidate needs its verdict."""
    if site_id not in {str(s["site_id"]) for s in FL._population(run)}:
        raise D59Error(f"{site_id} is not in the population of {run.name}")
    if not (run / CJ.TARGETS).is_file():
        raise D59Error(f"{run.name} has not written its targets - the research is not finished")
    for target in FL._jsonl(run / CJ.TARGETS):
        if str(target["site_id"]) == site_id:
            return TARGET, str(target["commons_file"])
    for refusal in _jsonl_or_empty(run / CS.REFUSALS):
        if str(refusal["site_id"]) == site_id:
            return NO_CANDIDATE, f"{refusal['reason']}: {refusal.get('detail') or ''}".strip()
    candidates = next(
        (s["candidates"] for s in FL._jsonl(run / CS.CANDIDATES) if str(s["site_id"]) == site_id),
        None,
    )
    if candidates is None:
        raise D59Error(f"{site_id}: {run.name} neither searched nor refused this site")
    gone = {
        str(r["file"])
        for r in _jsonl_or_empty(run / FL.PICTURE_REFUSALS)
        if str(r["site_id"]) == site_id
    }
    skip_prefilter = FL.skips_prefilter(run)
    prefiltered = (
        {}
        if skip_prefilter
        else {
            str(r["file"]): r
            for r in PF.judged(SG.read_results(run, PF.SPEC))
            if str(r["site_id"]) == site_id
        }
    )
    verdicts = {
        str(r["file"]): str(r["verdict"])
        for r in _jsonl_or_empty(run / FL.VERDICTS)
        if str(r["site_id"]) == site_id
    }
    left_out = {
        str(r["file"])
        for r in _jsonl_or_empty(run / "DEPICTS_LEFT_OUT.jsonl")
        if str(r["site_id"]) == site_id
    }
    counts = {
        "not fetched": 0,
        "prefilter dropped": 0,
        "not depicts": 0,
        "depicts, not confirmed": 0,
    }
    for candidate in candidates:
        file = str(candidate["file"])
        if file in gone:
            counts["not fetched"] += 1
        elif not skip_prefilter and file not in prefiltered:
            raise D59Error(
                f"{site_id}: {file!r} has no prefilter answer - the research is not done"
            )
        elif not skip_prefilter and not prefiltered[file]["survives"]:
            counts["prefilter dropped"] += 1
        elif file in left_out:
            raise D59Error(f"{site_id}: {file!r} was left out of the depicts stage - ask it first")
        elif file not in verdicts:
            raise D59Error(f"{site_id}: {file!r} has no depicts verdict - the research is not done")
        elif verdicts[file] != CJ.DEPICTS:
            counts["not depicts"] += 1
        else:
            counts["depicts, not confirmed"] += 1
    detail = ", ".join(f"{n} {what}" for what, n in counts.items() if n)
    return NONE_CONFIRMED, f"{len(candidates)} candidate(s): {detail}"


# ------------------------------------------------------------------------- the INSERT outcome
def insert_state(
    insert_runs: Sequence[Path], site_id: str, file: str
) -> tuple[str, str, dict[str, Any]]:
    """What the INSERT runs did with the confirmed `file` of one site: `(state, detail, evidence)`.

    `NOT_CLAIMED` - no run claims the site (`insert-claims` never ran for it); `NOT_PLANNED` - a run
    claims it and its `insert-plan` has not decided it; `PLANNED` - a chunk of the run plans the row;
    `REFUSED` - the run's plan refused it, with the lane's reason (and, for `not_fetched`, the
    fetch's own failure line). Refused outright: two runs claiming one site, or a claim of another
    file than the research confirmed."""
    claimed: list[Path] = []
    for run in insert_runs:
        seeds = _jsonl_or_empty(run / INSERT_SEEDS)
        if any(
            str(s.get("site_id")) == site_id and s.get("reason") == "no_target_row" for s in seeds
        ):
            claimed.append(run)
    if not claimed:
        return NOT_CLAIMED, "no INSERT run given claims the site", {}
    if len(claimed) > 1:
        raise D59Error(f"{site_id} is claimed by two INSERT runs ({claimed[0].name}, ...)")
    run = claimed[0]
    claims = json.loads((run / INSERT_CLAIMS).read_text(encoding="utf-8"))
    url = str((claims.get(site_id) or {}).get("image") or "")
    if ST.file_of_url(url) != ST.canonical_file(file):
        raise D59Error(
            f"{site_id}: {run.name} claims {url!r}, the research confirmed {file!r} - the claim is "
            "not the research's"
        )
    evidence: dict[str, Any] = {"source": f"import_hero/{run.name}", "claimed": url}
    for chunk in sorted(run.glob("chunk-0*")):
        for row in _jsonl_or_empty(chunk / "INSERT.jsonl"):
            if str(row.get("site_id")) == site_id:
                return PLANNED, f"{run.name}/{chunk.name} plans the row", evidence
    if not (run / INSERT_REFUSALS).is_file():
        return NOT_PLANNED, f"{run.name} has not run insert-plan", evidence
    for refusal in FL._jsonl(run / INSERT_REFUSALS):
        if str(refusal.get("site_id")) == site_id:
            reason = str(refusal["reason"])
            evidence |= {"insert_refusal": reason, "detail": str(refusal.get("detail") or "")}
            if reason == "not_fetched":
                failed = [
                    f["why"]
                    for f in _jsonl_or_empty(run / FETCH_FAILURES)
                    if str(f.get("site_id")) == site_id
                ]
                if not failed:
                    return NOT_PLANNED, f"{run.name} never fetched the file", evidence
                evidence["fetch_failure"] = failed[-1]
            return REFUSED, reason, evidence
    return NOT_PLANNED, f"{run.name}'s insert-plan neither planned nor refused it", evidence


def _population_thumbnail(research: Path, site_id: str) -> str | None:
    for site in FL._population(research):
        if str(site["site_id"]) == site_id:
            value = site.get("thumbnail_url")
            return None if value is None else str(value)
    raise D59Error(f"{site_id} is not in the population of {research.name}")


def null_plan(
    run: Path, research_runs: Sequence[Path], insert_runs: Sequence[Path] = ()
) -> dict[str, Any]:
    """The NULL writes of the third-party thumbnails D59 empties: no research run found a picture,
    or the INSERT lane refused the confirmed one for good. Every other state of a read site is
    refused by name (see the module docstring); the summary is written first, the chunks last."""
    out = run / CHUNKS
    if out.exists():
        raise D59Error(f"{out} holds a plan already - a delivered plan is never replaced")
    if not research_runs:
        raise D59Error("name the D17 research run(s) with --research-run")
    read = json.loads((run / READ_FILE).read_text(encoding="utf-8"))
    by_run: dict[str, Path] = {}
    for research in research_runs:
        for site in FL._population(research):
            sid = str(site["site_id"])
            if sid in by_run:
                raise D59Error(f"{sid} is in two research runs")
            by_run[sid] = research
    changes: list[CW.Change] = []
    expected: list[dict[str, Any]] = []
    basis: dict[str, int] = {}
    for site in read["sites"]:
        sid, thumb = str(site["id"]), site["thumbnail_url"]
        if not PP.is_third_party_thumbnail(thumb):
            raise D59Error(f"{sid}: {thumb!r} is no third-party thumbnail - the read is not D59's")
        research = by_run.get(sid)
        if research is None:
            raise D59Error(f"{sid}: no research run holds this site - D59 sends it to D17 first")
        researched = _population_thumbnail(research, sid)
        if researched != thumb:
            raise D59Error(
                f"{sid}: {research.name} researched the site while it showed {researched!r}, the "
                f"read shows {thumb!r} - an empty thumbnail must rest on research about this one"
            )
        outcome, detail = research_outcome(research, sid)
        evidence: list[dict[str, Any]] = [
            {"source": f"image_roles/{research.name}", "outcome": outcome, "detail": detail},
            {"source": "d59 READ.json", "thumbnail_url": thumb},
        ]
        if outcome == TARGET:
            state, why, insert = insert_state(insert_runs, sid, detail)
            if state != REFUSED:
                raise D59Error(
                    f"{sid}: the research confirmed {detail!r} and the INSERT lane has not ended "
                    f"it ({state}: {why}) - run insert-claims and the INSERT wave to its "
                    "acceptance, then plan again with --insert-run"
                )
            if why in STALE_INSERT_REASONS:
                raise D59Error(
                    f"{sid}: {insert['source']} refused the row as {why!r}, which speaks of another "
                    "state of the site - plan the INSERT again from a fresh read"
                )
            evidence.append(insert)
            reason = (
                f"the site's only picture was a third-party hotlink without a credit; the D17 "
                f"research confirmed {detail!r}, and the INSERT lane refused it ({why}); D59: the "
                "thumbnail goes NULL"
            )
            key = f"insert_refused:{why}"
        else:
            reason = (
                "the site's only picture was a third-party hotlink without a credit, and the D17 "
                f"research found no checked Commons picture of it ({outcome}); D59: the thumbnail "
                "goes NULL"
            )
            key = outcome
        basis[key] = basis.get(key, 0) + 1
        changes.append(
            CW.Change(
                "unified_sites", "thumbnail_url", sid, sid, thumb, None, RULE_NULL, reason, evidence
            )
        )
        expected.append(
            {"site_id": sid, "outcome": CLEARED, "served_image_id": None, "thumbnail_url": None}
        )
    chunks = CW.chunk_changes(lane_for(run), changes) if changes else []
    chunk_of = {sid: chunk.number for chunk in chunks for sid in chunk.sites}
    summary = {
        "read_sha256": ST.file_sha256(run / READ_FILE),
        "research_runs": [str(r.resolve()) for r in research_runs],
        "insert_runs": [str(r.resolve()) for r in insert_runs],
        "sites": len(read["sites"]),
        "cleared": len(changes),
        "cleared_by": basis,
        "chunks": len(chunks),
        "lane": asdict(lane_for(run)),
    }
    ST.write_text_once(out / SUMMARY, ST.json_text(summary))
    ST.write_text_once(
        out / EXPECTED, ST.jsonl_text(e | {"chunk": chunk_of[e["site_id"]]} for e in expected)
    )
    CW.emit_chunks(out, chunks)
    return summary


def null_accept(run: Path, chunk: Path) -> dict[str, Any]:
    """Read-only: every site of `chunk` serves no picture now (`served_image.plan.deviations`)."""
    delivered = CW.check_delivered(chunk)
    expected = FL._jsonl(run / CHUNKS / EXPECTED)
    mine = [e for e in expected if e["chunk"] == delivered.number]
    if {e["site_id"] for e in mine} != set(delivered.sites):
        raise D59Error(f"{chunk}: EXPECTED.jsonl and the chunk name different sites")
    ids = ", ".join(f"'{e['site_id']}'::uuid" for e in mine)
    found = SP.deviations(
        mine,
        CW.pv.read_rows(SP.ACCEPT_SITES_SQL.replace("{ids}", ids)),
        CW.pv.read_rows(SP.ACCEPT_IMAGES_SQL.replace("{ids}", ids)),
    )
    return {"chunk": delivered.number, "sites": len(mine), "deviations": found}


# ------------------------------------------------------------------------- the per-site outcome
#: The owner's question for a Commons thumbnail below the floor: the page shows it already.
FLOOR_QUESTION = (
    "below the owner's floor: lower the floor for this D59 run (the page already shows this "
    "picture, without its credit), or leave the uncredited hotlink"
)


def outcomes(run: Path, insert_runs: Sequence[Path] = ()) -> dict[str, Any]:
    """Where every site of a D59 candidate run stands: `D59_OUTCOMES.jsonl` (one line per site) and
    `D59_OWNER_LIST.jsonl` (every site that keeps its uncredited hotlink, with the reason; a floor
    refusal carries the owner question). A statement about the run as it stands - rewritten by every
    call, never an answer record - and refused while the research is not finished."""
    if not FL.skips_prefilter(run):
        raise D59Error(f"{run.name} is no D59 candidate run (no {MARKER})")
    lines: list[dict[str, Any]] = []
    owner: list[dict[str, Any]] = []
    for site in FL._population(run):
        sid = str(site["site_id"])
        line: dict[str, Any] = {
            "site_id": sid,
            "name": site.get("name"),
            "thumbnail_url": site.get("thumbnail_url"),
        }
        outcome, detail = research_outcome(run, sid)
        line |= {"research": outcome, "detail": detail}
        if outcome == TARGET and insert_runs:
            state, why, _ = insert_state(insert_runs, sid, detail)
            line |= {"insert": state, "insert_detail": why}
        lines.append(line)
        if outcome == TARGET and line.get("insert") != REFUSED:
            continue
        reason = (
            FLOOR_QUESTION
            if outcome == NO_CANDIDATE and detail.startswith(CS.ALL_TOO_SMALL)
            else f"the INSERT lane refused the confirmed file: {line['insert_detail']}"
            if outcome == TARGET
            else f"{outcome}: {detail}"
        )
        owner.append(line | {"reason": reason})
    for name, rows in ((OUTCOMES, lines), (OWNER_LIST, owner)):
        (run / name).write_text(ST.jsonl_text(rows), encoding="utf-8", newline="\n")
    counts: dict[str, int] = {}
    for line in lines:
        key = line["research"] if "insert" not in line else f"target:{line['insert']}"
        if line["research"] == NO_CANDIDATE:
            key = f"{NO_CANDIDATE}:{line['detail'].split(':')[0]}"
        counts[key] = counts.get(key, 0) + 1
    return {"sites": len(lines), "outcomes": counts, "owner_list": len(owner)}


# ----------------------------------------------------------------------------------- the CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        prog="image_roles/d59.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("candidates", "outcomes", "null-read", "null-plan", "null-accept"):
        sub.add_parser(name).add_argument("--run-dir", required=True, type=Path)
    sub.choices["candidates"].add_argument("--min-width", type=int, default=IH.OWNER_FLOOR_WIDTH)
    sub.choices["candidates"].add_argument("--min-height", type=int, default=IH.OWNER_FLOOR_HEIGHT)
    sub.choices["null-plan"].add_argument("--research-run", required=True, type=Path, nargs="+")
    for name in ("null-plan", "outcomes"):
        sub.choices[name].add_argument("--insert-run", type=Path, nargs="*", default=[])
    sub.choices["null-accept"].add_argument("--chunk", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    run = args.run_dir
    try:
        if args.command == "candidates":
            rows = CW.pv.read_rows(PP.population_sql(kind=PP.COMMONS_THUMBNAIL))
            commons = CM.Commons(run / "commons", research_web.client(), pace=CM.PACE_SECONDS)
            payload: Any = write_candidates(
                run, rows, commons, floor=(args.min_width, args.min_height)
            )
        elif args.command == "outcomes":
            payload = outcomes(run, args.insert_run)
        elif args.command == "null-read":
            lane_for(run)
            data = {
                "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sites": CW.pv.read_rows(THIRD_PARTY_SQL),
            }
            digest = ST.write_text_once(run / READ_FILE, ST.json_text(data))
            payload = {"sha256": digest, "sites": len(data["sites"])}
        elif args.command == "null-plan":
            payload = null_plan(run, args.research_run, args.insert_run)
        else:
            payload = null_accept(run, args.chunk)
            print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
            return 0 if not payload["deviations"] else 1
    except ST.StateError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
