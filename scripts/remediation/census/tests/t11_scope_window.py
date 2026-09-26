"""T11 - the site is inside the E3 scope window, or flagged so a human can retire it.

Plan Phase 1 item 11 (line 690) is this check, added after the gold-standard measurement
exposed the gap: **no census check covered the E3 window**, so the census could not certify a
site clean by its own definition. Three places in the plan require it and none of them was
executable:

* §1.3 "Definition of clean" (`:59`): *"The site is in scope (E3), or flagged as out of scope
  and hidden."*
* §1.2 E3 (`:46`): *"Cutoff: Americas through 1500 AD, rest of world through 500 AD."* E4
  (`:47`) adds the remedy: *"Flag it AND hide it platform-wide."*
* §7 gate S12 (`:383`) measures it by hand: 4,920 pass / 84 fail.

## The rule, and the 69-versus-84 discrepancy the plan left open

The scope rule is a pure function of two stored values, and it already exists in the code:
`pipeline/normalizers/dates.py::passes_date_cutoff()` calls itself *"the GLOBAL
regional date cutoff ... This defines project scope"* and is what `pipeline/unified_loader.py`
applies to every record at load time. It reads `period_end or period_start`, decides the region
from `AMERICAS_LON_MIN <= lon <= AMERICAS_LON_MAX` (-170..-30) and tests `date <= cutoff`.
This module imports that function and its four constants; it does not re-type them, and `run()`
calls the function on every site it decides and raises if the arithmetic ever disagrees with it.

Plan §8.1's SQL, run over the frozen snapshot, gives **69** sites strictly past the cutoff.
Gate S12 reports **84** failures. Both numbers are right, and the difference is not a boundary
rule, not a region rule and not a different date column - it is the 15 sites with no date at
all. The assessment's own S12 line says so verbatim, in
`output/audit_inventory/_wf2_result.json`: *"S12 Zeitfenster eingehalten (Amerika <= 1500 AD,
Rest <= 500 AD): 4.920 pass / 84 fail (69 ausserhalb, 15 ohne period_start)"*. The plan's §7
table kept the total and dropped the parenthetical, which is how 84 became unattributable.

`passes_date_cutoff()` is explicit that it *includes* a record without a date -
`if date is None: return True  # No date = include (conservative)` - and it does the same for a
record without a location (`if region is None: return True  # No location = include`). That is the right behaviour for a loader (it must not drop rows it
cannot judge) and the **wrong** behaviour for a census: a `pass` row in `census.jsonl` is a claim
that the test applied here and found nothing, so a site whose date is unknown would be certified
clean by a function that never looked at it. "Could not check" must not become "checked and
fine". T11 therefore separates the two: the comparison `date <= cutoff` is the rule, and a site
whose date is missing is a **finding** (undecidable), not a pass. That single decision reproduces
S12 exactly - 4,920 pass / 84 flagged - and it is why the plan's two numbers are 69 and 84.

## The measured result on this snapshot (running the module, not counting by hand)

    in window                4,920  pass
    out of window               51  flagged  severe    (2 Americas / 49 rest of world)
    museum out of window        18  flagged  moderate  (8 / 10)
    no date                     15  flagged  moderate  (2 / 13)
                             ----
    flagged total               84  = S12's fail count
    strictly past the cutoff    69  = §8.1's SQL (51 + 18)

The boundary is inclusive because E3's word is *"through"* and because the plan measured the
trap both ways: §8.1 (`:424-426`) records that 9 Old World sites sit exactly on 500 AD and pass,
*"because `passes_date_cutoff()` tests `date <= cutoff`"*. Re-measured on this snapshot: **8**
sites sit exactly on 500 AD outside the Americas and **1** sits exactly on 1500 AD inside them
(Orongo, Easter Island) - all pass. The boundary class is not what the 69-versus-84 difference
turns on (every site on either boundary passes either way), but the one-site gap against the
plan's count is recorded here rather than smoothed over. Closing that boundary would be a new
scope rule, not a repair, so it is not closed silently.

## Why every finding is REVIEW, and never a value

E4 wants out-of-scope rows flagged *and hidden*, and §8.4 proposes the column
(`scope_status`: `in_scope` / `retired` / `pending` + `scope_reason`). It does not exist yet.
T11 nonetheless records a contradiction it can prove - the stored date lies past the cutoff for
the region the stored coordinates fall in - and refuses to write a value for two measured
reasons:

* **`period_start` is often not the site's date.** 75 % of the sites carry a bucket lower bound
  there (§3.1), and the plan's own review of the museum rows (§8.2) found 41 of 51 museums kept,
  3 retired and 9 that are not museums at all. Retiring a row because a sort key is coarse, or
  because a museum's `period_start` is the year the *building* opened, would delete sites the
  owner's rule keeps.
* **The inverse error exists too,** and T11 cannot see it: the gold-standard sample's third E3
  error (`output/remediation/gold_standard/GOLD_STANDARD.md:883`, *Font dels Coms*, Andorra) is a
  spring with a fabricated `period_start = -3500` whose scope verdict is wrong *because* the date
  is wrong - it passes this window. So the class is "the date and the dataset disagree"; which one
  is wrong is a factual question (Phase 3), never a mechanical one.

## Two geographies, and why the second one is T02's

The region decides the cutoff, so a wrong region is a wrong verdict. The project's region rule is
a **longitude window** - an approximation that misplaces French Polynesia (`Hane, Marquesas
Islands` and `Fa'ahia` sit at lon -139 / -151, inside the window, while Natural Earth calls them
Oceania) - and there is no second dataset worth inventing here. So the second opinion reuses
T02's: `census.tests.t02_admin_country._atlas()` (`containing()`, its STRtree, its `make_valid`
handling, the same cached `ne_10m_admin_0_countries`), plus one attribute of that same shapefile
read without geometry, `CONTINENT`. Where the two answers disagree **about the verdict** (not
merely about the region), the site is un-decidable from stored data and is flagged
(`T11/ambiguous-region`). Measured on this snapshot: 208 of the 5,004 coordinates fall in no
Natural Earth polygon at all (open water - the longitude rule answers alone and the evidence says
so), 4,796 fall inside a continent polygon, exactly 2 of which (the Marquesas pair) contradict the
longitude window's region - without contradicting the verdict, both being in scope under either
cutoff - and **zero sites flip the verdict**. No site lies in one of Natural Earth's own sea or
Antarctica features, so the `NO_REGION_CONTINENTS` branch is a guard with no data behind it yet.
That guard costs nothing today and is the difference between "the rule decided this" and "a
longitude guessed this".

There is no `collect()`. Scope needs stored values only: the snapshot row and a dataset T02 has
already unpacked. A missing dataset raises (`_geography`), exactly as it does in T02, rather than
degrading to a longitude-only pass.

## Oceania joins the Americas' cutoff (O7, owner, 2026-09-26)

"Ozeanien wie Amerika": Oceania is in scope through 1500 AD. The region is `e3_region`'s now
(`pipeline/normalizers/dates.py`): Oceania by the row's country - the UN M49 list plus the Pacific
island groups of states whose rows carry the state's name (Easter Island as "Chile", French
Polynesia as "France") - then the Americas by the longitude window, then the rest of the world.
Natural Earth's CONTINENT `Oceania` answers 1500 AD too, so the Marquesas pair above now agrees in
region as well as in verdict. The measurements in this docstring are the 2026-09-20 snapshot's
under the rule as it was; on production on 2026-09-26 (read-only) the 45 curated Oceania rows
(Australia 30, Easter Island 11, French Polynesia 3, Northern Mariana Islands 1) hold no date past
500 AD outside the longitude window, so O7 moves no verdict of today's rows.

## What this check cannot decide from stored values

Named here, flagged in the census, never silently passed:

* **15 sites with no `period_start`, `period_end` or `period_name`** - e.g. Situs Megalit Tebing
  Tinggi (Indonesia), Yonaguni Monument (Japan), The Davidson Center (Israel). The bucket is the
  only dating field these rows carry.
* **Museum rows among the 84:** 18 past the cutoff, plus 2 of the 15 undecidable ones (The
  Davidson Center, Leptis Magna Museum). Whether a museum exhibits ancient material is not in
  `unified_sites`, so the E3 museum rule needs the hand review §8.2 performed.
* **The fabricated-date direction** (Font dels Coms), which is only visible against the source.
"""

