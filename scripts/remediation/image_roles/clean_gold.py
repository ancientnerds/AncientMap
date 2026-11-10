"""D117 (owner, 2026-11-06): a clean, checked gold for the image roles, measured one more time.

image-roles-v2 measured the image roles against the gold of image-roles-v1, whose truth came from
the 652 labels of 2026-09-19 and the C1 kinds; about 40 of those entries were wrong (quinoa plants,
a beach, village churches as "the site"; the Woodhenge post markers and the Senegambian circles as
foreign places; museum pieces of the site itself as foreign - the rule conflict D116 settled). A
correction of that sealed gold would have been no measurement, so the owner chose a new one:

* **fresh cases**, none of which any earlier calibration asked, drawn with a sealed seed in strata
  that hold the traps the earlier runs fell into: the site's own pictures beside a neighbour's hero
  (`neighbour`), sites a few kilometres from a site of the same type with each other's pictures
  (`pair_own`, `pair_other`; Stonehenge/Woodhenge and Avebury/Silbury Hill forced in), the gallery
  pictures whose file names promise a church, a village, a beach, a plant, a view or a street
  (`gallery_trap`), museum pieces (`museum`, D116), and the Commons search pool of the sites without
  a picture (`pool`, re-fetched: `candidate_search/repicture.py --need gold`);
* **labelled twice, independently**, by two Opus xhigh agents in the role `pilot_judge` with the
  production rules and the adjudicator's research order (the depicts question of the lane plus the
  Commons file and the order to research it on the web, `calibrate.ADJUDICATE_PROMPT`; for the
  prefilter the prefilter's own question), each from its own handoff; a **third** labels only the
  cases on which the two disagree, and the majority is the truth;
* **30 labels checked by the orchestrator** against the pictures (`SPOTCHECK.jsonl`, an override
  only with its reason) before the gold is fixed;
* **sealed before the measured roles answer**: the thresholds and the pins of the prompts and of the
  code (`pins`) before the first case is drawn, the draw before the first label, the gold before the
  first measured answer - each a line of `SEAL.jsonl`, each written once.

Two calibration directories, because the prefilter's tier was open when the depicts gold was drawn
(D118: the prefilter is probed at Opus first, `prefilter_probe.py`): `image-roles-v3` measures the
depicts judge and the hero re-check (slot `adversarial`, role `image_adversarial`), `image-roles-v3p`
the prefilter. The thresholds are v1's numbers except D119: a false `depicts` is tolerated up to
2 % (it was 3 % with zero foreign rows), because the hero re-check looks at every pick again.

    clean_gold.py seal          --dir D --kind depicts|kind
    clean_gold.py draw          --dir D --read READ.json --wiki-cache W --pool-run OLD
                                --exclude-gold image-roles-v1/GOLD.jsonl --exclude-heroes F
                                --insert-root import_hero                    -> D/DRAW.jsonl
    repicture.py --old-run OLD --need gold --calibration-dir D             (the pool's pictures)
    clean_gold.py void          --dir D --case ID --reason R                  a picture not served
    clean_gold.py label-export  --dir D --labeller a|b --handoff H
    run.py brief | check-answer | import  --run-dir D --stage image-gold-label-a|b|c (or
                                image-kind-label-a|b|c)
    clean_gold.py disputes      --dir D                                       -> D/DISPUTES.json
    clean_gold.py label-export  --dir D --labeller c --handoff H             (only the disputes)
    clean_gold.py spotcheck     --dir D                                       -> D/SPOTCHECK_LIST.jsonl
    (the orchestrator writes D/SPOTCHECK.jsonl)
    clean_gold.py fix           --dir D                                       -> GOLD.jsonl, JOBS.jsonl
    clean_gold.py export        --dir D --role R --handoff H                  the measured questions
    run.py brief | check-answer | import  --run-dir D --stage image-depicts-calibration |
                                image-recheck --round 1 | image-prefilter
    clean_gold.py evaluate      --dir D --role R                              -> D/verdicts/R.json
    clean_gold.py disagreements --dir D --role R                              every one, for the check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import roles as RO  # noqa: E402
from candidate_search import judge as CJ  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402

from image_roles import calibrate as CAL  # noqa: E402
from image_roles import depicts as DP  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402

DEPICTS_KIND, KIND_KIND = "depicts", "kind"
DRAW_FILE = "DRAW.jsonl"
DISPUTES_FILE = "DISPUTES.json"
SPOTCHECK_LIST = "SPOTCHECK_LIST.jsonl"
SPOTCHECK_FILE = "SPOTCHECK.jsonl"
LABELLERS = ("a", "b")
THIRD = "c"
SEED = 20261106
CHECKED_LABELS = 30
#: The decisions this gold rests on.
SOURCE = (
    "owner decisions D116-D119 of 2026-11-06 (output/remediation/OWNER_DECISIONS_2026-10-08.md); "
    "thresholds of output/remediation/final-2026-10-08/plans/images.md section 4, D119 for "
    "false depicts"
)

#: What each directory draws and measures, sealed before the first case is drawn.
THRESHOLDS: dict[str, dict[str, Any]] = {
    DEPICTS_KIND: {
        "interval": "Clopper-Pearson, 95 %",
        "seed": SEED,
        "source": SOURCE,
        "gold": DEPICTS_KIND,
        "measured": ["image_depicts", "adversarial"],
        "draw": {
            "hero_sites": 70,
            "gallery_per_site": 2,
            "neighbour_km": 20,
            "pair_sites": 15,
            "pair_km": 5,
            "forced_pairs": [["Stonehenge", "Woodhenge"], ["Avebury", "Silbury Hill"]],
            "per_pair_side": 2,
            "museum_sites": 20,
            "museum_per_site": 2,
            "pool_sites": 25,
            "pool_per_site": 3,
            "adversarial_positive": 100,
            "adversarial_negative": 100,
        },
        "labels": {"labellers": 2, "third": "the binary disagreements", "checked": CHECKED_LABELS},
        "roles": {
            "image_depicts": {
                "sensitivity_min": 0.90,
                "precision_min": 0.95,
                "false_depicts_max": 0.02,
                "every_foreign_not_depicts": False,
            },
            "adversarial": {"agreement_min": 0.95},
        },
    },
    KIND_KIND: {
        "interval": "Clopper-Pearson, 95 %",
        "seed": SEED,
        "source": SOURCE,
        "gold": KIND_KIND,
        "measured": ["image_prefilter"],
        "draw": {"gallery_per_class": 40, "pool": 100},
        "labels": {"labellers": 2, "third": "the binary disagreements", "checked": CHECKED_LABELS},
        "roles": {
            "image_prefilter": {
                "photo_agreement_min": 0.92,
                "depicts_capable_recall_min": 0.98,
            }
        },
    },
}

#: The file names of the gallery's trap pictures (the classes image-roles-v2 found in its gold) and
#: of museum pieces; matched against the offsite file name, case-insensitive.
TRAP_WORDS = re.compile(
    r"church|kirche|iglesia|[eé]glise|chapel|kapelle|village|beach|plant|flower|landscape|"
    r"panorama|view|street|house",
    re.IGNORECASE,
)
MUSEUM_WORDS = re.compile(r"museum|museo|mus[eé]e|museu", re.IGNORECASE)
#: The kind draw's classes by file name (the prefilter's kinds are what the labels decide).
KIND_CLASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("map", re.compile(r"map|plan|karte|carte|mapa|diagram|section|grundriss", re.IGNORECASE)),
    (
        "art",
        re.compile(
            r"drawing|engraving|painting|litho|sketch|illustration|reconstruct|print|gravure",
            re.IGNORECASE,
        ),
    ),
    ("museum", MUSEUM_WORDS),
    ("people", re.compile(r"portrait|people|visitor|tourist|man\b|woman", re.IGNORECASE)),
)
PLAIN = "plain"

# ------------------------------------------------------------------------------- the label stages
LABEL_PROMPT_ID = "image-gold-label-v1"
KIND_LABEL_PROMPT_ID = "image-kind-label-v1"


def _label_spec(who: str) -> SG.Spec:
    return replace(
        CAL.ADJUDICATE_SPEC,
        name=f"image-gold-label-{who}",
        prompt_id=LABEL_PROMPT_ID,
        questions_file=f"QUESTIONS_LABEL_{who.upper()}.jsonl",
        export_file=f"EXPORT_LABEL_{who.upper()}.json",
        result_file=f"LABEL_{who.upper()}.jsonl",
        what=f"label each candidate with web evidence (gold labeller {who})",
    )


def _kind_label_spec(who: str) -> SG.Spec:
    return replace(
        PF.SPEC,
        name=f"image-kind-label-{who}",
        role="pilot_judge",
        prompt_id=KIND_LABEL_PROMPT_ID,
        questions_file=f"QUESTIONS_KIND_LABEL_{who.upper()}.jsonl",
        export_file=f"EXPORT_KIND_LABEL_{who.upper()}.json",
        result_file=f"KIND_LABEL_{who.upper()}.jsonl",
        what=f"label the kind of each picture and whether it is usable (gold labeller {who})",
    )


LABEL_SPECS: dict[str, SG.Spec] = {w: _label_spec(w) for w in (*LABELLERS, THIRD)}
KIND_LABEL_SPECS: dict[str, SG.Spec] = {w: _kind_label_spec(w) for w in (*LABELLERS, THIRD)}
STAGES: dict[str, SG.Spec] = {
    s.name: s for s in (*LABEL_SPECS.values(), *KIND_LABEL_SPECS.values())
}


class GoldError(ST.StateError):
    """The clean gold cannot take this step. Nothing is half-written."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise GoldError(f"{path} does not exist")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _append_log(directory: Path, entry: Mapping[str, Any]) -> None:
    with open(directory / CAL.SEAL_LOG, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(entry), sort_keys=True) + "\n")


