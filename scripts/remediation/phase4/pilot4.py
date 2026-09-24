"""The Phase-4 pilot: the pilot set and the two documents sealed with it before the first model call.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, key
pilot_and_thresholds ("ARTEFACTS WRITTEN BEFORE THE FIRST CALL", "PILOT SET", the forbidden anchors,
"THRESHOLDS", "ON FAILURE"). No model is called and nothing is written to production; the one
production access here is `routeless`, a single read-only SELECT.

The design writes three artefacts into `output/remediation/phase4_runner/` before any model call,
and their sha256 go into AUDIT_LOG.md before the first model question is exported:

* `PILOT.jsonl` (`build`): one line per pilot site, in the pilot's order - the fixed members, then
  the seeded draws - with the strata that put it there and the census facts it was drawn on.
  `plan4.py build --pilot PILOT.jsonl` then writes `PLAN4.jsonl` with the pilot's own batches first.
* `gold_prose_errors.json` (`prose-errors`): the forbidden anchors of the 15 prose errors the gold
  standard's humans found and of the 10 canary defects, each with its verbatim claim and source.
* `PILOT_THRESHOLDS.md` (`thresholds`): T1-T13 and the failure rules, copied verbatim from the
  design by code, and the dated note of what the owner's orders change around them.

**The order the design's stages imply.** A draw by lane needs the lanes, and the lanes are the
routes stage's (S1b), which needs S1, which needs S0 - so the draw runs over a census of every
curated site through S0, S1 and S1b, and the pilot is drawn from it:

    plan4.py read; plan4.py names; plan4.py build --out PLAN4.census.jsonl      S0 (fresh, read-only)
    pilot4.py routeless                                                          the B3 read
    mass4.py --plan PLAN4.census.jsonl --run-dir runs/<census> --live \\
        --stages prepare,sources,routes --searches-off                          S1, S1b: the lanes
    pilot4.py build --plan PLAN4.census.jsonl --run-dir runs/<census>            PILOT.jsonl
    pilot4.py prose-errors; pilot4.py thresholds
    plan4.py build --pilot PILOT.jsonl                                           PLAN4.jsonl

**The pilot set** (design, "PILOT SET"). Fixed, in this order: the 36 gold-standard sites; the 10
severe canaries; the 3 B5 fixtures; the identity traps - the named pairs and sub-sites, all 7 sites
on 'History'/Q309 (the external-id repair's plan names them, the fresh export shows what is left of
them) and the sites stored with the titles 'Theatre' and 'Mortuary temple'; f6b8fa8a and Wroxeter
Stone. A canary, fixture or trap is resolved from its id prefix and must carry the design's name.
Then the seeded draws, each with seed 20260922 through `audit4.draw_sample`, each excluding every site
placed before it; a stratum with fewer sites is taken whole:

* `draw-W` 30, `draw-S` 8 - the census lanes W and S (`lanes.jsonl`).
* `draw-T-candidate` 6, `draw-R-candidate` 8 - **no MiniMax search is sent** (owner order
  2026-09-23, "everything with Opus"), so the routes stage assigns no lane T or R: a site its free
  routes left without an own English article waits on the search and is held `search-stopped`.
  The candidates are the sites held so whose `source_url` names an article on another-language
  Wikipedia (T: the design's langlinks route) or only http(s) pages on no wiki host (R: design
  entry [2], "whose only route is a non-Wikipedia source_url"). They stay held in the pilot and are
  reported; nobody guesses their lane.
* `draw-B3-routeless` 5 - HUMAN_ONLY B3 ("sites without a text route"): no enwiki title, no QID, no
  http(s) URL in `source_url` and no `site_content_links` URL (AUDIT_LOG, "The routing measurement";
  17 sites on the 2026-09-21 snapshot). `routeless` reads them fresh; `build` refuses a list that the
  plan's own rows contradict.
* `draw-extract-over-40000` 5 - a site of lane W, S or T whose lane source's pinned text is longer
  than 40,000 characters.

**Pilot 2 (2026-09-24, seed 20260924, `PILOT2.jsonl`).** Pilot 1 failed T2, T5 and T8
(`PILOT_RESULT_1.md`); the design's failure rule asks for "a fresh draw of the same strata in a new
run directory". `build --after PILOT.jsonl --seed 20260924 --out PILOT2.jsonl` draws it over the
same census, gold standard, Q309 repair plan and routeless read: **the fixed members are exactly
pilot 1's** - the same code resolves them, and `build` refuses a list that is not PILOT.jsonl's fixed
lines, site for site, in its order, with their strata - and **every seeded stratum is drawn anew with
seed 20260924, excluding pilot 1's seeded draws** (all 62 of them, from every stratum) besides
everything placed before it. A stratum left with fewer eligible sites than asked is taken whole,
as in pilot 1. `PILOT_THRESHOLDS.md` and `gold_prose_errors.json` are pilot 1's, unchanged, byte
for byte: the thresholds were sealed before the first model question and are never changed after.

    pilot4.py build --plan PLAN4.census.jsonl --run-dir runs/census-2026-09-24 \\
        --after PILOT.jsonl --seed 20260924 --out PILOT2.jsonl                   PILOT2.jsonl
    plan4.py build --pilot PILOT2.jsonl --out PLAN4.pilot2.jsonl                   S0

**Pilot 3 (2026-09-24, seed 20260925, `PILOT3.jsonl`).** Pilot 2 failed T3, T4, T6 and T8
(`PILOT_RESULT_2.md`). `--after` is given once per earlier pilot: every one's fixed members must be
this pilot's, site for site and in order, and the seeded draws of all of them are excluded (pilots
1 and 2: 124 sites). The thresholds and the prose errors stay pilot 1's, byte for byte.

    pilot4.py build --plan PLAN4.census.jsonl --run-dir runs/census-2026-09-24 \\
        --after PILOT.jsonl --after PILOT2.jsonl --seed 20260925 --out PILOT3.jsonl
    plan4.py build --pilot PILOT3.jsonl --out PLAN4.pilot3.jsonl                   S0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import run as R  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

from phase4 import audit4 as AU  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import licences as LIC  # noqa: E402
from phase4 import mass4 as M4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import plan4 as P4  # noqa: E402
from phase4 import route_stage as RS  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402

REPO = P4.REPO
RUNNER = P4.RUNNER
OUTPUT = REPO / "output" / "remediation"
DEFAULT_CENSUS_PLAN = RUNNER / "PLAN4.census.jsonl"
DEFAULT_ROUTELESS = RUNNER / "S0_ROUTELESS.json"
DEFAULT_PROSE_ERRORS = RUNNER / "gold_prose_errors.json"
DEFAULT_THRESHOLDS = RUNNER / "PILOT_THRESHOLDS.md"
DEFAULT_QID_REPAIR = OUTPUT / "qid_repair" / "PLAN.jsonl"
DEFAULT_REMEDIATION_PLAN = REPO / "docs" / "procedures" / "SITES_DB_REMEDIATION_2026-09.md"
DESIGN = OUTPUT / "logs" / "design_texts_images_2026-09-22.json"
#: The design file's digest as `docs/procedures/PHASE4_CONTRACTS.md` pins it.
DESIGN_SHA256 = "515601c3e91a770ce096ee001e6bfc1659c875d008f11d1b508d07a31d20e5af"
DESIGN_ENTRY = 6

SEED = 20260922
#: Pilot 2's seed (module docstring): its seeded strata are drawn anew, pilot 1's draws excluded.
SEED_PILOT2 = 20260924
#: Pilot 3's seed (module docstring): drawn anew again, pilots 1's and 2's draws excluded.
SEED_PILOT3 = 20260925
EXTRACT_OVER = 40_000
#: The design names 7 sites on Q309 'history' (entries [5] and [6]).
Q309_SITES = 7
HISTORY_QID = "Q309"
HISTORY_TITLE = "History"


@dataclass(frozen=True)
class Named:
    """A site the design names by id prefix (and by name, except f6b8fa8a)."""

    prefix: str
    name: str | None
    stratum: str


CANARIES: tuple[Named, ...] = (
    Named("2968fd35", "Hatunmarka", "canary"),
    Named("411cacb0", "Kit Hill", "canary"),
    Named("c5747999", "Partiscum (Castra)", "canary"),
    Named("45ac8925", "House of Taga", "canary"),
    Named("3dd6b568", "Maray Qalla", "canary"),
    Named("0569a73d", "Justinianopolis (Epirus)", "canary"),
    Named("09327f42", "Eileithyia Cave", "canary"),
    Named("d3b11ebc", "Neos Panteleimonas", "canary"),
    Named("006294ae", "El Tintal", "canary"),
    Named("786cada5", "Ahin Posh Tape", "canary"),
)
B5_FIXTURES: tuple[Named, ...] = (
    Named("32429f3c", "Midford Castle", "b5-fixture"),
    Named("0529af31", "Bulls of Guisando", "b5-fixture"),
    Named("82f23c96", "Arc de Berà", "b5-fixture"),
)
IDENTITY_TRAPS: tuple[Named, ...] = (
    Named("318414bc", "Templos de Tarxien", "identity-trap"),
    Named("4a5a324f", "Tarxien Temples", "identity-trap"),
    Named("f5ca382a", "Dooey's Cairn", "identity-trap"),
    Named("f6b6e039", "Ballymacaldrack", "identity-trap"),
    Named("9b998265", "America's Stonehenge", "identity-trap"),
    Named("6f6cebaa", "Altar Stone - Stonehenge", "identity-trap"),
    Named("72980dbd", "Station Stones", "identity-trap"),
    Named("5752ff6c", "House of the Faun", "identity-trap"),
)
#: The generic titles whose sites are identity traps, besides 'History'/Q309.
TRAP_TITLES: tuple[tuple[str, str], ...] = (
    ("Theatre", "identity-trap-theatre"),
    ("Mortuary temple", "identity-trap-mortuary-temple"),
)
SPECIAL: tuple[Named, ...] = (
    Named("f6b8fa8a", None, "boot-seeded-grokipedia-citation"),
    Named("dae9bc10", "Wroxeter Stone", "bracket-notation"),
)

DRAW_W = "draw-W"
DRAW_S = "draw-S"
DRAW_T = "draw-T-candidate"
DRAW_R = "draw-R-candidate"
DRAW_B3 = "draw-B3-routeless"
DRAW_LONG = "draw-extract-over-40000"
#: The seeded draws, in the design's order, with the count it asks for.
DRAWS: tuple[tuple[str, int], ...] = (
    (DRAW_W, 30),
    (DRAW_S, 8),
    (DRAW_T, 6),
    (DRAW_R, 8),
    (DRAW_B3, 5),
    (DRAW_LONG, 5),
)

#: The routeless read (HUMAN_ONLY B3): one read-only SELECT, one `to_jsonb` object per site.
ROUTELESS_SQL = (
    "SELECT to_jsonb(x)::text FROM (SELECT u.id::text AS id, u.name FROM unified_sites u "
    f"WHERE u.source_id = '{W.CURATED_SOURCE}' "
    "AND NOT EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = u.id "
    "AND e.kind IN ('enwiki_title', 'wikidata_qid')) "
    "AND (u.source_url IS NULL OR u.source_url !~ 'https?://') "
    "AND NOT EXISTS (SELECT 1 FROM site_content_links l WHERE l.site_id = u.id "
    "AND l.content_url ~ '^https?://') ORDER BY u.id) x;"
)
_HTTP_ANYWHERE = re.compile(r"https?://")


# ------------------------------------------------------------------------------------ the census


@dataclass(frozen=True)
class Census:
    """What S1 and S1b decided for one site: its lane, its site holds, its lane source's length."""

    batch_id: str
    lane: M.Lane
    holds: tuple[str, ...]
    extract_chars: int | None


