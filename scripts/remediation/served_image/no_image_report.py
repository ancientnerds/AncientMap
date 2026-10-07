"""Why a curated site serves no image - one measured reason per site.

The goal asks for the no-image remainder to be reported **per site with its measured reason**,
not left open. This is that report, and it is the one clause of the goal no vision model can
block: it reads what the run already measured, and it writes nothing outside its run directory.

**Where the reason comes from.** The pre-check short-circuits to `no-image` before it reads the
site's Wikidata item (`precheck.decide`), so a site that serves nothing carries no P18/P373 in
`PRECHECK.jsonl` - the claim of exactly the population this report is about would be missing.
The claim is therefore read here with the pre-check's own readers (`load_harvest`, `p18_files`,
`p373_categories`), never with a second implementation of "what is an image claim".

**What state a claim is in** comes from the run's replace export (`vision.EXPORT_REPLACE`),
which writes `claimed_sites` for exactly this purpose. A claiming site is only reported as open
or as without a picture when the export says so; a claiming site the export does not cover, a
site the export asks about that does not serve nothing, an export pinned to another pre-check -
each is refused by name rather than counted into a number nobody checked.

Measured on production 2026-10-05 (`NO_IMAGE_SUMMARY.json` of the run `served-image-2026-10-05`,
read 4,900 shown sites, pre-check sha256 `c14790f3…`): of 5,004 curated sites 104 are retired,
2,722 serve an image their own Wikidata item vouches for, 939 serve one it does not (out of scope -
they need the vision check) and 1,239 serve nothing: 307 have no Wikidata item, 688 have one that
claims no image, 4 name a Commons category that lists no file, and 240 claim a file the run
exported for the vision check. `claimed-no-file-is-a-picture` is reachable but measured 0: every
site whose export named a file it could not serve also got a picture.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image.commons import Commons  # noqa: E402
from served_image.precheck import (  # noqa: E402
    CONFIRMED,
    NO_IMAGE,
    PRECHECK_FILE,
    UNCONFIRMED,
    Harvest,
    load_harvest,
    load_prechecks,
    p18_files,
    p373_categories,
)
from served_image.state import (  # noqa: E402
    StateError,
    file_sha256,
    json_text,
    jsonl_text,
    load_read,
    write_text_once,
)
from served_image.vision import EXPORT_REPLACE, wanted_files  # noqa: E402

READ = "READ.json"
REPORT_FILE = "NO_IMAGE_REPORT.jsonl"
SUMMARY_FILE = "NO_IMAGE_SUMMARY.json"

#: The site is curated, but `scope_status = 'retired'`: the platform does not show it, so it
#: serves no image and no lane of this remediation reaches it.
RETIRED = "retired"
#: The pre-check found no Wikidata item for the site; nothing there could claim an image.
NO_ITEM = "no-wikidata-item"
#: The item exists and claims no image (no P18, no P373): nothing exists to serve.
NO_CLAIM = "no-image-claim"
#: The item names a Commons category (P373) and the category lists no file, so the claim names
#: nothing that could be served. Measured 2026-10-05: four of the 244 claiming sites, each an
#: empty category; `export_replace` leaves them out, because it asks only about named files.
CLAIMED_NO_FILE = "claimed-no-file-named"
#: The item claims a file and the run exported its candidates: open until the vision check judged
#: them. This is the addressable remainder the goal counts down.
CLAIMED_OPEN = "claimed-awaiting-vision-check"
#: The item claims a file, but every file named is no still picture (`unavailable` in the export).
CLAIMED_NO_PICTURE = "claimed-no-file-is-a-picture"
#: The five reasons of a site that serves nothing, in the order they are decided.
NO_IMAGE_REASONS = (NO_ITEM, NO_CLAIM, CLAIMED_NO_FILE, CLAIMED_OPEN, CLAIMED_NO_PICTURE)
REASONS = (RETIRED, *NO_IMAGE_REASONS)


def _claim_of(check: Mapping[str, Any], harvest: Harvest) -> dict[str, list[str]] | None:
    """The site's own image claim, or None when it has no Wikidata item at all. A harvest that
    does not hold the item is refused by `Harvest.entity`, by name."""
    qid = check.get("qid")
    if not qid:
        return None
    entity = harvest.entity(str(qid))
    return {"p18": p18_files(entity), "p373": p373_categories(entity)}


def _load_export(run: Path, precheck_sha: str) -> dict[str, Any]:
    """The replace export, and what it says about this pre-check. Refused when it was written for
    another pre-check, and when it asks about a site it does not list as a claimed site."""
    path = run / EXPORT_REPLACE
    if not path.is_file():
        raise StateError(
            f"{path} does not exist - a site whose item claims an image is only accounted for by "
            "the replace export. Run `run.py export-replace --claimed-only` on this read first."
        )
    export = json.loads(path.read_text(encoding="utf-8"))
    if export.get("precheck_sha256") != precheck_sha:
        raise StateError(
            f"{path} was written for another pre-check ({export.get('precheck_sha256')}, not "
            f"{precheck_sha}): its claim states are not this read's."
        )
    claimed = frozenset(str(sid) for sid in export["claimed_sites"])
    asked: dict[str, int] = {}
    for batch, sites in export["batches"].items():
        for sid in sites:
            if str(sid) not in claimed:
                raise StateError(
                    f"{path} asks about {sid} in {batch}, which it does not list as a claimed "
                    "site: the export and this report disagree about the population."
                )
            asked[str(sid)] = asked.get(str(sid), 0) + 1
    return {
        "claimed": claimed,
        "asked": asked,
        "unavailable": {str(k): list(v) for k, v in export["unavailable"].items()},
        "sha256": file_sha256(path),
    }


def _reason_for(
    site_id: str,
    check: Mapping[str, Any],
    claim: dict[str, list[str]] | None,
    harvest: Harvest,
    commons: Commons,
    export: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any] | None]:
    """The reason, the sentence that says what was measured, and the export's state of the claim
    - or the refusal that names the site."""
    if claim is None:
        return NO_ITEM, "the pre-check found no Wikidata item for the site", None
    if not claim["p18"] and not claim["p373"]:
        return (
            NO_CLAIM,
            f"its item {check['qid']} claims no image (no P18, no P373)",
            None,
        )
    named = claim["p18"] or claim["p373"]
    wanted = wanted_files(check, harvest, commons)
    if not wanted:
        return (
            CLAIMED_NO_FILE,
            f"its item {check['qid']} names the Commons category {named[0]!r}, and the category "
            f"lists no file (measured with `wanted_files`, {len(named)} category/categories)",
            None,
        )
    if export is None or site_id not in export["claimed"]:
        raise StateError(
            f"{site_id} serves no image and its item {check['qid']} claims {named}, but this run's "
            f"{EXPORT_REPLACE} does not list it as a claimed site: there is no measured state for "
            f"its claim. Run `run.py export-replace --claimed-only` on this read."
        )
    state = {
        "candidates": export["asked"].get(site_id, 0),
        "unavailable": export["unavailable"].get(site_id, []),
    }
    if state["candidates"]:
        return (
            CLAIMED_OPEN,
            f"its item {check['qid']} claims {len(named)} file/category name(s); the run exported "
            f"{state['candidates']} candidate(s) for the vision check, which has not judged them",
            state,
        )
    if state["unavailable"]:
        return (
            CLAIMED_NO_PICTURE,
            f"its item {check['qid']} claims {len(named)} file/category name(s), and none of the "
            f"{len(state['unavailable'])} file(s) named is a still picture",
            state,
        )
    raise StateError(
        f"{site_id} serves no image, its item {check['qid']} claims {named}, and {EXPORT_REPLACE} "
        "neither exported a candidate for it nor named a file it could not serve: there is no "
        "measured reason for it."
    )


def write_report(run: Path, harvest_root: Path, commons: Commons) -> dict[str, Any]:
    """`NO_IMAGE_REPORT.jsonl` and `NO_IMAGE_SUMMARY.json`, both written once.

    A row per curated site that serves no image and one per retired curated site, the reason
    measured for it, and a summary whose counts close over every curated site of the read.
    Returns the summary.
    """
    state = load_read(run / READ)
    prechecks = load_prechecks(run / PRECHECK_FILE)
    harvest = load_harvest(harvest_root)
    precheck_sha = file_sha256(run / PRECHECK_FILE)

    missing = [sid for sid in state.site_ids() if sid not in prechecks]
    if missing:
        raise StateError(
            f"{len(missing)} site(s) of the read have no pre-check row (first {missing[0]}): the "
            "report cannot say what they serve. Run `run.py precheck` on this read."
        )
    statuses = Counter(str(prechecks[sid]["status"]) for sid in state.site_ids())
    serving = sum(n for name, n in statuses.items() if name != NO_IMAGE)
    confirmed = sum(n for name, n in statuses.items() if name in CONFIRMED)
    if serving != confirmed + statuses.get(UNCONFIRMED, 0):
        raise StateError(
            f"the pre-check's statuses do not add up: {dict(statuses)} - a site that serves an "
            "image is either confirmed or unconfirmed, nothing else."
        )

    blanks = sorted(sid for sid in state.site_ids() if prechecks[sid]["status"] == NO_IMAGE)
    claims = {sid: _claim_of(prechecks[sid], harvest) for sid in blanks}
    # The export is the only record of what became of a claim that names a file, so it is read
    # exactly when this read has one - and refused when it does not cover one.
    export = (
        _load_export(run, precheck_sha)
        if any(
            claim is not None
            and (claim["p18"] or claim["p373"])
            and wanted_files(prechecks[sid], harvest, commons)
            for sid, claim in claims.items()
        )
        else None
    )

    rows: list[dict[str, Any]] = []
    for sid in blanks:
        reason, detail, export_state = _reason_for(
            sid, prechecks[sid], claims[sid], harvest, commons, export
        )
        rows.append(
            {
                "site_id": sid,
                "name": state.sites[sid].get("name"),
                "country": state.sites[sid].get("country"),
                "site_type": state.sites[sid].get("site_type"),
                "qid": prechecks[sid].get("qid"),
                "serves_image": False,
                "reason": reason,
                "detail": detail,
                "claim": claims[sid],
                "export": export_state,
                "evidence": f"{PRECHECK_FILE} status {NO_IMAGE}",
            }
        )
    for sid in sorted(state.retired):
        rows.append(
            {
                "site_id": sid,
                "name": None,
                "country": None,
                "site_type": None,
                "qid": None,
                "serves_image": False,
                "reason": RETIRED,
                "detail": "curated, but scope_status = 'retired': the platform does not show it",
                "claim": None,
                "export": None,
                "evidence": f"{READ} retired",
            }
        )

    reasons = Counter(str(row["reason"]) for row in rows)
    summary = {
        "read_at": state.read_at,
        "read_sha256": state.sha256,
        "precheck_sha256": precheck_sha,
        "harvest": str(harvest_root),
        "export_replace_sha256": export["sha256"] if export else None,
        "counts": {
            "curated": len(state.sites) + len(state.retired),
            "shown": len(state.sites),
            "retired": len(state.retired),
            "serving": serving,
            "confirmed": confirmed,
            "unconfirmed": statuses.get(UNCONFIRMED, 0),
            "no_image": len(blanks),
            "reasons": {name: reasons.get(name, 0) for name in REASONS},
        },
        "addressable_remainder": reasons.get(CLAIMED_OPEN, 0),
        "report_sha256": write_text_once(run / REPORT_FILE, jsonl_text(rows)),
    }
    write_text_once(run / SUMMARY_FILE, json_text(summary))
    return summary