from __future__ import annotations

import functools
import logging
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import geopandas as gpd

from census.model import Confidence, Evidence, Finding, Proposal, Severity
from census.tests import t02_admin_country as t02

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T11"
NAME = "E3 scope window (Americas and Oceania through 1500 AD, rest of world through 500 AD)"
DIMENSION = "SCOPE"

REPO = Path(__file__).resolve().parents[4]

#: `scope_status` is the column E4 approved and plan §8.4 proposes (`in_scope` / `retired` /
#: `pending` plus `scope_reason`); it does not exist in the database yet. Every finding names
#: it, because that is the transition a repair performs - `scope_status` NULL -> retired or
#: pending, so the write's conditional WHERE clause is `scope_status IS NULL` - and no finding
#: here proposes the value it would set (see the module docstring: which of "the date is
#: wrong" and "the row does not belong" is true is a factual question).
FIELD = "scope_status"

#: Natural Earth's own continent labels that mean the Americas.
AMERICAS_CONTINENTS = frozenset({"North America", "South America"})
#: Natural Earth's continent label of Oceania, whose cutoff is the Americas' since O7.
OCEANIA_CONTINENT = "Oceania"

#: CONTINENT values that answer nothing about the region: the ocean and the polar shelf are
#: drawable, not inhabited, and E3 carries no cutoff for either.
NO_REGION_CONTINENTS = frozenset({"Seven seas (open ocean)", "Antarctica"})