def read_census(plan: Path, run_dir: Path) -> tuple[dict[str, M.PlanSite], dict[str, Census]]:
    """Every site of the plan and its census facts, from the run directory's batches.

    The run must be the plan's: each batch's `input.json` holds exactly its plan line's sites, and
    each batch finished S1b (`routes.json`). A site re-queued by the driver counts in its latest
    batch, as `run4.aggregate_holds` counts it.
    """
    lines = M4.read_plan4_lines(plan)
    lines = [*lines, *M4.read_requeue(run_dir, lines)]
    latest = {site.site_id: line.batch_id for line in lines for site in line.sites}
    sites = {site.site_id: site for line in lines for site in line.sites}
    census: dict[str, Census] = {}
    for line in lines:
        batch_dir = run_dir / line.batch_id
        if not (batch_dir / RS.ROUTES_REPORT).exists():
            raise R.InputError(f"{batch_dir}: no {RS.ROUTES_REPORT}; the census is not complete")
        _, batch_sites = B.read_batch(batch_dir)
        if tuple(batch_sites) != line.sites:
            raise R.InputError(
                f"{batch_dir}: its input.json is not the plan's line {line.batch_id}"
            )
        lanes = B.read_lanes(batch_dir, batch_sites)
        held: dict[str, set[str]] = {}
        for hold in B.read_holds(batch_dir):
            if hold.scope is M.HoldScope.SITE:
                held.setdefault(hold.site_id, set()).add(hold.reason.value)
        for site in line.sites:
            if latest[site.site_id] != line.batch_id:
                continue
            lane = lanes[site.site_id]
            chars = None
            if lane.lane in (M.Lane.W, M.Lane.S, M.Lane.T):
                (source_id,) = lane.sources
                chars = len(B.read_source(batch_dir, site.site_id, source_id)[1])
            census[site.site_id] = Census(
                batch_id=line.batch_id,
                lane=lane.lane,
                holds=tuple(sorted(held.get(site.site_id, set()))),
                extract_chars=chars,
            )
    return sites, census