def _log_entry(directory: Path, key: str) -> dict[str, Any] | None:
    found = [e for e in CAL._log(directory) if key in e]
    if len(found) > 1:
        raise GoldError(f"{directory / CAL.SEAL_LOG} holds {key} twice")
    return found[0] if found else None


# --------------------------------------------------------------------------------------- the pins
#: The modules whose text a measured or labelling question is built from.
PINNED_MODULES = (
    "scripts/remediation/image_roles/depicts.py",
    "scripts/remediation/image_roles/prefilter.py",
    "scripts/remediation/image_roles/hero_recheck.py",
    "scripts/remediation/image_roles/stage.py",
    "scripts/remediation/image_roles/calibrate.py",
    "scripts/remediation/image_roles/clean_gold.py",
    "scripts/remediation/served_image/vision.py",
    "scripts/remediation/web_rules.py",
)


def prompt_pins() -> dict[str, str]:
    """The sha256 of every prompt text a question of these calibrations is made from."""
    texts = {
        "depicts.PROMPT": DP.PROMPT,
        "depicts.JUDGE_LINE": DP.JUDGE_LINE,
        "depicts.VERDICT_TERMS": DP.VERDICT_TERMS,
        "depicts.PROMPT_ID": DP.PROMPT_ID,
        "calibrate.ADJUDICATE_PROMPT": CAL.ADJUDICATE_PROMPT,
        "vision.CHECK_PROMPT_V3": V.CHECK_PROMPT_V3,
        "vision.CHECK_PROMPT_V3_ID": V.CHECK_PROMPT_V3_ID,
        "prefilter.PROMPT": PF.PROMPT,
        "prefilter.PROMPT_ID": PF.PROMPT_ID,
        "stage.BRIEF": SG.BRIEF,
    }
    return {name: _sha(text) for name, text in texts.items()}


def module_pins(root: Path | None = None) -> dict[str, str]:
    """The sha256 of the pinned modules (universal newlines, so a CRLF checkout pins the same)."""
    base = root or _HERE.parents[3]
    return {name: ST.file_sha256(base / name) for name in PINNED_MODULES}


def check_prompts(document: Mapping[str, Any]) -> None:
    """Refuse a prompt that is not the one the seal pinned: the gold would measure another
    question."""
    pinned = document["pins"]["prompts"]
    moved = sorted(k for k, v in prompt_pins().items() if pinned.get(k) != v)
    if moved:
        raise GoldError(
            f"the prompts moved after the seal ({', '.join(moved)}): seal a new directory"
        )


def modules_changed(document: Mapping[str, Any]) -> list[str]:
    pinned = document["pins"]["modules"]
    return sorted(k for k, v in module_pins().items() if pinned.get(k) != v)


# --------------------------------------------------------------------------------------- the seal
def thresholds_text(directory: Path, kind: str) -> str:
    if kind not in THRESHOLDS:
        raise GoldError(f"kind {kind!r} is not one of {sorted(THRESHOLDS)}")
    base = THRESHOLDS[kind]
    slots = [*base["measured"], "pilot_judge"]
    document = {
        **base,
        "version": directory.name,
        "role_registry": {slot: CAL._registry_entry(slot) for slot in slots},
        "roles_sha256": RO.registry_sha256(),
        "pins": {"prompts": prompt_pins(), "modules": module_pins()},
    }
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def seal(directory: Path, kind: str, *, now: Callable[[], str] = _now) -> dict[str, Any]:
    """THRESHOLDS.json and its log line, before any case is drawn; once."""
    if (directory / CAL.SEAL_LOG).exists() or (directory / DRAW_FILE).exists():
        raise GoldError(f"{directory} is sealed already - a seal is never rewritten")
    text = thresholds_text(directory, kind)
    directory.mkdir(parents=True, exist_ok=True)
    ST.write_text_once(directory / CAL.THRESHOLDS_FILE, text)
    _append_log(directory, {"thresholds_sha256": _sha(text), "sealed_at": now()})
    return {"thresholds_sha256": _sha(text), "kind": kind}