PLAN = "docs/procedures/SITES_DB_REMEDIATION_2026-09.md"
PLAN_E3 = f"{PLAN}:46 (E3)"
PLAN_CLEAN = f"{PLAN}:59 (1.3)"
PLAN_MUSEUM_REVIEW = f"{PLAN}:430 (8.2)"

log = logging.getLogger("census.t11")


@dataclass(frozen=True)
class _ScopeRule:
    """The project's own E3 rule, bound to the module that implements it.

    Since O7 (owner, 2026-09-26: "Ozeanien wie Amerika") the region is `e3_region`'s: Oceania by
    the row's country (or a Pacific island group of the state it names), then the Americas by the
    longitude window, then the rest of the world.
    """

    americas_lon_min: float
    americas_lon_max: float
    cutoffs: Mapping[str, int]
    region_of: Callable[[Mapping[str, Any]], str | None]
    passes: Callable[[dict[str, Any]], bool]
    americas: str
    oceania: str
    rest_of_world: str

    def region(self, site: Mapping[str, Any]) -> tuple[str, int]:
        """(region name, cutoff in AD) for a site with a longitude, by the project's own rule."""
        region = self.region_of(site)
        if region is None:
            raise AssertionError(f"{TEST_ID}: region asked for a site without a longitude")
        return region, self.cutoffs[region]

    def continent_cutoff(self, continent: str) -> int:
        """The cutoff of a Natural Earth CONTINENT: 1500 AD for the Americas and Oceania."""
        if continent in AMERICAS_CONTINENTS:
            return self.cutoffs[self.americas]
        if continent == OCEANIA_CONTINENT:
            return self.cutoffs[self.oceania]
        return self.cutoffs[self.rest_of_world]


