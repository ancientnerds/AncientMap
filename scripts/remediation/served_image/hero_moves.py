"""D48 and D49 (owner decisions of 2026-10-19): the hero moves that ride in the D15 pass.

**D48** "Swap strips and broken ones in the D15 pass where a checked larger row of the same site
exists, incl. the 20 unflagged; the 433 small heroes only go on the owner list." **D49** "A hero moves
to a fully attributed row where one exists; the rest stay in the gallery and stay barred from Shorts
(D28)." Both are the same write - the hero flag moves from one live row of a site to another, and the
globe's `thumbnail_url` follows it - so one planner makes both, from one fresh production read, and the
shared image writer (`gallery_audit/chunk_writer.py`) writes them under the lane `hero-moves`.

What a site can be planned for (`problems_of`), each measured on the read:

* `unflagged` (D48) - the site serves live rows and none carries the hero flag (20 on 2026-10-24);
* `strip` (D48) - the live hero is below the owner's floor of 800x300 (19);
* `hotlink` (D48) - the site serves live rows but its `thumbnail_url` is a remote address or the
  empty string, so the globe shows a picture nobody checked or credited;
* `no_author` (D49) - the live hero's licence asks for an author (`licenses.credit_columns`) and the
  row has none (50).

**The new hero is always a qualifying row** (`qualifies`), whatever the problem: live, judged
`depicts` by a Claude check of that very file, at least 800x300, with every credit column its licence
demands; for a strip larger than the hero it replaces, and for any other move not below 1600x900 where
the hero it replaces is not (the move would otherwise make one of D48's small heroes). A qualifying row
is never chosen because it is the only one: a site without one is not planned and goes on the owner
list with the measured reason. "Checked" has two sources, never a guess:

1. the served-image runs (`--verdicts-run`, `CHECK.jsonl` and `REPLACE.jsonl`, in the order given;
   a later run's verdict on an image replaces an earlier one): Claude stamps only (D6/D10);
2. candidate check runs of the image roles (`--check-run`): the `TARGETS.jsonl` pick of a site, which
   the depicts role chose and the adversarial re-check confirmed (`check-pictures` builds that run's
   population and pictures from this read).

**And it is a chosen row** (`chosen_by`): a `depicts` says the picture is of the site, and the served
check's `depicts` includes a find from the site, a drawing and a reconstruction (`served_image/
vision.py`), so it does not say the picture is the site's main picture. A row becomes the hero only
when a judgement chose it as that: the confirmed pick of a check run (the depicts role's quality, "suits
the main picture of the site's page", then the adversarial re-check), the served-image replacement
stage's own `pick` ("the best main image of the site - a clear photograph of its remains before a
drawing, a plan or an object"), or - for an unflagged site only - the row the page already shows, which
the served check judged as the page's main image and which the flag leaves in place. A `depicts` row
nobody chose is not ranked by its pixels; `check-pictures` hands it to the image roles with the rows
nobody judged, and their confirmed pick comes back through `--check-run`.

A site whose hero the latest Claude check called `other_site` is not planned here: it is the D15
re-check's subject (`served_image/recheck.py`), and a hero move here would pre-empt that judgement.
Planning after the D15 chunk was accepted, from a fresh read with the D15 run among the verdict runs,
is the order the runbook gives.

The ranking among chosen rows: a confirmed check-run pick, then the replacement stage's pick, then the
row the page shows, then the depicts role's quality, then the pixels, then `sort_order` and the id.

**Nothing is written before a review** (`emit`). `plan` writes the review page `PLANNED.jsonl` (per site
the old hero, the new one and what its check said) and the site plans, no chunk. A reviewer - the
owner, or a Claude agent (D6) - answers every planned site in a review file, `accept` or `veto`, and
only `emit --review` turns the accepted sites into chunks of the shared writer; every journal row
carries the review line that accepted it. A vetoed row goes to `VETOED.jsonl`, in the shape `--veto`
reads, for the next plan in a new run directory.

    hero_moves.py read           --run-dir R
    hero_moves.py check-pictures --run-dir R --verdicts-run S [S ...] --check-run C
    hero_moves.py plan           --run-dir R --verdicts-run S [S ...] [--check-run C ...] [--veto V]
    hero_moves.py emit           --run-dir R --review REVIEW.jsonl
    chunk_writer.py R/chunks/chunk-NNN --check | --rehearse | --apply | --readback | --rehearse-rollback
    hero_moves.py accept         --run-dir R --chunk R/chunks/chunk-NNN

A review line: `{"site_id", "new_image_id", "decision": "accept" | "veto", "by", "reason"}` - one per
line of `PLANNED.jsonl`, `new_image_id` the planned new hero, `by` `owner` or a Claude answer stamp,
`reason` required for a veto.

`plan` also writes `OWNER_LIST.jsonl` (every site with a problem and no qualifying chosen row, with the
reason) and `SMALL_HEROES.jsonl` (D48's 433: a live hero below 1600x900 at a site that holds another
live row of at least 1600x900 - the census definition, reproduced on 2026-10-24 at 433).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import licenses as LIC  # noqa: E402
from candidate_search import judge as CJ  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from gallery_audit.worklist import served_row  # noqa: E402
from hero_repair.thumbnail import local_path  # noqa: E402
from import_hero import plan as IH  # noqa: E402

from served_image import plan as SP  # noqa: E402
from served_image import recheck as RC  # noqa: E402
from served_image import state as ST  # noqa: E402

LANE_NAME = "hero-moves"
TEST_ID = "D48-D49/hero-moves"
LABEL = "hero moves"
RUN_RE = re.compile(r"hero-moves-(\d{4}-\d{2}-\d{2}[a-z]?)")

RULE_D48_HERO = "d48-hero"
RULE_D48_ALIGN = "d48-align"
RULE_D49_HERO = "d49-hero"
RULE_D49_ALIGN = "d49-align"

UNFLAGGED, STRIP, HOTLINK, NO_AUTHOR = "unflagged", "strip", "hotlink", "no_author"
#: The order a site's problems are named in; the first one names the rule (D48 before D49).
PROBLEMS = (UNFLAGGED, STRIP, HOTLINK, NO_AUTHOR)
D48_PROBLEMS = frozenset({UNFLAGGED, STRIP, HOTLINK})

FLAGGED, MOVED, ALIGNED = "hero flagged", "hero moved", "thumbnail aligned"
#: The owner's floor (2026-10-06), the floor every image lane applies to a picture a page serves.
FLOOR = (IH.OWNER_FLOOR_WIDTH, IH.OWNER_FLOOR_HEIGHT)
#: D48's "small hero": below the INSERT lane's hero size while the site holds a row of that size.
LARGE = (IH.HERO_MIN_WIDTH, IH.HERO_MIN_HEIGHT)

READ_FILE = "READ.json"
CHUNKS = "chunks"
EXPECTED = "EXPECTED.jsonl"
SUMMARY = "PLAN_SUMMARY.json"
EMIT_SUMMARY = "EMIT_SUMMARY.json"
OWNER_LIST = "OWNER_LIST.jsonl"
PLANNED = "PLANNED.jsonl"
PLAN_SITES = "PLAN_SITES.jsonl"
VETOED = "VETOED.jsonl"
SMALL_HEROES = "SMALL_HEROES.jsonl"
DEFERRED = "DEFERRED_D15.jsonl"
CHECK_SOURCE = "HERO_MOVES_SOURCE.json"
CHECK_REFUSALS = "PICTURE_REFUSALS.jsonl"
#: The files `plan` writes into the run directory, each once; the summary last.
PLAN_FILES = (PLANNED, PLAN_SITES, OWNER_LIST, DEFERRED, SMALL_HEROES, SUMMARY)

#: The reasons a row is not a qualifying hero, as `qualifies` names them.
UNCHECKED = "no Claude check of this row"
OTHER_FILE = "the row holds another file than the one the check judged"
BELOW_FLOOR = f"below the floor of {FLOOR[0]}x{FLOOR[1]}"
NOT_LARGER = "not larger than the hero it would replace"
SMALLER = (
    f"below {LARGE[0]}x{LARGE[1]} while the hero it would replace is not: the move would make "
    "a D48 small hero"
)
CREDIT = "its licence demands a credit the row does not carry"
NOT_CHOSEN = (
    "judged depicts, but no judgement chose it as the site's main picture - the image roles "
    "choose among such rows (check-pictures)"
)

#: How a qualifying row was chosen as the site's main picture (`chosen_by`), best first.
CONFIRMED_PICK, REPLACEMENT_PICK, SHOWN = "check-run pick", "replacement pick", "shown already"
CHOICES = (CONFIRMED_PICK, REPLACEMENT_PICK, SHOWN)

#: A review line's decision, and who may make it: the owner or a Claude answer stamp (D6).
ACCEPT, VETO = "accept", "veto"
OWNER = "owner"


class HeroMovesError(ST.StateError):
    """The read, a verdict source or the plan does not allow the step. Nothing was written."""


# ---------------------------------------------------------------------------------- the read
SITES_SQL = f"""SELECT row_to_json(t) FROM (
  SELECT u.id::text AS id, u.name, u.country, u.site_type, u.lat, u.lon, u.thumbnail_url,
         left(coalesce(u.description, ''), 700) AS description,
         (SELECT min(e.value) FROM site_external_ids e
           WHERE e.site_id = u.id AND e.kind = 'wikidata_qid') AS qid,
         (SELECT min(e.value) FROM site_external_ids e
           WHERE e.site_id = u.id AND e.kind = 'enwiki_title') AS enwiki_title
    FROM unified_sites u
   WHERE u.source_id = '{ST.CURATED_SOURCE}' AND u.scope_status IS DISTINCT FROM 'retired'
   ORDER BY u.id
) t;"""

IMAGES_SQL = f"""SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.filename, w.title, w.commons_page_url,
         w.original_url, w.is_hero, w.is_lead, w.is_excluded, w.sort_order, w.width, w.height,
         w.license, w.license_url, w.author, w.file_size_bytes
    FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id
   WHERE u.source_id = '{ST.CURATED_SOURCE}' AND u.scope_status IS DISTINCT FROM 'retired'
   ORDER BY w.site_id, w.id
) t;"""


def read_production() -> dict[str, Any]:
    """The shown curated sites and every image row of them: two read-only statements."""
    return {
        "read_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sites": CW.pv.read_rows(SITES_SQL),
        "images": CW.pv.read_rows(IMAGES_SQL),
    }


@dataclass(frozen=True)
class Read:
    sites: Mapping[str, Mapping[str, Any]]
    rows: Mapping[str, tuple[Mapping[str, Any], ...]]
    sha256: str
    read_at: str


def load_read(run: Path) -> Read:
    path = run / READ_FILE
    if not path.is_file():
        raise HeroMovesError(f"{path} does not exist - run `hero_moves.py read` first")
    data = json.loads(path.read_text(encoding="utf-8"))
    sites = {str(s["id"]): s for s in data["sites"]}
    if not sites:
        raise HeroMovesError(f"{path} holds no site")
    rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in data["images"]:
        sid = str(row["site_id"])
        if sid not in sites:
            raise HeroMovesError(
                f"image {row['id']} belongs to {sid}, which the read does not hold"
            )
        rows.setdefault(sid, []).append(row)
    return Read(
        sites, {s: tuple(r) for s, r in rows.items()}, ST.file_sha256(path), str(data["read_at"])
    )


def lane_for(run: Path) -> CW.Lane:
    match = RUN_RE.fullmatch(run.name)
    if match is None:
        raise HeroMovesError(f"{run} is not a run directory (hero-moves-YYYY-MM-DD[a-z])")
    return CW.Lane(LANE_NAME, TEST_ID, f"{LANE_NAME}-{match.group(1)}", "authoritative", LABEL)


# ------------------------------------------------------------------------------ the checks
@dataclass(frozen=True)
class Check:
    """One Claude judgement of one file of one site: where it is recorded and what it said."""

    site_id: str
    file: str
    verdict: str
    source: str
    stage: str
    answered_by: str
    model: str
    quality: int | None = None
    #: A check-run pick: the depicts role chose it and the adversarial re-check confirmed it.
    confirmed: bool = False
    #: The served-image replacement stage's own `pick`: the agent saw the whole gallery and named
    #: this row the best picture of the site (`REPLACE.jsonl`, a `G` label).
    picked: bool = False
    #: What the checker said this very picture shows: the served check's `shows`, a check run's
    #: per-candidate `note`. A replacement answer has no per-candidate text, so it stays None there.
    shows: str | None = None
    #: The served check's `basis` - about this picture, since that stage judges one picture.
    basis: str | None = None
    #: A replacement answer judges a whole gallery: the row's label in it, and the answer's `basis`,
    #: which speaks of the answer's pick (often another candidate), not of this row.
    label: str | None = None
    answer_basis: str | None = None

    def evidence(self, image_id: int) -> dict[str, Any]:
        out = {k: v for k, v in asdict(self).items() if v is not None}
        return out | {"image_id": image_id}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise HeroMovesError(f"{path} does not exist")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def served_checks(runs: Sequence[Path]) -> dict[int, Check]:
    """`image id -> its latest Claude check` over served-image runs, in the order given.

    A record stamped by a model that is not a Claude model is dropped before the merge - it is no
    check under D6/D10 - so it can neither count nor hide the Claude verdict before it."""
    stamps = CJ.claude_stamps()
    out: dict[int, Check] = {}
    for run in runs:
        checks = [r for r in _jsonl(run / "CHECK.jsonl") if r.get("model") in stamps]
        replace_path = run / "REPLACE.jsonl"
        replaces = (
            [r for r in _jsonl(replace_path) if r.get("model") in stamps]
            if (replace_path.is_file())
            else []
        )
        picked = replacement_picks(replaces)
        labels = replacement_labels(replaces)
        for image_id, judged in RC.judged_gallery_rows(checks, replaces).items():
            replace = judged["stage"] == "served-replace"
            if not judged.get("file"):
                raise HeroMovesError(f"{run.name}: the verdict on image {image_id} names no file")
            out[image_id] = Check(
                site_id=str(judged["site_id"]),
                file=ST.canonical_file(str(judged["file"])),
                verdict=str(judged["verdict"]),
                source=f"served_image/{run.name}/{'REPLACE' if replace else 'CHECK'}.jsonl",
                stage=str(judged["stage"]),
                answered_by=str(judged.get("answered_by") or ""),
                model=str(judged["model"]),
                picked=image_id in picked and replace,
                shows=None if replace else judged.get("shows"),
                basis=None if replace else judged.get("basis"),
                label=labels[image_id] if replace else None,
                answer_basis=judged.get("basis") if replace else None,
            )
    return out


def replacement_labels(replaces: Iterable[Mapping[str, Any]]) -> dict[int, str]:
    """`image id -> its label` in the latest replacement answer that showed it (the order
    `judged_gallery_rows` keeps the verdict of)."""
    out: dict[int, str] = {}
    for row in replaces:
        for shown in row["candidates_shown"]:
            if shown.get("kind") == "gallery" and shown.get("image_id"):
                out[int(shown["image_id"])] = str(shown["label"])
    return out


def replacement_picks(replaces: Iterable[Mapping[str, Any]]) -> set[int]:
    """The gallery rows a replacement answer picked as the best picture of its site."""
    out: set[int] = set()
    for row in replaces:
        pick = row.get("pick")
        if pick is None:
            continue
        shown = {c["label"]: c for c in row["candidates_shown"]}
        if shown[pick].get("kind") == "gallery" and shown[pick].get("image_id"):
            out.add(int(shown[pick]["image_id"]))
    return out


def check_picks(runs: Sequence[Path]) -> dict[str, Check]:
    """`site id -> its confirmed pick` over candidate check runs (`image_roles`): the `TARGETS.jsonl`
    line of the site, refused unless its `depicts` came from Claude and a Claude re-check confirmed
    that very file. A site picked by two runs is refused - one site has one hero."""
    out: dict[str, Check] = {}
    for run in runs:
        targets = _jsonl(run / CJ.TARGETS)
        verdicts = _jsonl(run / CJ.VERDICTS)
        confirmed = CJ.confirmed_by_recheck(run)
        unjudged = CJ.targets_without_claude(targets, verdicts, confirmed)
        if unjudged:
            raise HeroMovesError(
                f"{run.name}: {len(unjudged)} target(s) no Claude model judged (first {unjudged[0]})"
            )
        by_key = {
            (str(v["site_id"]), str(v["file"])): v for v in verdicts if v["verdict"] == CJ.DEPICTS
        }
        for target in targets:
            key = (str(target["site_id"]), str(target["commons_file"]))
            if key not in confirmed:
                raise HeroMovesError(
                    f"{run.name}: target {key[1]!r} of {key[0]} was never confirmed by the "
                    "adversarial re-check - write-targets is the only writer of a pick"
                )
            if key[0] in out:
                raise HeroMovesError(f"{key[0]} is picked by two check runs")
            verdict = by_key[key]
            out[key[0]] = Check(
                site_id=key[0],
                file=ST.canonical_file(key[1]),
                verdict=CJ.DEPICTS,
                source=f"image_roles/{run.name}/{CJ.TARGETS}",
                stage="image-recheck",
                answered_by=str(verdict.get("answered_by") or ""),
                model=str(verdict["model"]),
                quality=int(verdict["quality"]) if verdict.get("quality") is not None else None,
                confirmed=True,
                shows=verdict.get("note"),
            )
    return out


def row_check(
    row: Mapping[str, Any], served: Mapping[int, Check], picks: Mapping[str, Check]
) -> Check | None:
    """The check that speaks for `row`: a check-run pick of its file first, else the latest
    served-image verdict on the row. A verdict recorded for another site is refused."""
    sid = str(row["site_id"])
    file = ST.file_of_row(row)
    pick = picks.get(sid)
    if pick is not None and file == pick.file:
        return pick
    check = served.get(int(row["id"]))
    if check is not None and check.site_id != sid:
        raise HeroMovesError(f"image {row['id']} of {sid} carries a verdict for {check.site_id}")
    return check


# ----------------------------------------------------------------------------- the rules
def _size(row: Mapping[str, Any]) -> tuple[int, int]:
    return int(row.get("width") or 0), int(row.get("height") or 0)


def below(row: Mapping[str, Any], box: tuple[int, int]) -> bool:
    width, height = _size(row)
    return width < box[0] or height < box[1]


def missing_credit(row: Mapping[str, Any]) -> list[str]:
    """The credit columns the row's licence demands and the row does not carry (D18's rule)."""
    demanded = LIC.credit_columns(str(row.get("license") or ""))
    return [c for c in demanded if not str(row.get(c) or "").strip()]


def is_local(thumbnail: str) -> bool:
    return thumbnail.startswith("/data/")


def problems_of(
    site: Mapping[str, Any], live: Sequence[Mapping[str, Any]], hero: Mapping[str, Any] | None
) -> list[str]:
    """The D48/D49 problems of one site, in `PROBLEMS` order (see the module docstring)."""
    if not live:
        return []
    found = []
    if hero is None:
        found.append(UNFLAGGED)
    if hero is not None and below(hero, FLOOR):
        found.append(STRIP)
    thumb = site.get("thumbnail_url")
    if thumb is not None and not is_local(str(thumb)):
        found.append(HOTLINK)
    if hero is not None and "author" in missing_credit(hero):
        found.append(NO_AUTHOR)
    return found


def size_and_credit(
    row: Mapping[str, Any],
    *,
    larger_than: Mapping[str, Any] | None = None,
    keeps_large: Mapping[str, Any] | None = None,
) -> str | None:
    """What the row itself lacks as a hero, or None: the floor, larger than a strip it replaces
    (`larger_than`), not small beside a large hero it replaces (`keeps_large`), its credit."""
    if below(row, FLOOR):
        return BELOW_FLOOR
    if larger_than is not None:
        width, height = _size(row)
        hero_w, hero_h = _size(larger_than)
        if width * height <= hero_w * hero_h:
            return NOT_LARGER
    if keeps_large is not None and not below(keeps_large, LARGE) and below(row, LARGE):
        return SMALLER
    missing = missing_credit(row)
    if missing:
        return f"{CREDIT}: {', '.join(missing)}"
    return None


def qualifies(
    row: Mapping[str, Any],
    check: Check | None,
    *,
    larger_than: Mapping[str, Any] | None = None,
    keeps_large: Mapping[str, Any] | None = None,
) -> str | None:
    """Why `row` cannot be the site's hero, or None when it can (see the module docstring)."""
    if check is None:
        return UNCHECKED
    if check.verdict != CJ.DEPICTS:
        return f"judged {check.verdict} ({check.source})"
    if ST.file_of_row(row) != check.file:
        return OTHER_FILE
    return size_and_credit(row, larger_than=larger_than, keeps_large=keeps_large)


