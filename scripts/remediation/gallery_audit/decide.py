"""S9 - the sealed rule table: verdicts and liveness lines in, planned rows out.

The model never writes a value. A planned row is produced only by one of the rules below, and it
carries pointers, never prose: the ledger line it rests on (`verdict_id`, the sha256 of that line)
or the liveness line (`liveness_sha256`), the model, the prompt's sha256, the image's sha256 and
the rule id - and a vision rule's row the sha256 of the C1 admission that allowed it, which is
re-derived from the sealed calibration before any plan is made (`load_admission`). The table's own
sha256 is pinned in `tests/remediation/test_gallery_vision.py`; a rule is changed by changing the
pin, in review, never quietly.

What each rule may do, and when it is silent
--------------------------------------------
* K1/K2 write `image_kind` only when calibration admitted kind writes (T-kind), and K2 only when it
  admitted the strict pass too (T-strict). A row that already carries a kind is never overwritten -
  that value is somebody's recorded verdict (G0, G0b) - it is listed instead.
* X1-X3 exclude only when calibration admitted that trigger, never a row a founder added or
  restored by hand (`source_type = 'manual'`), and never for `artifact` (on a museum-typed site the
  artifacts are the site). An excluded hero loses its flag in the same chunk: an excluded hero
  would still be picked by `ORDER BY is_hero DESC` on the pages that do not filter.
* H1 moves the hero only to a strict-confirmed site photo with the attribution its licence needs
  and a Commons original that gives a 1600x900 derivative (T09's own projection), ranked like the
  hero repair (tier D before C, largest true area, lowest id). With no such candidate the site keeps
  what it has and is listed.
* L1 excludes the rows of a Commons file deleted as a copyright violation or for any other stated
  reason; L2 points the two URL columns of a renamed file at its live target. When L1 takes a
  hero, the replacement is chosen by the hero repair's own mechanical rule
  (`hero_repair.plan.candidate_verdict`/`rank_key`, the rule already applied to 2,719 sites):
  this lane runs before any vision verdict exists.
* R1 (hero re-derivation), A1-A4 (attribution) and T1 (thumbnail URL) belong to their own lanes
  (W12, W7, W13); their ids live in this table so every journal row of the image lanes cites one
  table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION = ROOT / "scripts" / "remediation"
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

from census.tests.t09_commons_dimensions import _as_derivative, _hero_ready  # noqa: E402
from hero_repair.plan import (  # noqa: E402
    TIERS_ACCEPTED,
    candidate_verdict,
    commons_file_name,
    load_truth,
    rank_key,
)

from gallery_audit import calibrate, liveness, vision, worklist  # noqa: E402
from gallery_audit.persist_verdicts import VOCAB  # noqa: E402
from gallery_audit.planned import PlannedRow, write_plan  # noqa: E402
from gallery_audit.worklist import served_row  # noqa: E402
from pipeline.commons_urls import commons_page_url_for  # noqa: E402

RULES: dict[str, str] = {
    "K1": "image_kind := the first-pass kind when it is artifact, map_or_document, painting_or_artwork, people or other, only if C1 admitted kind writes and the row carries no kind yet",
    "K2": "image_kind := 'site_photo' only when the first pass said site_photo and HERO_PROMPT confirmed shows_archaeology, only if C1 admitted kind writes and the strict pass",
    "X1": "is_excluded := true when the first pass says other_site, only if C1 admitted X1; never on a manual row",
    "X2": "is_excluded := true when the first-pass kind is people, only if C1 admitted X2; never on a manual row",
    "X3": "is_excluded := true when the first-pass kind is other, only if C1 admitted X3; never on a manual row",
    "H1": "is_hero moves to the best strict-confirmed site photo with attribution and a 1600x900 Commons derivative when the served image is excluded or fails the strict pass; tier D before C, largest true area, lowest id",
    "R1": "filename/width/height/file_size_bytes := a new derivative of the row's own Commons original, never wider than the original (hero_repair/rederive.py, W12)",
    "A1": "author/author_url := the extmetadata Artist value (gallery_audit/attribution.py, W7)",
    "A2": "author := the extmetadata Attribution value (W7)",
    "A3": "author/author_url := the own-work Credit's User: link (W7)",
    "A4": "author := the File page's {{Information|author=}} span (W7)",
    "L1": "is_excluded := true for a Commons file deleted as a copyright violation or for another stated reason; a hero among them loses the flag to the hero repair's own mechanical choice",
    "L2": "commons_page_url/original_url := the live target of a file moved without a redirect (evidence: the move logid)",
    "T1": "unified_sites.thumbnail_url := '/data/images/wiki/<shard>/<served filename>' (hero_repair/thumbnail.py, W13)",
}


def rules_sha256() -> str:
    return hashlib.sha256(json.dumps(RULES, sort_keys=True).encode("utf-8")).hexdigest()


K1_KINDS = ("artifact", "map_or_document", "painting_or_artwork", "people", "other")
X_RULES = (("X1", "other_site"), ("X2", "people"), ("X3", "other"))
MANUAL = "manual"
#: Licences that ask for no attribution (the values the snapshot carries, 2026-09-20): every other
#: licence needs a named author before its image may become a hero (design, H1).
NO_ATTRIBUTION_LICENCES = frozenset(
    {"Public domain", "CC0", "No restrictions", "Copyrighted free use"}
)


class DecideError(RuntimeError):
    """A plan that would break the state it is meant to leave behind."""


@dataclass(frozen=True)
class Admission:
    """What calibration (C1) admitted. Anything not admitted writes nothing."""

    kind: bool
    strict: bool
    x1: bool
    x2: bool
    x3: bool
    thresholds_sha256: str
    #: The sha256 of the ADMISSION.json these flags come from; every vision-planned row cites it.
    admission_sha256: str

    def admits(self, rule: str) -> bool:
        return {"X1": self.x1, "X2": self.x2, "X3": self.x3}[rule]


def load_admission(calibration_dir: Path) -> Admission:
    """The admission of a C1 run directory, re-derived from its sealed inputs before it is used
    (`calibrate.verify_admission`): a hand-written or stale ADMISSION.json switches nothing on.
    The flags are the re-derivation's own, so they are `evaluate`'s five booleans by construction.
    """
    record, digest = calibrate.verify_admission(calibration_dir)
    admitted = record["admitted"]
    return Admission(
        kind=admitted["kind"],
        strict=admitted["strict"],
        x1=admitted["x1"],
        x2=admitted["x2"],
        x3=admitted["x3"],
        thresholds_sha256=record["thresholds_sha256"],
        admission_sha256=digest,
    )


def _verdict_evidence(verdict: vision.Verdict, rule: str, admission: Admission) -> dict[str, Any]:
    return {
        "rule": rule,
        "rules_sha256": rules_sha256(),
        "admission_sha256": admission.admission_sha256,
        "verdict_id": verdict.verdict_id,
        "model": verdict.line["model"],
        "prompt_id": verdict.line["prompt_id"],
        "prompt_sha256": verdict.line["prompt_sha256"],
        "image_sha256": verdict.line["image_sha256"],
    }


def attribution_ok(row: Mapping[str, Any]) -> bool:
    licence = row.get("license")
    if licence in NO_ATTRIBUTION_LICENCES:
        return True
    return bool(licence) and bool((row.get("author") or "").strip())


def hero_candidate_static(
    row: Mapping[str, Any], truth: Mapping[str, Mapping[str, Any]]
) -> str | None:
    """Why a row cannot become the hero before any vision verdict, or None.

    The half of H1 that needs no model: not excluded, a C/D tier, the attribution its licence
    asks for, and a Commons original whose 1600 px derivative is at least 900 px high.
    """
    if row.get("is_excluded"):
        return "excluded"
    if row.get("_tier") not in TIERS_ACCEPTED:
        return f"tier-{row.get('_tier')}"
    if not attribution_ok(row):
        return "attribution-missing"
    name = commons_file_name(row)
    record = truth.get(name) if name else None
    if record is None or record.get("status") != "ok":
        return "no-commons-original"
    projected = _as_derivative(dict(record))
    if projected is None or not _hero_ready(*projected):
        return "original-below-1600x900"
    return None


def rank_candidates(
    rows: Iterable[Mapping[str, Any]], truth: Mapping[str, Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """The static candidates in the hero repair's order: tier D first, largest true area, id."""
    candidates = [
        (row, truth[str(commons_file_name(row))])
        for row in rows
        if hero_candidate_static(row, truth) is None
    ]
    return [row for row, _ in sorted(candidates, key=rank_key)]