# ------------------------------------------------------------------------------------ the strata


def _names_the_site(names: Iterable[str], name: str) -> bool:
    """The design's name, folded, occurs as whole words in one of the stored names."""
    wanted = f" {SG.fold(name)} "
    return any(wanted in f" {SG.fold(stored)} " for stored in names)


def resolve(named: Named, sites: Mapping[str, M.PlanSite]) -> str:
    """The one curated site the design names by id prefix, which must carry the design's name."""
    found = sorted(site_id for site_id in sites if site_id.startswith(named.prefix))
    if len(found) != 1:
        raise R.InputError(f"{named.prefix} ({named.name}) names {len(found)} curated sites")
    site = sites[found[0]]
    if named.name is not None and not _names_the_site((site.name, *site.aliases), named.name):
        raise R.InputError(f"{found[0]} is {site.name!r}, not the design's {named.name!r}")
    return found[0]


def q309_sites(repair: Iterable[Mapping[str, Any]], sites: Mapping[str, M.PlanSite]) -> list[str]:
    """The 7 sites on 'History'/Q309: those the external-id repair moved off Q309, and any site the
    fresh export still stores on Q309 or the title 'History'. Any other count is refused."""
    ids = {
        str(row["site_id"])
        for row in repair
        if row.get("kind") == "wikidata_qid" and row.get("old_value") == HISTORY_QID
    }
    ids |= {
        site_id
        for site_id, site in sites.items()
        if site.wikidata_qid == HISTORY_QID or site.enwiki_title == HISTORY_TITLE
    }
    strangers = sorted(ids - set(sites))
    if strangers:
        raise R.InputError(f"Q309 sites that are not curated rows: {strangers}")
    if len(ids) != Q309_SITES:
        raise R.InputError(f"the design names {Q309_SITES} sites on 'History'/Q309, not {len(ids)}")
    return sorted(ids)


def _waits_on_the_search(census: Census) -> bool:
    return census.lane is M.Lane.ZERO and M.HoldReason.SEARCH_STOPPED.value in census.holds


def is_t_candidate(site: M.PlanSite, census: Census) -> bool:
    """Held for its search, with a `source_url` article on another-language Wikipedia."""
    if not _waits_on_the_search(census):
        return False
    titles = [RS.wikipedia_title(url) for url in RS.source_urls(site)]
    return any(title is not None and title[0] != "en" for title in titles)


def is_r_candidate(site: M.PlanSite, census: Census) -> bool:
    """Held for its search, with only http(s) pages on no wiki host in its `source_url` (a
    Wikipedia article URL is on a wiki host, so it is no R page either)."""
    if not _waits_on_the_search(census):
        return False
    hosts = [host for host in map(_web_host, RS.source_urls(site)) if host is not None]
    return bool(hosts) and not any(LIC.is_wiki_host(host) for host in hosts)