def chosen_by(
    row: Mapping[str, Any],
    check: Check,
    *,
    hero: Mapping[str, Any] | None,
    shown: Mapping[str, Any] | None,
) -> str | None:
    """How a judgement chose `row` as the site's main picture (`CHOICES`), or None: a `depicts`
    alone is no such choice (see the module docstring). `shown` is the row the page shows now
    (`gallery_audit.worklist.served_row`); it counts only for a site without a hero flag, where
    flagging it changes nothing a visitor sees."""
    if check.confirmed:
        return CONFIRMED_PICK
    if check.picked:
        return REPLACEMENT_PICK
    if hero is None and shown is not None and int(shown["id"]) == int(row["id"]):
        return SHOWN
    return None


def _rank(row: Mapping[str, Any], check: Check, choice: str) -> tuple[int, int, int, int, int]:
    width, height = _size(row)
    order = row.get("sort_order")
    return (
        -CHOICES.index(choice),
        int(check.quality or 0),
        width * height,
        -(order if order is not None else 1 << 30),
        -int(row["id"]),
    )


@dataclass
class Decision:
    site_id: str
    problems: list[str]
    plan: SP.SitePlan | None = None
    owner_reason: str | None = None
    rejected: dict[int, str] | None = None
    deferred: Check | None = None
    hero: Mapping[str, Any] | None = None
    new: Mapping[str, Any] | None = None
    check: Check | None = None
    choice: str | None = None