def strict_confirmed(
    image_id: int, gallery: Mapping[int, vision.Verdict], hero: Mapping[int, vision.Verdict]
) -> bool:
    first = gallery.get(image_id)
    second = hero.get(image_id)
    return bool(
        first is not None
        and first.verdict["kind"] == "site_photo"
        and first.verdict["other_site"] is False
        and second is not None
        and second.verdict["shows_archaeology"] is True
    )


# ------------------------------------------------------------------------------ vision rules
def plan_vision(
    rows_by_site: Mapping[str, Sequence[Mapping[str, Any]]],
    kinds: Mapping[int, str | None],
    gallery: Mapping[int, vision.Verdict],
    hero: Mapping[int, vision.Verdict],
    admission: Admission,
    truth: Mapping[str, Mapping[str, Any]],
    blocked: Mapping[int, str],
) -> tuple[list[PlannedRow], list[dict[str, Any]]]:
    """K1, K2, X1-X3 and H1 over the current rows. Returns the planned rows and what was listed.

    `blocked` holds the rows whose Commons file is not live (`worklist.liveness_blocked`): no rule
    here plans on them - they are listed instead - and none of them can become a hero.
    """
    planned: list[PlannedRow] = []
    listed: list[dict[str, Any]] = []
    for site_id, rows in rows_by_site.items():
        excluded_now: set[int] = set()
        hero_dropped: set[int] = set()
        for row in rows:
            image_id = int(row["id"])
            first = gallery.get(image_id)
            if first is None:
                continue
            if image_id in blocked:
                listed.append(
                    {
                        "image_id": image_id,
                        "why": f"liveness: its Commons file is {blocked[image_id]} - no vision rule plans on it",
                    }
                )
                continue
            kind = first.verdict["kind"]
            current = kinds.get(image_id)
            new_kind = None
            rule = None
            if admission.kind and kind in K1_KINDS:
                new_kind, rule = kind, "K1"
            elif (
                admission.kind
                and admission.strict
                and kind == "site_photo"
                and strict_confirmed(image_id, gallery, hero)
            ):
                new_kind, rule = "site_photo", "K2"
            if new_kind is not None and rule is not None:
                if current is None:
                    planned.append(
                        PlannedRow(
                            "wiki_images",
                            image_id,
                            site_id,
                            "image_kind",
                            None,
                            new_kind,
                            rule,
                            "kind",
                            _verdict_evidence(
                                first if rule == "K1" else hero[image_id], rule, admission
                            ),
                        )
                    )
                elif current != new_kind:
                    listed.append(
                        {
                            "image_id": image_id,
                            "why": f"{rule}: carries {current!r}, the verdict says {new_kind!r} - not overwritten",
                        }
                    )
            if row.get("is_excluded") or row.get("source_type") == MANUAL:
                continue
            for rule_id, trigger in X_RULES:
                fired = (
                    first.verdict["other_site"] is True
                    if trigger == "other_site"
                    else kind == trigger
                )
                if fired and admission.admits(rule_id):
                    planned.append(
                        PlannedRow(
                            "wiki_images",
                            image_id,
                            site_id,
                            "is_excluded",
                            False,
                            True,
                            rule_id,
                            "exclude",
                            _verdict_evidence(first, rule_id, admission),
                        )
                    )
                    excluded_now.add(image_id)
                    if row.get("is_hero"):
                        planned.append(
                            PlannedRow(
                                "wiki_images",
                                image_id,
                                site_id,
                                "is_hero",
                                True,
                                False,
                                rule_id,
                                "hero-drop",
                                _verdict_evidence(first, rule_id, admission),
                            )
                        )
                        hero_dropped.add(image_id)
                    break
        if admission.strict:
            planned.extend(
                _plan_hero(
                    site_id,
                    rows,
                    excluded_now,
                    hero_dropped,
                    gallery,
                    hero,
                    truth,
                    blocked,
                    admission,
                    listed,
                )
            )
    return planned, listed