def _web_host(url: str) -> str | None:
    """The host of an http(s) URL that has one; anything else (`www.x.org/...`, `https://`) is no
    page a fetch could ask, as `route_stage.wikipedia_title` reads it."""
    try:
        return LIC.host_of(url)
    except ValueError:
        return None


def routeless_ids(
    routeless: Sequence[Mapping[str, Any]], sites: Mapping[str, M.PlanSite]
) -> set[str]:
    """The B3 read, checked against the plan's own rows: a routeless site stores no title, no QID
    and no http(s) URL. A disagreement means the two reads saw different databases: refused."""
    ids: set[str] = set()
    for row in routeless:
        site_id = row.get("id")
        site = sites.get(str(site_id))
        if site is None:
            raise R.InputError(
                f"the routeless read names {site_id!r}, which the plan does not have"
            )
        if (
            site.enwiki_title is not None
            or site.wikidata_qid is not None
            or _HTTP_ANYWHERE.search(site.source_url or "")
        ):
            raise R.InputError(f"{site_id}: the plan's row has a route the routeless read denies")
        ids.add(site.site_id)
    return ids


def populations(
    sites: Mapping[str, M.PlanSite], census: Mapping[str, Census], routeless: set[str]
) -> dict[str, list[str]]:
    """Every draw stratum's population, sorted by site id (module docstring)."""
    missing = sorted(set(sites) - set(census))
    if missing:
        raise R.InputError(f"{len(missing)} site(s) without census facts, first {missing[0]}")
    tests: dict[str, Callable[[M.PlanSite, Census], bool]] = {
        DRAW_W: lambda site, facts: facts.lane is M.Lane.W,
        DRAW_S: lambda site, facts: facts.lane is M.Lane.S,
        DRAW_T: is_t_candidate,
        DRAW_R: is_r_candidate,
        DRAW_B3: lambda site, facts: site.site_id in routeless,
        DRAW_LONG: lambda site, facts: (facts.extract_chars or 0) > EXTRACT_OVER,
    }
    return {
        stratum: sorted(sid for sid, site in sites.items() if test(site, census[sid]))
        for stratum, test in tests.items()
    }


#: Every seeded stratum's name: a pilot line is a draw when its stratum is one of these.
DRAW_STRATA = frozenset(stratum for stratum, _ in DRAWS)


def earlier_pilot(
    lines: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[str, list[str]]], set[str]]:
    """An earlier pilot's fixed members (site id and strata, in its order) and its seeded draws.

    A line is a draw when its one stratum is a seeded one, and fixed when none of its strata is;
    a line that mixes the two, or names two draws, is no line `build_pilot` writes: refused."""
    fixed: list[tuple[str, list[str]]] = []
    drawn: set[str] = set()
    for number, line in enumerate(lines, start=1):
        site_id, strata = str(line["site_id"]), [str(s) for s in line["strata"]]
        seeded = [stratum for stratum in strata if stratum in DRAW_STRATA]
        if not seeded:
            fixed.append((site_id, strata))
        elif strata == seeded and len(seeded) == 1:
            drawn.add(site_id)
        else:
            raise R.InputError(f"line {number}: {site_id} is neither fixed nor one draw: {strata}")
    return fixed, drawn