def _reason_text(problems: Sequence[str], hero: Mapping[str, Any] | None) -> str:
    parts = []
    for problem in problems:
        if problem == UNFLAGGED:
            parts.append("the site serves live rows and none carries the hero flag")
        elif problem == STRIP and hero is not None:
            parts.append(
                f"the hero {hero['id']} is {_size(hero)[0]}x{_size(hero)[1]}, below the floor"
            )
        elif problem == HOTLINK:
            parts.append("the globe's thumbnail is no local file of the site")
        elif problem == NO_AUTHOR and hero is not None:
            parts.append(f"the hero {hero['id']}'s licence asks for an author and it has none")
    return "; ".join(parts)


def bounds_of(
    hero: Mapping[str, Any] | None, problems: Sequence[str]
) -> dict[str, Mapping[str, Any] | None]:
    """The size bounds a new hero of this site must keep (`size_and_credit`'s keywords): larger
    than a strip, not small beside any other hero it replaces."""
    if hero is None:
        return {"larger_than": None, "keeps_large": None}
    if STRIP in problems:
        return {"larger_than": hero, "keeps_large": None}
    return {"larger_than": None, "keeps_large": hero}


def decide(
    site: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    served: Mapping[int, Check],
    picks: Mapping[str, Check],
    vetoes: Mapping[int, str] | None = None,
) -> Decision | None:
    """One site's decision: None when it has no D48/D49 problem. `vetoes` are rows a reviewer
    refused as the site's hero (`image id -> reason`); a vetoed row is never chosen."""
    sid = str(site["id"])
    live = ST.live_rows(rows)
    heroes = [r for r in live if r.get("is_hero")]
    if len(heroes) > 1:
        raise HeroMovesError(f"{sid}: {len(heroes)} live hero rows - the one-hero invariant broke")
    hero = heroes[0] if heroes else None
    problems = problems_of(site, live, hero)
    if not problems:
        return None
    decision = Decision(sid, problems, hero=hero)
    vetoes = vetoes or {}
    hero_check = row_check(hero, served, picks) if hero is not None else None
    if hero_check is not None and hero_check.verdict == RC.OTHER_SITE:
        decision.deferred = hero_check
        return decision
    rule_hero, rule_align = (
        (RULE_D48_HERO, RULE_D48_ALIGN)
        if D48_PROBLEMS & set(problems)
        else (RULE_D49_HERO, RULE_D49_ALIGN)
    )
    why = _reason_text(problems, hero)
    # the hero itself can stay when the only problem is the globe's thumbnail and it qualifies
    if (
        problems == [HOTLINK]
        and hero is not None
        and int(hero["id"]) not in vetoes
        and qualifies(hero, hero_check) is None
    ):
        assert hero_check is not None
        decision.new, decision.check = hero, hero_check
        target = local_path(sid, str(hero["filename"]))
        evidence = [hero_check.evidence(int(hero["id"])), _read_evidence(site, hero, problems)]
        changes = _thumb(site, target, rule_align, f"{why}; it becomes the hero's file", evidence)
        decision.plan = SP.SitePlan(sid, ALIGNED, int(hero["id"]), target, changes)
        return decision
    bounds = bounds_of(hero, problems)
    shown = served_row(live)
    rejected: dict[int, str] = {}
    candidates: list[tuple[Mapping[str, Any], Check, str]] = []
    for row in live:
        if hero is not None and int(row["id"]) == int(hero["id"]):
            continue
        check = row_check(row, served, picks)
        reason = qualifies(row, check, **bounds)
        choice = None
        if reason is None:
            assert check is not None
            choice = chosen_by(row, check, hero=hero, shown=shown)
            if choice is None:
                reason = NOT_CHOSEN
        if reason is None and int(row["id"]) in vetoes:
            reason = f"vetoed: {vetoes[int(row['id'])]}"
        if reason is None:
            assert check is not None and choice is not None
            candidates.append((row, check, choice))
        else:
            rejected[int(row["id"])] = reason
    if not candidates:
        decision.owner_reason = _owner_reason(rejected)
        decision.rejected = rejected
        return decision
    new, check, choice = max(candidates, key=lambda c: _rank(*c))
    decision.new, decision.check, decision.choice = new, check, choice
    evidence = [
        check.evidence(int(new["id"])) | {"chosen_by": choice},
        _read_evidence(site, hero, problems),
    ]
    changes: list[CW.Change] = []
    if hero is not None:
        changes.append(
            CW.Change(
                "wiki_images",
                "is_hero",
                str(hero["id"]),
                sid,
                "true",
                "false",
                rule_hero,
                f"{why}; {new['id']} replaces it and {hero['id']} stays in the gallery",
                evidence,
            )
        )
    changes.append(
        CW.Change(
            "wiki_images",
            "is_hero",
            str(new["id"]),
            sid,
            "false",
            "true",
            rule_hero,
            f"{why}; {new['id']} is a checked picture of the site of "
            f"{_size(new)[0]}x{_size(new)[1]} with its full credit ({choice})",
            evidence,
        )
    )
    target = local_path(sid, str(new["filename"]))
    changes += _thumb(site, target, rule_align, "the globe shows the new hero too", evidence)
    outcome = FLAGGED if hero is None else MOVED
    decision.plan = SP.SitePlan(sid, outcome, int(new["id"]), target, changes)
    return decision