def sealed(directory: Path) -> dict[str, Any]:
    document, _, _ = CAL.sealed(directory)
    if document.get("gold") not in THRESHOLDS:
        raise GoldError(f"{directory} is not a clean-gold calibration (D117)")
    return document


# ---------------------------------------------------------------------------------------- the draw
def haversine_km(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _rng(seed: int, *parts: str) -> random.Random:
    digest = hashlib.sha256("\t".join([str(seed), *parts]).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))  # noqa: S311 - a reproducible sample


def case_id(prefix: str, site_id: str, file: str) -> str:
    return f"{prefix}-{hashlib.sha256((site_id + chr(9) + file).encode()).hexdigest()[:12]}"


def _case(
    group: str,
    site: Mapping[str, Any],
    picture: Mapping[str, Any],
    *,
    why: str = "a Commons picture",
) -> dict[str, Any]:
    """A depicts case: the site asked about, the picture shown and where it came from. The truth
    is the labels', so the draw has none."""
    return {
        "case_id": case_id(group, str(site["site_id"]), str(picture["file"])),
        "role": "image_depicts",
        "group": group,
        "site": dict(site),
        "file": str(picture["file"]),
        "commons_file": picture.get("commons_file"),
        "path": str(picture["path"]),
        "picture_site": picture.get("picture_site"),
        "why": why,
        "truth": None,
    }