def build_pilot(
    sites: Mapping[str, M.PlanSite],
    census: Mapping[str, Census],
    *,
    gold: Sequence[str],
    q309: Sequence[str],
    routeless: set[str],
    seed: int,
    earlier: Sequence[Sequence[Mapping[str, Any]]] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The pilot's lines, in order, and the draw's summary (module docstring).

    `earlier` holds the lines of every earlier pilot (pilot 2: pilot 1's `PILOT.jsonl`; pilot 3:
    `PILOT.jsonl` and `PILOT2.jsonl`): each one's fixed members must be exactly this pilot's, and
    the seeded draws of all of them are excluded from every stratum of this one."""
    strata: dict[str, list[str]] = {}

    def place(site_id: str, stratum: str) -> None:
        if site_id not in sites:
            raise R.InputError(f"{stratum}: {site_id} is not a site of the plan")
        strata.setdefault(site_id, []).append(stratum)

    for site_id in gold:
        place(site_id, "gold-standard")
    for named in (*CANARIES, *B5_FIXTURES, *IDENTITY_TRAPS):
        place(resolve(named, sites), named.stratum)
    for site_id in q309:
        place(site_id, "identity-trap-q309-history")
    for title, stratum in TRAP_TITLES:
        for site_id in sorted(s for s, site in sites.items() if site.enwiki_title == title):
            place(site_id, stratum)
    for named in SPECIAL:
        place(resolve(named, sites), named.stratum)
    fixed = len(strata)
    earlier_drawn: set[str] = set()
    for number, lines_before in enumerate(earlier, start=1):
        earlier_fixed, drawn_before = earlier_pilot(lines_before)
        if list(strata.items()) != earlier_fixed:
            raise R.InputError(
                f"the fixed members are not the earlier pilot's (--after number {number}), site "
                "for site and in order"
            )
        earlier_drawn |= drawn_before
    pools = populations(sites, census, routeless)
    draws: dict[str, dict[str, int]] = {}
    for stratum, count in DRAWS:
        before = set(strata) | earlier_drawn
        drawn = AU.draw_sample(pools[stratum], seed=seed, count=count, exclude=before)
        for site_id in drawn:
            place(site_id, stratum)
        draws[stratum] = {
            "asked": count,
            "population": len(pools[stratum]),
            "eligible": len(set(pools[stratum]) - before),
            "taken": len(drawn),
        }
    lines = [
        {
            "site_id": site_id,
            "name": sites[site_id].name,
            "strata": names,
            "census_batch": census[site_id].batch_id,
            "census_lane": census[site_id].lane.value,
            "census_holds": list(census[site_id].holds),
            "census_extract_chars": census[site_id].extract_chars,
        }
        for site_id, names in strata.items()
    ]
    summary = {"seed": seed, "fixed": fixed, "sites": len(lines), "draws": draws}
    if earlier:
        summary["earlier_draws_excluded"] = len(earlier_drawn)
    return lines, summary


def write_pilot(path: Path, lines: Sequence[Mapping[str, Any]]) -> None:
    body = "".join(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n" for line in lines)
    B.write_text_atomic(path, body)


# --------------------------------------------------------------------------- the prose errors

#: The human-found prose errors of the gold standard: error id -> (the text field that carries the
#: error, the anchors). Every anchor is a substring of that field in the gold record's `db_fields`
#: (checked by `prose_errors`), and every gold error whose field names a text field is listed.
GOLD_ANCHORS: dict[str, tuple[str, tuple[str, ...]]] = {
    "LS-1": ("description", ("late Archaic to Middle Formative", "1000 BC-300 AD")),
    "LM-2": ("card_description", ("48,000 BC",)),
    "ABe-1": ("description", ("through the will of Lucius Licinius Sura",)),
    "AT-1": ("description", ("constructed between 1-500 AD",)),
    "GP-1": ("description", ("14 m high", "101 m")),
    "GP-3": ("card_description", ("5th-4th millennium BC",)),
    "BG-1": ("description", ("El Tiémblo",)),
    "PC-1": ("card_description", ("copied Egyptian style",)),
    "OV-1": ("card_description", ("70 square barrows", "Arras culture", "Over 160 skeletons")),
    "MM-1": ("description", ("4500-3000 BC",)),
    "FC-2": ("description", ("is a spring in Andorra la Vella",)),
    "AM-1": ("card_description", ("King Amyntas",)),
    "TD-1": ("description", ("Dedun was a Kushite or Nehasi god",)),
    "BH-1": ("card_description", ("80-hectare fort",)),
    "OC-1": ("description", ("Roman temple to Jupiter (1st c. AD)",)),
}
GOLD_PROSE_ERRORS = 15
TEXT_FIELDS = ("description", "card_description")
#: The S0 row key of each text field.
ROW_FIELD = {"description": "description", "card_description": "card"}

PLAN_42 = "docs/procedures/SITES_DB_REMEDIATION_2026-09.md, section 4.2"
PLAN_51 = "docs/procedures/SITES_DB_REMEDIATION_2026-09.md, section 5.1"
DESIGN_2 = "output/remediation/logs/design_texts_images_2026-09-22.json, entry [2]"
DESIGN_5 = "output/remediation/logs/design_texts_images_2026-09-22.json, entry [5]"
DESIGN_6 = "output/remediation/logs/design_texts_images_2026-09-22.json, entry [6]"


@dataclass(frozen=True)
class Canary:
    """One canary defect: its claim, verbatim from its source, and its anchors.

    `anchors` are `(field, text)`: with a field, the text occurs in that stored field of the fresh
    export (checked); with `None`, it is the defect's own value that no stored text carries now, and
    `note` says why it is forbidden. `quotes` are `(source, text)` the note leans on, each verbatim
    in its source (checked, like the claim).
    """

    prefix: str
    field: str
    claim: str
    source: str
    anchors: tuple[tuple[str | None, str], ...]
    note: str | None
    quotes: tuple[tuple[str, str], ...] = ()


CANARY_DEFECTS: tuple[Canary, ...] = (
    Canary(
        "2968fd35",
        "card_description",
        "Card text describes **Choquequirao**, 400 km away",
        PLAN_42,
        (("card_description", "Choquequirao"), ("card_description", "Apurimac gorge")),
        "Section 5.1 quotes the stored card; the design names the defect.",
        (
            (PLAN_51, "Hatunmarka … below Choquequirao, above the Apurímac gorge"),
            (DESIGN_6, "Choquequirao on Hatunmarka"),
        ),
    ),
    Canary(
        "411cacb0",
        "description",
        "Description asserts a hillfort — there is none",
        PLAN_42,
        (("description", "hillfort"),),
        None,
    ),
    Canary(
        "c5747999",
        "description",
        "Description invents a fort in Dacia; it was a settlement / road station",
        PLAN_42,
        (
            ("description", "Roman fort in the province of Dacia"),
            ("description", "most western fort of Dacia"),
            ("card_description", "westernmost fort of Roman Dacia"),
        ),
        "The stored card repeats the description's fort.",
    ),
    Canary(
        "45ac8925",
        "card_description",
        "House of Taga … from a site occupied as early as 10,000 BC",
        PLAN_51,
        (("card_description", "10,000 BC"),),
        "Section 5.1 gives the settlement of the Marianas; the design names the defect.",
        (
            (PLAN_51, "(the Marianas were settled around 1500 BC)"),
            (DESIGN_6, "'10,000 BC' on House of Taga"),
        ),
    ),
    Canary(
        "3dd6b568",
        "card_description",
        "Maray Qalla … Inca road system that stretched over 30,000 km",
        PLAN_51,
        (("card_description", "30,000 km"),),
        "The design names the defect.",
        ((DESIGN_6, "'30,000 km' on Maray Qalla"),),
    ),
    Canary(
        "0569a73d",
        "period_start",
        "`period_start = -500`, actually 6th c. AD → off by 1,000 years and several buckets",
        PLAN_42,
        (("card_description", "3rd-century BC"),),
        "The stored card dates the city to the 3rd century BC, the BC dating the claim refutes "
        "(the town took Justinian I's name in the 6th century AD, as the stored description says).",
    ),
    Canary(
        "09327f42",
        "period_start",
        "`period_start = -500`, actually in use from the Neolithic",
        PLAN_42,
        (),
        "A field defect: the stored description and card both say the cave was used from the "
        "Neolithic, so no stored text carries it. A text that starts the cave's use at c. 500 BC "
        "would be its recurrence; the audit judges it against the claim.",
    ),
    Canary(
        "d3b11ebc",
        "period_start",
        "A 20th-century village carrying `period_start = -1000`; does not belong in an archaeology "
        "database",
        PLAN_42,
        (("card_description", "from the 1st millennium BC"),),
        "The stored card dates the modern village to the 1st millennium BC.",
    ),
    Canary(
        "006294ae",
        "coordinates",
        "Coordinate sits 11–12 km off the actual site (correct: 17.5744 / −89.9958)",
        PLAN_42,
        (),
        "A coordinate defect: Phase 4 writes no coordinate and no stored text carries it; listed "
        "because the design names the canary.",
    ),
    Canary(
        "786cada5",
        "wikidata_qid",
        "for example Ahin Posh -> a Pakistani village",
        DESIGN_5,
        ((None, "Pakistan"),),
        "The stored item Q4695118 is a village in Pakistan (output/remediation/bcases/coords.jsonl: "
        "container-item, P17 Pakistan); the site is the stupa near Jalalabad, Afghanistan, as the "
        "stored description says. Design entry [2] records the country the wrong item gave. A text "
        "about that village, or one that places the site in Pakistan, is the recurrence "
        "(WRONG_SITE).",
        (
            (
                DESIGN_2,
                "Location fact contradicts the stored country (e.g. Ahin Posh 'Jalalabad, "
                "Afghanistan' vs stored Pakistan)",
            ),
        ),
    ),
)


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gold_errors(gold: Mapping[str, Any], gold_path: str) -> list[dict[str, Any]]:
    """The 15 prose errors of the gold standard, their claims copied, their anchors checked."""
    entries: list[dict[str, Any]] = []
    for index, record in enumerate(gold["records"]):
        for number, error in enumerate(record["errors_found"]):
            if not set(str(error["field"]).split(" + ")) & set(TEXT_FIELDS):
                continue
            if error["id"] not in GOLD_ANCHORS:
                raise R.InputError(f"{error['id']}: a prose error with no anchors in GOLD_ANCHORS")
            text_field, anchors = GOLD_ANCHORS[error["id"]]
            text = record["db_fields"][text_field]
            for anchor in anchors:
                if anchor not in text:
                    raise R.InputError(f"{error['id']}: {anchor!r} is not in its {text_field}")
            entries.append(
                {
                    "id": error["id"],
                    "kind": "gold",
                    "site_id": record["site_id"],
                    "site_name": record["site_name"],
                    "field": error["field"],
                    "severity": error["severity"],
                    "claim": error["claim"],
                    "source": f"{gold_path} records[{index}].errors_found[{number}]",
                    "anchors": [{"field": text_field, "text": anchor} for anchor in anchors],
                    "note": None,
                    "quotes": [],
                }
            )
    listed = {entry["id"] for entry in entries}
    if listed != set(GOLD_ANCHORS) or len(entries) != GOLD_PROSE_ERRORS:
        raise R.InputError(
            f"the gold standard's prose errors {sorted(listed)} are not the "
            f"{GOLD_PROSE_ERRORS} GOLD_ANCHORS names"
        )
    return entries


def canary_errors(
    rows: Mapping[str, Mapping[str, Any]], sources: Mapping[str, str]
) -> list[dict[str, Any]]:
    """The 10 canary defects: each claim verbatim in its source, each stored anchor in the export.

    `rows` are the fresh S0 rows by site id; `sources` maps each source label to its text.
    """
    if [canary.prefix for canary in CANARY_DEFECTS] != [named.prefix for named in CANARIES]:
        raise R.InputError("the canary defects are not the design's 10 canaries, in its order")
    entries: list[dict[str, Any]] = []
    for number, (canary, named) in enumerate(zip(CANARY_DEFECTS, CANARIES, strict=True), start=1):
        found = [site_id for site_id in rows if site_id.startswith(canary.prefix)]
        if len(found) != 1:
            raise R.InputError(f"{canary.prefix}: {len(found)} rows of the export")
        row = rows[found[0]]
        if not _names_the_site((row["name"], *row["names"]), str(named.name)):
            raise R.InputError(f"{found[0]} is {row['name']!r}, not the canary {named.name!r}")
        for source, text in ((canary.source, canary.claim), *canary.quotes):
            if _collapsed(text) not in _collapsed(sources[source]):
                raise R.InputError(f"{canary.prefix}: {text!r} is not verbatim in {source}")
        for field, anchor in canary.anchors:
            if field is None:
                if not canary.note:
                    raise R.InputError(f"{canary.prefix}: {anchor!r} is in no stored text; why?")
                continue
            if anchor not in (row[ROW_FIELD[field]] or ""):
                raise R.InputError(f"{canary.prefix}: {anchor!r} is not in the stored {field}")
        if not canary.anchors and not canary.note:
            raise R.InputError(f"{canary.prefix}: no anchor and no note saying why")
        entries.append(
            {
                "id": f"CANARY-{number:02d}",
                "kind": "canary",
                "site_id": found[0],
                "site_name": row["name"],
                "field": canary.field,
                "severity": "severe",
                "claim": canary.claim,
                "source": canary.source,
                "anchors": [{"field": field, "text": anchor} for field, anchor in canary.anchors],
                "note": canary.note,
                "quotes": [{"source": source, "text": text} for source, text in canary.quotes],
            }
        )
    return entries


def design_entries(path: Path) -> list[Any]:
    """The design file's entries; its digest must be the one PHASE4_CONTRACTS.md pins."""
    if _sha256(path) != DESIGN_SHA256:
        raise R.InputError(f"{path} is not the design file PHASE4_CONTRACTS.md pins")
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise R.InputError(f"{path}: the design file is not a list of entries")
    return entries


def prose_errors(
    *, gold_path: Path, rows_path: Path, plan_doc: Path, design: Path
) -> dict[str, Any]:
    """`gold_prose_errors.json`: the 15 gold prose errors, then the 10 canary defects."""
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    rows = {str(row["id"]): row for row in R.read_jsonl(rows_path)}
    entries = design_entries(design)
    plan_text = plan_doc.read_text(encoding="utf-8")
    sources = {
        PLAN_42: plan_text,
        PLAN_51: plan_text,
        DESIGN_2: "\n".join(_strings(entries[2])),
        DESIGN_5: "\n".join(_strings(entries[5])),
        DESIGN_6: "\n".join(_strings(entries[DESIGN_ENTRY])),
    }
    errors = [
        *gold_errors(gold, _relative(gold_path)),
        *canary_errors(rows, sources),
    ]
    return {
        "version": 1,
        "design": "entry [6] of output/remediation/logs/design_texts_images_2026-09-22.json, "
        "pilot_and_thresholds: gold_prose_errors.json lists forbidden anchors",
        "inputs": {
            "gold_standard": {"path": _relative(gold_path), "sha256": _sha256(gold_path)},
            "export": {"path": _relative(rows_path), "sha256": _sha256(rows_path)},
            "plan": {"path": _relative(plan_doc), "sha256": _sha256(plan_doc)},
            "design": {"path": _relative(design), "sha256": DESIGN_SHA256},
        },
        "errors": errors,
    }


def _relative(path: Path) -> str:
    resolved = path.resolve()
    return resolved.relative_to(REPO).as_posix() if resolved.is_relative_to(REPO) else str(path)


# ------------------------------------------------------------------------------- the thresholds

THRESHOLDS_HEAD = "THRESHOLDS (fixed now; never loosened after the data is seen)\n"
FAILURE_HEAD = "ON FAILURE\n"
AFTER_FAILURE = "\n\nMASS RUN GATES"

THRESHOLDS_NOTE = """\
## Note, 2026-09-24 - written before the first model question of this pilot was exported

- **The answering model is Opus, through the handoff.** By the owner's order of 2026-09-23 ("no
  DeepSeek any more - everything with Opus"), every model question of this pilot - selector,
  translator, restricted lane, reviewer - is exported to a handoff directory and answered by an Opus
  agent of the orchestrating Claude Code session (`scripts/remediation/opus_handoff.py`,
  `OPUS_MODEL` = `anthropic/claude-opus-5-5 (Claude Code agent)`), never by a model API called from
  the pipeline. The design's "opencode-go/deepseek-v4.1-flash through Pi" does not run.
- **MiniMax route searches are not used** (owner order, "everything with Opus"). The routes stage
  (S1b) runs with a search allowance of 0 (`mass4.py --searches-off`): it builds no MiniMax client
  and sends no search. A site its free routes (the `source_url` title, langlinks, geosearch) leave
  without an own English article waits on the search and is **held `search-stopped`** by the route
  stage, and is reported - its lane is never guessed. The pilot's lane-T and lane-R strata are
  therefore candidates held so (`phase4/pilot4.py`).
- **What follows from the two orders, under the thresholds as written above (none is changed or
  loosened):** the design's pilot step 3 ("20 MiniMax searches between two quota probes") is not
  run, so T13 has no search to record; no site reaches lane T or R, so T11 ("over at least 8 sites")
  and T12 ("over at least 5 sites") cannot be met - lanes T and R do not pass their pilot and none
  of their sites is written; T9's dollar bound reads a ledger whose Opus lines are unmetered
  (`metering: unmetered`, cost 0): the ledger's dollars measure nothing, and the pilot reports the
  number of unmetered calls instead of a price. T9's parse-failure bound, and T1-T8 and T10, apply
  unchanged.
"""


def threshold_blocks(text: str) -> tuple[str, str]:
    """The design's THRESHOLDS block and its ON FAILURE block, each exactly as written."""
    start = text.index(THRESHOLDS_HEAD)
    failure = text.index(FAILURE_HEAD, start)
    end = text.index(AFTER_FAILURE, failure)
    return text[start:failure].rstrip("\n"), text[failure:end]


def thresholds_document(entry: Mapping[str, Any]) -> str:
    thresholds, failure = threshold_blocks(entry["pilot_and_thresholds"])
    return (
        "# Phase-4 pilot thresholds, sealed before the first model question\n\n"
        f"Source: entry [{DESIGN_ENTRY}] of `output/remediation/logs/design_texts_images_2026-09-22"
        f".json` (sha256 `{DESIGN_SHA256}`), key `pilot_and_thresholds`. The two blocks between the "
        "rules are copied verbatim by `scripts/remediation/phase4/pilot4.py thresholds`. They are "
        "fixed: nothing in them changes after the first model question is exported.\n\n"
        "---\n\n"
        f"{thresholds}\n\n{failure}\n\n"
        "---\n\n"
        f"{THRESHOLDS_NOTE}"
    )


# --------------------------------------------------------------------------------------- CLI


def cmd_routeless(args: argparse.Namespace, *, runner: W.SqlRunner = W.run_sql) -> int:
    rows = W._json_rows(runner(ROUTELESS_SQL, host=args.host))
    payload = {
        "read_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "sql": ROUTELESS_SQL,
        "sites": sorted(({"id": r["id"], "name": r["name"]} for r in rows), key=lambda r: r["id"]),
    }
    B.write_text_atomic(
        Path(args.out), json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    )
    print(json.dumps({"out": str(args.out), "sites": len(rows)}, sort_keys=True))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    plan, run_dir = Path(args.plan), Path(args.run_dir)
    sites, census = read_census(plan, run_dir)
    routeless_payload = json.loads(Path(args.routeless).read_text(encoding="utf-8"))
    earlier = [R.read_jsonl(Path(path)) for path in args.after]
    lines, summary = build_pilot(
        sites,
        census,
        gold=R._gold_site_ids(Path(args.gold)),
        q309=q309_sites(R.read_jsonl(Path(args.qid_repair)), sites),
        routeless=routeless_ids(routeless_payload["sites"], sites),
        seed=args.seed,
        earlier=earlier,
    )
    out = Path(args.out)
    write_pilot(out, lines)
    lanes: dict[str, int] = {}
    for line in lines:
        lanes[line["census_lane"]] = lanes.get(line["census_lane"], 0) + 1
    summary.update(
        out=str(out),
        sha256=_sha256(out),
        census_lanes=dict(sorted(lanes.items())),
        inputs={
            "plan": _sha256(plan),
            "routeless": _sha256(Path(args.routeless)),
            "gold": _sha256(Path(args.gold)),
            "qid_repair": _sha256(Path(args.qid_repair)),
            **({"after": [_sha256(Path(path)) for path in args.after]} if args.after else {}),
        },
    )
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def cmd_prose_errors(args: argparse.Namespace) -> int:
    payload = prose_errors(
        gold_path=Path(args.gold),
        rows_path=Path(args.rows),
        plan_doc=Path(args.plan_doc),
        design=Path(args.design),
    )
    out = Path(args.out)
    B.write_text_atomic(out, json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    kinds = [error["kind"] for error in payload["errors"]]
    print(
        json.dumps(
            {"out": str(out), "gold": kinds.count("gold"), "canary": kinds.count("canary")},
            sort_keys=True,
        )
    )
    return 0


def cmd_thresholds(args: argparse.Namespace) -> int:
    out = Path(args.out)
    entry = design_entries(Path(args.design))[DESIGN_ENTRY]
    B.write_text_atomic(out, thresholds_document(entry))
    print(json.dumps({"out": str(out), "sha256": _sha256(out)}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pilot4", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    routeless = sub.add_parser("routeless", help="the B3 read: one read-only production SELECT")
    routeless.add_argument("--out", default=str(DEFAULT_ROUTELESS))
    routeless.add_argument("--host", default=W.SSH_HOST)
    routeless.set_defaults(handler=cmd_routeless)
    build = sub.add_parser("build", help="PILOT.jsonl: the seeded draw over the census")
    build.add_argument("--plan", default=str(DEFAULT_CENSUS_PLAN))
    build.add_argument("--run-dir", required=True, help="the census run (S1 and S1b over the plan)")
    build.add_argument("--routeless", default=str(DEFAULT_ROUTELESS))
    build.add_argument("--gold", default=str(P4.DEFAULT_GOLD))
    build.add_argument("--qid-repair", default=str(DEFAULT_QID_REPAIR))
    build.add_argument("--seed", type=int, default=SEED)
    build.add_argument(
        "--after",
        action="append",
        default=[],
        help="an earlier pilot (PILOT.jsonl), once per pilot: keep its fixed members, exclude its "
        "seeded draws",
    )
    build.add_argument("--out", default=str(P4.DEFAULT_PILOT))
    build.set_defaults(handler=cmd_build)
    prose = sub.add_parser("prose-errors", help="gold_prose_errors.json: the forbidden anchors")
    prose.add_argument("--gold", default=str(P4.DEFAULT_GOLD))
    prose.add_argument("--rows", default=str(P4.DEFAULT_ROWS))
    prose.add_argument("--plan-doc", default=str(DEFAULT_REMEDIATION_PLAN))
    prose.add_argument("--design", default=str(DESIGN))
    prose.add_argument("--out", default=str(DEFAULT_PROSE_ERRORS))
    prose.set_defaults(handler=cmd_prose_errors)
    thresholds = sub.add_parser("thresholds", help="PILOT_THRESHOLDS.md, verbatim from the design")
    thresholds.add_argument("--design", default=str(DESIGN))
    thresholds.add_argument("--out", default=str(DEFAULT_THRESHOLDS))
    thresholds.set_defaults(handler=cmd_thresholds)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand and print `STAGE_EXIT=<code>`: that line is what a caller reads."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        code = args.handler(args)
    except BaseException:
        print("STAGE_EXIT=1", flush=True)
        raise
    print(f"STAGE_EXIT={code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