def _read_evidence(
    site: Mapping[str, Any], hero: Mapping[str, Any] | None, problems: Sequence[str]
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": "hero-moves READ.json",
        "problems": list(problems),
        "thumbnail_url": site.get("thumbnail_url"),
    }
    if hero is not None:
        out["hero"] = {
            "image_id": int(hero["id"]),
            "width": _size(hero)[0],
            "height": _size(hero)[1],
            "license": hero.get("license"),
            "author": hero.get("author"),
        }
    return out


def _thumb(
    site: Mapping[str, Any], new: str, rule: str, reason: str, evidence: list[dict[str, Any]]
) -> list[CW.Change]:
    """The globe's thumbnail onto `new`. The old value is the read's exactly - an empty string is
    not NULL, and the writer's guard compares the text it finds."""
    old = site.get("thumbnail_url")
    if old == new:
        return []
    sid = str(site["id"])
    return [CW.Change("unified_sites", "thumbnail_url", sid, sid, old, new, rule, reason, evidence)]


def _owner_reason(rejected: Mapping[int, str]) -> str:
    if not rejected:
        return "no other live row"
    counts: dict[str, int] = {}
    for reason in rejected.values():
        head = reason.split(" (")[0].split(":")[0]
        counts[head] = counts.get(head, 0) + 1
    return "no qualifying row: " + ", ".join(f"{n} {r}" for r, n in sorted(counts.items()))


