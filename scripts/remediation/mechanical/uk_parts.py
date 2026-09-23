"""B9: spell the United Kingdom's parts by region - the mechanical UK lane.

## The decision

The owner decided on 2026-09-21 that the United Kingdom's parts are spelled by region
(`HANDOVER.md:103`, `HUMAN_ONLY.md` B9: `Northern Ireland`). The curated set already spells Great
Britain that way (England 1,052, Scotland 83, Wales 118 on 2026-09-22) and 4 rows say
`Northern Ireland`. Measured the same day, two groups do not:

* **17 rows say `Ireland` for a point in Northern Ireland.** The census found them (T02, 2.5 to 93 km
  outside the Ireland polygon) but could not say whether the country or the point is wrong - which
  is why the candidates here come from the live database, not from the census, and why an
  independent Wikidata `P625` in the same geo unit is required before a row is written.
* **6 rows say `United Kingdom`.** Five were written by phase 3 (`Ireland -> United Kingdom`,
  geographically right, the wrong spelling); `Eartham Pit, Boxgrove` held it before the remediation.

## How a row is decided (`classify_uk`, first failure refuses)

1. curated rows only; 2. the stored value must be `Ireland` or `United Kingdom` - England, Scotland,
   Wales and Northern Ireland rows are never touched (a border-crossing earthwork such as Wat's Dyke
   is a coordinate question, not a spelling one); 3. the row needs a point.
4. **The geo unit** is Natural Earth's admin-0 *map units* feature (`GEOUNIT`, never `NAME`, which
   reads `N. Ireland`) that covers the point, else the one unit within T02's 1000 m tolerance (an
   offshore tomb), else the row is refused as undecided.
5. A point in the `Ireland` unit is *consistent* for an `Ireland` row (counted, never written) and a
   contradiction for a `United Kingdom` row; 6. a unit that is not one of the United Kingdom's four
   (the Isle of Man, Jersey, Guernsey are their own features) is refused; 7. an `Ireland` row within
   1000 m of the Ireland unit is refused as border-ambiguous.
8. The new value is the unit's name (the lane's four names are checked writable once, by `Lane`);
   9. it must be a `COUNTRY_CODES` key
   with `GB` and resolve to `GB` through `normalize_country` - this is what the vocabulary change of
   2026-09-22 made true, and without it every Northern-Irish row is refused here; 10. the ISO
   transition must be exactly `IE -> GB` (from `Ireland`) or `GB -> GB` (from `United Kingdom`);
   11. the value must be a fixed point of the census T05 predicate.
12. **Wikidata `P625` must lie in the same geo unit** - not within 1000 m of the row: Aghanaglack's
    entity point is 1.9 km and Haughey's Fort's 2.8 km from the row, both still in Northern Ireland.
13. A decisive `P17` that resolves to another ISO code refuses; 14. a `P131*` chain that reaches
    another of England/Scotland/Wales/Northern Ireland/Ireland (Q21/Q22/Q25/Q26/Q27) refuses.
15. A row whose ISO code changes (`Ireland -> Northern Ireland`) needs one positive external
    witness: `P17 -> GB`, or `P131* -> ` the unit, or - only when the entity states neither `P17`
    nor `P131` - an English-Wikipedia category of its sitelink that names the unit (Annaghmare
    Court Tomb, Q123134330, has only `P31` and `P625`). A same-ISO row records a missing witness
    as a gap.

Every write carries its premise - the point as the database prints it - so the transaction refuses
a row whose point moved after this plan (`lane.UK_PARTS.premise_sql`, guard 5).

`--collect` needs the network (NACIS, Wikidata, en.wikipedia) and the production database
(read-only); `--write` needs the database (read-only) and the cache `--collect` filled. Nothing is
written to production here: `apply.py --lane uk-parts` renders and runs the transaction.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from census.fetch import USER_AGENT  # noqa: E402
from census.tests.t05_country_values import _is_canonical, _iso, _vocabulary  # noqa: E402

from mechanical.lane import UK_PARTS, sql_literal  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    Anchor,
    JournalLink,
    Plan,
    PlanError,
    Site,
    Verdict,
    _claims,
    _coordinate,
    _now,
    _p17_claims,
    check_wikidata,
    country_codes,
    fetch_entities,
    get_json,
    journal_break,
    load_journal,
    psql_json_reader,
    sql_ids,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)

log = logging.getLogger("mechanical.uk_parts")

LANE = UK_PARTS
DEFAULT_OUT = REPO / "output" / "remediation" / LANE.out_dir_name
DEFAULT_CACHE = REPO / "output" / "remediation" / "cache"
WITNESS_FILE = "mechanical_uk_witnesses.json"
SPARQL = "https://query.wikidata.org/sparql"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"

IN_SCOPE = ("Ireland", "United Kingdom")
UK_UNITS = LANE.allowed_new_values
IRELAND = "Ireland"
UNIT_QIDS = {
    "England": "Q21",
    "Scotland": "Q22",
    "Wales": "Q25",
    "Northern Ireland": "Q26",
    "Ireland": "Q27",
}
#: The only ISO transitions this lane makes: a `United Kingdom` row stays GB, an `Ireland` row in
#: Northern Ireland moves from IE to GB.
EXPECTED_ISO = {"United Kingdom": ("GB", "GB"), "Ireland": ("IE", "GB")}
#: Category titles that name a unit explicitly. `in Ireland` is not among them: English Wikipedia
#: uses it for the whole island, so it names neither side of the border.
CATEGORY_UNITS = {
    "England": "England",
    "Scotland": "Scotland",
    "Wales": "Wales",
    "Northern Ireland": "Northern Ireland",
    "the Republic of Ireland": "Ireland",
}
CONSISTENT = "consistent"

DECISION: tuple[dict[str, Any], ...] = (
    {
        "source": "output/remediation/HANDOVER.md:103",
        "url": "output/remediation/HANDOVER.md",
        "quote": "2. The United Kingdom's parts are spelled by region: **`Northern Ireland`**, "
        "not `United Kingdom`.",
    },
    {
        "source": "output/remediation/HUMAN_ONLY.md:49 (B9, Schreibweise Nordirland)",
        "url": "output/remediation/HUMAN_ONLY.md",
        "quote": "**entschieden 2026-09-21: `Northern Ireland`**",
    },
)


# -------------------------------------------------------------------------------- the geo units
@dataclass(frozen=True)
class Unit:
    """One Natural Earth admin-0 map unit: `GEOUNIT`, its sovereign, its polygon."""

    name: str
    sovereign: str
    geom: Any


@dataclass(frozen=True)
class Location:
    """Where a point lies: the unit (or None when undecided), and how that was measured."""

    unit: str | None
    inside: bool
    metres: float
    note: str


class MapUnits:
    """The geo units, indexed for locating a point. Built from real polygons only."""

    def __init__(self, units: Sequence[Unit]) -> None:
        from shapely.strtree import STRtree

        names = [u.name for u in units]
        if not units or len(names) != len(set(names)):
            raise PlanError("the map units must be a non-empty set with unique GEOUNIT names")
        self.units = {u.name: u for u in units}
        self._order = list(units)
        self._tree = STRtree([u.geom for u in units])

    def distance_m(self, name: str, lat: float, lon: float) -> float:
        """Metres from the point to the unit's nearest boundary (0 inside), T02's geodesic rule."""
        from census.tests.t02_admin_country import _nearest_m
        from shapely.geometry import Point

        geom = self.units[name].geom
        return 0.0 if geom.covers(Point(lon, lat)) else _nearest_m(geom, lon, lat)[0]

    def _near(self, lat: float, lon: float, metres: float) -> list[Unit]:
        """Units whose envelope lies within `metres` of the point - a superset, then measured.

        The box is widened by the longitude scale at this latitude, so it is a true superset away
        from the poles; the UK lane's points lie between 49 and 61 degrees north.
        """
        from shapely.geometry import box

        dlat = metres / 111_000.0 * 1.5
        dlon = dlat / max(math.cos(math.radians(lat)), 0.05)
        found = self._tree.query(box(lon - dlon, lat - dlat, lon + dlon, lat + dlat))
        return [self._order[int(i)] for i in found]

    def locate(self, lat: float, lon: float) -> Location:
        from census.tests.t02_admin_country import TOLERANCE_M
        from shapely.geometry import Point

        point = Point(lon, lat)
        nearby = self._near(lat, lon, TOLERANCE_M)
        covering = sorted(u.name for u in nearby if u.geom.covers(point))
        if len(covering) == 1:
            return Location(covering[0], True, 0.0, f"inside the {covering[0]!r} geo unit")
        if covering:
            return Location(None, True, 0.0, f"covered by {len(covering)} units: {covering}")
        near = sorted(
            (metres, u.name)
            for u in nearby
            if (metres := self.distance_m(u.name, lat, lon)) <= TOLERANCE_M
        )
        if len(near) == 1:
            metres, name = near[0]
            return Location(
                name,
                False,
                metres,
                f"{metres:.0f} m outside the {name!r} geo unit, the only unit within "
                f"{TOLERANCE_M:.0f} m",
            )
        if not near:
            return Location(None, False, math.inf, f"no geo unit within {TOLERANCE_M:.0f} m")
        return Location(None, False, near[0][0], f"{len(near)} units within 1000 m: {near}")


def load_units(shapefile: Path) -> MapUnits:
    """The map units from the cached shapefile - `GEOUNIT`, not `NAME` (`N. Ireland`)."""
    if not shapefile.exists():
        raise PlanError(f"{shapefile} is missing - run uk_parts.py --collect first")
    import geopandas as gpd
    from census.tests.t02_admin_country import _polygonal, _text

    units: list[Unit] = []
    for row in gpd.read_file(str(shapefile)).itertuples():
        geom = _polygonal(row.geometry)
        if geom is None:
            raise PlanError(f"map unit {_text(row.GEOUNIT)!r} has no polygon")
        units.append(Unit(_text(row.GEOUNIT), _text(row.SOVEREIGNT), geom))
    return MapUnits(units)


def map_units_dir(cache: Path) -> Path:
    from census.tests.t02_admin_country import MAP_UNITS_DIRNAME

    return cache / MAP_UNITS_DIRNAME


# ------------------------------------------------------------------------------ the candidates
@dataclass(frozen=True)
class Candidate:
    """A live row in scope, with its premise, its entity and its journal chain."""

    site: Site
    premise: str | None
    qids: tuple[str, ...] = ()
    journal: tuple[JournalLink, ...] = ()


CANDIDATE_SQL = (
    "SELECT u.id::text AS id, u.name, u.country, u.lat::text AS lat, u.lon::text AS lon, "
    f"u.source_id, {LANE.premise_sql} AS premise FROM unified_sites u "
    f"WHERE u.source_id = {sql_literal(CURATED_SOURCE)} AND u.country IN ("
    + ", ".join(sql_literal(v) for v in IN_SCOPE)
    + ") ORDER BY u.id"
)


def load_candidates(reader: Callable[[str], list[dict[str, Any]]]) -> list[Candidate]:
    """The rows in scope, read from production with their QIDs and journal - read-only."""
    rows = reader(CANDIDATE_SQL)
    if not rows:
        raise PlanError("no curated row holds 'Ireland' or 'United Kingdom' - nothing to plan")
    ids = sql_ids(str(r["id"]) for r in rows)
    qids: dict[str, list[str]] = {}
    for r in reader(
        "SELECT site_id::text AS site_id, value FROM site_external_ids "
        f"WHERE kind = 'wikidata_qid' AND site_id::text IN ({ids}) ORDER BY value"
    ):
        qids.setdefault(str(r["site_id"]), []).append(str(r["value"]))
    journal = load_journal(reader, LANE.column, [str(r["id"]) for r in rows])
    out: list[Candidate] = []
    for r in rows:
        sid = str(r["id"])
        out.append(
            Candidate(
                site=Site(
                    site_id=sid,
                    name=str(r["name"]),
                    country=r["country"],
                    lat=None if r["lat"] is None else float(r["lat"]),
                    lon=None if r["lon"] is None else float(r["lon"]),
                    source_id=str(r["source_id"]),
                ),
                premise=r["premise"],
                qids=tuple(qids.get(sid, ())),
                journal=tuple(journal.get(sid, ())),
            )
        )
    return out


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class UkPlan:
    """The UK plan: what is written, what is already right (`consistent`), what is refused."""

    plan: Plan
    consistent: tuple[Verdict, ...] = ()
    counters: Mapping[str, int] = field(default_factory=dict)


def classify_uk(
    candidate: Candidate,
    *,
    units: MapUnits,
    codes: Mapping[str, str],
    normalize: Any,
    witnesses: Mapping[str, Any],
    countries: Mapping[str, Any],
    retrieved_at: str | None,
) -> Verdict:
    """Decide one row. Every check is named, and the first failure is the reason."""
    from census.tests.t02_admin_country import NE_MAP_UNITS_URL, TOLERANCE_M

    site = candidate.site
    stored = site.country
    last = candidate.journal[-1] if candidate.journal else None
    phase3 = last is not None and last.run_stamp.startswith("phase3:")

    def verdict(
        ok: bool, reason: str, note: str, evidence: Sequence[dict[str, Any]] = (), **kw: Any
    ) -> Verdict:
        return Verdict(
            site_id=site.site_id,
            site_name=site.name,
            ok=ok,
            old_value=stored,
            new_value=kw.get("new_value"),
            rule=kw.get("rule", ""),
            reason=reason,
            note=note,
            phase3=phase3,
            finding_test_id="live:unified_sites.country",
            evidence=tuple(evidence),
            premise=candidate.premise if ok else None,
        )

    def refuse(reason: str, note: str, evidence: Sequence[dict[str, Any]] = ()) -> Verdict:
        return verdict(False, reason, note, evidence)

    # 1-3: scope
    if site.source_id != CURATED_SOURCE:
        return refuse(
            "row-not-in-curated-source",
            f"the row belongs to source_id={site.source_id!r}; this lane writes curated sites only",
        )
    if stored not in IN_SCOPE:
        return refuse(
            "out-of-scope",
            f"the row holds {stored!r}; this lane reads only 'Ireland' and 'United Kingdom' rows, "
            "and never touches a region that is already spelled out",
        )
    if site.lat is None or site.lon is None:
        return refuse("no-point", "the row carries no point to locate")

    # the journal must agree with the live value, or the row was written around it
    broken = journal_break(candidate.journal, stored)
    if broken is not None:
        return refuse(*broken)

    # 4: the geo unit
    where = units.locate(site.lat, site.lon)
    if where.unit is None:
        return refuse(
            "geography-undecided",
            f"point ({site.lat:.5f}, {site.lon:.5f}): {where.note}",
        )
    unit = where.unit
    geo = {
        "source": f"naturalearth:ne_10m_admin_0_map_units (GEOUNIT={unit})",
        "url": NE_MAP_UNITS_URL,
        "retrieved_at": retrieved_at,
        "quote": f"point ({site.lat:.5f}, {site.lon:.5f}) {where.note}",
    }

    # 5-7: which side of which border
    if unit == IRELAND:
        if stored == IRELAND:
            return verdict(
                False,
                CONSISTENT,
                f"'Ireland' row inside the Ireland geo unit: {where.note}",
                (geo,),
            )
        return refuse(
            "geography-contradicts",
            f"a {stored!r} row whose point lies in the Ireland geo unit ({where.note})",
            (geo,),
        )
    if unit not in UK_UNITS:
        return refuse(
            "not-a-uk-part",
            f"the point lies in {unit!r} (sovereign {units.units[unit].sovereign!r}), which is not "
            "one of England, Scotland, Wales, Northern Ireland",
            (geo,),
        )
    if stored == IRELAND:
        to_ireland = units.distance_m(IRELAND, site.lat, site.lon)
        if to_ireland <= TOLERANCE_M:
            return refuse(
                "border-ambiguous",
                f"an 'Ireland' row {to_ireland:.0f} m from the Ireland geo unit - inside the "
                f"{TOLERANCE_M:.0f} m this project calls 'the same place'",
                (geo,),
            )
        geo["quote"] += f"; {to_ireland:.0f} m from the Ireland geo unit"

    # 8-11: the value and the two vocabularies. The value is one of the lane's four unit names,
    # which `Lane` has already checked are writable in the column.
    new = unit
    old_iso, new_iso = _iso(str(stored), normalize), _iso(new, normalize)
    vocabulary = {
        "source": "ancient-nerds-map/src/utils/countryFlags.ts:COUNTRY_CODES",
        "url": "ancient-nerds-map/src/utils/countryFlags.ts",
        "quote": f"COUNTRY_CODES[{new!r}] = {codes.get(new)!r}",
    }
    if codes.get(new) != "GB" or new_iso != "GB":
        return refuse(
            "not-a-country-code",
            f"{new!r} is not a GB spelling in both vocabularies (COUNTRY_CODES: "
            f"{codes.get(new)!r}, normalize_country: {new_iso!r}), so no flag would render",
            (geo, vocabulary),
        )
    if (old_iso, new_iso) != EXPECTED_ISO[str(stored)]:
        return refuse(
            "iso-transition-unexpected",
            f"normalize_country({stored!r}) -> {old_iso!r}, normalize_country({new!r}) -> "
            f"{new_iso!r}; this lane moves only IE -> GB and GB -> GB",
            (geo, vocabulary),
        )
    lookup = {
        "source": "pipeline/utils/country_lookup.py:NAME_TO_ISO / normalize_country",
        "url": "pipeline/utils/country_lookup.py",
        "quote": f"normalize_country({stored!r}) = {old_iso!r}; normalize_country({new!r}) = "
        f"{new_iso!r}",
    }
    if not _is_canonical(new, dict(codes), normalize):
        return refuse(
            "not-a-fixed-point",
            f"the census T05 predicate would flag {new!r} again; the write would not settle it",
            (geo, vocabulary, lookup),
        )
    base = [geo, lookup, vocabulary]

    # 12-15: the independent witness
    if len(candidate.qids) != 1:
        return refuse(
            "no-single-wikidata-entity",
            f"site_external_ids holds {len(candidate.qids)} wikidata_qid(s) for this site: "
            f"{list(candidate.qids)}",
            base,
        )
    qid = candidate.qids[0]
    entity = witnesses.get(qid)
    if entity is None:
        return refuse("witness-not-collected", f"{qid} is not in the witness cache", base)
    point = entity.get("p625")
    if point is None:
        return refuse(
            "wikidata-point-missing",
            f"{qid} states no P625: nothing independent says the point, not the country, is right",
            base,
        )
    wd_where = units.locate(float(point[0]), float(point[1]))
    if wd_where.unit != unit:
        return refuse(
            "wikidata-point-elsewhere",
            f"{qid} P625 ({point[0]}, {point[1]}): {wd_where.note} - not {unit!r}",
            base,
        )
    fetched_at = entity.get("fetched_at")
    base.append(
        {
            "source": f"wikidata:{qid}:P625",
            "url": f"https://www.wikidata.org/entity/{qid}",
            "retrieved_at": fetched_at,
            "quote": f"P625 ({point[0]}, {point[1]}) {wd_where.note}",
        }
    )
    p17_ok, p17_note, p17_evidence = check_wikidata(
        Anchor(qid, "site_external_ids:wikidata_qid"),
        {"p17": entity.get("p17") or [], "countries": countries, "fetched_at": fetched_at},
        "GB",
    )
    if p17_ok is False:
        return refuse("wikidata-contradicts", p17_note, base)
    reached = set(entity.get("p131_units") or [])
    others = sorted(reached - {UNIT_QIDS[unit]})
    if others:
        return refuse(
            "wikidata-contradicts",
            f"the P131 chain of {qid} reaches {others}, not only {UNIT_QIDS[unit]} ({unit})",
            base,
        )
    categories = list(entity.get("categories") or [])
    named = {
        CATEGORY_UNITS[suffix]
        for title in categories
        for suffix in CATEGORY_UNITS
        if title.endswith(f" in {suffix}")
    }
    if named - {unit}:
        return refuse(
            "category-contradicts",
            f"the categories of {entity.get('enwiki')!r} name {sorted(named - {unit})}: "
            f"{categories}",
            base,
        )

    witnessed: list[str] = []
    if p17_ok and p17_evidence:
        base.append(p17_evidence)
        witnessed.append("P17")
    if UNIT_QIDS[unit] in reached:
        witnessed.append("P131*")
        base.append(
            {
                "source": f"wikidata:{qid}:P131* -> {UNIT_QIDS[unit]}",
                "url": SPARQL,
                "retrieved_at": fetched_at,
                "quote": f"the P131 chain of {qid} reaches {UNIT_QIDS[unit]} ({unit})",
            }
        )
    states_neither = not entity.get("p17") and not entity.get("p131")
    if states_neither and unit in named:
        matching = [t for t in categories if t.endswith(f" in {unit}")]
        witnessed.append("enwiki category")
        base.append(
            {
                "source": f"enwiki:{entity.get('enwiki')} (categories)",
                "url": f"https://en.wikipedia.org/wiki/{str(entity.get('enwiki')).replace(' ', '_')}",
                "retrieved_at": fetched_at,
                "quote": f"{qid} states neither P17 nor P131; its enwiki article is in "
                + ", ".join(matching),
            }
        )
    iso_changes = old_iso != new_iso
    if iso_changes and not witnessed:
        return refuse(
            "no-external-witness",
            f"{stored!r} -> {new!r} changes the ISO code ({old_iso} -> {new_iso}) and no external "
            f"witness names it: {p17_note or 'no P17 to GB'}, no P131* to {UNIT_QIDS[unit]}, no "
            "category naming the unit",
            base,
        )

    if last is not None:
        base.append(
            {
                "source": f"remediation_change_log:{last.id}",
                "url": "remediation_change_log",
                "quote": f"{last.run_stamp} ({last.test_id}): {last.old_value!r} -> "
                f"{last.new_value!r} - the value this lane supersedes",
            }
        )
    base.extend(DECISION)
    note = f"{stored!r} -> {new!r} (ISO {old_iso} -> {new_iso}); witnesses: " + (
        ", ".join(witnessed) if witnessed else "none - recorded as a gap, the ISO code is unchanged"
    )
    return verdict(
        True,
        "",
        note,
        base,
        new_value=new,
        rule="geo-unit" if where.inside else "geo-unit-within-tolerance",
    )


WITNESS_KINDS = ("P17", "P131*", "enwiki category")


def witness_kinds(verdict: Verdict) -> list[str]:
    """The positive external witnesses a written row carries, read from its evidence sources."""
    sources = [str(e["source"]) for e in verdict.evidence]
    kinds = {
        "P17": any(s.startswith("wikidata:") and ":P17 -> " in s for s in sources),
        "P131*": any(s.startswith("wikidata:") and ":P131* -> " in s for s in sources),
        "enwiki category": any(s.startswith("enwiki:") for s in sources),
    }
    return [kind for kind in WITNESS_KINDS if kinds[kind]]


def build_uk_plan(
    candidates: Sequence[Candidate],
    *,
    units: MapUnits,
    codes: Mapping[str, str],
    normalize: Any,
    witnesses: Mapping[str, Any],
    countries: Mapping[str, Any],
    retrieved_at: str | None,
    built_at: str,
) -> UkPlan:
    """A pure function of its inputs: no network, no database, no clock of its own."""
    verdicts = [
        classify_uk(
            candidate,
            units=units,
            codes=codes,
            normalize=normalize,
            witnesses=witnesses,
            countries=countries,
            retrieved_at=retrieved_at,
        )
        for candidate in sorted(candidates, key=lambda c: c.site.site_id)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    consistent = tuple(v for v in verdicts if not v.ok and v.reason == CONSISTENT)
    skipped = tuple(v for v in verdicts if not v.ok and v.reason != CONSISTENT)
    counters: dict[str, int] = {
        "candidates": len(verdicts),
        "changes": len(changes),
        "consistent": len(consistent),
        "skipped": len(skipped),
        "changes_superseding_phase3": sum(1 for c in changes if c.phase3),
        **{
            f"transition:{old} -> {new}": n
            for (old, new), n in sorted(
                Counter((c.old_value, c.new_value) for c in changes).items()
            )
        },
        **{f"skip:{k}": n for k, n in sorted(Counter(s.reason for s in skipped).items())},
        **{
            f"witness:{kind}": sum(1 for c in changes if kind in witness_kinds(c))
            for kind in WITNESS_KINDS
        },
    }
    plan = Plan(changes=changes, skipped=skipped, built_at=built_at, counters=counters, lane=LANE)
    return UkPlan(plan=plan, consistent=consistent, counters=counters)


# ------------------------------------------------------------------------------ the witnesses
def sparql_units_query(qids: Iterable[str]) -> str:
    """One query: which of Q21/Q22/Q25/Q26/Q27 each entity's `P131` chain reaches."""
    items = " ".join(f"wd:{q}" for q in sorted(set(qids)))
    units = " ".join(f"wd:{q}" for q in UNIT_QIDS.values())
    return (
        "SELECT ?item ?unit WHERE {\n"
        f"  VALUES ?item {{ {items} }}\n"
        f"  VALUES ?unit {{ {units} }}\n"
        "  ?item wdt:P131* ?unit .\n"
        "}"
    )


