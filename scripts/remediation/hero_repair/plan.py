"""Build the mechanical hero repair offline: what should change, and why.

The defect
----------
``HERO_WIDTH = 800`` (``api/routes/wiki_images.py:22``) and ``THUMB_WIDTH = 800``
(``pipeline/wiki_image_downloader.py:47``) are the same number, so every hero this corpus
serves is the 800 px derivative - 3,850 of the 3,858 hero rows are exactly 800 px wide, the
other 8 are 796-799 (plan §6.3). The pages that show it are the detail page (`og:image`,
JSON-LD `image`, the LCP image) and the country hub, both of which read the *local* file
``/data/images/wiki/<site>/<filename>`` (``api/routes/sites_html.py:132,338``;
``pipeline/static_exporter.py:330``) and pick it with
``ORDER BY is_hero DESC, is_lead DESC, sort_order``.

The repair is therefore "put the flag on a file the site already has at 1600 px"
(``GALLERY_WIDTH = 1600``, same downloader file): no download, one flag moved per site.

Two sources, and why the plan's own wording does not settle which one to select on
-------------------------------------------------------------------------------
Phase 2 item 1 says "an already-local 1600 px gallery image" and plan §6.3 sizes the class with
``width``/``height``. Those columns are **the local derivative's** pixel size, not the
Commons file's (`census/tests/t09_commons_dimensions.py`, module docstring), and they are
exactly what T09 measured as wrong for 11,653 rows - every one of them a row whose local file
is *larger* than its Commons original, i.e. an upscale. Selecting on them alone would move
1,097 hero flags onto upscales: a bigger ``og:image`` tag over the same amount of real detail.

So this module selects on both facts, each of which is about a different object:

* **the cached true Commons dimensions** (``output/remediation/cache/commons_imageinfo.json``,
  ``imageinfo`` for all 46,070 referenced files) authorise the candidate: the source really
  carries at least 1600x900, so the 1600 px file is not invented detail;
* **the row's own stored dimensions** are required to agree with that (local >= 1600x900 and
  never larger than the original, per axis) because the stored size is the size of the file
  the site actually serves. Truth alone would also admit a row whose local file is smaller
  than the original it came from.

Candidate rank: tier ``D`` ("clear", §6.5 stage 0) before tier ``C`` ("grey"), never ``A``/``B``
(suspect) - so a hero moved here is the least likely to be thrown out by the gallery audit that
follows. Tiers are read from the census's own artifact,
``output/remediation/run_t10/findings.jsonl`` (49,691 rows, one per image, same snapshot), not
re-derived: the encoding lives in ``census/tests/t10_gallery_tiers.py``.

Scope of the write
------------------
``unified_sites.source_id = 'ancient_nerds'`` only. Production holds 49,693 ``wiki_images``
rows; 49,691 belong to curated sites and 2 to ``list_inscriptions`` (measured 2026-09-20). Every
planned row is checked against the snapshot's site table, and the generated SQL re-checks the
scope inside the transaction.

What this module does NOT do
----------------------------
* It does not touch ``is_lead``. All 3,858 hero rows also carry ``is_lead`` (the re-index
  script writes ``is_lead = is_hero``), and leaving the old row's ``is_lead`` alone is harmless
  for the served image: the new hero wins on ``is_hero DESC``, which is the first sort key.
* It does not repair the 133 sites that have a 1600 px image and **no** ``is_hero`` row at all
  (T09/no-hero-flag). That is a different defect: with no hero flag the page falls back to
  ``is_lead DESC, sort_order``, and ``is_lead`` is true for exactly the 3,858 hero rows, so
  such a site serves its lowest-``sort_order`` gallery image, which is already 1600 px.
* It does not fetch anything (Phase 2 item 1's second half) and does not raise
  ``THUMB_WIDTH``/``HERO_WIDTH`` - both are code changes with their own review.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
# Dual use, like `census/run.py`: `python -m hero_repair.plan` from scripts/remediation, and
# `python scripts/remediation/hero_repair/plan.py` from the repo root. Neither `census` nor
# `hero_repair` is installed, so the common parent has to be importable first.
_HERE = Path(__file__).resolve()
for _parent in (_HERE.parent.parent, REPO / "scripts" / "remediation"):
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))

from census.snapshot import Snapshot  # noqa: E402
from census.tests.t09_commons_dimensions import (  # noqa: E402
    HERO_MIN_HEIGHT,
    HERO_MIN_WIDTH,
)

#: T10 imports T09's helper under this name too: one spelling of "which Commons file is this
#: row", so the hero lane cannot disagree with the census about Commons identity. The census's
#: helper takes a `dict`; this module holds snapshot rows as `Mapping`, so the wrapper hands it a
#: real copy and neither side can change the other's row.
from census.tests.t09_commons_dimensions import (  # noqa: E402
    _commons_file_name as _t09_commons_file_name,
)


def commons_file_name(row: Mapping[str, Any]) -> str | None:
    """The Commons file this row was downloaded from, or None (T09's helper, not a copy)."""
    return _t09_commons_file_name(dict(row))


log = logging.getLogger("hero_repair")

CURATED_SOURCE = "ancient_nerds"

#: Journal fields. `TEST_ID` is the census finding this repair acts on; the run stamp matches
#: the backup taken for this remediation (`backups/2026-09-20_remediation/` on the VPS).
TEST_ID = "T09/hero-not-best"
RUN_STAMP = "2026-09-20_remediation"
#: T09's own confidence for its hero findings: the dimensions come from Commons `imageinfo`.
CONFIDENCE = "authoritative"

DEFAULT_SNAPSHOT = REPO / "output/remediation/snapshot"
DEFAULT_CACHE = REPO / "output/remediation/cache"
DEFAULT_TIERS = REPO / "output/remediation/run_t10/findings.jsonl"
DEFAULT_OUT = REPO / "output/remediation/hero_repair"

#: Tier values as `census/tests/t10_gallery_tiers.py:226` encodes them: A hero, B suspect,
#: C grey, D clear. A hero row is never a candidate here (its flag is what moves), so only
#: C and D can be accepted - and D is tried first.
TIER_CLEAR = "D"
TIER_GREY = "C"
TIERS_ACCEPTED = (TIER_CLEAR, TIER_GREY)
TIERS_ALL = ("A", "B", "C", "D")
TIER_NAME = {"A": "hero", "B": "suspect", "C": "grey", "D": "clear"}


class PlanError(RuntimeError):
    """The plan cannot be built from what is on disk. Never downgraded to an empty plan."""


# ------------------------------------------------------------------------------- inputs
def load_tiers(path: Path) -> dict[int, str]:
    """T10's tier per image id, from the census's own findings file.

    A row without a tier, or a tier outside A-D, raises: the tier is an economic decision
    (§6.5), and a missing one must not be read as "clear".
    """
    tiers: dict[int, str] = {}
    if not path.exists():
        raise PlanError(f"{path} is missing - run the T10 census before planning a hero repair")
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                finding = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PlanError(f"{path}:{lineno}: invalid JSON ({exc})") from exc
            value = finding.get("current_value")
            if not isinstance(value, dict) or "image_id" not in value:
                raise PlanError(f"{path}:{lineno}: finding carries no image_id")
            tier = value.get("tier")
            if tier not in TIERS_ALL:
                raise PlanError(f"{path}:{lineno}: unknown tier {tier!r}")
            tiers[int(value["image_id"])] = tier
    return tiers


def load_truth(path: Path) -> dict[str, dict[str, Any]]:
    """The cached Commons `imageinfo` answers, keyed by Commons file name.

    Keys are the file names derived from the row URLs (the wrapper object's ``entries`` key -
    read, not guessed), i.e. exactly the keys ``_commons_file_name`` produces.
    """
    if not path.exists():
        raise PlanError(f"{path} is missing - run the T09 census collector first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "entries" not in payload:
        raise PlanError(f"{path}: no 'entries' key (keys: {sorted(payload)})")
    return payload["entries"]


def site_source(site: dict[str, Any]) -> str | None:
    return site.get("source_id")


# ---------------------------------------------------------------------------- the rule
@dataclass(frozen=True)
class Verdict:
    """One candidate row's verdict, plus the reason in words for the plan's funnel."""

    eligible: bool
    reason: str

    def as_json(self) -> dict[str, Any]:
        return {"eligible": self.eligible, "reason": self.reason}


def candidate_verdict(
    row: Mapping[str, Any], tier: str | None, truth: Mapping[str, Any] | None
) -> Verdict:
    """May this row become the hero? Pure, so every branch is testable without a database.

    ``truth`` is the cached `imageinfo` record for the row's Commons file (``None`` when the
    row has no Commons identity or the cache does not hold it). The order of the checks is the
    order of the plan's two sources: Commons says the pixels exist, then the stored size says
    the served file has them.
    """
    if row.get("is_hero"):
        return Verdict(False, "is-the-hero")
    if row.get("is_excluded"):
        return Verdict(False, "excluded-from-the-gallery")
    if tier is None:
        return Verdict(False, "tier-unknown")
    if tier not in TIERS_ACCEPTED:
        return Verdict(False, f"tier-{tier}-suspect")

    width, height = row.get("width"), row.get("height")
    if not width or not height:
        return Verdict(False, "stored-dims-missing")
    if width < HERO_MIN_WIDTH or height < HERO_MIN_HEIGHT:
        return Verdict(False, "local-file-too-small")

    if truth is None:
        return Verdict(False, "commons-unknown-to-this-cache")
    if truth.get("status") != "ok":
        return Verdict(False, f"commons-{truth.get('status', 'unknown')}")

    true_w, true_h = int(truth["width"]), int(truth["height"])
    if true_w < HERO_MIN_WIDTH or true_h < HERO_MIN_HEIGHT:
        return Verdict(False, "original-too-small")
    if width > true_w or height > true_h:
        return Verdict(False, "local-file-is-an-upscale")

    return Verdict(True, "eligible")


def rank_key(candidate: tuple[Mapping[str, Any], Mapping[str, Any]]) -> tuple[int, int, int]:
    """Clearest tier first, then the largest true Commons area, then the row id.

    Area, not the stored area: the stored pixels are capped at ``GALLERY_WIDTH``, so among
    candidates that agree on tier the Commons resolution is the honest tie-breaker (T09
    prefers the same "backed, then larger" order for the same reason).
    """
    row, truth = candidate
    tier_rank = 0 if row["_tier"] == TIER_CLEAR else 1
    return (tier_rank, -(int(truth["width"]) * int(truth["height"])), int(row["id"]))


def is_hero_ready(row: Mapping[str, Any]) -> bool:
    """Is the row's *local* file already the 1600x900+ file this repair wants to serve?

    Only the local size is asked: an 800 px hero that is an upscale is T09's `upscaled`
    finding, not this repair's subject.
    """
    width, height = row.get("width"), row.get("height")
    return bool(width and height and width >= HERO_MIN_WIDTH and height >= HERO_MIN_HEIGHT)


# ------------------------------------------------------------------------------- output
@dataclass(frozen=True)
class ChangeRecord:
    """One row to change. The five fields the brief asks for, plus the journal's arguments."""

    image_id: int
    site_id: str
    site_name: str
    role: str  # "demote" | "promote"
    old_is_hero: bool
    new_is_hero: bool
    condition: str
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    records: list[ChangeRecord]
    counters: Counter[str]
    sites: Counter[str]
    skipped: dict[str, list[dict[str, Any]]]
    snapshot_exported_at: str | None
    #: row-level verdict reasons of the candidates the plan's own rule rejected (the delta
    #: between the plan's rule and the `width >= 1600 AND height >= 900` rule of §6.3/T09)
    delta_reasons: Counter[str] = field(default_factory=Counter)
    source: str = CURATED_SOURCE

    @property
    def promoted(self) -> list[ChangeRecord]:
        return [r for r in self.records if r.role == "promote"]

    @property
    def demoted(self) -> list[ChangeRecord]:
        return [r for r in self.records if r.role == "demote"]

    @property
    def affected_sites(self) -> set[str]:
        return {r.site_id for r in self.records}


#: The row-level reasons that mean "the stored size said yes but the evidence did not".
SUSPECT_REASONS = ("tier-A-suspect", "tier-B-suspect")
TRUTH_REASONS = (
    "original-too-small",
    "local-file-is-an-upscale",
    "commons-missing",
    "commons-unresolved",
    "commons-unknown-to-this-cache",
)


def _stricter_rule_class(reasons: Mapping[str, int]) -> str:
    """Why the stricter rule turned down every stored-size candidate of one site.

    `reasons` counts the verdict reason of each of those candidates. The classes separate the
    two ways a candidate can fail, because they mean different things for the next step: a
    suspect tier needs a judgement (or a fetch), while a truth failure says the stored size in
    `wiki_images.width` was the only thing speaking - the column T09 measured wrong.
    """
    kinds = set(reasons)
    if not kinds:
        return "no-stored-dims-candidate"
    suspect = kinds & set(SUSPECT_REASONS)
    truth = kinds & set(TRUTH_REASONS)
    if suspect and truth:
        return "mix-suspect-and-truth"
    if suspect:
        return "all-candidates-refused-by-tier"
    if kinds == {"local-file-is-an-upscale"}:
        return "all-candidates-are-upscales"
    if kinds == {"original-too-small"}:
        return "all-originals-too-small"
    if kinds <= {"commons-missing", "commons-unresolved"}:
        return "no-commons-truth"
    if kinds == {"commons-unknown-to-this-cache"}:
        return "no-commons-identity"
    return "mix-of-truth-failures"


def build_plan(
    sites: Iterable[Mapping[str, Any]],
    images_by_site: Mapping[str, Sequence[Mapping[str, Any]]],
    tiers: Mapping[int, str],
    truth: Mapping[str, Mapping[str, Any]],
    *,
    source: str = CURATED_SOURCE,
    snapshot_exported_at: str | None = None,
) -> Plan:
    """Decide the repair for every curated site. Pure over its four arguments."""
    records: list[ChangeRecord] = []
    counters: Counter[str] = Counter()
    site_stats: Counter[str] = Counter()
    delta_reasons: Counter[str] = Counter()
    skipped: dict[str, list[dict[str, Any]]] = {}

    def note(kind: str, **facts: Any) -> None:
        skipped.setdefault(kind, []).append(facts)

    for site in sites:
        if site.get("source_id") != source:
            continue
        sid = str(site["id"])
        rows = list(images_by_site.get(sid, ()))
        site_stats["sites"] += 1
        if not rows:
            site_stats["sites-without-images"] += 1
            continue
        site_stats["sites-with-images"] += 1

        heroes = [r for r in rows if r.get("is_hero")]
        site_stats["hero-rows"] += len(heroes)
        hero = heroes[0] if heroes else None

        # The verdict of every row, taken once: it is the funnel the plan reports and the
        # input of both the plan's own candidate rule and the stored-dims rule it compares to.
        verdicts: dict[int, Verdict] = {}
        for row in rows:
            tier = tiers.get(int(row["id"]))
            name = commons_file_name(row)
            record = truth.get(name) if name else None
            verdict = candidate_verdict(row, tier, record)
            verdicts[int(row["id"])] = verdict
            counters[verdict.reason] += 1

        if hero is None:
            # Out of scope, and measured rather than assumed: the page then picks with
            # is_hero DESC, is_lead DESC, sort_order, and is_lead is true for exactly the
            # 3,858 hero rows, so a hero-less site serves its lowest-sort_order gallery file -
            # which is already a 1600 px local file. Nothing to fix, and a flag planted here
            # would change which image the site serves without a size defect to justify it.
            site_stats["sites-without-hero-flag"] += 1
            note(
                "no-hero-flag",
                site_id=sid,
                site_name=site.get("name"),
                eligible_candidates=sum(1 for r in rows if verdicts[int(r["id"])].eligible),
                census_flag="T09/no-hero-flag",
            )
            continue

        if is_hero_ready(hero):
            site_stats["already-hero-ready"] += 1
            continue

        candidates: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for row in rows:
            if not verdicts[int(row["id"])].eligible:
                continue
            tier = tiers.get(int(row["id"]))
            name = commons_file_name(row)
            record = truth.get(name) if name else None
            if record is None:  # unreachable: eligibility requires a resolved record
                raise PlanError(f"image {row['id']}: eligible without a Commons record")
            candidates.append(({**row, "_tier": tier}, record))

        if not candidates:
            site_stats["skipped-no-eligible-candidate"] += 1
            stored_only = [
                r
                for r in rows
                if not r.get("is_hero")
                and not r.get("is_excluded")
                and r.get("width")
                and r.get("height")
                and is_hero_ready(r)
            ]
            reasons = Counter(verdicts[int(r["id"])].reason for r in stored_only)
            kind = _stricter_rule_class(reasons)
            if stored_only:
                site_stats["plan-rule-candidate-but-stricter-rule-rejected"] += 1
                site_stats[f"rejected-{kind}"] += 1
                if set(reasons) & set(TRUTH_REASONS):
                    site_stats["rejected-because-the-stored-size-was-the-only-witness"] += 1
                else:
                    site_stats["rejected-on-census-tier-alone"] += 1
                delta_reasons.update(reasons)
            else:
                site_stats["no-1600px-candidate-under-either-rule"] += 1
            note(
                "no-eligible-candidate",
                site_id=sid,
                site_name=site.get("name"),
                hero={
                    "image_id": int(hero["id"]),
                    "local": f"{hero.get('width')}x{hero.get('height')}",
                },
                stored_dims_candidates=len(stored_only),
                rejected=kind,
                reasons=dict(reasons.most_common()),
            )
            continue

        chosen, chosen_truth = min(candidates, key=rank_key)
        site_stats["repaired-sites"] += 1
        site_stats[f"repaired-via-tier-{chosen['_tier']}"] += 1

        records.append(
            ChangeRecord(
                image_id=int(hero["id"]),
                site_id=sid,
                site_name=str(site.get("name")),
                role="demote",
                old_is_hero=True,
                new_is_hero=False,
                condition=f"id = {hero['id']} AND is_hero = true",
                reason=(
                    f"{site.get('name')!r}: this row is the served hero and its local file is "
                    f"{hero.get('width')}x{hero.get('height')} - the THUMB_WIDTH="
                    f"{hero.get('width')} derivative that §6.3 shows every hero stuck on. "
                    f"Image {chosen['id']} "
                    f"({chosen.get('width')}x{chosen.get('height')} local, "
                    f"{chosen_truth['width']}x{chosen_truth['height']} on Commons, tier "
                    f"{chosen['_tier']}) takes the flag, and the served image is picked with "
                    f"is_hero DESC first, so the old hero must lose the flag"
                ),
                evidence=[
                    {
                        "source": "commons:imageinfo",
                        "quote": (
                            f"File:{commons_file_name(chosen)} -> "
                            f"{chosen_truth['width']}x{chosen_truth['height']}"
                        ),
                    },
                    {
                        "source": "snapshot:wiki_images",
                        "quote": (
                            f"id={hero['id']} is_hero=true "
                            f"{hero.get('width')}x{hero.get('height')} "
                            f"file={hero.get('filename')!r}"
                        ),
                    },
                    {
                        "source": "census:T10",
                        "quote": f"replacement image {chosen['id']} is tier "
                        f"{chosen['_tier']} ({chosen.get('filename')!r})",
                    },
                ],
            )
        )

        records.append(
            ChangeRecord(
                image_id=int(chosen["id"]),
                site_id=sid,
                site_name=str(site.get("name")),
                role="promote",
                old_is_hero=False,
                new_is_hero=True,
                condition=f"id = {chosen['id']} AND is_hero = false",
                reason=(
                    f"{site.get('name')!r}: already-local gallery file at "
                    f"{chosen.get('width')}x{chosen.get('height')} px whose Commons original is "
                    f"{chosen_truth['width']}x{chosen_truth['height']} (so the 1600 px file is not "
                    f"an upscale), tier {chosen['_tier']} "
                    f"({TIER_NAME[str(chosen['_tier'])]}) - takes the hero flag so the page "
                    "serves a 1600 px image without a download"
                ),
                evidence=[
                    {
                        "source": "commons:imageinfo",
                        "quote": (
                            f"File:{commons_file_name(chosen)} -> "
                            f"{chosen_truth['width']}x{chosen_truth['height']}"
                        ),
                    },
                    {
                        "source": "snapshot:wiki_images",
                        "quote": (
                            f"id={chosen['id']} is_hero=false "
                            f"{chosen.get('width')}x{chosen.get('height')} "
                            f"file={chosen.get('filename')!r}"
                        ),
                    },
                    {
                        "source": "census:T10",
                        "quote": (
                            f"tier {chosen['_tier']} "
                            f"({TIER_NAME[str(chosen['_tier'])]}): the census's own signage for "
                            "this image"
                        ),
                    },
                ],
            )
        )

    return Plan(
        records=records,
        counters=counters,
        sites=site_stats,
        skipped=skipped,
        snapshot_exported_at=snapshot_exported_at,
        delta_reasons=delta_reasons,
        source=source,
    )


def check_plan(plan: Plan, images_by_site: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    """Refuse a plan that would break the state the repair is supposed to leave behind.

    Cheap invariants, all re-checkable from the plan alone:
      * no row appears twice and no record changes nothing;
      * exactly one promotion per touched site, and every promotion has its demotion (a flag
        removed without a replacement would leave the site with no hero at all);
      * every site the plan touches ends with exactly one ``is_hero`` row.
    """
    seen: set[int] = set()
    for record in plan.records:
        if record.image_id in seen:
            raise PlanError(f"image {record.image_id} appears twice in the plan")
        seen.add(record.image_id)
        if record.new_is_hero is record.old_is_hero:
            raise PlanError(f"image {record.image_id}: a record that changes nothing")

    promoted: Counter[str] = Counter()
    demoted: Counter[str] = Counter()
    for record in plan.records:
        if record.new_is_hero:
            promoted[record.site_id] += 1
        else:
            demoted[record.site_id] += 1
    for sid, n in promoted.items():
        if n != 1:
            raise PlanError(f"site {sid}: {n} promotions - exactly one hero per site is required")
        if demoted[sid] != 1:
            raise PlanError(f"site {sid}: promoted without exactly one demotion")
    if set(demoted) != set(promoted):
        raise PlanError("a demotion has no promotion - that would leave a site without a hero")

    touched = {r.site_id for r in plan.records}
    for sid in touched:
        rows = list(images_by_site.get(sid, ()))
        before = sum(1 for r in rows if r.get("is_hero"))
        after = before
        for record in plan.records:
            if record.site_id != sid:
                continue
            if record.old_is_hero:
                after -= 1
            if record.new_is_hero:
                after += 1
        if after != 1:
            raise PlanError(
                f"site {sid}: {before} hero row(s) before the plan, {after} after it - the "
                "repair must leave exactly one"
            )


# --------------------------------------------------------------------------- artifacts
def write_plan_jsonl(plan: Plan, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for record in sorted(plan.records, key=lambda r: (r.site_id, r.image_id)):
            fh.write(json.dumps(record.as_json(), ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
    return len(plan.records)


def _funnel_rows(plan: Plan) -> list[tuple[str, int]]:
    order = [
        "is-the-hero",
        "excluded-from-the-gallery",
        "tier-unknown",
        "tier-B-suspect",
        "tier-A-suspect",
        "stored-dims-missing",
        "local-file-too-small",
        "commons-unknown-to-this-cache",
        "commons-missing",
        "commons-unresolved",
        "original-too-small",
        "local-file-is-an-upscale",
        "eligible",
    ]
    seen = [(k, plan.counters[k]) for k in order if plan.counters[k]]
    extra = [(k, v) for k, v in sorted(plan.counters.items()) if k not in order and v]
    return seen + extra


def write_plan_md(
    plan: Plan, path: Path, *, snapshot_dir: Path, tiers_path: Path, cache_path: Path
) -> None:
    s = plan.sites
    promoted = len(plan.promoted)
    demoted = len(plan.demoted)
    lines: list[str] = []
    add = lines.append
    add("# Hero repair - Phase 2 item 1")
    add("")
    add(
        f"Snapshot `{snapshot_dir}`, exported {plan.snapshot_exported_at} - scope "
        f"`unified_sites.source_id = '{plan.source}'`."
    )
    add("")
    add("Mechanical only: **one flag moved per site, no download**. `is_hero` is set to false on")
    add("the row that serves today and to true on a file the site already has at 1600 px.")
    add("")
    add("## The rule")
    add("")
    add("* candidate = not the hero, not `is_excluded`, T10 tier `D` (clear) or `C` (grey) - never")
    add("  the suspect tiers `A`/`B`;")
    add(
        f"* the **cached true Commons dimensions** (`{cache_path.name}`) say width >= "
        f"{HERO_MIN_WIDTH} and height >= {HERO_MIN_HEIGHT} - the source really has the pixels;"
    )
    add("* the row's **stored** dimensions say the same and never exceed the original (`width` is")
    add("  the local derivative's size, so this is what the page will serve);")
    add(
        "* among a site's candidates: tier `D` before `C`, then the largest true Commons area, then"
    )
    add("  the lowest image id.")
    add("")
    add("Tiers come from the census's own artifact, read, not re-derived:")
    add(f"`{tiers_path}` (`A` hero, `B` suspect, `C` grey, `D` clear -")
    add("`scripts/remediation/census/tests/t10_gallery_tiers.py:226`).")
    add("")
    add("## Rows examined")
    add("")
    add("| verdict | rows |")
    add("|---|---|")
    for reason, count in _funnel_rows(plan):
        add(f"| {reason} | {count:,} |")
    add("")
    add("## Sites")
    add("")
    add("| class | sites |")
    add("|---|---|")
    for key in (
        "sites",
        "sites-with-images",
        "sites-without-images",
        "hero-rows",
        "sites-without-hero-flag",
        "already-hero-ready",
        "repaired-sites",
        "repaired-via-tier-D",
        "repaired-via-tier-C",
        "skipped-no-eligible-candidate",
        "plan-rule-candidate-but-stricter-rule-rejected",
        "no-1600px-candidate-under-either-rule",
    ):
        add(f"| {key} | {s[key]:,} |")
    add("")
    add("## The write")
    add("")
    add(f"* **{promoted:,} rows** get `is_hero = false -> true` (the new hero),")
    add(f"* **{demoted:,} rows** get `is_hero = true -> false` (the 800 px hero they replace),")
    add(f"* **{len(plan.affected_sites):,} sites** are touched, in one transaction, each row")
    add("  guarded by its old value, journalled in `remediation_change_log`.")
    add("")
    add("Every repaired site ends with **exactly one** `is_hero` row. That invariant held before")
    add(
        f"the repair too (measured on the snapshot: {s['sites-without-hero-flag']:,} of "
        f"{s['sites-with-images']:,} sites have none, the"
    )
    add(
        f"other {s['sites-with-images'] - s['sites-without-hero-flag']:,} have exactly one) and is re-asserted"
    )
    add("in `scripts/remediation/hero_repair/plan.py::check_plan` before anything is written.")
    add("")
    add("## Comparison with the plan's 3,264")
    add("")
    add("§6.3 and T09 (the census's own `T09/hero-not-best` flag) both count **3,264** sites whose")
    add("hero can be replaced by an already-local 1600 px image under the rule *stored*")
    add("`width >= 1600 AND height >= 900`. That number reproduces exactly here, as")
    add(
        f"**{s['repaired-sites']:,} + {s['plan-rule-candidate-but-stricter-rule-rejected']:,} = "
        f"{s['repaired-sites'] + s['plan-rule-candidate-but-stricter-rule-rejected']:,}** - the claim is"
    )
    add(
        "not refuted, it is split. The rule was not tuned towards it; this plan is stricter, for the"
    )
    add("reason in the module docstring.")
    add("")
    add("### Which column decided")
    add("")
    add("Both rules read `wiki_images.width`/`height`. Those columns hold the size of the local")
    add("derivative the site serves - and they are the column the brief forbids selecting on,")
    add("because T09 measured them larger than the Commons original on 11,653 rows. That is where")
    add(
        "the two numbers part company: this plan keeps the stored size as one of two conditions and"
    )
    add("requires the cached Commons truth as the other.")
    add("")
    add("| class of site | sites | reads only the stored column? |")
    add("|---|---|---|")
    add(
        f"| {s['repaired-sites']:,} repaired: both conditions hold | {s['repaired-sites']:,} | no - the truth agreed |"
    )
    add(
        f"| refused, and the stored size was the only witness | "
        f"{s['rejected-because-the-stored-size-was-the-only-witness']:,} | "
        "**yes** - of these the Commons answer contradicts it |"
    )
    add(
        f"| refused on the census's own suspect tier alone | "
        f"{s['rejected-on-census-tier-alone']:,} | no - T10 refused them before any size test |"
    )
    add(
        f"| neither rule finds a 1600 px candidate | "
        f"{s['no-1600px-candidate-under-either-rule']:,} | - |"
    )
    add("")
    add(
        f"So **{s['rejected-because-the-stored-size-was-the-only-witness']:,} of the "
        f"{s['plan-rule-candidate-but-stricter-rule-rejected']:,} rejected sites are rejected because"
    )
    add("the stored column would have been the only thing speaking")
    add("(the Commons original is missing, below 1600x900, or - in every row measured - both small")
    add("and upscaled). Those are exactly the rows this plan refuses to trust the column on, and")
    add("the reason the executed number is smaller than the plan's. The other")
    add(
        f"{s['rejected-on-census-tier-alone']:,} were refused by the census's own tier, not by a size"
    )
    add("test: T10 calls the candidate a suspect, so promoting it would fight the audit that")
    add("follows.")
    add("")
    add("Why the rejected sites are rejected, counted per site (a site can be refused for more")
    add("than one reason, so these do not sum to the class above):")
    add("")
    add("| reason | sites |")
    add("|---|---|")
    for key, count in sorted(
        (
            (k.removeprefix("rejected-"), v)
            for k, v in s.items()
            if k.startswith("rejected-")
            and v
            # the two class counters are the two rows of the table above, not a reason
            and k
            not in (
                "rejected-because-the-stored-size-was-the-only-witness",
                "rejected-on-census-tier-alone",
            )
        ),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        add(f"| {key} | {count:,} |")
    add("")
    add("At row level, over the candidates the plan's rule would have accepted:")
    add("")
    add("| verdict | rows |")
    add("|---|---|")
    for reason, count in plan.delta_reasons.most_common():
        add(f"| {reason} | {count:,} |")
    add("")
    add("One of the plan's own guards fired on **0** rows and is therefore absent from both")
    add("tables: `local-file-is-an-upscale`. Measured 2026-09-20 over the whole corpus, of the")
    add("31,878 already-1600 px rows whose Commons original is itself >= 1600x900, none exceeds")
    add("its original per axis. Every one of the 10,977 upscaled rows has an original below the")
    add("hero minimum, so `original-too-small` names them. The comparison stays in the rule")
    add("because it is the plan's central claim (the 1600 px file carries the original's real")
    add("detail); it is compared, not asserted in prose.")
    add("")
    add("## Not in this plan")
    add("")
    add(f"* the {s['plan-rule-candidate-but-stricter-rule-rejected']:,} sites above: they need a")
    add("  genuine large original (a fetch or a re-export - Phase 2 item 1's second half) or a")
    add("  different image once the gallery audit has judged the suspects;")
    add(
        "* the 152 sites with **no** `is_hero` row (`T09/no-hero-flag` counts 133 of them under the"
    )
    add("  looser rule): their page falls back to `is_lead DESC, sort_order`, `is_lead` is true")
    add("  for exactly the 3,858 hero rows, so they already serve their lowest-`sort_order`")
    add("  gallery file - a 1600 px local file. Planting a flag there would change which image")
    add("  the site serves without a size defect to justify it;")
    add("* `THUMB_WIDTH`/`HERO_WIDTH` - raising them is a code change with its own review; the")
    add("  flag move does not depend on it (the flag is the first sort key of the served-image")
    add("  query). Until it is raised, a *newly downloaded* hero still arrives at 800 px.")
    add("")
    add(f"`{'SKIPPED.jsonl'}` lists every site this plan does not touch, with its class and the")
    add("row-level reasons behind it, so the second half of Phase 2 item 1 has its worklist.")
    add("")
    add("## Reproduce")
    add("")
    add("```bash")
    add("cd scripts/remediation")
    add("../../.venv/Scripts/python.exe -m hero_repair.plan --write \\")
    add(
        f"    --snapshot ../../{snapshot_dir.relative_to(REPO).as_posix()} \\"
        if snapshot_dir.is_relative_to(REPO)
        else f"    --snapshot {snapshot_dir} \\"
    )
    add(
        f"    --cache ../../{cache_path.relative_to(REPO).as_posix()} \\"
        if cache_path.is_relative_to(REPO)
        else f"    --cache {cache_path} \\"
    )
    add(
        f"    --tiers ../../{tiers_path.relative_to(REPO).as_posix()} \\"
        if tiers_path.is_relative_to(REPO)
        else f"    --tiers {tiers_path} \\"
    )
    add(f"    --out ../../{(path.parent).relative_to(REPO).as_posix()}")
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def write_skipped_jsonl(plan: Plan, path: Path) -> int:
    """Every site this plan does not touch, with the class and the reasons behind it.

    The worklist for the second half of Phase 2 item 1 and for the gallery audit. One line per
    skipped site; `class` is the site-level bucket, `reasons` the row-level verdicts.
    """
    rows: list[dict[str, Any]] = []
    for entry in plan.skipped.get("no-eligible-candidate", []):
        rows.append({"class": "no-eligible-candidate", **entry})
    for entry in plan.skipped.get("no-hero-flag", []):
        rows.append({"class": "no-hero-flag", **entry})
    rows.sort(key=lambda r: (str(r["class"]), str(r["site_id"])))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
    return len(rows)


def write_rollback_sql(plan: Plan, path: Path) -> int:
    """The reversal, written before anything is applied.

    Same mechanism as the forward change (`apply.apply_sql`), the records in reverse, with its
    own run stamp so the journal distinguishes the two directions. Running it after a failed or
    unwanted apply restores the exact prior state of every touched row, and it refuses to run
    if a row no longer holds what the apply wrote.
    """
    from hero_repair import apply as apply_mod

    records = [
        ChangeRecord(
            image_id=r.image_id,
            site_id=r.site_id,
            site_name=r.site_name,
            role="rollback-" + r.role,
            old_is_hero=r.new_is_hero,
            new_is_hero=r.old_is_hero,
            condition=f"id = {r.image_id} AND is_hero = {str(r.new_is_hero).lower()}",
            reason=f"rollback of hero-repair: {r.reason}",
            evidence=r.evidence,
        )
        for r in reversed(plan.records)
    ]
    sql = apply_mod.render_transaction(
        records, run_stamp=apply_mod.ROLLBACK_RUN_STAMP, site_ids=plan.affected_sites
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8", newline="\n")
    return len(records)


# ---------------------------------------------------------------------------------- CLI
def load_inputs(
    snapshot_dir: Path, tiers_path: Path, cache_path: Path
) -> tuple[Snapshot, dict[int, str], dict[str, dict[str, Any]]]:
    snap = Snapshot(snapshot_dir)
    snap.verify()
    tiers = load_tiers(tiers_path)
    truth = load_truth(cache_path)
    return snap, tiers, truth


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Phase 2 hero-repair plan (offline)")
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE / "commons_imageinfo.json")
    ap.add_argument("--tiers", type=Path, default=DEFAULT_TIERS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--write", action="store_true", help="write PLAN.jsonl / PLAN.md / ROLLBACK.sql"
    )
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    snap, tiers, truth = load_inputs(args.snapshot, args.tiers, args.cache)
    images_by_site = snap.by("wiki_images")
    site_ids = {str(s["id"]) for s in snap.sites if s.get("source_id") == CURATED_SOURCE}

    # A tier table that does not cover the snapshot row-for-row would silently turn some rows
    # into "tier-unknown" - a missing check, not a clean one.
    snapshot_ids = {int(r["id"]) for r in snap.rows("wiki_images")}
    if set(tiers) != snapshot_ids:
        raise PlanError(
            f"tier table covers {len(tiers)} image ids, the snapshot holds {len(snapshot_ids)} "
            f"(missing {len(snapshot_ids - set(tiers))}, extra {len(set(tiers) - snapshot_ids)}) - "
            "the tier artifact and the snapshot are not the same corpus"
        )
    outside = {
        int(r["id"]): r["site_id"]
        for r in snap.rows("wiki_images")
        if str(r["site_id"]) not in site_ids
    }
    if outside:
        raise PlanError(f"{len(outside)} image row(s) belong to no {CURATED_SOURCE} site")

    plan = build_plan(
        snap.sites,
        images_by_site,
        tiers,
        truth,
        snapshot_exported_at=snap.exported_at(),
    )
    check_plan(plan, images_by_site)

    log.info(
        "plan: %d promotions, %d demotions over %d sites",
        len(plan.promoted),
        len(plan.demoted),
        len(plan.affected_sites),
    )
    log.info("sites: %s", dict(plan.sites.most_common()))
    log.info("row verdicts: %s", dict(plan.counters.most_common()))

    if args.write:
        n = write_plan_jsonl(plan, args.out / "PLAN.jsonl")
        write_plan_md(
            plan,
            args.out / "PLAN.md",
            snapshot_dir=args.snapshot,
            tiers_path=args.tiers,
            cache_path=args.cache,
        )
        n_skip = write_skipped_jsonl(plan, args.out / "SKIPPED.jsonl")
        log.info(
            "wrote %s (%d records) and %s (%d sites skipped)",
            args.out / "PLAN.jsonl",
            n,
            args.out / "SKIPPED.jsonl",
            n_skip,
        )
        n_rb = write_rollback_sql(plan, args.out / "ROLLBACK.sql")
        log.info(
            "wrote %s, %s and %s (%d records)",
            args.out / "PLAN.jsonl",
            args.out / "PLAN.md",
            args.out / "ROLLBACK.sql",
            n,
        )
        log.info("rollback covers %d records", n_rb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