def small_heroes(read: Read) -> list[dict[str, Any]]:
    """D48's small heroes: a live hero below 1600x900 at a site holding another live row of at least
    1600x900 (the census definition; 433 on 2026-10-24). Owner list only, nothing moves."""
    out = []
    for sid, site in read.sites.items():
        live = ST.live_rows(read.rows.get(sid, ()))
        for hero in (r for r in live if r.get("is_hero")):
            if not below(hero, LARGE):
                continue
            larger = [
                int(r["id"])
                for r in live
                if int(r["id"]) != int(hero["id"]) and not below(r, LARGE)
            ]
            if larger:
                out.append(
                    {
                        "site_id": sid,
                        "name": site["name"],
                        "hero_id": int(hero["id"]),
                        "hero_size": list(_size(hero)),
                        "larger_rows": larger,
                    }
                )
    return out


# ---------------------------------------------------------------------------------- the plan
def _resolved(paths: Iterable[Path]) -> list[str]:
    return [str(p.resolve()) for p in paths]


def load_vetoes(path: Path | None, read: Read) -> dict[str, dict[int, str]]:
    """`site id -> {image id: reason}` from a veto file (one JSON object per line: `site_id`,
    `image_id`, `reason`, `by`). A veto of a row the read does not hold at that site, or without
    a reason and a reviewer, is refused: a veto is a judgement and carries who made it."""
    if path is None:
        return {}
    out: dict[str, dict[int, str]] = {}
    for line in _jsonl(path):
        sid, image_id = str(line["site_id"]), int(line["image_id"])
        reason, by = str(line.get("reason") or "").strip(), str(line.get("by") or "").strip()
        if not reason or not by:
            raise HeroMovesError(f"the veto of image {image_id} names no reason or no reviewer")
        if not any(int(r["id"]) == image_id for r in read.rows.get(sid, ())):
            raise HeroMovesError(f"the veto names image {image_id}, which {sid} does not hold")
        out.setdefault(sid, {})[image_id] = f"{reason} ({by})"
    return out


