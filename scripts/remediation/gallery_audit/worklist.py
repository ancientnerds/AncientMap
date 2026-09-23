"""S6/S8 - the current state of every curated gallery, its tiers, and the jobs of each G stage.

Why the census tiers cannot be used as they are
-----------------------------------------------
T10 tiered the 2026-09-20 snapshot, and the hero repair moved 2,719 hero flags four hours later
(5,438 journal rows, `hero_repair/APPLIED.md`). Tier A *is* "the hero", so every moved flag changed
two tiers: the promoted row (T10 said C or D) is now the served hero, and the demoted row (T10 said
A) now has whatever tier its own signals give it. This module therefore re-tiers the current
state, with T10's own functions (`signals_for`, `tier_for`, the place dictionary, the cross-site
shares) over T10's own signal index - and then proves the re-tiering faithful: every row whose
hero flag did not move must get exactly the tier T10 recorded (`hero_repair.plan.load_tiers`), every
promoted row must have been C or D, every demoted row A. One disagreement stops the module.

The current state is the snapshot plus the hero moves (`hero_repair/PLAN.jsonl`, whose old values
are checked against the snapshot row by row). The journal holds no other `wiki_images` change
except `image_kind` on 105 rows (design, item 5), and no tier reads `image_kind`.

The stages (design S8), all in export order, chunked by 100 sites
-----------------------------------------------------------------
``G3``             the served image of every site (``ORDER BY is_hero DESC, is_lead DESC,
                   sort_order`` over the non-excluded rows - `api/routes/sites_html.py:134-135`)
``G3-strict``      the hero question on every served image the first pass called ``site_photo``
``G2``             every non-excluded tier-B row
``G4``             ``G4_PROBES`` non-excluded tier-C rows per site, chosen by sha256(seed:id)
``G4-escalation``  the whole non-excluded gallery (tier D included) of a site a probe hit
``H-reselect``     the ranked hero candidates of a site whose served image fails

A job is one question about one image (`vision.Job`); the ledger never asks a question twice.

Usage:
    worklist.py tiers --hero-moves PLAN.jsonl [--snapshot DIR] [--cache DIR] [--t10 FINDINGS]
    worklist.py jobs --stage G3|G2|G4 --hero-moves PLAN.jsonl --out JOBS.jsonl [--chunk N]
    worklist.py jobs --stage G3-strict|G4-escalation --ledger VERDICTS.jsonl ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION = ROOT / "scripts" / "remediation"
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

from census.run import Context  # noqa: E402
from census.snapshot import Snapshot  # noqa: E402
from census.tests import t10_gallery_tiers as T10  # noqa: E402
from hero_repair.plan import commons_file_name, load_tiers  # noqa: E402

from gallery_audit import vision  # noqa: E402
from pipeline.video.shorts_select import image_title  # noqa: E402

DEFAULT_SNAPSHOT = ROOT / "output" / "remediation" / "snapshot"
DEFAULT_CACHE = ROOT / "output" / "remediation" / "cache"
DEFAULT_T10 = ROOT / "output" / "remediation" / "run_t10" / "findings.jsonl"
DEFAULT_HERO_MOVES = ROOT / "output" / "remediation" / "hero_repair" / "PLAN.jsonl"
CURATED_SOURCE = "ancient_nerds"

CHUNK_SITES = 100
G4_PROBES = 3
#: The seed the design fixes for everything drawn in this lane's runs (final acceptance: 20260923).
G4_SEED = 20260923

G3, G3_STRICT, G2, G4, G4_ESCALATION, H_RESELECT = (
    "G3",
    "G3-strict",
    "G2",
    "G4",
    "G4-escalation",
    "H-reselect",
)
STAGES = (G3, G3_STRICT, G2, G4, G4_ESCALATION, H_RESELECT)

HERO, SUSPECT, GREY, CLEAR = T10.HERO, T10.SUSPECT, T10.GREY, T10.CLEAR


class WorklistError(RuntimeError):
    """The current state cannot be established without guessing."""


# ------------------------------------------------------------------------------ hero moves
def load_hero_moves(path: Path) -> dict[int, tuple[bool, bool]]:
    """`image_id -> (old is_hero, new is_hero)` from the hero repair's PLAN.jsonl."""
    if not path.is_file():
        raise WorklistError(
            f"{path} is missing - the current hero flags are the snapshot plus this plan"
        )
    moves: dict[int, tuple[bool, bool]] = {}
    for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not text.strip():
            continue
        record = json.loads(text)
        image_id, old, new = (
            record.get("image_id"),
            record.get("old_is_hero"),
            record.get("new_is_hero"),
        )
        if not isinstance(image_id, int) or not isinstance(old, bool) or not isinstance(new, bool):
            raise WorklistError(f"{path}:{lineno}: not a hero move ({sorted(record)})")
        if old == new:
            raise WorklistError(f"{path}:{lineno}: image {image_id} moves nothing")
        if image_id in moves:
            raise WorklistError(f"{path}:{lineno}: image {image_id} is moved twice")
        moves[image_id] = (old, new)
    if not moves:
        raise WorklistError(f"{path} holds no hero move")
    return moves