#: What the vision verdicts say about a site's served image (H1).
UNJUDGED, PENDING, PASSES, FAILS = "unjudged", "strict-pending", "passes", "fails"


def served_state(
    served_id: int,
    excluded_now: set[int],
    gallery: Mapping[int, vision.Verdict],
    hero: Mapping[int, vision.Verdict],
) -> str:
    """`fails` when the served image is being excluded, is not a site photo, shows another place,
    or the strict pass said no; `passes` only on a strict yes; otherwise not decided yet."""
    if served_id in excluded_now:
        return FAILS
    first = gallery.get(served_id)
    if first is None:
        return UNJUDGED
    if first.verdict["kind"] != "site_photo" or first.verdict["other_site"] is True:
        return FAILS
    second = hero.get(served_id)
    if second is None:
        return PENDING
    return PASSES if second.verdict["shows_archaeology"] is True else FAILS


def reselection_jobs(
    state: worklist.State,
    site_ids: Iterable[str],
    gallery: Mapping[int, vision.Verdict],
    hero: Mapping[int, vision.Verdict],
    truth: Mapping[str, Mapping[str, Any]],
    *,
    top: int = 3,
) -> list[vision.Job]:
    """H-reselect: the next question about the `top` static candidates of every site whose served
    image fails - the gallery question first, the strict one once the gallery said site photo."""
    jobs: list[vision.Job] = []
    for site_id in site_ids:
        rows = state.by_site.get(site_id, [])
        served = served_row(rows)
        if served is None or served_state(int(served["id"]), set(), gallery, hero) != FAILS:
            continue
        others = [row for row in state.live_rows(site_id) if int(row["id"]) != int(served["id"])]
        for row in rank_candidates(others, truth)[:top]:
            image_id = int(row["id"])
            first = gallery.get(image_id)
            if first is None:
                jobs.append(worklist.job_for(state, row, vision.GALLERY, worklist.H_RESELECT))
            elif (
                first.verdict["kind"] == "site_photo"
                and first.verdict["other_site"] is False
                and image_id not in hero
            ):
                jobs.append(worklist.job_for(state, row, vision.HERO, worklist.H_RESELECT))
    return jobs