def _entity_ids(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for claim in values:
        value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(str(value["id"]))
    return out


def collect_witnesses(qids: Sequence[str], *, fetched_at: str) -> dict[str, Any]:
    """P17/P131/P625 per entity, P131* per SPARQL, P297 per country, enwiki categories where
    an entity states neither P17 nor P131. One attempt per request; any failure raises."""
    if not qids:
        raise PlanError("no Wikidata entity to collect")
    entities = fetch_entities(qids, "claims|sitelinks", sitefilter="enwiki")
    query = sparql_units_query(qids)
    bindings = (
        get_json(SPARQL, {"query": query, "format": "json"}, timeout=120).get("results") or {}
    ).get("bindings")
    if bindings is None:
        raise PlanError("the SPARQL endpoint answered without results.bindings")
    reached: dict[str, set[str]] = {}
    for b in bindings:
        item = str(b["item"]["value"]).rsplit("/", 1)[-1]
        reached.setdefault(item, set()).add(str(b["unit"]["value"]).rsplit("/", 1)[-1])

    out: dict[str, Any] = {}
    for qid, entity in sorted(entities.items()):
        enwiki = ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")
        record = {
            "p17": _p17_claims(entity),
            "p131": _entity_ids(_claims(entity, "P131")),
            "p625": list(_coordinate(entity) or ()) or None,
            "p131_units": sorted(reached.get(qid, ())),
            "enwiki": enwiki,
            "categories": None,
            "fetched_at": fetched_at,
        }
        if not record["p17"] and not record["p131"] and enwiki:
            pages = (
                get_json(
                    ENWIKI_API,
                    {
                        "action": "query",
                        "titles": enwiki,
                        "prop": "categories",
                        "cllimit": "max",
                        "clshow": "!hidden",
                        "format": "json",
                        "formatversion": "2",
                    },
                ).get("query")
                or {}
            ).get("pages") or []
            if len(pages) != 1:
                raise PlanError(f"en.wikipedia answered {len(pages)} pages for {enwiki!r}")
            record["categories"] = [str(c["title"]) for c in pages[0].get("categories") or []]
        out[qid] = record
    countries = sorted({str(c["id"]) for r in out.values() for c in r["p17"]})
    return {
        "generated_at": fetched_at,
        "user_agent": USER_AGENT,
        "queries": {
            "wbgetentities": "action=wbgetentities&props=claims|sitelinks&sitefilter=enwiki",
            "sparql": query,
            "enwiki": "action=query&prop=categories&cllimit=max&clshow=!hidden",
        },
        "entities": out,
        "countries": country_codes(countries),
    }


# ------------------------------------------------------------------------------ the output
def _row(v: Verdict) -> dict[str, Any]:
    return {
        "site_id": v.site_id,
        "site_name": v.site_name,
        "current_value": v.old_value,
        "reason": v.reason,
        "note": v.note,
        "phase3": v.phase3,
        "evidence": list(v.evidence),
    }


def write_consistent_jsonl(uk: UkPlan, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for v in uk.consistent:
            fh.write(json.dumps(_row(v), ensure_ascii=False) + "\n")
    return len(uk.consistent)


def write_plan_md(uk: UkPlan, path: Path, witnesses: Mapping[str, Any]) -> None:
    plan = uk.plan
    add = (lines := []).append
    add("# B9 - the United Kingdom's parts, spelled by region: plan")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/uk_parts.py`. Lane "
        f"`{LANE.name}`: run stamp `{LANE.run_stamp}`, journal test id `{LANE.test_id}`, "
        f"change keys `{LANE.key_prefix}:<site_id>`, source `{plan.source_id}`."
    )
    add("")
    add(
        f"**{len(plan.changes)} row(s) will be written, {len(uk.consistent)} are already right, "
        f"{len(plan.skipped)} refused.** {uk.counters.get('changes_superseding_phase3', 0)} of the "
        "written rows supersede a phase-3 write (`Ireland -> United Kingdom`); their journal row "
        "is named in each record's evidence."
    )
    add("")
    add("| stored value | written value | rows |")
    add("|---|---|---|")
    for (old, new), n in sorted(Counter((c.old_value, c.new_value) for c in plan.changes).items()):
        add(f"| `{old}` | `{new}` | {n} |")
    add("")
    add("## Every row")
    add("")
    add("| site | stored | written | rule | witnesses | phase 3 |")
    add("|---|---|---|---|---|---|")
    for c in sorted(plan.changes, key=lambda c: (str(c.old_value), c.site_name)):
        add(
            f"| {c.site_name} (`{c.site_id}`) | `{c.old_value}` | `{c.new_value}` | {c.rule} | "
            f"{', '.join(witness_kinds(c)) or 'none (same ISO code: a gap)'} | "
            f"{'yes' if c.phase3 else ''} |"
        )
    add("")
    add("## The checks")
    add("")
    add("See the module docstring of `uk_parts.py` for all fifteen, in order. The mandatory ones:")
    add("")
    add("| check | source | what it proves |")
    add("|---|---|---|")
    for row in (
        (
            "geo unit",
            "naturalearth:ne_10m_admin_0_map_units v5.1.1 (GEOUNIT)",
            "the point lies in that unit, or within 1000 m of it and of no other",
        ),
        ("vocabulary 1", "pipeline/utils/country_lookup.py", "the value resolves to GB"),
        (
            "vocabulary 2",
            "countryFlags.ts:COUNTRY_CODES",
            "the value is a key with GB: the flag renders",
        ),
        ("fixed point", "census T05 predicate", "the census would not flag the written value"),
        ("entity point", "Wikidata P625", "an independent point lies in the same unit"),
        (
            "external",
            "Wikidata P17/P131*, enwiki categories",
            "no contradiction; an IE -> GB row needs one positive witness",
        ),
    ):
        add("| " + " | ".join(row) + " |")
    add("")
    add("## Witness coverage")
    add("")
    add(
        f"Of {len(plan.changes)} written rows: P17 -> GB {uk.counters.get('witness:P17', 0)}, "
        f"P131* -> the unit {uk.counters.get('witness:P131*', 0)}, enwiki category "
        f"{uk.counters.get('witness:enwiki category', 0)} (only for an entity that states neither "
        f"P17 nor P131). Witnesses collected {witnesses.get('generated_at')} with the project's "
        "User-Agent; the queries are in the cache file."
    )
    add("")
    if plan.skipped:
        add("## Refusals")
        add("")
        add("| site | stored | reason | note |")
        add("|---|---|---|---|")
        for s in plan.skipped:
            add(f"| {s.site_name} | `{s.old_value}` | `{s.reason}` | {s.note} |")
        add("")
    add("## Residuals this write leaves (owner decisions, not this lane's)")
    add("")
    add(
        "* `card_stats.civilization` copies `country` and is not written here: the divergence "
        "grows by every written row whose card still says the old value (`APPLIED.md` of T05 names "
        "the check SQL). Re-running the card generator is the owner's call."
    )
    add(
        "* `/sites/united-kingdom` matches no row after the write and answers 404, like "
        "`/sites/georgia-country` since the T05 lane; detail pages 301 to the new country segment."
    )
    add(
        "* Until the vocabulary change (`'Northern Ireland': 'GB'`) is deployed, live pages show the "
        "Northern-Irish rows without a flag, under 'Other'."
    )
    add(
        "* Dooey's Cairn and Ballymacaldrack Court Tomb share Wikidata Q1242421 and lie 7.1 m apart "
        "(a duplicate pair, B6-type); both get `Northern Ireland` either way."
    )
    add("")
    add("## Reproduce")
    add("")
    add("```bash")
    for command in (
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/uk_parts.py --collect",
        "./.venv/Scripts/python.exe scripts/remediation/mechanical/uk_parts.py --write",
        "./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_uk.py -q -rs",
    ):
        add(command)
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def _retrieved_at(cache: Path) -> str | None:
    state = map_units_dir(cache) / "source.json"
    if not state.exists():
        return None
    return str(json.loads(state.read_text(encoding="utf-8")).get("fetched_at"))


def main(argv: list[str] | None = None) -> int:
    from census.tests import t02_admin_country as t02

    ap = argparse.ArgumentParser(description="Plan the B9 UK-part spellings (mechanical lane)")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--collect",
        action="store_true",
        help="download the NE map units and the Wikidata/Wikipedia witnesses (network; reads prod)",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="write PLAN.jsonl, PLAN.md, SKIPPED.jsonl, CONSISTENT.jsonl, ROLLBACK.sql (reads prod)",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    witness_path = args.cache / WITNESS_FILE

    if args.collect:
        t02.collect_archive(
            map_units_dir(args.cache),
            t02.NE_MAP_UNITS_URL,
            t02.NE_MAP_UNITS_ARCHIVE,
            t02.NE_MAP_UNITS_SHAPEFILE,
        )
        candidates = load_candidates(psql_json_reader())
        qids = sorted({q for c in candidates for q in c.qids})
        payload = collect_witnesses(qids, fetched_at=_now())
        witness_path.parent.mkdir(parents=True, exist_ok=True)
        witness_path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        log.info("wrote %s (%d entities)", witness_path, len(payload["entities"]))
        return 0
    if not args.write:
        ap.print_help()
        return 0

    if not witness_path.exists():
        raise PlanError(f"{witness_path} is missing - run uk_parts.py --collect first")
    witnesses = json.loads(witness_path.read_text(encoding="utf-8"))
    units = load_units(map_units_dir(args.cache) / t02.NE_MAP_UNITS_SHAPEFILE)
    codes, normalize = _vocabulary()
    uk = build_uk_plan(
        load_candidates(psql_json_reader()),
        units=units,
        codes=codes,
        normalize=normalize,
        witnesses=witnesses["entities"],
        countries=witnesses["countries"],
        retrieved_at=_retrieved_at(args.cache),
        built_at=_now(),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    rows = write_plan_jsonl(uk.plan, args.out / "PLAN.jsonl")
    skipped = write_skipped_jsonl(uk.plan, args.out / "SKIPPED.jsonl")
    consistent = write_consistent_jsonl(uk, args.out / "CONSISTENT.jsonl")
    write_plan_md(uk, args.out / "PLAN.md", witnesses)
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo.
    write_rollback_sql(uk.plan, args.out / "ROLLBACK.sql", plan_path=args.out / "PLAN.jsonl")
    log.info("PLAN.jsonl %d, SKIPPED.jsonl %d, CONSISTENT.jsonl %d", rows, skipped, consistent)
    print(json.dumps(dict(uk.counters), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
