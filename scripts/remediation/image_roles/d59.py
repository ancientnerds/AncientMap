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
`research-outcomes` does the same for a D17 research run (`D17_OUTCOMES.jsonl`,
`D17_OWNER_LIST.jsonl`: every site the run leaves without a picture, with the reason - D82).

The INSERT lane's end of a confirmed file is read here for all three (`insert_state`), and so are
the picks it refused for a reason that lies in the file (`refused_files`): the image roles then try
the site's next-ranked `depicts` (`run.py recheck-export | write-targets --insert-run I`), and
`null-plan` empties no thumbnail while such a candidate is untried. Three rules keep that honest:

* a `not_fetched` lies in the file only when the fetch's own line says so (`FILE_FAILURES`: a
  missing credit, a size, an upscale, a file type, a name). The fetch records a download that got
  no answer in the same file; such a claim is open (`NOT_PLANNED`), fetched again in a new INSERT
  run, and passes no pick over;
* the runs that claim one file answer together (`claim_answer`): a later run is the retry of an
  earlier one, the run that plans the row answers, else the last run named - so the runs are
  named in the order they ran;
* a confirmed pick `TARGETS.jsonl` no longer names (`INSERT_REFUSED`) is no evidence by itself:
  `refused_picks` reads the refusal in the INSERT runs given and refuses by name without it.

    d59.py candidates     --run-dir C [--min-width 800 --min-height 300]
    d59.py outcomes       --run-dir C [--insert-run I ...]
    d59.py research-outcomes --run-dir C [--insert-run I ...]   (C = a D17 research run)
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
from image_roles import targets as TG  # noqa: E402

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
#: The same two files of a D17 research run (`research_outcomes`).
D17_OUTCOMES = "D17_OUTCOMES.jsonl"
D17_OWNER_LIST = "D17_OWNER_LIST.jsonl"

#: The research outcomes `research_outcome` names.
TARGET, NO_CANDIDATE, NONE_CONFIRMED = "target", "no_candidate", "none_confirmed"
#: The fourth: a re-check confirmed a `depicts` of the site and `TARGETS.jsonl` does not name it,
#: because `write-targets --insert-run` passed it over. The run's files say only that much; the
#: refusal itself is the INSERT run's record (`refused_picks`).
INSERT_REFUSED = "insert_refused"
#: What an INSERT run did with a confirmed target (`insert_state`).
NOT_CLAIMED, NOT_PLANNED, PLANNED, REFUSED = "not_claimed", "not_planned", "planned", "refused"
#: INSERT refusals that speak of another state of the site than the one read now: the INSERT is
#: planned again from a fresh read, the thumbnail is not emptied on them.
STALE_INSERT_REASONS = frozenset({"retired", "d59_thumbnail_moved"})
#: INSERT refusals that lie in the file and not in the site (`import_hero/insert.py`): the fetch
#: refused it for good (a credit its licence demands and the file lacks, an original below the
#: floor, an upscale, a file type it does not take - the line in `FETCH_FAILURES.jsonl` says which)
#: or a row of the site already holds it. Another file of the site can still get its row, so the
#: site's next-ranked `depicts` is tried (`targets.pick_round`).
FILE_REFUSALS = frozenset({"not_fetched", "already_holds_the_file"})
#: What a line of `FETCH_FAILURES.jsonl` says when the fetch refused the **file**
#: (`import_hero/fetch.py` and the downloader it drives; `test_d59_thumbnails.py` reads every one of
#: these wordings out of that code): a credit column its licence demands, a size below the floor
#: (the original, the box it stores as, the download, a stored strip), an upscale, a file over the
#: byte limit, a file type without a thumbnail rule, a name the file system refuses, a file
#: Commons does not host. The fetch records every other failure in the same file and in the same
#: form - Commons or the network gave no answer, an HTTP status, a download that is no picture, a
#: file in the way on disk: that fetch did not happen and says nothing about the file.
FILE_FAILURES = (
    "which the licence",
    "this run serves",
    "a panorama at least",
    "wider than the",
    "is over the limit",
    "no thumbnail naming rule for this file type",
    "cannot be stored as a local file name",
    "has no extension to swap",
    "Commons hosts no file of this name",
)
#: The INSERT lane's record files (`import_hero/run.py`).
INSERT_CLAIMS = "IMPORT_CLAIMS.json"
INSERT_SEEDS = "IMPORT_HERO_REFUSALS.jsonl"
INSERT_REFUSALS = "INSERT_REFUSALS.jsonl"
FETCH_FAILURES = "FETCH_FAILURES.jsonl"