def _plan_hero(
    site_id: str,
    rows: Sequence[Mapping[str, Any]],
    excluded_now: set[int],
    hero_dropped: set[int],
    gallery: Mapping[int, vision.Verdict],
    hero: Mapping[int, vision.Verdict],
    truth: Mapping[str, Mapping[str, Any]],
    blocked: Mapping[int, str],
    admission: Admission,
    listed: list[dict[str, Any]],
) -> list[PlannedRow]:
    """H1 for one site: a new hero when the served image is excluded or fails the strict pass."""
    served = served_row(rows)
    if served is None:
        return []
    served_id = int(served["id"])
    state = served_state(served_id, excluded_now, gallery, hero)
    if state == PENDING:
        listed.append(
            {
                "site_id": site_id,
                "image_id": served_id,
                "why": "H1: the served site photo has no strict verdict yet",
            }
        )
    if state != FAILS:
        return []
    current_hero = [
        row for row in rows if row.get("is_hero") and int(row["id"]) not in hero_dropped
    ]
    if any(int(row["id"]) in blocked for row in current_hero):
        listed.append(
            {
                "site_id": site_id,
                "image_id": served_id,
                "why": "H1: the hero's Commons file is not live - the liveness lane owns it, no vision rule moves it",
            }
        )
        return []
    live = [
        row
        for row in rows
        if not row.get("is_excluded")
        and int(row["id"]) not in excluded_now
        and int(row["id"]) not in blocked
    ]
    confirmed = [
        row
        for row in live
        if strict_confirmed(int(row["id"]), gallery, hero) and int(row["id"]) != served_id
    ]
    ranked = rank_candidates(confirmed, truth)
    if not ranked:
        listed.append(
            {
                "site_id": site_id,
                "image_id": served_id,
                "why": "H1: the served image fails and no strict-confirmed candidate qualifies - the hero stays",
            }
        )
        return []
    chosen = ranked[0]
    chosen_id = int(chosen["id"])
    out: list[PlannedRow] = []
    for row in current_hero:
        out.append(
            PlannedRow(
                "wiki_images",
                int(row["id"]),
                site_id,
                "is_hero",
                True,
                False,
                "H1",
                "hero-demote",
                _verdict_evidence(hero[chosen_id], "H1", admission),
            )
        )
    out.append(
        PlannedRow(
            "wiki_images",
            chosen_id,
            site_id,
            "is_hero",
            False,
            True,
            "H1",
            "hero-promote",
            _verdict_evidence(hero[chosen_id], "H1", admission),
        )
    )
    return out