def gallery_pictures(
    state: ST.State,
    on_disk: Callable[[str, str], str | None],
    excluded_images: Collection[int],
    excluded_files: Collection[tuple[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    """`{site id: [picture]}`: every non-excluded gallery row on disk that no earlier calibration
    asked about and that is no lane subject; the hero first."""
    out: dict[str, list[dict[str, Any]]] = {}
    for sid in state.site_ids():
        pictures = []
        for row in state.rows.get(sid, ()):
            if row.get("is_excluded") or int(row["id"]) in excluded_images:
                continue
            if (sid, str(row["filename"])) in excluded_files:
                continue
            path = on_disk(sid, str(row["filename"]))
            if path is None:
                continue
            pictures.append(
                {
                    "file": str(row["filename"]),
                    "commons_file": ST.file_of_row(row),
                    "path": path,
                    "picture_site": sid,
                    "is_hero": bool(row.get("is_hero")),
                    "image_id": int(row["id"]),
                }
            )
        if pictures:
            pictures.sort(key=lambda p: (not p["is_hero"], p["image_id"]))
            out[sid] = pictures
    return out


def _pick(rng: random.Random, items: Sequence[Mapping[str, Any]], n: int) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda p: p["file"])
    return [dict(p) for p in rng.sample(ordered, min(n, len(ordered)))]


def draw_depicts(
    *,
    state: ST.State,
    site_context: Callable[[str], dict[str, Any]],
    gallery: Mapping[str, Sequence[Mapping[str, Any]]],
    pool: Sequence[tuple[str, Mapping[str, Any], str]],
    pool_path: Callable[[Mapping[str, Any]], str],
    draw: Mapping[str, Any],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The depicts cases of the clean gold, and what the draw could not find (recorded, never
    hidden). A site is drawn into one stratum only, so that every question asks about one site.

    `gallery` is `gallery_pictures`; `pool` holds `(site id, candidate, MiniMax verdict)` of the
    search pool the earlier calibrations did not ask about."""
    sites = state.sites
    used: set[str] = set()
    cases: list[dict[str, Any]] = []
    notes: dict[str, Any] = {}
    heroes = {sid: ps[0] for sid, ps in gallery.items() if ps[0]["is_hero"]}

    # -- pairs: two sites a few km apart and of the same type, each other's pictures (forced first)
    by_name = defaultdict(list)
    for sid, site in sites.items():
        by_name[site["name"]].append(sid)
    pairs: list[tuple[str, str]] = []
    missing_forced = []
    for a_name, b_name in draw["forced_pairs"]:
        a_ids, b_ids = by_name.get(a_name, []), by_name.get(b_name, [])
        if len(a_ids) == 1 and len(b_ids) == 1 and a_ids[0] in gallery and b_ids[0] in gallery:
            pairs.append((a_ids[0], b_ids[0]))
        else:
            missing_forced.append([a_name, b_name])
    notes["forced_pairs_missing"] = missing_forced
    rich = sorted(sid for sid, ps in gallery.items() if len(ps) >= draw["per_pair_side"])
    candidates = []
    cells: dict[tuple[int, int], list[str]] = defaultdict(list)
    for sid in rich:
        cells[(int(sites[sid]["lat"] // 0.1), int(sites[sid]["lon"] // 0.1))].append(sid)
    for sid in rich:
        la, lo = int(sites[sid]["lat"] // 0.1), int(sites[sid]["lon"] // 0.1)
        for dla in (-1, 0, 1):
            for dlo in (-1, 0, 1):
                for other in cells.get((la + dla, lo + dlo), ()):
                    if other <= sid or sites[other].get("site_type") != sites[sid].get("site_type"):
                        continue
                    if sites[other]["name"] == sites[sid]["name"]:
                        continue
                    if haversine_km(sites[sid], sites[other]) <= draw["pair_km"]:
                        candidates.append({"a": sid, "b": other})
    forced_ids = {s for p in pairs for s in p}
    free = [c for c in candidates if c["a"] not in forced_ids and c["b"] not in forced_ids]
    rng = _rng(seed, "pairs")
    rng.shuffle(free)
    for pair in free:
        if len(pairs) >= draw["pair_sites"]:
            break
        a, b = (pair["a"], pair["b"]) if rng.random() < 0.5 else (pair["b"], pair["a"])
        if {a, b} & {s for p in pairs for s in p}:
            continue
        pairs.append((a, b))
    notes["pairs"] = len(pairs)
    for a, b in pairs:
        used |= {a, b}
        site = site_context(a)
        r = _rng(seed, "pair", a, b)
        for p in [*gallery[a][:1], *_pick(r, gallery[a][1:], draw["per_pair_side"] - 1)]:
            cases.append(_case("pair_own", site, p))
        for p in [*gallery[b][:1], *_pick(r, gallery[b][1:], draw["per_pair_side"] - 1)]:
            cases.append(_case("pair_other", site, p))

    # -- museum pieces (D116): a site's own gallery pictures whose names say museum
    museum_sites = sorted(
        sid
        for sid, ps in gallery.items()
        if sid not in used and any(MUSEUM_WORDS.search(p["file"]) for p in ps)
    )
    chosen = CAL.sample([{"site_id": s} for s in museum_sites], draw["museum_sites"], seed)
    for item in chosen:
        sid = str(item["site_id"])
        used.add(sid)
        pieces = [p for p in gallery[sid] if MUSEUM_WORDS.search(p["file"])]
        for p in _pick(_rng(seed, "museum", sid), pieces, draw["museum_per_site"]):
            cases.append(_case("museum", site_context(sid), p))
    notes["museum_sites"] = len(chosen)

    # -- the search pool of the sites without a picture: one candidate per MiniMax class first
    by_site: dict[str, list[tuple[Mapping[str, Any], str]]] = defaultdict(list)
    for sid, candidate, verdict in pool:
        if sid in sites and sid not in used:
            by_site[sid].append((candidate, verdict))
    pool_sites = CAL.sample([{"site_id": s} for s in sorted(by_site)], draw["pool_sites"], seed)
    for item in pool_sites:
        sid = str(item["site_id"])
        used.add(sid)
        r = _rng(seed, "pool", sid)
        classes: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for candidate, verdict in sorted(by_site[sid], key=lambda cv: str(cv[0]["file"])):
            classes[verdict].append(candidate)
        picked: list[Mapping[str, Any]] = []
        for verdict in sorted(classes):
            picked.append(r.choice(classes[verdict]))
        rest = [
            c for cs in classes.values() for c in cs if all(c["file"] != p["file"] for p in picked)
        ]
        r.shuffle(rest)
        for candidate in [*picked, *rest][: draw["pool_per_site"]]:
            picture = {
                "file": str(candidate["file"]),
                "commons_file": str(candidate["file"]),
                "path": pool_path(candidate),
                "picture_site": sid,
                "picture_url": candidate.get("picture_url"),
            }
            case = _case(
                "pool",
                site_context(sid),
                picture,
                why=str(candidate.get("why") or "a Commons search"),
            )
            case["picture_url"] = candidate.get("picture_url")
            cases.append(case)
    notes["pool_sites"] = len(pool_sites)

    # -- sites with a hero: the hero, two gallery pictures (a trap first) and a neighbour's hero
    eligible = [
        {"site_id": sid, "site_type": str(sites[sid].get("site_type") or "none")}
        for sid in sorted(heroes)
        if sid not in used and len(gallery[sid]) >= 1 + draw["gallery_per_site"]
    ]
    hero_sites = CAL.stratified(eligible, "site_type", draw["hero_sites"], seed)
    hero_ids = [str(s["site_id"]) for s in hero_sites]
    used |= set(hero_ids)
    with_hero = sorted(heroes)
    neighbours_missing = 0
    for sid in hero_ids:
        site = site_context(sid)
        r = _rng(seed, "hero", sid)
        cases.append(_case("hero", site, gallery[sid][0]))
        rest = gallery[sid][1:]
        traps = [p for p in rest if TRAP_WORDS.search(p["file"])]
        picked = _pick(r, traps, 1)
        others = [p for p in rest if all(p["file"] != q["file"] for q in picked)]
        picked += _pick(r, others, draw["gallery_per_site"] - len(picked))
        for p in picked:
            cases.append(
                _case("gallery_trap" if TRAP_WORDS.search(p["file"]) else "gallery", site, p)
            )
        near = sorted(
            (haversine_km(sites[sid], sites[o]), o)
            for o in with_hero
            if o != sid
            and sites[o]["name"] != sites[sid]["name"]
            and abs(sites[o]["lat"] - sites[sid]["lat"]) < 0.5
            and abs(sites[o]["lon"] - sites[sid]["lon"]) < 0.8
        )
        if near and near[0][0] <= draw["neighbour_km"]:
            cases.append(_case("neighbour", site, heroes[near[0][1]]))
        else:
            neighbours_missing += 1
    notes["hero_sites"] = len(hero_ids)
    notes["hero_sites_without_neighbour"] = neighbours_missing
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise GoldError("the draw holds a case twice")
    return cases, notes


def kind_class(file: str) -> str:
    for name, pattern in KIND_CLASSES:
        if pattern.search(file):
            return name
    return PLAIN


def draw_kinds(
    *,
    gallery: Mapping[str, Sequence[Mapping[str, Any]]],
    pool: Sequence[tuple[str, Mapping[str, Any], str]],
    pool_path: Callable[[Mapping[str, Any]], str],
    draw: Mapping[str, Any],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The prefilter's cases: gallery pictures stratified by what their file names promise (the
    labels decide the kind) and pictures of the search pool, in one shuffled order."""
    pictures = [
        {**p, "site_id": sid, "class": kind_class(p["file"])}
        for sid, ps in sorted(gallery.items())
        for p in ps
    ]
    classes = [name for name, _ in KIND_CLASSES] + [PLAIN]
    chosen = CAL.stratified(
        [p for p in pictures if p["class"] in classes],
        "class",
        draw["gallery_per_class"] * len(classes),
        seed,
    )
    pool_items = [
        {
            "site_id": sid,
            "file": str(c["file"]),
            "commons_file": str(c["file"]),
            "path": pool_path(c),
            "picture_url": c.get("picture_url"),
            "class": "pool",
        }
        for sid, c, _ in pool
    ]
    chosen = [*chosen, *CAL.sample(pool_items, draw["pool"], seed)]
    cases = [
        {
            "case_id": case_id("kind", str(p["site_id"]), str(p["file"])),
            "role": "image_prefilter",
            "group": str(p["class"]),
            "site": {"site_id": str(p["site_id"])},
            "file": str(p["file"]),
            "commons_file": p.get("commons_file"),
            "path": str(p["path"]),
            "picture_url": p.get("picture_url"),
            "truth": None,
        }
        for p in chosen
    ]
    _rng(seed, "kind-order").shuffle(cases)
    return cases, {"by_group": dict(Counter(c["group"] for c in cases))}


def write_draw(
    directory: Path, cases: Sequence[Mapping[str, Any]], notes: Mapping[str, Any], *, now=_now
) -> str:
    """DRAW.jsonl (no truth) and its log line; after the seal, once."""
    sealed(directory)
    if _log_entry(directory, "draw_sha256") is not None:
        raise GoldError(f"{directory} is drawn already - a draw is never rewritten")
    if not cases:
        raise GoldError("the draw is empty")
    digest = ST.write_text_once(directory / DRAW_FILE, CAL.gold_text(cases, truth=True))
    _append_log(
        directory, {"draw_sha256": digest, "cases": len(cases), "drawn_at": now(), "notes": notes}
    )
    return digest


def drawn(directory: Path) -> tuple[list[dict[str, Any]], str]:
    """`(cases, drawn_at)`, refusing a DRAW.jsonl that is not the logged one."""
    entry = _log_entry(directory, "draw_sha256")
    if entry is None:
        raise GoldError(f"{directory} is not drawn: run `draw` first")
    path = directory / DRAW_FILE
    if ST.file_sha256(path) != entry["draw_sha256"]:
        raise GoldError(f"{path} changed after it was drawn")
    voided = {e["void"] for e in CAL._log(directory) if "void" in e}
    return [c for c in _jsonl(path) if c["case_id"] not in voided], str(entry["drawn_at"])


def void(
    directory: Path, case: str, reason: str, *, now: Callable[[], str] = _now
) -> dict[str, Any]:
    """Take a drawn case out whose picture cannot be shown (a rendering Commons does not serve at
    the lane's width): a log line with its reason, before the first label is asked. A case whose
    picture is on disk is never voided - the draw is not chosen after the fact."""
    document = sealed(directory)
    cases, _ = drawn(directory)
    found = [c for c in cases if c["case_id"] == case]
    if not found:
        raise GoldError(f"{case} is no case of the draw (or voided already)")
    if any((directory / s.export_file).is_file() for s in _specs(document).values()):
        raise GoldError("a label was asked already: the draw is no longer voided")
    if Path(found[0]["path"]).is_file():
        raise GoldError(f"{case}: its picture is on disk - a shown case is never voided")
    if not reason.strip():
        raise GoldError("a void names its reason")
    _append_log(directory, {"void": case, "reason": reason, "voided_at": now()})
    return {"void": case, "reason": reason, "cases_left": len(cases) - 1}


# ------------------------------------------------------------------------------- the label rounds
def label_line(candidate: Mapping[str, Any]) -> str:
    """What a labeller is told about a candidate: its Commons file (to research), then its route."""
    return f'Commons file "File:{candidate["commons_file"]}"; found by {DP.source_line(candidate)}'


def depicts_label_questions(
    cases: Sequence[Mapping[str, Any]], read: Callable[[Mapping[str, Any]], bytes]
) -> tuple[list[SG.Question], dict[str, bytes]]:
    """The labellers' questions: the adjudicator's question (the depicts prompt, the Commons file,
    the research order), one per site, packed as the depicts role is."""
    by_site: dict[str, dict[str, Any]] = {}
    for c in cases:
        if not c.get("commons_file"):
            raise GoldError(f"{c['case_id']}: the picture names no Commons file to research")
        site = by_site.setdefault(str(c["site"]["site_id"]), {**c["site"], "candidates": []})
        site["candidates"].append(
            {
                "file": c["file"],
                "commons_file": c["commons_file"],
                "path": c["path"],
                "why": c["why"],
            }
        )
    questions, pictures, left_out = DP.build_questions(
        list(by_site.values()), read, prompt=CAL.ADJUDICATE_PROMPT, line=label_line
    )
    if left_out:
        raise GoldError(f"{len(left_out)} case(s) do not fit one question of their site")
    return questions, pictures


def kind_label_questions(
    cases: Sequence[Mapping[str, Any]], read: Callable[[Mapping[str, Any]], bytes]
) -> tuple[list[SG.Question], dict[str, bytes]]:
    flat = [{"site_id": c["case_id"], "file": c["file"], "path": c["path"]} for c in cases]
    return PF.build_questions(flat, read)


def _specs(document: Mapping[str, Any]) -> dict[str, SG.Spec]:
    return LABEL_SPECS if document["gold"] == DEPICTS_KIND else KIND_LABEL_SPECS


def label_export(
    directory: Path,
    labeller: str,
    handoff: Path,
    read: Callable[[Mapping[str, Any]], bytes],
) -> dict[str, Any]:
    """One labeller's questions: `a` and `b` the whole draw, `c` only the disputed cases. Refused
    once the gold is fixed (a label after that would be no label of this gold)."""
    document = sealed(directory)
    if _log_entry(directory, "gold_sha256") is not None:
        raise GoldError(f"{directory}: the gold is fixed, nothing is labelled any more")
    cases, _ = drawn(directory)
    if labeller == THIRD:
        disputed = set(disputes(directory)["disputed"])
        cases = [c for c in cases if c["case_id"] in disputed]
        if not cases:
            raise GoldError("the two labellers agree on every case: there is nothing to ask c")
    elif labeller not in LABELLERS:
        raise GoldError(f"labeller {labeller!r} is not one of {[*LABELLERS, THIRD]}")
    if document["gold"] == DEPICTS_KIND:
        questions, pictures = depicts_label_questions(cases, read)
    else:
        questions, pictures = kind_label_questions(cases, read)
    others = [
        Path(json.loads((directory / s.export_file).read_text(encoding="utf-8"))["handoff"])
        for w, s in _specs(document).items()
        if w != labeller and (directory / s.export_file).is_file()
    ]
    if any(o.resolve() == handoff.resolve() for o in others):
        raise GoldError(f"{handoff} is another labeller's handoff: each labels on its own")
    return SG.export(directory, handoff, _specs(document)[labeller], questions, pictures)


def _binary(document: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`{case id: label}` from one labeller's imported answers: for the depicts gold
    `{"depicts": bool, "verdict", "note"}`, for the kind gold `{"photo", "survives", "kind",
    "usable"}`."""
    out: dict[str, Any] = {}
    if document["gold"] == DEPICTS_KIND:
        for result in rows:
            files = {i["label"]: i["file"] for i in result["meta"]["items"]}
            sid = str(result["meta"]["site_id"])
            for label, entry in result["candidates"].items():
                out[(sid, files[label])] = {
                    "depicts": entry["verdict"] == CJ.DEPICTS,
                    "verdict": entry["verdict"],
                    "note": entry["note"],
                    "answered_by": result["answered_by"],
                }
        return out
    for row in PF.judged(rows):
        out[row["site_id"]] = {
            "photo": row["kind"] in CAL.PHOTO_KINDS,
            "survives": row["survives"],
            "kind": row["kind"],
            "usable": row["usable"],
            "answered_by": row["answered_by"],
        }
    return out


def _key(document: Mapping[str, Any], case: Mapping[str, Any]) -> Any:
    if document["gold"] == DEPICTS_KIND:
        return (str(case["site"]["site_id"]), case["file"])
    return case["case_id"]


def _dims(document: Mapping[str, Any]) -> tuple[str, ...]:
    return ("depicts",) if document["gold"] == DEPICTS_KIND else ("photo", "survives")


def labels_of(directory: Path, labeller: str) -> dict[str, Any]:
    """`{case id: label}` of one labeller, every answer the pilot judge's and given after the draw
    and before the gold was fixed."""
    document = sealed(directory)
    cases, drawn_at = drawn(directory)
    rows = SG.read_results(directory, _specs(document)[labeller])
    gold = _log_entry(directory, "gold_sha256")
    for row in rows:
        if row["answered_at"] < drawn_at:
            raise GoldError(f"{row['batch_id']}/{row['label']}: labelled before the draw")
        if gold is not None and row["answered_at"] > gold["fixed_at"]:
            raise GoldError(f"{row['batch_id']}/{row['label']}: labelled after the gold was fixed")
        if RO.role_of(row["answered_by"]) != CAL.slot_role("pilot_judge"):
            raise GoldError(f"{row['batch_id']}/{row['label']}: not the pilot judge's answer")
    by_key = _binary(document, rows)
    out = {}
    for c in cases:
        label = by_key.get(_key(document, c))
        if label is not None:
            out[c["case_id"]] = label
    return out


def disputes(directory: Path, *, write: bool = False) -> dict[str, Any]:
    """The cases on which labellers a and b disagree (on any measured dimension), and the agents:
    a case the same agent labelled twice would be no independent label."""
    document = sealed(directory)
    cases, _ = drawn(directory)
    a, b = labels_of(directory, "a"), labels_of(directory, "b")
    missing = [c["case_id"] for c in cases if c["case_id"] not in a or c["case_id"] not in b]
    if missing:
        raise GoldError(f"{len(missing)} case(s) lack a label of a or b (first {missing[0]})")
    agents_a = {v["answered_by"] for v in a.values()}
    agents_b = {v["answered_by"] for v in b.values()}
    if agents_a & agents_b:
        raise GoldError(f"labellers a and b share agents: {sorted(agents_a & agents_b)[:3]}")
    dims = _dims(document)
    disputed = sorted(
        c["case_id"] for c in cases if any(a[c["case_id"]][d] != b[c["case_id"]][d] for d in dims)
    )
    result = {
        "cases": len(cases),
        "disputed": disputed,
        "agreement": round(1 - len(disputed) / len(cases), 4),
        "by_group": dict(Counter(c["group"] for c in cases if c["case_id"] in set(disputed))),
    }
    if write:
        ST.write_text_once(directory / DISPUTES_FILE, ST.json_text(result))
    return result


def consensus(directory: Path) -> dict[str, dict[str, Any]]:
    """`{case id: {"truth", "labels"}}`: the label a and b agree on, else the majority with c."""
    document = sealed(directory)
    cases, _ = drawn(directory)
    a, b = labels_of(directory, "a"), labels_of(directory, "b")
    disputed = set(disputes(directory)["disputed"])
    c_labels = labels_of(directory, THIRD) if disputed else {}
    lacking = sorted(disputed - set(c_labels))
    if lacking:
        raise GoldError(
            f"{len(lacking)} disputed case(s) lack the third label (first {lacking[0]})"
        )
    if disputed and {v["answered_by"] for v in c_labels.values()} & {
        v["answered_by"] for v in (*a.values(), *b.values())
    }:
        raise GoldError("labeller c shares an agent with a or b")
    out = {}
    for case in cases:
        cid = case["case_id"]
        votes = [a[cid], b[cid]] + ([c_labels[cid]] if cid in disputed else [])
        truth = {d: sum(v[d] for v in votes) * 2 > len(votes) for d in _dims(document)}
        out[cid] = {"truth": truth, "labels": votes}
    return out


def spotcheck_list(directory: Path) -> list[dict[str, Any]]:
    """The 30 labels the orchestrator checks against the pictures: every group, the disputed cases
    over-represented (half of the list when there are as many), deterministic for the seed."""
    document = sealed(directory)
    cases, _ = drawn(directory)
    agreed = consensus(directory)
    disputed = set(disputes(directory)["disputed"])
    seed = int(document["seed"])
    hard = CAL.sample([c for c in cases if c["case_id"] in disputed], CHECKED_LABELS // 2, seed)
    rest = CAL.stratified(
        [c for c in cases if c["case_id"] not in disputed],
        "group",
        CHECKED_LABELS - len(hard),
        seed,
    )
    rows = []
    for c in [*hard, *rest]:
        cid = c["case_id"]
        rows.append(
            {
                "case_id": cid,
                "group": c["group"],
                "site": c["site"].get("name"),
                "commons_file": c.get("commons_file"),
                "path": c["path"],
                "truth": agreed[cid]["truth"],
                "labels": agreed[cid]["labels"],
                "disputed": cid in disputed,
            }
        )
    path = directory / SPOTCHECK_LIST
    text = ST.jsonl_text(rows)
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise GoldError(f"{path} exists with another list")
    if not path.exists():
        ST.write_text_once(path, text)
    return rows


def read_spotcheck(directory: Path, document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The orchestrator's check of the listed labels: exactly the listed cases, each
    `{case_id, truth: {dim: bool}, agrees: bool, note}`; an `agrees: false` is an override of the
    consensus with its reason in the note."""
    listed = [r["case_id"] for r in _jsonl(directory / SPOTCHECK_LIST)]
    rows = _jsonl(directory / SPOTCHECK_FILE)
    by_id = {r["case_id"]: r for r in rows}
    if sorted(by_id) != sorted(listed) or len(rows) != len(listed):
        raise GoldError(f"{SPOTCHECK_FILE} must check exactly the {len(listed)} listed cases once")
    dims = set(_dims(document))
    for r in rows:
        if set(r) != {"case_id", "truth", "agrees", "note"} or set(r["truth"]) != dims:
            raise GoldError(
                f"{r.get('case_id')}: a check carries case_id, truth {sorted(dims)}, agrees, note"
            )
        if not isinstance(r["agrees"], bool) or not str(r["note"]).strip():
            raise GoldError(f"{r['case_id']}: 'agrees' is true or false, and the note says why")
    return by_id


def adversarial_draw(
    cases: Sequence[Mapping[str, Any]], *, positive: int, negative: int, seed: int
) -> list[dict[str, Any]]:
    """The re-check's cases from the labelled depicts cases: `positive` that depict the site and
    `negative` that do not, each stratified by group (the traps among the negatives). The re-check
    is asked about a pick a judge called depicts, so the question says so for every case."""
    yes = [c for c in cases if c["truth"] == "depicts"]
    no = [c for c in cases if c["truth"] == "not_depicts"]
    picked = [
        *CAL.stratified(yes, "group", positive, seed),
        *CAL.stratified(no, "group", negative, seed),
    ]
    return [
        {
            **c,
            "case_id": f"rck-{c['case_id']}",
            "role": "adversarial",
            "note": "a judge called it depicts",
        }
        for c in picked
    ]


def fix(directory: Path, *, now: Callable[[], str] = _now) -> dict[str, Any]:
    """GOLD.jsonl and JOBS.jsonl from the draw, the consensus and the orchestrator's check; the
    prompts must still be the pinned ones. Once (`calibrate.fix_gold`)."""
    document = sealed(directory)
    check_prompts(document)
    cases, _ = drawn(directory)
    agreed = consensus(directory)
    checked = read_spotcheck(directory, document)
    gold = []
    overrides = 0
    for case in cases:
        cid = case["case_id"]
        truth = dict(agreed[cid]["truth"])
        check = checked.get(cid)
        if check is not None and not check["agrees"]:
            truth = dict(check["truth"])
            overrides += 1
        row = {**case, "labels": agreed[cid]["labels"], "checked": check}
        if document["gold"] == DEPICTS_KIND:
            row["truth"] = "depicts" if truth["depicts"] else "not_depicts"
        else:
            row["truth"] = truth
        gold.append(row)
    if document["gold"] == DEPICTS_KIND:
        d = document["draw"]
        gold += adversarial_draw(
            gold,
            positive=d["adversarial_positive"],
            negative=d["adversarial_negative"],
            seed=int(document["seed"]),
        )
    digest = CAL.fix_gold(directory, gold, now=now)
    _append_log(
        directory,
        {"gold_pins": {"prompts": prompt_pins(), "modules": module_pins()}, "overrides": overrides},
    )
    return {
        "gold_sha256": digest,
        "cases": len(gold),
        "overrides": overrides,
        "by_role": dict(Counter(c["role"] for c in gold)),
        "truth": dict(Counter(str(c["truth"]) for c in gold)),
    }


def export(directory: Path, role: str, handoff: Path) -> dict[str, Any]:
    """The measured role's production questions over the fixed gold (`calibrate.cmd_export`),
    refused while a prompt is not the pinned one."""
    check_prompts(sealed(directory))
    return CAL.cmd_export(directory, role, handoff)


# --------------------------------------------------------------------------------------- measuring
def measure_kinds(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Photo versus non-photo agreement and the recall of the pictures the labels let survive."""
    truth = {c["case_id"]: c["truth"] for c in cases if c["role"] == "image_prefilter"}
    judged = {r["site_id"]: r for r in PF.judged(results)}
    missing = sorted(set(truth) - set(judged))
    if missing:
        raise GoldError(f"{len(missing)} prefilter case(s) unanswered (first {missing[0]})")
    agree = sum(t["photo"] == (judged[i]["kind"] in CAL.PHOTO_KINDS) for i, t in truth.items())
    capable = [i for i, t in truth.items() if t["survives"]]
    kept = sum(judged[i]["survives"] for i in capable)
    return {
        "photo_agreement": CAL.interval(agree, len(truth), cp),
        "depicts_capable_recall": CAL.interval(kept, len(capable), cp),
        "dropped": sorted(i for i in capable if not judged[i]["survives"]),
        "photo_disagreements": sorted(
            i for i, t in truth.items() if t["photo"] != (judged[i]["kind"] in CAL.PHOTO_KINDS)
        ),
    }


def _wrong_site(case: Mapping[str, Any]) -> bool:
    """A negative whose labels call it another site (the D119 class), not a region or a type."""
    return sum(v.get("verdict") == CJ.OTHER for v in case.get("labels") or ()) * 2 > len(
        case.get("labels") or ()
    )


def measure_depicts(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    """Sensitivity over every case the gold calls depicts, the false-depicts rate over every case it
    does not, precision, and the wrong-site negatives called depicts, by group."""
    mine = [c for c in cases if c["role"] == "image_depicts"]
    verdicts = CAL._verdicts_of(results)
    called = {}
    for c in mine:
        entry = verdicts.get((str(c["site"]["site_id"]), c["file"]))
        if entry is None:
            raise GoldError(f"{c['case_id']}: unanswered")
        called[c["case_id"]] = entry["verdict"] == CJ.DEPICTS
    positives = [c["case_id"] for c in mine if c["truth"] == "depicts"]
    negatives = [c["case_id"] for c in mine if c["truth"] == "not_depicts"]
    false_depicts = sum(called[i] for i in negatives)
    true_depicts = sum(called[i] for i in positives)
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for c in mine:
        kind = (
            ("tp" if called[c["case_id"]] else "fn")
            if c["truth"] == "depicts"
            else ("fp" if called[c["case_id"]] else "tn")
        )
        groups[c["group"]][kind] += 1
    return {
        "sensitivity": CAL.interval(true_depicts, len(positives), cp),
        "false_depicts": CAL.interval(false_depicts, len(negatives), cp),
        "precision": CAL.interval(true_depicts, true_depicts + false_depicts, cp),
        "foreign_called_depicts": sorted(
            c["case_id"]
            for c in mine
            if c["truth"] == "not_depicts" and _wrong_site(c) and called[c["case_id"]]
        ),
        "foreign_rows": sum(1 for c in mine if c["truth"] == "not_depicts" and _wrong_site(c)),
        "by_group": {g: dict(v) for g, v in sorted(groups.items())},
    }


def measure_adversarial(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    cp: Callable[[int, int], tuple[float, float]],
) -> dict[str, Any]:
    mine = [c for c in cases if c["role"] == "adversarial"]
    by_file = {(r["meta"]["site_id"], r["meta"]["file"]): r["verdict"] for r in results}
    agree = 0
    kept_false = []
    for c in mine:
        verdict = by_file.get((c["case_id"], c["file"]))
        if verdict is None:
            raise GoldError(f"{c['case_id']}: unanswered")
        agree += (verdict == CJ.DEPICTS) == (c["truth"] == "depicts")
        if verdict == CJ.DEPICTS and c["truth"] != "depicts":
            kept_false.append(c["case_id"])
    return {"agreement": CAL.interval(agree, len(mine), cp), "confirmed_false": sorted(kept_false)}


def evaluate(
    directory: Path,
    role: str,
    *,
    now: Callable[[], str] = _now,
    cp: Callable[[int, int], tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """One measured slot against the sealed thresholds -> `verdicts/<slot>.json`, once. Refused: a
    slot this directory does not measure, a moved prompt, an answer given before the gold was
    fixed. A failing role at Opus is held for the owner (`roles.escalation` refuses the top)."""
    document = sealed(directory)
    if role not in CAL.measured_slots(document):
        raise GoldError(f"slot {role} is not measured in {directory.name}")
    check_prompts(document)
    cases, fixed_at = CAL.fixed_gold(directory)
    results = SG.read_results(directory, CAL.ROLE_SPECS[role])
    for row in results:
        if row["answered_at"] < fixed_at:
            raise GoldError(f"{row['batch_id']}/{row['label']}: answered before the gold was fixed")
    cp = cp or CAL.clopper_pearson()
    if role == "image_prefilter":
        metrics = measure_kinds(cases, results, cp)
    elif role == "image_depicts":
        metrics = measure_depicts(cases, results, cp)
    else:
        metrics = measure_adversarial(cases, results, cp)
    failures = CAL.decide(role, document, metrics)
    name = CAL.slot_role(role)
    verdict: dict[str, Any] = {
        "role": name,
        "slot": role,
        "model": RO.role(name).model,
        "effort": RO.role(name).effort,
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
        "modules_changed_since_seal": modules_changed(document),
        "decided_at": now(),
        "tier_move": None,
    }
    if failures:
        try:
            verdict["tier_move"] = RO.escalation(
                name, calibration_id=directory.name, reason="; ".join(failures)
            )
        except RO.RoleError as exc:
            verdict["held"] = f"{exc}: the owner decides"
    path = directory / CAL.VERDICTS_DIR / f"{role}.json"
    if path.exists():
        raise GoldError(f"{path} exists - a verdict is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return verdict


def disagreements(directory: Path, role: str) -> list[dict[str, Any]]:
    """Every case where the measured role and the gold disagree, with the labels' notes and the
    role's own, for the orchestrator's check of each one."""
    sealed(directory)
    cases, _ = CAL.fixed_gold(directory)
    results = SG.read_results(directory, CAL.ROLE_SPECS[role])
    out = []
    if role == "image_depicts":
        verdicts = CAL._verdicts_of(results)
        for c in cases:
            if c["role"] != role:
                continue
            entry = verdicts[(str(c["site"]["site_id"]), c["file"])]
            if (entry["verdict"] == CJ.DEPICTS) != (c["truth"] == "depicts"):
                out.append({**_brief_case(c), "answer": entry})
    elif role == "adversarial":
        by_file = {(r["meta"]["site_id"], r["meta"]["file"]): r for r in results}
        for c in cases:
            if c["role"] != role:
                continue
            r = by_file[(c["case_id"], c["file"])]
            if (r["verdict"] == CJ.DEPICTS) != (c["truth"] == "depicts"):
                answer = {k: r[k] for k in ("verdict", "shows", "basis") if k in r}
                out.append({**_brief_case(c), "answer": answer})
    else:
        judged = {r["site_id"]: r for r in PF.judged(results)}
        for c in cases:
            if c["role"] != role:
                continue
            j, t = judged[c["case_id"]], c["truth"]
            if t["photo"] != (j["kind"] in CAL.PHOTO_KINDS) or (
                t["survives"] and not j["survives"]
            ):
                out.append(
                    {**_brief_case(c), "answer": {k: j[k] for k in ("kind", "usable", "survives")}}
                )
    return out


def _brief_case(c: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": c["case_id"],
        "group": c["group"],
        "site": c["site"].get("name"),
        "commons_file": c.get("commons_file"),
        "path": c["path"],
        "truth": c["truth"],
        "labels": c.get("labels"),
    }


# ------------------------------------------------------------------------------------------ the CLI
def cmd_draw(directory: Path, args: argparse.Namespace) -> dict[str, Any]:
    """Choose the cases from production's read (read-only) and the files, and fix the draw."""
    from candidate_search import pool as PL
    from gallery_audit import persist_verdicts as pv
    from gallery_audit.vision import Images, VisionError

    from image_roles.wiki_cache import WikiCache

    document = sealed(directory)
    state = ST.load_read(args.read)
    images = Images()

    def on_disk(site_id: str, filename: str) -> str | None:
        try:
            return str(images.path_for(site_id, filename))
        except VisionError:
            return None

    excluded = CAL.inserted_heroes(state, args.insert_root)
    for path in args.exclude_heroes:
        excluded |= {int(r["image_id"]) for r in _jsonl(path)}
    asked: set[tuple[str, str]] = set()
    for path in args.exclude_gold:
        for row in _jsonl(path):
            if row.get("file"):
                asked.add((str(row["site"]["site_id"]), str(row["file"])))
    gallery = gallery_pictures(state, on_disk, excluded, asked)
    # the pool: candidates of shown sites, not asked before (the v1 adjudication drew from it)
    verdicts = {
        (str(v["site_id"]), str(v["file"])): str(v["verdict"])
        for v in _jsonl(args.pool_run / CJ.VERDICTS)
    }
    pool = [
        (str(s["site_id"]), c, verdicts[(str(s["site_id"]), str(c["file"]))])
        for s in _jsonl(args.pool_run / CJ.CANDIDATES)
        for c in s["candidates"]
        if str(s["site_id"]) in state.sites
        and (str(s["site_id"]), str(c["file"])) in verdicts
        and (str(s["site_id"]), str(c["file"])) not in asked
        and c.get("picture_url")
    ]
    pool_path = lambda c: str(PL.picture_path(args.pool_run, c))  # noqa: E731
    seed = int(document["seed"])
    if document["gold"] == DEPICTS_KIND:
        context = {str(r["site_id"]): r for r in pv.read_rows(CAL.DESCRIPTIONS_SQL)}
        cache = WikiCache(args.wiki_cache)

        def site_context(sid: str) -> dict[str, Any]:
            return CAL._site_context(state.sites[sid], context, cache.lead)

        cases, notes = draw_depicts(
            state=state,
            site_context=site_context,
            gallery=gallery,
            pool=pool,
            pool_path=pool_path,
            draw=document["draw"],
            seed=seed,
        )
    else:
        cases, notes = draw_kinds(
            gallery=gallery, pool=pool, pool_path=pool_path, draw=document["draw"], seed=seed
        )
    notes = {**notes, "read_sha256": state.sha256, "read_at": state.read_at}
    digest = write_draw(directory, cases, notes)
    return {
        "draw_sha256": digest,
        "cases": len(cases),
        "sites": len({str(c["site"]["site_id"]) for c in cases}),
        "by_group": dict(Counter(c["group"] for c in cases)),
        "notes": notes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="image_roles/clean_gold.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    names = ("seal", "draw", "void", "label-export", "disputes", "spotcheck", "fix", "export", "evaluate",
             "disagreements")  # fmt: skip
    for name in names:
        sub.add_parser(name).add_argument("--dir", required=True, type=Path)
    sub.choices["seal"].add_argument("--kind", required=True, choices=sorted(THRESHOLDS))
    draw = sub.choices["draw"]
    draw.add_argument("--read", required=True, type=Path)
    draw.add_argument("--wiki-cache", required=True, type=Path)
    draw.add_argument("--pool-run", required=True, type=Path)
    draw.add_argument("--exclude-gold", required=True, type=Path, nargs="+")
    draw.add_argument("--exclude-heroes", required=True, type=Path, nargs="+")
    draw.add_argument("--insert-root", required=True, type=Path)
    sub.choices["void"].add_argument("--case", required=True)
    sub.choices["void"].add_argument("--reason", required=True)
    sub.choices["label-export"].add_argument("--labeller", required=True, choices=["a", "b", "c"])
    sub.choices["label-export"].add_argument("--handoff", required=True, type=Path)
    sub.choices["export"].add_argument("--role", required=True, choices=CAL.MEASURED)
    sub.choices["export"].add_argument("--handoff", required=True, type=Path)
    sub.choices["evaluate"].add_argument("--role", required=True, choices=CAL.MEASURED)
    sub.choices["disagreements"].add_argument("--role", required=True, choices=CAL.MEASURED)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "seal":
            payload: Any = seal(args.dir, args.kind)
        elif args.command == "draw":
            payload = cmd_draw(args.dir, args)
        elif args.command == "void":
            payload = void(args.dir, args.case, args.reason)
        elif args.command == "label-export":
            from pipeline.video.shorts_select import vlm_bytes

            payload = label_export(
                args.dir, args.labeller, args.handoff, lambda c: vlm_bytes(Path(str(c["path"])))
            )
        elif args.command == "disputes":
            payload = disputes(args.dir, write=True)
        elif args.command == "spotcheck":
            payload = spotcheck_list(args.dir)
        elif args.command == "fix":
            payload = fix(args.dir)
        elif args.command == "export":
            payload = export(args.dir, args.role, args.handoff)
        elif args.command == "evaluate":
            payload = evaluate(args.dir, args.role)
        else:
            payload = disagreements(args.dir, args.role)
    except (ST.StateError, RO.RoleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if args.command != "evaluate" or payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