class D59Error(ST.StateError):
    """D59's inputs do not allow the step. Nothing was written."""


def lies_in_the_file(fetch_failure: str) -> bool:
    """Whether a line of `FETCH_FAILURES.jsonl` is a refusal of the file (`FILE_FAILURES`)."""
    return any(wording in fetch_failure for wording in FILE_FAILURES)


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


def research_outcome(run: Path, site_id: str, *, count_left_out: bool = False) -> tuple[str, str]:
    """What the research run `run` found for one site: `(TARGET, file)`, `(NO_CANDIDATE, why)`,
    `(NONE_CONFIRMED, counts)` or `(INSERT_REFUSED, counts)`. Refused while the run has not written
    its targets, does not hold the site, or left a candidate of it unjudged - an empty thumbnail
    must rest on a finished search. A D59 run has no prefilter (`flow.skips_prefilter`): every
    fetched candidate needs its verdict.

    A candidate the depicts stage left out (a site with more survivors than one question holds,
    `DEPICTS_LEFT_OUT.jsonl`) is refused by name too, unless `count_left_out`: the outcome list of a
    run states it as it stands and counts such a candidate as never judged.

    `INSERT_REFUSED`: a re-check confirmed a `depicts` of the site and the targets do not name it
    - `write-targets --insert-run` passed it over (`targets.pick_round`). The missing line is all
    this run's files say: the caller reads the refusal itself in the INSERT runs
    (`refused_picks`), and no step may rest on the outcome without it."""
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
    confirmed = {file for sid, file in CJ.confirmed_by_recheck(run) if sid == site_id}
    counts = {
        "not fetched": 0,
        "prefilter dropped": 0,
        "left out of the depicts stage, never judged": 0,
        "not depicts": 0,
        "depicts, not confirmed": 0,
        "confirmed, refused by the INSERT lane": 0,
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
            if not count_left_out:
                raise D59Error(
                    f"{site_id}: {file!r} was left out of the depicts stage - ask it first"
                )
            counts["left out of the depicts stage, never judged"] += 1
        elif file not in verdicts:
            raise D59Error(f"{site_id}: {file!r} has no depicts verdict - the research is not done")
        elif verdicts[file] != CJ.DEPICTS:
            counts["not depicts"] += 1
        elif file in confirmed:
            counts["confirmed, refused by the INSERT lane"] += 1
        else:
            counts["depicts, not confirmed"] += 1
    detail = ", ".join(f"{n} {what}" for what, n in counts.items() if n)
    outcome = INSERT_REFUSED if counts["confirmed, refused by the INSERT lane"] else NONE_CONFIRMED
    return outcome, f"{len(candidates)} candidate(s): {detail}"


# ------------------------------------------------------------------------- the INSERT outcome
def claims_of(run: Path) -> dict[str, str]:
    """`{site id: the URL claimed}` of the sites an INSERT run claims a first row for (its
    `no_target_row` seeds, `judge.insert_claims`)."""
    claimed = {
        str(s.get("site_id"))
        for s in _jsonl_or_empty(run / INSERT_SEEDS)
        if s.get("reason") == "no_target_row"
    }
    if not claimed:
        return {}
    claims = json.loads((run / INSERT_CLAIMS).read_text(encoding="utf-8"))
    return {sid: str((claims.get(sid) or {}).get("image") or "") for sid in sorted(claimed)}


def claim_state(run: Path, site_id: str, url: str) -> tuple[str, str, dict[str, Any]]:
    """What one INSERT run did with its claim of `url` for the site: `(state, detail, evidence)`,
    `PLANNED`, `NOT_PLANNED` or `REFUSED` as `insert_state` words them. A `not_fetched` is a
    refusal only when the fetch refused the file (`lies_in_the_file`): a file the run never
    fetched, or whose fetch got no answer, is a claim the run left open."""
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
                if not lies_in_the_file(failed[-1]):
                    return (
                        NOT_PLANNED,
                        f"{run.name}'s fetch did not end ({failed[-1]}), which says nothing about "
                        "the file - fetch it again in a new INSERT run",
                        evidence,
                    )
            return REFUSED, reason, evidence
    return NOT_PLANNED, f"{run.name}'s insert-plan neither planned nor refused it", evidence


def claim_answer(
    site_id: str, claims: Sequence[tuple[Path, str]]
) -> tuple[str, str, dict[str, Any]]:
    """What the runs that claim one file for a site did with it, taken together (`claims`: `(run,
    the URL claimed)` in the order the runs were named). A later run is the retry of an earlier
    one: a new INSERT run from the target check after a refusal that speaks of the site, after a
    fetch that did not end, or after a run whose write stopped at a guard. A run that plans the
    row answers (the last of them: which one wrote it is the INSERT lane's acceptance, not read
    here), else the last run named does."""
    answers = [claim_state(run, site_id, url) for run, url in claims]
    planned = [answer for answer in answers if answer[0] == PLANNED]
    return (planned or answers)[-1]


def insert_state(
    insert_runs: Sequence[Path], site_id: str, file: str
) -> tuple[str, str, dict[str, Any]]:
    """What the INSERT runs did with the confirmed `file` of one site: `(state, detail, evidence)`.

    `NOT_CLAIMED` - no run claims the file for the site (`insert-claims` never ran for it);
    `NOT_PLANNED` - a run claims it and has not decided it: its `insert-plan` has not run, the
    file was never fetched, or its fetch got no answer; `PLANNED` - a chunk of the run plans the
    row; `REFUSED` - the run's plan refused it, with the lane's reason (and, for `not_fetched`,
    the fetch's own refusal of the file). Several runs that claim the file answer together
    (`claim_answer`), so the runs are named in the order they ran. Refused outright: a run
    claiming another file of the site - unless the runs that claim that one refused it for a
    reason that lies in the file (`FILE_REFUSALS`): then `file` is the site's next pick, tried
    after it (`targets.pick_round`), and the earlier claim says nothing about it."""
    by_file: dict[str | None, list[tuple[Path, str]]] = {}
    for run in insert_runs:
        url = claims_of(run).get(site_id)
        if url is not None:
            by_file.setdefault(ST.file_of_url(url), []).append((run, url))
    mine = by_file.pop(ST.canonical_file(file), None)
    for claims in by_file.values():
        state, why, _ = claim_answer(site_id, claims)
        if state != REFUSED or why not in FILE_REFUSALS:
            raise D59Error(
                f"{site_id}: {claims[-1][0].name} claims {claims[-1][1]!r}, the research "
                f"confirmed {file!r} - the claim is not the research's"
            )
    if mine is None:
        return NOT_CLAIMED, "no INSERT run given claims the file for the site", {}
    return claim_answer(site_id, mine)


def refused_files(insert_runs: Sequence[Path]) -> dict[tuple[str, str], dict[str, Any]]:
    """`{(site id, file in title form): the refusal's evidence}` of every file the INSERT runs
    refused for good for a reason that lies in the file (`FILE_REFUSALS`): the picks
    `targets.pick_round` passes over. The runs that claim one file answer together
    (`claim_answer`): a file one run refused and another plans, or still holds open, is not
    refused."""
    by_claim: dict[tuple[str, str], list[tuple[Path, str]]] = {}
    for run in insert_runs:
        for site_id, url in claims_of(run).items():
            file = ST.file_of_url(url)
            if file is not None:
                by_claim.setdefault((site_id, file), []).append((run, url))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for (site_id, file), claims in by_claim.items():
        state, why, evidence = claim_answer(site_id, claims)
        if state == REFUSED and why in FILE_REFUSALS:
            out[(site_id, file)] = evidence
    return out


def _round(run: Path, refused: Mapping[tuple[str, str], Any]) -> TG.Round:
    return TG.pick_round(FL._jsonl(run / FL.VERDICTS), FL.recheck_results(run), refused)


def untried_pick(run: Path, site_id: str, refused: Mapping[tuple[str, str], Any]) -> str | None:
    """The `depicts` file of the site the INSERT lane has still to try once `refused` is passed
    over - its confirmed pick, or the one that waits for its re-check - or None when the site has
    none left."""
    state = _round(run, refused)
    if site_id in state.confirmed:
        return str(state.confirmed[site_id]["file"])
    return next((str(r["file"]) for r in state.to_check if str(r["site_id"]) == site_id), None)


def passed_over(
    run: Path, site_id: str, refused: Mapping[tuple[str, str], Mapping[str, Any]]
) -> list[tuple[str, dict[str, Any]]]:
    """`(file, the INSERT refusal's evidence)` of every confirmed pick of the site that
    `targets.pick_round` passes over for `refused`, best first."""
    return [
        (str(row["file"]), dict(refused[(site_id, ST.canonical_file(str(row["file"])))]))
        for row in _round(run, refused).insert_refused.get(site_id, ())
    ]


def refused_picks(
    run: Path, site_id: str, refused: Mapping[tuple[str, str], Mapping[str, Any]]
) -> list[tuple[str, dict[str, Any]]]:
    """The refusals behind an `INSERT_REFUSED` site: `passed_over`, once nothing of the site is
    left to try. The target line that is missing proves nothing - `refused` must hold the INSERT
    lane's own refusal of every confirmed pick. Refused by name otherwise: a confirmed pick no
    run given refused for a reason that lies in the file (the targets were written with INSERT
    runs that are not named here, a named run plans that very file, or its fetch only got no
    answer), or a `depicts` that still waits for its re-check."""
    waiting = untried_pick(run, site_id, refused)
    if waiting is not None:
        raise D59Error(
            f"{site_id}: {run.name}/{CJ.TARGETS} does not name {waiting!r}, a depicts of the site "
            "no INSERT run given refused for a reason that lies in the file - name every INSERT "
            "run of the stage with --insert-run, in the order they ran, and run "
            "`recheck-export --insert-run` and `write-targets --insert-run` with them first"
        )
    return passed_over(run, site_id, refused)


def refusal_text(picks: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    """`'<file>': <the lane's reason> (<the fetch's own line>)` of every refused pick."""
    return "; ".join(
        f"{file!r}: {proof['insert_refusal']}"
        + (f" ({proof['fetch_failure']})" if "fetch_failure" in proof else "")
        for file, proof in picks
    )


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
    refused by name (see the module docstring) - also a site whose confirmed file was refused for
    a reason that lies in the file while another `depicts` of it has not been tried
    (`untried_pick`): a thumbnail is emptied only when the research has nothing left to offer. A
    confirmed pick is ended by the INSERT lane's own refusal and by nothing else - also once
    `write-targets --insert-run` dropped its target line (`refused_picks`) -, and every refusal
    is in the row's evidence. The summary is written first, the chunks last."""
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
    refused = refused_files(insert_runs)
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
            if why in FILE_REFUSALS:
                waiting = untried_pick(research, sid, refused)
                if waiting is not None:
                    raise D59Error(
                        f"{sid}: the INSERT lane refused {detail!r} ({why}) and the site's next "
                        f"depicts {waiting!r} is not tried yet - `run.py recheck-export "
                        "--insert-run`, `write-targets --insert-run` and its INSERT wave first"
                    )
            earlier = [pick for pick in passed_over(research, sid, refused) if pick[0] != detail]
            ended = [*earlier, (detail, insert)]
        elif outcome == INSERT_REFUSED:
            ended = refused_picks(research, sid, refused)
        else:
            ended = []
        if ended:
            evidence.extend(proof for _, proof in ended)
            reason = (
                "the site's only picture was a third-party hotlink without a credit; the D17 "
                f"research confirmed {', '.join(repr(file) for file, _ in ended)}, and the INSERT "
                f"lane refused {'it' if len(ended) == 1 else 'each'} "
                f"({', '.join(str(proof['insert_refusal']) for _, proof in ended)}); D59: the "
                "thumbnail goes NULL"
            )
            key = f"insert_refused:{ended[-1][1]['insert_refusal']}"
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
    refused = refused_files(insert_runs)
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
            else "the INSERT lane refused the confirmed file "
            + refusal_text(refused_picks(run, sid, refused))
            if outcome == INSERT_REFUSED
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


#: Why a D17 site without a confirmed picture stays without one, before the run's own detail.
D17_REASONS = {
    NO_CANDIDATE: "the search found no Commons candidate",
    NONE_CONFIRMED: "no candidate was confirmed to show the site",
}


def unwritten(
    run: Path,
    site_id: str,
    file: str,
    insert_runs: Sequence[Path],
    refused: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[dict[str, str], str | None]:
    """The INSERT state of a site's confirmed `file` as outcome keys, and why the site is still
    without it - None once an INSERT run plans the row. A refusal carries the fetch's own failure
    line, and says so when another `depicts` of the site has not been tried (`untried_pick`); the
    picks the INSERT lane refused before this one are named after it (`passed_over`)."""
    state, why, evidence = insert_state(insert_runs, site_id, file)
    keys = {"insert": state, "insert_detail": why}
    if state == PLANNED:
        return keys, None
    if state in (NOT_CLAIMED, NOT_PLANNED):
        reason = f"the confirmed file {file!r} was not written ({state}: {why})"
    else:
        reason = "the INSERT lane refused the confirmed file " + refusal_text([(file, evidence)])
        next_pick = untried_pick(run, site_id, refused) if why in FILE_REFUSALS else None
        if next_pick is not None:
            reason += f"; the site's next depicts {next_pick!r} is not tried yet"
    earlier = [pick for pick in passed_over(run, site_id, refused) if pick[0] != file]
    if earlier:
        reason += f"; before it the INSERT lane refused {refusal_text(earlier)}"
    return keys, reason


def research_outcomes(run: Path, insert_runs: Sequence[Path] = ()) -> dict[str, Any]:
    """Where every site of a D17 research run stands: `D17_OUTCOMES.jsonl` (one line per site) and
    `D17_OWNER_LIST.jsonl` - every site the run leaves without a picture, with the reason (D82: no
    usable Commons picture = the site stays without one and goes on the owner list). A site is off
    the list only when an INSERT run plans its confirmed file; `owner_list_final.py` reads the list
    and sets a row aside once production shows a picture. A site whose confirmed pick the targets
    no longer name (`INSERT_REFUSED`) is listed with the INSERT lane's own refusal of every such
    pick, read in the runs given (`refused_picks`: refused by name when they do not hold it). Like
    `outcomes` a statement about the run as it stands - rewritten by every call - and refused
    while the targets are not written or a candidate still waits for its prefilter or depicts
    answer; a candidate the depicts stage left out is counted as never judged."""
    if FL.skips_prefilter(run):
        raise D59Error(f"{run.name} is a D59 candidate run: `outcomes` states it")
    refused = refused_files(insert_runs)
    lines: list[dict[str, Any]] = []
    owner: list[dict[str, Any]] = []
    for site in FL._population(run):
        sid = str(site["site_id"])
        line: dict[str, Any] = {
            "site_id": sid,
            "name": site.get("name"),
            "country": site.get("country"),
            "thumbnail_url": site.get("thumbnail_url"),
        }
        outcome, detail = research_outcome(run, sid, count_left_out=True)
        line |= {"research": outcome, "detail": detail}
        reason: str | None
        if outcome == TARGET:
            keys, reason = unwritten(run, sid, detail, insert_runs, refused)
            line |= keys
        elif outcome == INSERT_REFUSED:
            reason = (
                "the INSERT lane refused the confirmed file "
                f"{refusal_text(refused_picks(run, sid, refused))}; no other candidate was "
                f"confirmed ({detail})"
            )
        else:
            reason = f"{D17_REASONS[outcome]} ({detail})"
        lines.append(line)
        if reason is not None:
            owner.append(line | {"reason": reason})
    for name, rows in ((D17_OUTCOMES, lines), (D17_OWNER_LIST, owner)):
        (run / name).write_text(ST.jsonl_text(rows), encoding="utf-8", newline="\n")
    counts: dict[str, int] = {}
    for line in lines:
        key = f"target:{line['insert']}" if "insert" in line else line["research"]
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
    for name in (
        "candidates",
        "outcomes",
        "research-outcomes",
        "null-read",
        "null-plan",
        "null-accept",
    ):
        sub.add_parser(name).add_argument("--run-dir", required=True, type=Path)
    sub.choices["candidates"].add_argument("--min-width", type=int, default=IH.OWNER_FLOOR_WIDTH)
    sub.choices["candidates"].add_argument("--min-height", type=int, default=IH.OWNER_FLOOR_HEIGHT)
    sub.choices["null-plan"].add_argument("--research-run", required=True, type=Path, nargs="+")
    for name in ("null-plan", "outcomes", "research-outcomes"):
        sub.choices[name].add_argument(
            "--insert-run",
            type=Path,
            nargs="*",
            default=[],
            help="every INSERT run of the research run's targets, in the order they ran",
        )
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
        elif args.command == "research-outcomes":
            payload = research_outcomes(run, args.insert_run)
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