def build(
    read: Read,
    served: Mapping[int, Check],
    picks: Mapping[str, Check],
    vetoes: Mapping[str, Mapping[int, str]] | None = None,
) -> list[Decision]:
    unknown = sorted(set(picks) - set(read.sites))
    if unknown:
        raise HeroMovesError(f"{len(unknown)} check-run pick(s) name sites the read does not show")
    vetoes = vetoes or {}
    decisions = []
    for sid in sorted(read.sites):
        decision = decide(read.sites[sid], read.rows.get(sid, ()), served, picks, vetoes.get(sid))
        if decision is not None:
            decisions.append(decision)
    return decisions


def _row_summary(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "image_id": int(row["id"]),
        "file": ST.file_of_row(row),
        "size": list(_size(row)),
        "license": row.get("license"),
        "author": row.get("author"),
    }


def review_lines(read: Read, decisions: Sequence[Decision]) -> list[dict[str, Any]]:
    """`PLANNED.jsonl`: per planned site the old hero, the new one, how it was chosen and what its
    check said - the page a reviewer reads before `emit` (see the module docstring)."""
    out = []
    for d in decisions:
        if d.plan is None or not d.plan.changes:
            continue
        assert d.check is not None and d.new is not None
        check = {
            k: v
            for k, v in {
                "source": d.check.source,
                "stage": d.check.stage,
                "verdict": d.check.verdict,
                "quality": d.check.quality,
                "shows": d.check.shows,
                "basis": d.check.basis,
                "label": d.check.label,
                "answer_basis": d.check.answer_basis,
                "answered_by": d.check.answered_by,
                "model": d.check.model,
            }.items()
            if v is not None
        }
        out.append(
            {
                "site_id": d.site_id,
                "name": read.sites[d.site_id]["name"],
                "outcome": d.plan.outcome,
                "problems": d.problems,
                "new_image_id": int(d.new["id"]),
                "chosen_by": d.choice,
                "old_hero": _row_summary(d.hero),
                "new_hero": _row_summary(d.new),
                "check": check,
            }
        )
    return out


def _site_plan_line(plan: SP.SitePlan) -> dict[str, Any]:
    return plan.expected() | {"changes": [asdict(c) for c in plan.changes]}


def _refuse_existing(paths: Iterable[Path], what: str) -> None:
    """Every write-once target is checked before the first write, so a refused step leaves no
    half of its files behind."""
    found = [p for p in paths if p.exists()]
    if found:
        raise HeroMovesError(f"{found[0]} exists - {what} is written once and never replaced")


def write_plan(
    run: Path,
    verdict_runs: Sequence[Path],
    check_runs: Sequence[Path],
    veto: Path | None = None,
) -> dict[str, Any]:
    """The review page, the site plans, the owner lists and the summary - no chunk (`emit` writes
    the chunks once a review accepted the sites)."""
    if not verdict_runs:
        raise HeroMovesError("name at least one served-image run with --verdicts-run")
    if (run / CHUNKS).exists() or any((run / name).exists() for name in PLAN_FILES):
        raise HeroMovesError(f"{run} holds a plan already - a delivered plan is never replaced")
    read = load_read(run)
    vetoes = load_vetoes(veto, read)
    decisions = build(read, served_checks(verdict_runs), check_picks(check_runs), vetoes)
    plans = [d.plan for d in decisions if d.plan is not None and d.plan.changes]
    changes = [c for p in plans for c in p.changes]
    if changes:
        CW.chunk_changes(lane_for(run), changes)  # the writer's own row checks, before any file
    owner = [
        {
            "site_id": d.site_id,
            "name": read.sites[d.site_id]["name"],
            "problems": d.problems,
            "reason": d.owner_reason,
            "rows": {str(k): v for k, v in sorted((d.rejected or {}).items())},
        }
        for d in decisions
        if d.owner_reason is not None
    ]
    deferred = [
        {"problems": d.problems, **asdict(d.deferred)} for d in decisions if d.deferred is not None
    ]
    small = small_heroes(read)
    planned_text = ST.jsonl_text(review_lines(read, decisions))
    sites_text = ST.jsonl_text(_site_plan_line(p) for p in plans)
    by_problem: dict[str, dict[str, int]] = {}
    for d in decisions:
        status = (
            "deferred_d15"
            if d.deferred
            else "owner_list"
            if d.owner_reason
            else d.plan.outcome
            if d.plan
            else "nothing"
        )
        for problem in d.problems:
            by_problem.setdefault(problem, {})
            by_problem[problem][status] = by_problem[problem].get(status, 0) + 1
    chosen: dict[str, int] = {}
    for d in decisions:
        if d.plan is not None and d.plan.changes and d.choice is not None:
            chosen[d.choice] = chosen.get(d.choice, 0) + 1
    summary = {
        "read_sha256": read.sha256,
        "read_at": read.read_at,
        "verdict_runs": _resolved(verdict_runs),
        "check_runs": _resolved(check_runs),
        "veto": None
        if veto is None
        else {"file": str(veto.resolve()), "sha256": ST.file_sha256(veto)},
        "sites_with_a_problem": len(decisions),
        "by_problem": by_problem,
        "chosen_by": chosen,
        "planned_sites": len(plans),
        "rows": len(changes),
        "planned_sha256": ST.sha256_text(planned_text),
        "plan_sites_sha256": ST.sha256_text(sites_text),
        "owner_list": len(owner),
        "deferred_d15": len(deferred),
        "small_heroes": len(small),
        "lane": asdict(lane_for(run)),
    }
    ST.write_text_once(run / PLANNED, planned_text)
    ST.write_text_once(run / PLAN_SITES, sites_text)
    ST.write_text_once(run / OWNER_LIST, ST.jsonl_text(owner))
    ST.write_text_once(run / DEFERRED, ST.jsonl_text(deferred))
    ST.write_text_once(run / SMALL_HEROES, ST.jsonl_text(small))
    ST.write_text_once(run / SUMMARY, ST.json_text(summary))
    return summary


def reviewers() -> frozenset[str]:
    """Who may accept or veto a planned move: the owner, or a Claude answer stamp (D6)."""
    return CJ.claude_stamps() | {OWNER}


