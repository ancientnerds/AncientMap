"""The steps of the picture research, one function each, between files of one candidate run directory.

A candidate run directory `C` (`output/remediation/candidate_search/candidates-<date>/`) holds the
state of one pass; every step reads files of `C`, writes files of `C` (each once) and returns a summary.
The command line (`run.py`) is a thin shell around these functions, so the whole chain can be tested
without a network and without a model:

    population      POPULATION.jsonl                  the sites that serve no picture (production, read-only)
    identity        IDENTITY_*.jsonl, POPULATION_2    verify and research the links; the merged population
    search          CANDIDATES.jsonl                  every route's candidates
    pictures        PICTURES.jsonl                    the renderings on disk, with their paths
    prefilter       PREFILTER.jsonl                   Haiku: kind and usable, at 640 px
    depicts         DEPICTS.jsonl, VERDICTS.jsonl     Sonnet: verdict and quality, at 1280 px
    recheck         RECHECK_NN.jsonl                  Opus: the best pick of every site, round by round
    targets         TARGETS.jsonl                     the confirmed picks the INSERT lane fetches
    prune           PICTURES_SHA256.jsonl             the pictures deleted, their hashes kept

`PICTURES.jsonl` is also what `pool` writes for the MiniMax-judged pool, so the same steps re-judge
it from the pictures already on disk.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from candidate_search import judge as CJ  # noqa: E402
from candidate_search import pool as PL  # noqa: E402
from candidate_search import population as PP  # noqa: E402
from candidate_search import search as CS  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import depicts as DP  # noqa: E402
from image_roles import hero_recheck as HR  # noqa: E402
from image_roles import identity as ID  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402
from image_roles import targets as TG  # noqa: E402
from image_roles.wiki_cache import WikiCache  # noqa: E402

POPULATION_2 = "POPULATION_2.jsonl"
PICTURES = "PICTURES.jsonl"
PICTURE_REFUSALS = "PICTURE_REFUSALS.jsonl"
VERDICTS = CJ.VERDICTS
PICTURES_SHA = "PICTURES_SHA256.jsonl"
JUDGED_FILE = "JUDGED_NOT_DEPICTS.jsonl"
#: Verdicts of models that were never ground truth (D10, X6): their rows do not exclude a file.
MINIMAX_WORD = "minimax"


class FlowError(ST.StateError):
    """A step cannot run from what the run directory holds. Never guessed."""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FlowError(f"{path} does not exist - run the step before it")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _population(run: Path) -> list[dict[str, Any]]:
    """The merged population when the identity stage ran, else the first one."""
    merged = run / POPULATION_2
    return _jsonl(merged if merged.is_file() else run / PP.POPULATION_FILE)


# ---------------------------------------------------------------------------------- population
def write_population(run: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sites = PP.build(rows)
    digest = PP.write_population(run / PP.POPULATION_FILE, sites)
    return PP.counts(sites) | {"sha256": digest}


# ------------------------------------------------------------------------------------ identity
def identity_export(
    run: Path,
    handoff: Path,
    mode: str,
    *,
    entities: Any,
    cache: WikiCache | None,
    found_nothing: Sequence[str] = (),
) -> dict[str, Any]:
    """The identity questions of one mode. `verify` asks about the flagged sites (the item's point
    far from the site's, or a label with no word of the name); `research` about the sites with no
    identity and the `found_nothing` ones (sites a first search found no file for)."""
    sites = _jsonl(run / PP.POPULATION_FILE)
    if mode == "verify":
        missing = entities.missing([s["qid"] for s in sites if s.get("qid")])
        if missing:
            raise FlowError(
                f"{len(missing)} item(s) are in neither the harvest nor its delta (first "
                f"{missing[0]}): `run.py fetch-entities` first"
            )
        asked = ID.verify_population(sites, entities)
        spec = ID.VERIFY_SPEC
    elif mode == "research":
        asked = [dict(s) for s in ID.research_population(sites, found_nothing)]
        spec = ID.RESEARCH_SPEC
    else:
        raise FlowError(f"mode {mode!r} is not 'verify' or 'research'")
    if not asked:
        raise FlowError(f"no site to {mode}")
    questions = ID.build_questions(asked, mode=mode, cache=cache)
    summary = SG.export(run, handoff, spec, questions, {})
    return summary | {"sites": len(asked)}


def identity_apply(run: Path, results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`POPULATION_2.jsonl`: the population with every identity answer applied."""
    sites = _jsonl(run / PP.POPULATION_FILE)
    answers = ID.identity_rows(results)
    unknown = sorted(set(answers) - {s["site_id"] for s in sites})
    if unknown:
        raise FlowError(
            f"{len(unknown)} answer(s) are for sites outside the population (first {unknown[0]})"
        )
    merged = ID.merge_identity(sites, answers)
    digest = ST.write_text_once(run / POPULATION_2, ST.jsonl_text(merged))
    return {
        "sites": len(merged),
        "answered": len(answers),
        "changed": sum(1 for s in merged if s.get("identity_changed")),
        "with_commons_category": sum(1 for s in merged if s.get("commons_category")),
        "with_local_names": sum(1 for s in merged if s.get("local_names")),
        "sha256": digest,
    }


# --------------------------------------------------------------------------------------- search
def judged_not_depicts(paths: Sequence[Path]) -> dict[str, list[str]]:
    """`{site id: files}` that a Claude pass judged not to depict the site, from `VERDICTS.jsonl`
    files. A MiniMax verdict never excludes a file (D10: the pool is re-judged, not trusted)."""
    out: dict[str, list[str]] = {}
    for path in paths:
        for row in _jsonl(path):
            model = str(row.get("model") or "")
            if row.get("verdict") != CJ.DEPICTS and MINIMAX_WORD not in model.lower():
                out.setdefault(str(row["site_id"]), []).append(str(row["file"]))
    return out


def search(
    run: Path,
    commons: Any,
    *,
    entities: Any | None,
    floor: tuple[int, int],
    workers: int = 1,
    judged: Mapping[str, Sequence[str]] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Every route's candidates for the population (the merged one when the identity stage ran)."""
    sites = _population(run)
    if limit is not None:
        sites = sites[:limit]
    judged = judged or {}
    prepared = [{**s, "judged_not_depicts": judged.get(str(s["site_id"]), [])} for s in sites]
    return CS.run(run, prepared, commons, floor=floor, entities=entities, workers=workers)


def pictures(run: Path, client: Any) -> dict[str, Any]:
    """Every candidate's rendering on disk (`<run>/pictures/`), and `PICTURES.jsonl`: the sites with
    their fetched candidates, each with its `path`. A candidate that could not be fetched is named
    in `PICTURE_REFUSALS.jsonl`."""
    sites = _jsonl(run / CS.CANDIDATES)
    fetched, refusals = CJ.download_all(run, sites, client)
    ST.write_text_once(run / PICTURES, ST.jsonl_text(fetched))
    ST.write_text_once(run / PICTURE_REFUSALS, ST.jsonl_text(refusals))
    return {
        "sites": len(fetched),
        "pictures": sum(len(s["candidates"]) for s in fetched),
        "refused": len(refusals),
    }


def _read_picture(candidate: Mapping[str, Any]) -> bytes:
    from pipeline.video.shorts_select import vlm_bytes

    return vlm_bytes(Path(str(candidate["path"])))


def prefilter_export(
    run: Path,
    handoff: Path,
    *,
    read: Callable[[Mapping[str, Any]], bytes] = _read_picture,
    limit: int | None = None,
) -> dict[str, Any]:
    """The prefilter's questions over every fetched candidate (sixty to a question)."""
    flat = [
        {"site_id": s["site_id"], "file": c["file"], "path": c["path"]}
        for s in _jsonl(run / PICTURES)
        for c in s["candidates"]
    ]
    if limit is not None:
        flat = flat[:limit]
    questions, pics = PF.build_questions(flat, read)
    return SG.export(run, handoff, PF.SPEC, questions, pics)


def depicts_export(
    run: Path,
    handoff: Path,
    *,
    cache: WikiCache | None,
    read: Callable[[Mapping[str, Any]], bytes] = _read_picture,
) -> dict[str, Any]:
    """The depicts role's questions over the prefilter's survivors, packed by site."""
    surviving = {
        (r["site_id"], r["file"]) for r in PF.judged(SG.read_results(run, PF.SPEC)) if r["survives"]
    }
    population = {s["site_id"]: s for s in _population(run)}
    sites = []
    for fetched in _jsonl(run / PICTURES):
        kept = [c for c in fetched["candidates"] if (fetched["site_id"], c["file"]) in surviving]
        if not kept:
            continue
        info = population.get(fetched["site_id"]) or {}
        sites.append(
            {
                "site_id": fetched["site_id"],
                "name": fetched["name"],
                "country": fetched.get("country") or info.get("country"),
                "site_type": info.get("site_type"),
                "lat": info.get("lat"),
                "lon": info.get("lon"),
                "description": info.get("description"),
                "wikipedia_lead": None if cache is None else cache.lead(str(fetched["site_id"])),
                "candidates": kept,
            }
        )
    for site in sites:
        if site["lat"] is None:
            raise FlowError(f"{site['site_id']}: no site record in the population")
    questions, pics, left_out = DP.build_questions(sites, read)
    summary = SG.export(run, handoff, DP.SPEC, questions, pics)
    ST.write_text_once(run / "DEPICTS_LEFT_OUT.jsonl", ST.jsonl_text(left_out))
    return summary | {"sites": len(sites), "left_out": len(left_out)}


def depicts_import(run: Path, handoff: Path) -> dict[str, Any]:
    """Import the depicts answers and write `VERDICTS.jsonl` in the shape `judge.py` reads."""
    summary = SG.import_answers(run, handoff, DP.SPEC)
    sizes = {
        (str(s["site_id"]), str(c["file"])): (int(c["width"]), int(c["height"]))
        for s in _jsonl(run / PICTURES)
        for c in s["candidates"]
    }
    rows = DP.verdict_rows(SG.read_results(run, DP.SPEC), sizes)
    ST.write_text_once(run / VERDICTS, ST.jsonl_text(rows))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return summary | {
        "verdicts": counts,
        "sites_with_depicts": len({r["site_id"] for r in rows if r["verdict"] == CJ.DEPICTS}),
    }


def recheck_results(run: Path) -> list[dict[str, Any]]:
    """Every re-check answer of every round so far, in round order."""
    out: list[dict[str, Any]] = []
    for path in sorted(run.glob("RECHECK_[0-9][0-9].jsonl")):
        out.extend(_jsonl(path))
    return out


def next_round(run: Path) -> int:
    """The number of the next re-check round: one more than the rounds already imported."""
    return len(list(run.glob("RECHECK_[0-9][0-9].jsonl"))) + 1


def _cache_file(cache: WikiCache | None, site_id: str) -> str | None:
    """Where the site's cached Wikipedia page is, as the agent is told to read it."""
    path = None if cache is None else cache.file_of(site_id)
    return None if path is None else path.as_posix()


def _picks_for(
    run: Path, rows: Sequence[Mapping[str, Any]], cache: WikiCache | None
) -> list[dict[str, Any]]:
    """The re-check's picks: each depicts row joined with its site and its picture."""
    population = {s["site_id"]: s for s in _population(run)}
    paths = {(s["site_id"], c["file"]): c for s in _jsonl(run / PICTURES) for c in s["candidates"]}
    picks = []
    for row in rows:
        key = (str(row["site_id"]), str(row["file"]))
        site, candidate = population.get(key[0]), paths.get(key)
        if site is None or candidate is None:
            raise FlowError(f"{key[0]}: {key[1]!r} has no site record or no picture on disk")
        picks.append(
            {
                **site,
                "file": key[1],
                "path": candidate["path"],
                "picture_url": candidate.get("picture_url"),
                "note": row["note"],
                "answered_by": row["answered_by"],
                "wikipedia_title": site.get("enwiki_title"),
                "wikipedia_cache_file": _cache_file(cache, key[0]),
            }
        )
    return picks


def recheck_export(
    run: Path,
    handoff: Path,
    *,
    cache: WikiCache | None = None,
    picks: Sequence[Mapping[str, Any]] | None = None,
    read: Callable[[Mapping[str, Any]], bytes] = _read_picture,
) -> dict[str, Any]:
    """The next round of the hero re-check: the best-ranked `depicts` of every site that has no
    confirmed pick yet. With `picks` (the pool's old targets) those are asked instead."""
    round_number = next_round(run)
    if picks is None:
        state = TG.pick_round(_jsonl(run / VERDICTS), recheck_results(run))
        if not state.to_check:
            raise FlowError("no site waits for a re-check: write the targets")
        picks = _picks_for(run, state.to_check, cache)
    questions, pics = HR.build_questions(list(picks), read, round_number=round_number)
    summary = SG.export(run, handoff, HR.spec_for_round(round_number), questions, pics)
    return summary | {"round": round_number, "picks": len(picks)}


def write_targets(run: Path) -> dict[str, Any]:
    return TG.write_targets(run, _jsonl(run / VERDICTS), recheck_results(run))


def prune_pictures(run: Path) -> dict[str, Any]:
    """Delete the fetched pictures once the targets are written, keeping only their hashes.

    Refused while `TARGETS.jsonl` does not exist: a picture a re-check round may still need is not
    deleted. `PICTURES_SHA256.jsonl` records every picture's sha256 and size first, so a verdict can
    always be tied to the bytes it judged."""
    if not (run / CJ.TARGETS).is_file():
        raise FlowError("the targets are not written yet: the re-check may still need the pictures")
    folder = run / CJ.PICTURES
    if not folder.is_dir():
        raise FlowError(f"{folder} does not exist - nothing to prune")
    rows = []
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        data = path.read_bytes()
        rows.append(
            {"name": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        )
    ST.write_text_once(run / PICTURES_SHA, ST.jsonl_text(rows))
    shutil.rmtree(folder)
    return {"pictures": len(rows), "bytes": sum(r["bytes"] for r in rows)}


# ------------------------------------------------------------------------- the MiniMax pool (C4)
def pool(run: Path, old_run: Path) -> dict[str, Any]:
    """`PICTURES.jsonl` of the MiniMax-judged pool: the old run's candidates of the sites in this
    run's population, with the pictures already on disk. The prefilter, the depicts role and the
    re-check then run on it exactly as on a fresh search."""
    ids = {s["site_id"] for s in _population(run)}
    sites, missing = PL.pool_sites(old_run, ids)
    ST.write_text_once(run / PICTURES, ST.jsonl_text(sites))
    ST.write_text_once(run / PICTURE_REFUSALS, ST.jsonl_text(missing))
    return {
        "sites": len(sites),
        "pictures": sum(len(s["candidates"]) for s in sites),
        "pictures_gone": len(missing),
    }


def pool_picks(run: Path, old_run: Path) -> list[dict[str, Any]]:
    """The old run's targets that are in this run's population, as picks for `recheck_export`."""
    ids = {s["site_id"] for s in _population(run)}
    return PL.target_picks(old_run, _population(run), ids)


def denied(run: Path, old_run: Path, state: ST.State) -> list[dict[str, Any]]:
    """The live heroes MiniMax's `depicts` put on a page and this Claude run does not confirm, in the
    shape `served_image.recheck` reads."""
    rejected = HR.rejected(recheck_results(run))
    pairs = PL.denied_pairs(
        _jsonl(old_run / CJ.VERDICTS),
        PF.judged(SG.read_results(run, PF.SPEC)),
        _jsonl(run / VERDICTS),
        rejected,
    )
    return PL.denied_heroes(state, pairs)