@functools.lru_cache(maxsize=1)
def _scope_rule() -> _ScopeRule:
    """`pipeline.normalizers.dates`, imported - never re-typed, never re-implemented."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.normalizers.dates import (
        AMERICAS,
        AMERICAS_LON_MAX,
        AMERICAS_LON_MIN,
        E3_CUTOFFS,
        OCEANIA,
        REST_OF_WORLD,
        e3_region,
        passes_date_cutoff,
    )

    return _ScopeRule(
        americas_lon_min=float(AMERICAS_LON_MIN),
        americas_lon_max=float(AMERICAS_LON_MAX),
        cutoffs=dict(E3_CUTOFFS),
        region_of=e3_region,
        passes=passes_date_cutoff,
        americas=AMERICAS,
        oceania=OCEANIA,
        rest_of_world=REST_OF_WORLD,
    )


@dataclass(frozen=True)
class _Geography:
    """The second, independent answer to "which region is this point in?"."""

    atlas: t02._Atlas
    continents: dict[str, str]
    retrieved_at: str | None

    def continent(self, lon: float, lat: float) -> tuple[str | None, tuple[str, ...]]:
        """(CONTINENT, ADMIN names) of the Natural Earth feature(s) containing the point.

        `None` for the continent when Natural Earth cannot speak: no polygon contains the
        point (open water), the only polygon is one of its own sea features, or two
        landmasses meet there. That means "no second opinion", never "confirmed fine" - the
        caller keeps the longitude rule's answer and says so in the evidence.
        """
        names = tuple(self.atlas.containing(lon, lat))
        land = {self.continents[name] for name in names} - NO_REGION_CONTINENTS
        if len(land) == 1:
            return next(iter(land)), names
        return None, names


def _geography(ctx: Context) -> _Geography:
    """T02's Natural Earth atlas plus the CONTINENT attribute of the same cached shapefile.

    Reuse, not a second geography: the dataset, the download, the `make_valid` repair and the
    point-in-polygon index are T02's, and this module adds one attribute read without
    geometry. The private names are deliberate - T02's public surface is its test-id
    contract, and a second atlas would be a second truth, which is the defect the rule in
    T02's own docstring exists to prevent.

    Raises when the dataset is absent, exactly as T02 does: a missing shapefile must never
    look like a clean run, and the longitude rule alone would leave the whole region guard
    silently off.
    """
    shapefile = t02._dataset_dir(ctx.cache) / t02.NE_SHAPEFILE
    if not shapefile.exists():
        raise FileNotFoundError(
            f"{TEST_ID}: {shapefile} is missing - run the census with --collect first "
            f"(T02.collect() downloads {t02.NE_URL})"
        )
    atlas = t02._atlas(ctx)
    frame = gpd.read_file(str(shapefile), ignore_geometry=True)
    continents = {
        str(admin): str(continent)
        for admin, continent in zip(frame["ADMIN"], frame["CONTINENT"], strict=True)
    }
    missing = sorted({feature.admin for feature in atlas.features} - continents.keys())
    if missing:
        # An incomplete attribute read would weaken the region guard to "no opinion" for
        # those features - i.e. turn "could not check" into "checked and clean".
        raise RuntimeError(
            f"{TEST_ID}: CONTINENT is missing for {len(missing)} Natural Earth features "
            f"({', '.join(missing[:5])}...) - the region guard would silently stop working"
        )
    return _Geography(atlas=atlas, continents=continents, retrieved_at=t02._retrieved_at(ctx))


def _is_museum(site: dict[str, Any]) -> bool:
    """The E3 museum rule turns on `site_type`, the same way plan §8.1 selected them."""
    return "museum" in (site.get("site_type") or "").casefold()


def _scope_evidence(date: int, lon: float, region: str, cutoff: int) -> Evidence:
    rule = _scope_rule()
    return Evidence(
        source="pipeline/normalizers/dates.py (passes_date_cutoff, e3_region)",
        quote=f"region = Oceania by country (O7), else Americas if {rule.americas_lon_min:g} <= "
        f"lon <= {rule.americas_lon_max:g}, else rest of world; "
        f"cutoff = {cutoff} ({region}); return date <= cutoff   "
        f"[lon = {lon}, date = {date}]",
    )


def _storage_evidence(site: dict[str, Any], date: int | None) -> Evidence:
    return Evidence(
        source="snapshot:unified_sites.period_start",
        quote=f"period_start = {date!r}, period_end = {site.get('period_end')!r}, "
        f"period_name = {site.get('period_name')!r}, lat = {site.get('lat')!r}, "
        f"lon = {site.get('lon')!r}",
    )


def _region_evidence(
    geo: _Geography, features: tuple[str, ...], continent: str | None, verdict: str
) -> Evidence:
    place = ", ".join(features) if features else "no feature (open water)"
    return Evidence(
        source="naturalearth:ne_10m_admin_0_countries (CONTINENT)",
        url=t02.NE_URL,
        quote=f"contains the point: {place}; CONTINENT = {continent or 'n/a'}; {verdict}",
        retrieved_at=geo.retrieved_at,
    )


def _base(
    sid: str,
    kind: str,
    severity: Severity,
    confidence: Confidence,
    note: str,
    evidence: list[Evidence],
) -> Finding:
    return Finding(
        site_id=sid,
        test_id=f"{TEST_ID}/{kind}",
        field=FIELD,
        severity=severity,
        dimension=DIMENSION,
        current_value=None,
        proposal=Proposal.REVIEW,
        confidence=confidence,
        note=note,
        evidence=evidence,
    )


def _out_of_window(
    site: dict[str, Any],
    sid: str,
    date: int,
    lon: float,
    region: str,
    cutoff: int,
    continent: str | None,
    features: tuple[str, ...],
    geo: _Geography,
) -> Finding:
    if continent is None:
        second = (
            "Natural Earth has no continent for this point, so the longitude window alone "
            "decided the region"
        )
        verdict = "no second opinion available"
    else:
        second = f"Natural Earth puts the point in {', '.join(features)} (CONTINENT {continent})"
        verdict = f"region agrees with the longitude window ({region})"
    return _base(
        sid,
        "out-of-window",
        Severity.SEVERE,
        Confidence.AUTHORITATIVE,
        f"period_start {date} is {date - cutoff} years past the {region} cutoff of {cutoff} AD, "
        f"and E4 says an out-of-scope site is flagged and hidden, never deleted. {second}. "
        "Which of the two is wrong is not decided here: `period_start` carries a bucket lower "
        "bound on 75 % of the sites (plan §3.1), so a site that does belong needs its date "
        "corrected instead of being retired",
        [
            _scope_evidence(date, lon, region, cutoff),
            _storage_evidence(site, date),
            _region_evidence(geo, features, continent, verdict),
        ],
    )


def _museum_past_cutoff(
    site: dict[str, Any],
    sid: str,
    date: int,
    lon: float,
    region: str,
    cutoff: int,
    continent: str | None,
    features: tuple[str, ...],
    geo: _Geography,
) -> Finding:
    return _base(
        sid,
        "museum-past-cutoff",
        Severity.MODERATE,
        Confidence.UNVERIFIABLE,
        f"site_type {site.get('site_type')!r} is a museum and period_start {date} is "
        f"{date - cutoff} years past the {region} cutoff of {cutoff} AD - but E3 keeps a museum "
        "*if it exhibits ancient material*, and whether it does is not in the stored data: on "
        "these rows period_start is usually the year the institution opened (plan §8.1 counts 18 "
        "such rows; the plan's §8.2 reviewed all 51 Museum rows by hand and kept 41)",
        [
            Evidence(
                source=PLAN_E3,
                quote="Museums stay if they exhibit ancient material. Cutoff: Americas through "
                "1500 AD, rest of world through 500 AD.",
            ),
            Evidence(
                source=PLAN_MUSEUM_REVIEW,
                quote="- **41 stay** — they exhibit ancient material",
            ),
            _scope_evidence(date, lon, region, cutoff),
            _storage_evidence(site, date),
            _region_evidence(
                geo,
                features,
                continent,
                f"region from the longitude window: {region} "
                f"(Natural Earth: {continent or 'no opinion'})",
            ),
        ],
    )


def _undecidable_date(site: dict[str, Any], sid: str, date: Any) -> Finding:
    if date is None:
        reason = "period_start, period_end and period_name are all empty"
        quote = "period_start = None, period_end = None, period_name = None"
    else:
        reason = f"the stored date is not a year: {date!r} ({type(date).__name__})"
        quote = f"period_start = {date!r} ({type(date).__name__})"
    return _base(
        sid,
        "undecidable-date",
        Severity.MODERATE,
        Confidence.UNVERIFIABLE,
        f"{reason}, so the E3 window cannot be tested - and the bucket is the only dating value "
        "this row carries. The project's own scope function includes a record without a date "
        '("No date = include (conservative)", passes_date_cutoff in '
        "pipeline/normalizers/dates.py), which is right for a loader and wrong for a "
        "census: reporting this site as `pass` would certify it clean on a comparison that "
        "never happened. It needs a date from a source, or an explicit scope decision",
        [
            Evidence(
                source="pipeline/normalizers/dates.py (passes_date_cutoff)",
                quote='date = record.get("period_end") or record.get("period_start"); '
                "if date is None: return True  # No date = include (conservative)",
            ),
            Evidence(source="snapshot:unified_sites", quote=quote),
            Evidence(
                source=PLAN_CLEAN,
                quote="The site is in scope (E3), or flagged as out of scope and hidden.",
            ),
        ],
    )


def _undecidable_location(site: dict[str, Any], sid: str) -> Finding:
    return _base(
        sid,
        "undecidable-location",
        Severity.MODERATE,
        Confidence.UNVERIFIABLE,
        "lat/lon are missing or outside the valid range, so the region - and with it the cutoff "
        "of 1500 or 500 AD - cannot be determined; the project's own scope function includes a "
        "record without a location, which would make this row a `pass` on a comparison that "
        "never happened",
        [
            Evidence(
                source="pipeline/normalizers/dates.py (passes_date_cutoff)",
                quote="region = e3_region(record); if region is None: return True  "
                "# No location = include",
            ),
            Evidence(
                source="pipeline/normalizers/dates.py (e3_region)",
                quote='lon = record.get("lon"); if lon is None: return None',
            ),
            _storage_evidence(site, None),
        ],
    )


def _ambiguous_region(
    site: dict[str, Any],
    sid: str,
    date: int,
    lon: float,
    region: str,
    cutoff: int,
    continent: str,
    features: tuple[str, ...],
    ne_cutoff: int,
    geo: _Geography,
) -> Finding:
    return _base(
        sid,
        "ambiguous-region",
        Severity.MODERATE,
        Confidence.UNVERIFIABLE,
        f"the longitude window calls this {region} (cutoff {cutoff} AD) while Natural Earth "
        f"places the point in {', '.join(features)} "
        f"(CONTINENT {continent}, cutoff {ne_cutoff} AD); "
        f"with period_start {date} the two give opposite scope verdicts. The longitude window "
        "is an approximation (it puts French Polynesia in the Americas), so neither answer is "
        "asserted here: the region of this site is a decision, not a computation",
        [
            _scope_evidence(date, lon, region, cutoff),
            _storage_evidence(site, date),
            Evidence(
                source="naturalearth:ne_10m_admin_0_countries (CONTINENT)",
                url=t02.NE_URL,
                quote=f"contains the point: {', '.join(features)}; CONTINENT = {continent}; "
                f"cutoff for that region = {ne_cutoff} AD",
                retrieved_at=geo.retrieved_at,
            ),
        ],
    )


def run(ctx: Context) -> list[Finding]:
    rule = _scope_rule()
    geo = _geography(ctx)
    findings: list[Finding] = []

    for site in ctx.sites:
        sid = str(site["id"])
        coords = t02._coordinates(site)
        if coords is None:
            findings.append(_undecidable_location(site, sid))
            continue
        lat, lon = coords

        date = site.get("period_end") or site.get("period_start")
        if isinstance(date, bool) or not isinstance(date, int):
            findings.append(_undecidable_date(site, sid, date))
            continue

        region, cutoff = rule.region(site)
        in_window = date <= cutoff
        # The census must not invent a second scope rule. Where the project's own function can
        # answer at all it has to agree with the comparison above, or the two checks this
        # database is filtered by have drifted apart and every verdict below is suspect.
        if rule.passes(site) != in_window:
            raise AssertionError(
                f"{TEST_ID}: {sid} (period_start={date}, lon={lon}) -> in_window={in_window}, "
                f"but passes_date_cutoff() says {rule.passes(site)}: the census and the project "
                "disagree about the scope rule itself"
            )

        continent, features = geo.continent(lon, lat)
        if continent is not None:
            ne_cutoff = rule.continent_cutoff(continent)
            if (date <= ne_cutoff) != in_window:
                findings.append(
                    _ambiguous_region(
                        site, sid, date, lon, region, cutoff, continent, features, ne_cutoff, geo
                    )
                )
                continue

        if in_window:
            continue  # in scope, and the second geography agrees about the verdict
        if _is_museum(site):
            findings.append(
                _museum_past_cutoff(site, sid, date, lon, region, cutoff, continent, features, geo)
            )
        else:
            findings.append(
                _out_of_window(site, sid, date, lon, region, cutoff, continent, features, geo)
            )

    log.info(
        "%s: %d findings over %d sites (%d different kinds)",
        TEST_ID,
        len(findings),
        len(ctx.sites),
        len({f.test_id for f in findings}),
    )
    return findings