# ------------------------------------------------------------------------------ liveness rules
def _liveness_evidence(line: Mapping[str, Any], rule: str) -> dict[str, Any]:
    log = line.get("log") or {}
    return {
        "rule": rule,
        "rules_sha256": rules_sha256(),
        "liveness_sha256": liveness.line_sha256(line),
        "commons_file": line["file"],
        "class": line["class"],
        "logid": log.get("logid"),
    }


def plan_liveness(
    lines: Iterable[Mapping[str, Any]],
    rows_by_site: Mapping[str, Sequence[Mapping[str, Any]]],
    truth: Mapping[str, Mapping[str, Any]],
) -> tuple[list[PlannedRow], list[dict[str, Any]]]:
    """L1 and L2 over the liveness store's non-live lines.

    A hero L1 takes is replaced by the hero repair's own rule among the rows that stay live: the
    rows of every file the store lists as not live (a redirect alone aside) are no candidate.
    """
    lines = list(lines)
    by_id = {int(row["id"]): row for rows in rows_by_site.values() for row in rows}
    not_live = {
        int(image_id)
        for line in lines
        if line["class"] not in (liveness.LIVE, liveness.MOVED_WITH_REDIRECT)
        for image_id in line["image_ids"]
    }
    planned: list[PlannedRow] = []
    listed: list[dict[str, Any]] = []
    dropped_heroes: dict[str, list[int]] = defaultdict(list)
    for line in lines:
        cls = line["class"]
        for image_id in line["image_ids"]:
            row = worklist.liveness_row(by_id, line, image_id)
            site_id = str(row["site_id"])
            if cls in (liveness.DELETED_COPYVIO, liveness.DELETED_OTHER):
                if row.get("is_excluded"):
                    continue
                evidence = _liveness_evidence(line, "L1")
                planned.append(
                    PlannedRow(
                        "wiki_images",
                        int(image_id),
                        site_id,
                        "is_excluded",
                        False,
                        True,
                        "L1",
                        "exclude",
                        evidence,
                    )
                )
                if row.get("is_hero"):
                    planned.append(
                        PlannedRow(
                            "wiki_images",
                            int(image_id),
                            site_id,
                            "is_hero",
                            True,
                            False,
                            "L1",
                            "hero-drop",
                            evidence,
                        )
                    )
                    dropped_heroes[site_id].append(int(image_id))
            elif cls == liveness.MOVED_WITHOUT_REDIRECT:
                target = line.get("move_target") or {}
                if target.get("class") != liveness.LIVE or not target.get("url"):
                    listed.append(
                        {
                            "image_id": image_id,
                            "why": f"L2: the move target {target.get('title')!r} is not a live file",
                        }
                    )
                    continue
                new_original = str(target["url"])
                new_page = commons_page_url(str(target["title"]))
                clash = [
                    r
                    for r in rows_by_site.get(site_id, ())
                    if r.get("original_url") == new_original and int(r["id"]) != int(image_id)
                ]
                if clash:
                    listed.append(
                        {
                            "image_id": image_id,
                            "why": f"L2: row {clash[0]['id']} of the same site already carries the target URL",
                        }
                    )
                    continue
                evidence = _liveness_evidence(line, "L2")
                for column, new in (("commons_page_url", new_page), ("original_url", new_original)):
                    if row.get(column) != new:
                        planned.append(
                            PlannedRow(
                                "wiki_images",
                                int(image_id),
                                site_id,
                                column,
                                row.get(column),
                                new,
                                "L2",
                                "url",
                                evidence,
                            )
                        )
            elif cls != liveness.LIVE:
                listed.append({"image_id": image_id, "why": f"{cls}: no rule acts on this class"})
    for site_id, ids in dropped_heroes.items():
        planned.extend(
            _replace_hero(
                site_id,
                rows_by_site[site_id],
                set(ids) | {r.key for r in planned if r.column == "is_excluded"} | not_live,
                truth,
                listed,
            )
        )
    return planned, listed