# ------------------------------------------------------------------------------ the state
@dataclass
class State:
    """The curated sites in export order and their current rows, each with its current tier."""

    sites: list[dict[str, Any]]
    by_site: dict[str, list[dict[str, Any]]]
    exported_at: str | None
    report: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._sites = {str(site["id"]): site for site in self.sites}
        self._rows = {int(row["id"]): row for rows in self.by_site.values() for row in rows}

    def site(self, site_id: str) -> dict[str, Any]:
        return self._sites[site_id]

    def row(self, image_id: int) -> dict[str, Any]:
        return self._rows[image_id]

    def site_ids(self) -> list[str]:
        return [str(site["id"]) for site in self.sites]

    def live_rows(self, site_id: str) -> list[dict[str, Any]]:
        return [row for row in self.by_site.get(site_id, []) if not row.get("is_excluded")]


def served_row(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The image a site's page shows: `ORDER BY is_hero DESC, is_lead DESC, sort_order` over the
    rows that are not excluded (`api/routes/sites_html.py:134-135`). Postgres sorts a NULL
    `sort_order` last; the row id breaks a tie the database would leave to chance."""
    live = [row for row in rows if not row.get("is_excluded")]
    if not live:
        return None
    return min(
        live,
        key=lambda r: (
            not r.get("is_hero"),
            not r.get("is_lead"),
            r.get("sort_order") is None,
            r.get("sort_order") or 0,
            int(r["id"]),
        ),
    )


def retier(
    sites: Sequence[Mapping[str, Any]],
    rows_by_site: Mapping[str, Sequence[Mapping[str, Any]]],
    moves: Mapping[int, tuple[bool, bool]],
    census_tiers: Mapping[int, str],
    tier_of: Callable[[Mapping[str, Any], str], tuple[str, str]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """The current rows with `_tier`/`_tier_reason`, and the proof the re-tiering is T10's own.

    `tier_of(row, site_id)` is T10's non-hero tier of a row (`tier_for(signals_for(...))`). A row
    whose flag did not move must get the census tier back; a promoted row must have been C or D
    (the hero repair accepted nothing else); a demoted row must have been A.
    """
    unknown = set(moves) - {int(r["id"]) for rows in rows_by_site.values() for r in rows}
    if unknown:
        raise WorklistError(
            f"{len(unknown)} hero move(s) name rows the snapshot does not hold: {sorted(unknown)[:3]}"
        )
    out: dict[str, list[dict[str, Any]]] = {}
    report: Counter[str] = Counter()
    demoted_to: Counter[str] = Counter()
    for site in sites:
        sid = str(site["id"])
        current: list[dict[str, Any]] = []
        for row in rows_by_site.get(sid, ()):
            image_id = int(row["id"])
            copy = dict(row)
            census = census_tiers.get(image_id)
            if census is None:
                raise WorklistError(f"image {image_id} has no census tier")
            if image_id in moves:
                old, new = moves[image_id]
                if bool(row.get("is_hero")) != old:
                    raise WorklistError(
                        f"image {image_id}: the hero move expects is_hero={old}, the snapshot says "
                        f"{row.get('is_hero')} - the plan does not belong to this snapshot"
                    )
                copy["is_hero"] = new
            tier, reason = (HERO, "hero") if copy.get("is_hero") else tier_of(row, sid)
            if image_id not in moves:
                if tier != census:
                    raise WorklistError(
                        f"image {image_id}: re-tiered {tier}, the census recorded {census} for an "
                        "unchanged row - the re-tiering is not T10's"
                    )
            elif copy["is_hero"]:
                if census not in (GREY, CLEAR):
                    raise WorklistError(
                        f"image {image_id}: promoted to hero from census tier {census}"
                    )
                report["promoted"] += 1
            else:
                if census != HERO:
                    raise WorklistError(
                        f"image {image_id}: demoted from census tier {census}, not A"
                    )
                report["demoted"] += 1
                demoted_to[tier] += 1
            copy["_tier"], copy["_tier_reason"] = tier, reason
            current.append(copy)
        out[sid] = current
    return out, {
        "promoted": report["promoted"],
        "demoted": report["demoted"],
        "demoted_retiered": dict(sorted(demoted_to.items())),
    }


def build_state(snapshot_dir: Path, cache_dir: Path, hero_moves: Path, t10_findings: Path) -> State:
    """The snapshot, the hero moves and T10's index, folded into the current tiered state."""
    snap = Snapshot(snapshot_dir)
    snap.verify()
    sites = [site for site in snap.sites if site.get("source_id") == CURATED_SOURCE]
    ctx = Context(snap=snap, cache=Path(cache_dir), out=Path(cache_dir), sites=sites)
    index = T10._read_index(ctx)
    context = T10.build_site_context(sites)
    T10.distinctive_place_tokens(context, snap.rows("wiki_images"))
    shares = T10.cross_site_shares(ctx, context)

    def tier_of(row: Mapping[str, Any], site_id: str) -> tuple[str, str]:
        return T10.tier_for(T10.signals_for(dict(row), site_id, context, index, shares))

    rows_by_site = {str(site["id"]): snap.images(str(site["id"])) for site in sites}
    by_site, report = retier(
        sites, rows_by_site, load_hero_moves(hero_moves), load_tiers(t10_findings), tier_of
    )
    for rows in by_site.values():
        for row in rows:
            name = commons_file_name(row)
            record = index.files.get(name) if name else None
            row["_commons"] = name
            row["_categories"] = (
                list(record.get("raw_categories") or [])
                if record and record.get("status") == "ok"
                else None
            )
    return State(sites=sites, by_site=by_site, exported_at=snap.exported_at(), report=report)


def tier_counts(state: State) -> dict[str, Any]:
    """The numbers the design quotes, measured on the current state (design, item 7)."""
    live: Counter[str] = Counter()
    grey_sites = 0
    served = 0
    for sid in state.site_ids():
        rows = state.live_rows(sid)
        live.update(row["_tier"] for row in rows)
        grey_sites += any(row["_tier"] == GREY for row in rows)
        served += served_row(state.by_site.get(sid, [])) is not None
    return {
        "snapshot_exported_at": state.exported_at,
        "sites": len(state.sites),
        "sites_serving_an_image": served,
        "live_rows_by_tier": dict(sorted(live.items())),
        "sites_with_live_grey_rows": grey_sites,
        **state.report,
    }


# ------------------------------------------------------------------------------ jobs
def job_for(state: State, row: Mapping[str, Any], pass_: str, stage: str) -> vision.Job:
    """The job for one row. The title is the Commons file name read the way the shorts selector
    reads one (`shorts_select.image_title`); a row without a Commons identity (all 649 are already
    excluded, the gold rows include one) is titled by its stored `title`, and says so."""
    site = state.site(str(row["site_id"]))
    name = row["_commons"]
    # The extension is cut as text: `Path(name).stem` parses per OS, and on Windows a Commons name
    # such as "A: detail.jpg" would read as a drive.
    title = image_title(
        {"title": name.rsplit(".", 1)[0] if name else row.get("title"), "filename": row["filename"]}
    )
    return vision.Job(
        image_id=int(row["id"]),
        site_id=str(row["site_id"]),
        filename=str(row["filename"]),
        pass_=pass_,
        stage=stage,
        site_name=str(site.get("name") or ""),
        country=str(site.get("country") or ""),
        site_type=str(site.get("site_type") or ""),
        title=title,
        title_source="commons" if name else "wiki_images.title",
        categories=None if row["_categories"] is None else tuple(row["_categories"]),
        tier=row["_tier"],
    )


def chunks(state: State, size: int = CHUNK_SITES) -> list[list[str]]:
    ids = state.site_ids()
    return [ids[start : start + size] for start in range(0, len(ids), size)]


def _in(site_ids: Iterable[str] | None, state: State) -> list[str]:
    return state.site_ids() if site_ids is None else list(site_ids)


def g3_jobs(state: State, site_ids: Iterable[str] | None = None) -> list[vision.Job]:
    out = []
    for sid in _in(site_ids, state):
        row = served_row(state.by_site.get(sid, []))
        if row is not None:
            out.append(job_for(state, row, vision.GALLERY, G3))
    return out


def g2_jobs(state: State, site_ids: Iterable[str] | None = None) -> list[vision.Job]:
    return [
        job_for(state, row, vision.GALLERY, G2)
        for sid in _in(site_ids, state)
        for row in state.live_rows(sid)
        if row["_tier"] == SUSPECT
    ]


def probe_rank(seed: int, image_id: int) -> str:
    return hashlib.sha256(f"{seed}:{image_id}".encode()).hexdigest()


def g4_jobs(
    state: State,
    site_ids: Iterable[str] | None = None,
    *,
    seed: int = G4_SEED,
    probes: int = G4_PROBES,
) -> list[vision.Job]:
    out = []
    for sid in _in(site_ids, state):
        grey = sorted(
            (row for row in state.live_rows(sid) if row["_tier"] == GREY),
            key=lambda r: probe_rank(seed, int(r["id"])),
        )
        out.extend(job_for(state, row, vision.GALLERY, G4) for row in grey[:probes])
    return out


def escalation_jobs(state: State, hit_sites: Iterable[str]) -> list[vision.Job]:
    """The whole live gallery of every site a probe hit - tier D included (Xcaret's eco-park
    pictures sit in D because the P373 anchor names the park)."""
    return [
        job_for(state, row, vision.GALLERY, G4_ESCALATION)
        for sid in hit_sites
        for row in state.live_rows(sid)
    ]


def strict_jobs(
    state: State, gallery: Mapping[int, Mapping[str, Any]], image_ids: Iterable[int], stage: str
) -> list[vision.Job]:
    """The hero question for every listed image whose first-pass kind is `site_photo`."""
    return [
        job_for(state, state.row(image_id), vision.HERO, stage)
        for image_id in image_ids
        if image_id in gallery and gallery[image_id]["kind"] == "site_photo"
    ]


# ------------------------------------------------------------------------------ CLI
def _write(path: Path, jobs: Sequence[vision.Job]) -> None:
    digest = vision.write_jobs(path, jobs)
    print(f"{len(jobs)} jobs -> {path} (sha256 {digest})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("tiers", "jobs"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
        cmd.add_argument("--cache", default=str(DEFAULT_CACHE))
        cmd.add_argument("--t10", default=str(DEFAULT_T10))
        cmd.add_argument("--hero-moves", default=str(DEFAULT_HERO_MOVES))
        cmd.add_argument("--out", default=None)
        if name == "jobs":
            cmd.add_argument(
                "--stage", required=True, choices=(G3, G3_STRICT, G2, G4, G4_ESCALATION)
            )
            cmd.add_argument("--chunk", type=int, default=None, help="0-based chunk of 100 sites")
            cmd.add_argument(
                "--ledger", default=None, help="VERDICTS.jsonl (strict and escalation)"
            )
            cmd.add_argument(
                "--hit-sites", default=None, help="a JSON list of site ids (escalation)"
            )
    args = parser.parse_args(argv)
    state = build_state(
        Path(args.snapshot), Path(args.cache), Path(args.hero_moves), Path(args.t10)
    )
    if args.command == "tiers":
        report = tier_counts(state)
        text = json.dumps(report, indent=1, sort_keys=True)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    site_ids = None if args.chunk is None else chunks(state)[args.chunk]
    if args.out is None:
        raise SystemExit("--out is required for jobs")
    if args.stage == G3:
        jobs = g3_jobs(state, site_ids)
    elif args.stage == G2:
        jobs = g2_jobs(state, site_ids)
    elif args.stage == G4:
        jobs = g4_jobs(state, site_ids)
    elif args.stage == G3_STRICT:
        if not args.ledger:
            raise SystemExit("--ledger is required for G3-strict")
        gallery = vision.verdicts_by_image(
            vision.Ledger(Path(args.ledger)).lines, vision.GALLERY_PROMPT_ID
        )
        served = [
            int(row["id"])
            for sid in _in(site_ids, state)
            if (row := served_row(state.by_site.get(sid, [])))
        ]
        jobs = strict_jobs(state, {k: v.verdict for k, v in gallery.items()}, served, G3_STRICT)
    else:
        if not args.hit_sites:
            raise SystemExit("--hit-sites is required for G4-escalation")
        jobs = escalation_jobs(state, json.loads(Path(args.hit_sites).read_text(encoding="utf-8")))
    _write(Path(args.out), jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