def load_review(path: Path, planned: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """`site id -> its review line`, refused unless the file answers exactly every planned site,
    each for the planned new hero, with `accept` or `veto` by a reviewer (`reviewers`), a veto with
    its reason. A review is a judgement of the pictures, so a missing or a foreign line is never
    read as an accept."""
    wanted = {str(p["site_id"]): int(p["new_image_id"]) for p in planned}
    allowed = reviewers()
    out: dict[str, dict[str, Any]] = {}
    for line in _jsonl(path):
        sid = str(line.get("site_id") or "")
        if sid in out:
            raise HeroMovesError(f"the review answers {sid} twice")
        if sid not in wanted:
            raise HeroMovesError(f"the review answers {sid!r}, which the plan does not move")
        if int(line.get("new_image_id") or 0) != wanted[sid]:
            raise HeroMovesError(
                f"the review of {sid} names image {line.get('new_image_id')}, the plan makes "
                f"{wanted[sid]} the hero - a review speaks of the plan it was made for"
            )
        decision = line.get("decision")
        if decision not in (ACCEPT, VETO):
            raise HeroMovesError(f"the review of {sid} decides {decision!r}, not accept or veto")
        by = str(line.get("by") or "").strip()
        if by not in allowed:
            raise HeroMovesError(
                f"the review of {sid} is by {by!r}: a review is the owner's or a Claude answer "
                f"stamp's ({', '.join(sorted(allowed))})"
            )
        reason = str(line.get("reason") or "").strip()
        if decision == VETO and not reason:
            raise HeroMovesError(f"the veto of {sid} names no reason")
        out[sid] = {"decision": decision, "by": by, "reason": reason}
    missing = sorted(set(wanted) - set(out))
    if missing:
        raise HeroMovesError(
            f"the review leaves {len(missing)} planned site(s) unanswered (first {missing[0]})"
        )
    return out


def emit(run: Path, review: Path) -> dict[str, Any]:
    """The chunks of the sites a review accepted, `EXPECTED.jsonl`, and `VETOED.jsonl` (the
    vetoed new heroes, in the shape `--veto` reads, for the next plan in a new run directory).
    Refused when the plan changed after it was made or a review line is missing or wrong."""
    out = run / CHUNKS
    if out.exists() or (run / VETOED).exists():
        raise HeroMovesError(f"{run} holds emitted chunks already - they are never replaced")
    path = run / SUMMARY
    if not path.is_file():
        raise HeroMovesError(f"{path} does not exist - run `hero_moves.py plan` first")
    summary = json.loads(path.read_text(encoding="utf-8"))
    for name, key in ((PLANNED, "planned_sha256"), (PLAN_SITES, "plan_sites_sha256")):
        if ST.file_sha256(run / name) != summary[key]:
            raise HeroMovesError(f"{run / name} changed after the plan was made")
    planned = _jsonl(run / PLANNED)
    reviewed = load_review(review, planned)
    review_sha = ST.file_sha256(review)
    lane = lane_for(run)
    accepted, vetoed, changes = [], [], []
    by_site = {str(p["site_id"]): p for p in planned}
    for line in _jsonl(run / PLAN_SITES):
        sid = str(line["site_id"])
        verdict = reviewed[sid]
        if verdict["decision"] == VETO:
            vetoed.append(
                {
                    "site_id": sid,
                    "image_id": int(by_site[sid]["new_image_id"]),
                    "reason": verdict["reason"],
                    "by": verdict["by"],
                }
            )
            continue
        note = {
            "source": "hero-moves review",
            "review_sha256": review_sha,
            "decision": ACCEPT,
            "by": verdict["by"],
        } | ({"reason": verdict["reason"]} if verdict["reason"] else {})
        accepted.append(line)
        changes += [
            CW.Change(**(c | {"evidence": [*c["evidence"], note]})) for c in line["changes"]
        ]
    chunks = CW.chunk_changes(lane, changes) if changes else []
    chunk_of = {sid: chunk.number for chunk in chunks for sid in chunk.sites}
    expected = [
        {k: v for k, v in line.items() if k != "changes"} | {"chunk": chunk_of[line["site_id"]]}
        for line in accepted
    ]
    record = {
        "review": {"file": str(review.resolve()), "sha256": review_sha},
        "planned_sha256": summary["planned_sha256"],
        "accepted_sites": len(accepted),
        "vetoed_sites": len(vetoed),
        "rows": len(changes),
        "chunks": len(chunks),
        "lane": asdict(lane),
    }
    # the review's record first, the chunks last: a chunk on disk always has its review beside it
    ST.write_text_once(run / VETOED, ST.jsonl_text(vetoed))
    ST.write_text_once(out / EMIT_SUMMARY, ST.json_text(record))
    ST.write_text_once(out / EXPECTED, ST.jsonl_text(expected))
    CW.emit_chunks(out, chunks)
    return record


# --------------------------------------------------------------------- the check population
#: Why `check-pictures` offers a row to the image roles.
OFFER_UNJUDGED = "a live gallery row of the site no Claude check judged (D48/D49)"
OFFER_UNCHOSEN = (
    "a live gallery row a Claude check judged depicts and no judgement chose as the site's main "
    "picture (D48/D49)"
)


def offer_reason(
    row: Mapping[str, Any],
    check: Check | None,
    *,
    hero: Mapping[str, Any] | None,
    shown: Mapping[str, Any] | None,
) -> str | None:
    """Why the image roles should judge `row` for its site's hero, or None: a row nobody judged
    (or whose check judged another file than it holds now), or a `depicts` nobody chose. A row
    judged anything but `depicts` keeps that verdict and is not asked again; a chosen row needs no
    second choice."""
    if check is None or ST.file_of_row(row) != check.file:
        return OFFER_UNJUDGED
    if check.verdict != CJ.DEPICTS:
        return None
    if chosen_by(row, check, hero=hero, shown=shown) is not None:
        return None
    return OFFER_UNCHOSEN


def check_pictures(
    run: Path,
    check_run: Path,
    verdict_runs: Sequence[Path],
    path_of: Any,
) -> dict[str, Any]:
    """The image roles' population and pictures for the sites the plan cannot settle:
    `C/POPULATION.jsonl` and `C/PICTURES.jsonl` (the shape `image_roles/flow.py` reads after its
    `pictures` step), so `prefilter-export`, `depicts-export`, `recheck-export` and `write-targets`
    run on them unchanged and their confirmed pick - the depicts role's best quality, confirmed by
    the adversarial re-check - comes back through `plan --check-run`. Offered is a live row other
    than the hero that `offer_reason` names and that keeps the site's bounds (`size_and_credit`:
    the floor, the credit, larger than a strip, not small beside a large hero). `path_of(site_id,
    filename)` is the offsite copy of a row; a row without one is refused by name in
    `C/PICTURE_REFUSALS.jsonl`, never skipped."""
    from candidate_search import population as PP
    from image_roles import flow as FL

    targets = [
        check_run / name for name in (PP.POPULATION_FILE, FL.PICTURES, CHECK_REFUSALS, CHECK_SOURCE)
    ]
    _refuse_existing(targets, "a check run's population")
    read = load_read(run)
    served = served_checks(verdict_runs)
    population: list[dict[str, Any]] = []
    pictures: list[dict[str, Any]] = []
    refusals: list[dict[str, str]] = []
    offered: dict[str, int] = {}
    for sid in sorted(read.sites):
        decision = decide(read.sites[sid], read.rows.get(sid, ()), served, {})
        if decision is None or decision.owner_reason is None:
            continue
        site = read.sites[sid]
        live = ST.live_rows(read.rows.get(sid, ()))
        hero = decision.hero
        shown = served_row(live)
        bounds = bounds_of(hero, decision.problems)
        candidates = []
        for row in live:
            if hero is not None and int(row["id"]) == int(hero["id"]):
                continue
            why = offer_reason(row, row_check(row, served, {}), hero=hero, shown=shown)
            if why is None or size_and_credit(row, **bounds) is not None:
                continue
            file = ST.file_of_row(row)
            if file is None:
                refusals.append(
                    {"site_id": sid, "file": str(row["filename"]), "reason": "no Commons file"}
                )
                continue
            try:
                path = str(path_of(sid, str(row["filename"])))
            except ST.StateError as exc:
                refusals.append({"site_id": sid, "file": file, "reason": str(exc)})
                continue
            offered[why] = offered.get(why, 0) + 1
            candidates.append(
                {
                    "file": file,
                    "image_id": int(row["id"]),
                    "path": path,
                    "width": _size(row)[0],
                    "height": _size(row)[1],
                    "why": why,
                }
            )
        if not candidates:
            continue
        population.append(
            {
                "site_id": sid,
                "name": site["name"],
                "country": site.get("country"),
                "site_type": site.get("site_type"),
                "lat": site["lat"],
                "lon": site["lon"],
                "description": str(site.get("description") or "").strip() or None,
                "qid": site.get("qid"),
                "enwiki_title": site.get("enwiki_title"),
            }
        )
        pictures.append(
            {
                "site_id": sid,
                "name": site["name"],
                "country": site.get("country"),
                "candidates": candidates,
            }
        )
    if not population:
        raise HeroMovesError("no unsettled site has a row to offer - there is nothing to check")
    ST.write_text_once(check_run / PP.POPULATION_FILE, ST.jsonl_text(population))
    ST.write_text_once(check_run / FL.PICTURES, ST.jsonl_text(pictures))
    ST.write_text_once(check_run / CHECK_REFUSALS, ST.jsonl_text(refusals))
    ST.write_text_once(
        check_run / CHECK_SOURCE,
        ST.json_text(
            {
                "hero_moves_run": str(run.resolve()),
                "read_sha256": read.sha256,
                "verdict_runs": _resolved(verdict_runs),
            }
        ),
    )
    return {
        "sites": len(population),
        "pictures": sum(len(p["candidates"]) for p in pictures),
        "offered": {
            "unjudged": offered.get(OFFER_UNJUDGED, 0),
            "depicts_unchosen": offered.get(OFFER_UNCHOSEN, 0),
        },
        "refused": len(refusals),
    }


# ----------------------------------------------------------------------------- acceptance
def accept(run: Path, chunk: Path) -> dict[str, Any]:
    """Read-only: every site of `chunk` serves what the plan says (`served_image.plan.deviations`:
    the served row, the thumbnail, one hero that is not excluded). 0 deviations or exit 1."""
    delivered = CW.check_delivered(chunk)
    expected = _jsonl(run / CHUNKS / EXPECTED)
    mine = [e for e in expected if e["chunk"] == delivered.number]
    if {e["site_id"] for e in mine} != set(delivered.sites):
        raise HeroMovesError(f"{chunk}: EXPECTED.jsonl and the chunk name different sites")
    ids = ", ".join(f"'{e['site_id']}'::uuid" for e in mine)
    found = SP.deviations(
        mine,
        CW.pv.read_rows(SP.ACCEPT_SITES_SQL.replace("{ids}", ids)),
        CW.pv.read_rows(SP.ACCEPT_IMAGES_SQL.replace("{ids}", ids)),
    )
    return {"chunk": delivered.number, "sites": len(mine), "deviations": found}


# ----------------------------------------------------------------------------------- the CLI
def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        prog="served_image/hero_moves.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("read", "check-pictures", "plan", "emit", "accept"):
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True, type=Path)
    for name in ("check-pictures", "plan"):
        sub.choices[name].add_argument("--verdicts-run", required=True, type=Path, nargs="+")
    sub.choices["check-pictures"].add_argument("--check-run", required=True, type=Path)
    sub.choices["plan"].add_argument("--check-run", type=Path, nargs="*", default=[])
    sub.choices["plan"].add_argument("--veto", type=Path, default=None)
    sub.choices["emit"].add_argument("--review", required=True, type=Path)
    sub.choices["accept"].add_argument("--chunk", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    run = args.run_dir
    try:
        if args.command == "read":
            lane_for(run)
            digest = ST.write_text_once(run / READ_FILE, ST.json_text(read_production()))
            read = load_read(run)
            payload: Any = {
                "sha256": digest,
                "sites": len(read.sites),
                "images": sum(len(r) for r in read.rows.values()),
            }
        elif args.command == "check-pictures":
            from gallery_audit.vision import Images

            images = Images()
            payload = check_pictures(run, args.check_run, args.verdicts_run, images.path_for)
        elif args.command == "plan":
            payload = write_plan(run, args.verdicts_run, args.check_run, args.veto)
        elif args.command == "emit":
            payload = emit(run, args.review)
        else:
            payload = accept(run, args.chunk)
            print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
            return 0 if not payload["deviations"] else 1
    except ST.StateError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