def commons_page_url(file_title: str) -> str:
    """The page URL the downloader stores for a move target's `File:` title - the project's
    own spelling (`pipeline.commons_urls.commons_page_url_for`, spaces quoted as %20) - for a
    title the liveness store holds as a file title; anything else is refused.
    """
    if not file_title.startswith("File:"):
        raise DecideError(f"{file_title!r} is not a File: title")
    return commons_page_url_for(file_title)


def _replace_hero(
    site_id: str,
    rows: Sequence[Mapping[str, Any]],
    gone: set[int],
    truth: Mapping[str, Mapping[str, Any]],
    listed: list[dict[str, Any]],
) -> list[PlannedRow]:
    """The hero repair's own choice among the rows L1 leaves standing (no vision verdict yet)."""
    candidates = []
    for row in rows:
        if int(row["id"]) in gone or row.get("is_hero"):
            continue
        name = commons_file_name(row)
        record = truth.get(name) if name else None
        if candidate_verdict(row, row.get("_tier"), record).eligible:
            candidates.append(({**row, "_tier": row["_tier"]}, record))
    if not candidates:
        listed.append(
            {
                "site_id": site_id,
                "why": "L1 took the hero and no row meets the hero repair's rule - the page falls back to is_lead/sort_order",
            }
        )
        return []
    chosen, record = min(candidates, key=rank_key)
    evidence = {
        "rule": "L1",
        "rules_sha256": rules_sha256(),
        "replacement_rule": "hero_repair.plan.candidate_verdict/rank_key",
        "tier": chosen["_tier"],
        "commons_original": f"{record['width']}x{record['height']}",
    }
    return [
        PlannedRow(
            "wiki_images",
            int(chosen["id"]),
            site_id,
            "is_hero",
            False,
            True,
            "L1",
            "hero-promote",
            evidence,
        )
    ]


# ------------------------------------------------------------------------------ invariants
def check_plan(
    planned: Sequence[PlannedRow], rows_by_site: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict[str, Any]:
    """Refuse a plan that breaks the design's per-chunk invariants; report the rest.

    Each (row, column) once and a real change; `image_kind` inside the column's vocabulary; at most
    one hero per site and no hero on an excluded row once the plan is applied.
    """
    seen: set[tuple[int, str]] = set()
    for row in planned:
        if row.rule not in RULES:
            raise DecideError(f"image {row.key}: rule {row.rule!r} is not in the table")
        if (row.key, row.column) in seen:
            raise DecideError(f"image {row.key}: {row.column} planned twice")
        seen.add((row.key, row.column))
        if row.old == row.new:
            raise DecideError(f"image {row.key}: {row.column} planned without a change")
        if row.column == "image_kind" and row.new not in VOCAB:
            raise DecideError(f"image {row.key}: image_kind {row.new!r} is outside the vocabulary")
    changes: dict[int, dict[str, Any]] = defaultdict(dict)
    for row in planned:
        changes[row.key][row.column] = row.new
    emptied = []
    for site_id, rows in rows_by_site.items():
        after = [{**row, **changes.get(int(row["id"]), {})} for row in rows]
        heroes = [row for row in after if row.get("is_hero")]
        if len(heroes) > 1:
            raise DecideError(f"site {site_id}: {len(heroes)} heroes after the plan")
        if any(row.get("is_excluded") for row in heroes):
            raise DecideError(f"site {site_id}: the hero is excluded after the plan")
        if any(not r.get("is_excluded") for r in rows) and not any(
            not r.get("is_excluded") for r in after
        ):
            emptied.append(site_id)
    return {"planned": len(planned), "sites_left_without_a_live_image": emptied}


def verify_evidence(
    planned: Sequence[PlannedRow], ledger: Sequence[vision.LedgerLine], images: vision.Images
) -> list[str]:
    """Design verification 3, per vision-planned row: the verdict it cites is in the ledger, is an
    ok verdict asked with today's frozen prompt of its id and answered by the pilot's model, the
    row's evidence repeats that line's hashes, and the image bytes the verdict judged are the bytes
    the offsite copy holds now. Returns every discrepancy; the caller refuses a plan with any."""
    by_id = {entry.verdict_id: entry for entry in ledger}
    templates = dict(vision.PROMPTS.values())
    digests: dict[Path, str] = {}
    problems: list[str] = []
    for row in planned:
        cited = row.evidence.get("verdict_id")
        if row.rule in ("L1", "L2"):
            continue  # a liveness row cites its store line, not a verdict
        entry = by_id.get(str(cited))
        if entry is None:
            problems.append(f"image {row.key} ({row.rule}): verdict {cited!r} is not in the ledger")
            continue
        line = entry.line
        if not entry.ok or line["model"] != vision.MODEL:
            problems.append(
                f"image {row.key} ({row.rule}): verdict {entry.verdict_id[:12]} is not an ok verdict of {vision.MODEL}"
            )
            continue
        if line["prompt_sha256"] != vision.prompt_sha256(templates[line["prompt_id"]]):
            problems.append(
                f"image {row.key} ({row.rule}): verdict {entry.verdict_id[:12]} was asked with another {line['prompt_id']}"
            )
            continue
        if (row.evidence.get("image_sha256"), row.evidence.get("prompt_sha256")) != (
            line["image_sha256"],
            line["prompt_sha256"],
        ):
            problems.append(
                f"image {row.key} ({row.rule}): the evidence does not repeat its verdict's hashes"
            )
            continue
        path = images.path_for(str(line["site_id"]), str(line["image_file"]).split("/", 1)[1])
        if path not in digests:
            digests[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        if digests[path] != line["image_sha256"]:
            problems.append(
                f"image {row.key} ({row.rule}): the offsite file changed since the verdict judged it"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    """`decide.py liveness --store DIR --hero-moves PLAN.jsonl`: the L1/L2 rows of a liveness store,
    written next to it as PLANNED.jsonl (+ LISTED.json). Offline; the chunk writer applies them.

    `decide.py vision --run-dir DIR --calibration C1-DIR --liveness-store DIR --chunk N
    --kinds-from G0-PLAN.jsonl ... --applied <store>/PLANNED.jsonl ...`: the K/X/H rows of one
    chunk, on the state with every applied plan folded in (the liveness write first), under the
    admission re-derived from the C1 directory."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("liveness")
    live.add_argument("--store", required=True)
    live.add_argument("--snapshot", default=str(worklist.DEFAULT_SNAPSHOT))
    live.add_argument("--cache", default=str(worklist.DEFAULT_CACHE))
    live.add_argument("--t10", default=str(worklist.DEFAULT_T10))
    live.add_argument("--hero-moves", default=str(worklist.DEFAULT_HERO_MOVES))
    worklist.add_state_flags(live)
    vis = sub.add_parser("vision")
    vis.add_argument(
        "--run-dir", required=True, help="holds VERDICTS.jsonl; PLANNED.jsonl goes here"
    )
    vis.add_argument(
        "--calibration",
        required=True,
        help="the C1 run directory; its ADMISSION.json is re-derived before it is used",
    )
    vis.add_argument(
        "--liveness-store",
        required=True,
        help="the liveness store whose L1/L2 write the state must have folded in (--applied)",
    )
    vis.add_argument("--chunk", type=int, required=True, help="0-based chunk of 100 sites")
    for flag, default in (
        ("--snapshot", worklist.DEFAULT_SNAPSHOT),
        ("--cache", worklist.DEFAULT_CACHE),
        ("--t10", worklist.DEFAULT_T10),
        ("--hero-moves", worklist.DEFAULT_HERO_MOVES),
    ):
        vis.add_argument(flag, default=str(default))
    worklist.add_state_flags(vis)
    args = parser.parse_args(argv)
    state = worklist.state_from_args(args)
    truth = load_truth(Path(args.cache) / "commons_imageinfo.json")
    if args.command == "vision":
        blocked = worklist.liveness_blocked(
            liveness.load_store(Path(args.liveness_store) / "NOT_LIVE.jsonl"), state.by_site
        )
        run_dir = Path(args.run_dir)
        ledger = vision.Ledger(run_dir / "VERDICTS.jsonl").lines
        site_ids = worklist.chunks(state)[args.chunk]
        rows = {sid: state.by_site[sid] for sid in site_ids}
        planned, listed = plan_vision(
            rows,
            {int(row["id"]): row["image_kind"] for site in rows.values() for row in site},
            vision.verdicts_by_image(ledger, vision.GALLERY_PROMPT_ID),
            vision.verdicts_by_image(ledger, vision.HERO_PROMPT_ID),
            load_admission(Path(args.calibration)),
            truth,
            blocked,
        )
        report = check_plan(planned, rows)
        problems = verify_evidence(planned, ledger, vision.Images())
        if problems:
            raise DecideError(
                f"{len(problems)} planned row(s) fail the verdict check: {problems[:3]}"
            )
        name = f"PLANNED-chunk-{args.chunk:03d}"
        digest = write_plan(run_dir / f"{name}.jsonl", planned)
        (run_dir / f"{name}.listed.json").write_text(
            json.dumps(listed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        print(json.dumps({**report, "planned_sha256": digest, "listed": len(listed)}, indent=1))
        return 0
    store = Path(args.store)
    lines = liveness.load_store(store / "NOT_LIVE.jsonl")
    planned, listed = plan_liveness(lines, state.by_site, truth)
    touched = {row.site_id for row in planned}
    report = check_plan(planned, {sid: state.by_site[sid] for sid in touched})
    digest = write_plan(store / "PLANNED.jsonl", planned)
    (store / "LISTED.json").write_text(
        json.dumps(listed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                **report,
                "planned_sha256": digest,
                "listed": len(listed),
                "rules_sha256": rules_sha256(),
            },
            indent=1,
        )
    )
    for row in planned:
        print(
            f"  {row.rule} {row.role:13} image {row.key} {row.column}: {row.old!r} -> {row.new!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
