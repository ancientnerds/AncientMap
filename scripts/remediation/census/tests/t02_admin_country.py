"""T02 - the point a site claims must lie inside the country the site claims.

One question, asked of every site that has a country and a point: does `unified_sites.country`
name a state whose territory contains `unified_sites.lat`/`lon`? It is the geometric half of
D3-LOCATION; T01 asks Wikidata the same question (P17 vs `country`, P625 vs `lat`/`lon`) and
T05 owns the *vocabulary* of the country column. A site both T01 and T02 flag, from two
independent references, is a stronger lead than either alone.

T01 also fixes the yardstick here. The plan's section 9.5 measured stored coordinates
against Wikidata and called them in agreement "within 1 km" (88.0 %); T01 adopted 1000 m so
the census reproduces that measurement instead of inventing a second scale. T02 uses the
same 1000 m, for the same reason. What that tolerance means *here* is measurement, not
taste - see below.

**Everything is `Proposal.REVIEW` and `applicable_findings` for this test is 0 by
construction,** exactly as in T01. Two reasons, both from the project's own rules:

* The test proves a contradiction, not a correction. A point outside the claimed polygon
  means `country` or the coordinates are wrong - never which one. Writing the polygon's
  answer into `country` would be guessing (anti-pattern 5: a wrong value is worse than an
  empty one), and the replacement must come from a source for THIS site (Wikidata P17,
  T01) in the project's own vocabulary (T05).
* Several genuine causes of a mismatch are not defects at all, and Natural Earth cannot
  tell them apart from an error: an overseas territory of the named sovereign (§9.4),
  a disputed border (Natural Earth draws de-facto lines: it puts Crimea inside the Russia
  polygon, so all 8 Crimean sites claimed as Ukraine come out "outside Ukraine" by
  139-160 km), or a coastline drawn smoother than the site's island. A human decides.

## Deciding the distance, rather than in/out

A binary test is unusable here, and the numbers say so on this snapshot:

* **4,712 of 5,004 sites are inside** the claimed polygon.
* **175 more are outside by at most 1 km** and are not defects: 1 km is the floor of what
  Natural Earth 10m and the stored coordinate can jointly produce. Rounding a coordinate to
  3 decimals is already ~100 m; the dot of a harbour or island site sits that far offshore,
  and the largest gap that is still tolerated on this snapshot is 998 m. 1 km is also
  T01's and the plan's own tolerance, so the two checks do not disagree about what "the
  same place" means.
* **112 sites are outside by more than 1 km, and 5 have a country string no feature
  matches.** That is the flag list: 117 findings, 2.3 % of the curated set - 71 `cosmetic`,
  35 `moderate` and 6 `severe` by distance, plus the 5 unmatched, which are `cosmetic`
  because nothing is known to be wrong there, only untested.
* Above that, severity is graded by the measured distance, so the queue can be worked from
  the top:
  - `<= 1 km` - no finding.
  - `1 - 25 km` - `cosmetic`. Within the range Natural Earth 10m generalisation itself
    explains: it drops small islands. Measured on the cached dataset, its *Greece* polygon
    contains Mykonos and Naxos but not Delos (3.8 km from the polygon), Pseira or Koufonisi,
    and the Delos finding below is exactly that artefact. Dismissing one costs a glance.
  - `25 - 250 km` - `moderate`. Past anything a coastline or a rounding can explain; the
    remaining causes are a border, an offshore coordinate or a wrong country value.
  - `> 250 km` - `severe`. The point is another region entirely, so at least one of the two
    fields is certainly wrong (6 sites, the worst measured 15,083 km: a Pakistan site whose
    coordinates lie in Peru).

The 25 km and 250 km edges are chosen so that the *disputed-territory* cohorts land in
`moderate` and `cosmetic` rather than in `severe`: Cyprus 1.2-68 km (12 sites claimed as
`Cyprus` that Natural Earth draws inside Northern Cyprus), Crimea 138-160 km (8 sites),
Ireland 2.5-93 km (22), Serbia/Kosovo 3.4-20 km (2). They need jurisdiction, not a data fix,
and sorting them above a 15,000 km inversion would be the wrong order to work in. Natural
Earth's de-facto borders are what produce the Crimean cohort at all: all 8 sites are claimed
as `Ukraine` and land inside its `Russia` polygon.

## What the resolver has to get right

**Country strings are matched through the project's own mapping first.** `England`,
`Scotland` and `Wales` (1,257 sites) are deliberate project vocabulary (plan §4.3) and are
not countries in Natural Earth, which carries a single *United Kingdom* feature; resolving
them through `pipeline/utils/country_lookup.py::normalize_country` to their ISO code - the
module's own mapping, so authoritative for our vocabulary - reaches the right polygon and
produces no finding. Without it, 1,257 sites would be reported as "unknown country string".
Only when the project's mapping yields no ISO code is Natural Earth's own name set used
(`ADMIN`, `NAME`, `BRK_NAME`, `NAME_LONG`, `NAME_ALT`, casefolded with punctuation and
diacritics folded). A trailing qualifier such as `Georgia (country)` is dropped, because it
is a disambiguation note and not part of the name.

**A claim naming a sovereign state covers its territories.** `France` (180 sites) must not
accuse the Marquesas: Natural Earth keeps French Polynesia as its own feature with
`SOVEREIGNT = France`. When the matched feature *is* its own sovereign, the tested geometry
is the union with every feature sharing that `SOVEREIGNT` (on this snapshot that is 2 sites,
both `France` in French Polynesia; `Denmark` -> Greenland and `United States of America` ->
Guam/Puerto Rico are the same rule on other data). A claim naming a dependency (`Greenland`)
is never widened upwards.

**The widening stops at contested ground,** where Natural Earth marks the feature `Disputed`,
`Indeterminate` or `Breakaway`: for those the honest answer is a decision, not a pass. It is
what keeps the two West Bank sites claimed as `Israel` in the queue - the point lies in
Natural Earth's `Palestine`, whose `SOVEREIGNT` is `Israel` and whose type is `Indeterminate`;
silently accepting it would be a political ruling made by a polygon.

**Multi-part countries and the antimeridian.** The tested geometry is the union of every
matched feature, so the 74 parts of Greece and the 344 of the United States are one
geometry. Natural Earth splits polygons at +/-180, so containment works natively; the
*distance*, however, would be measured along the wrong side of the planet (Fiji to its own
next island is 42 km, not 39,000 km), so the nearest point is taken over the geometry
translated by -360, 0 and +360 degrees and the shortest geodesic wins. Fiji, Russia and the
United States all carry parts on both sides of the line in this dataset.

**A country string that matches no feature is itself a finding** (`T02/unmatched-country`,
`review`): 5 sites on the 2026-09-20 snapshot (`Northern Ireland` 4, `Baltic Sea` 1), where
the project's vocabulary and Natural Earth's genuinely differed. It is reported rather than
forced onto a neighbour, and it means those sites were not geometry-checked - the run's
`pass` for them would otherwise be a claim T02 cannot make. Since 2026-09-22 both project
vocabularies map `Northern Ireland` to GB (the owner's B9 decision), so it resolves to the
United Kingdom polygon like England, Scotland and Wales; `Baltic Sea` is the one left.

## Where the reference data comes from

`collect()` downloads `ne_10m_admin_0_countries.zip` (4,930,492 bytes, sha256 `ce1ac703...`)
**once** into `<cache>/naturalearth/` and unpacks it; `run()` reads the unpacked shapefile
and raises if it is not there, so a missing dataset can never be mistaken for a clean
census. The mirror is hard-coded from a real request on 2026-09-20, not from a list to try:
`https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/
ne_10m_admin_0_countries.zip` answers **500** (and its http:// form 404), while the NACIS
CDN mirror answers **200** with that exact byte count and `Last-Modified: Fri, 13 May 2022`.
One verified URL, no mirror loop.

`census.fetch.Fetcher` is used for its etiquette (the same `USER_AGENT`, documented in
fetch.py, so NACIS sees the same responsible caller as Wikimedia), but the body is written
to the cache as bytes: `Fetcher`'s cache stores `r.text`, which is lossless for the JSON
APIs the other checks use and destructive for a ZIP. The archive is therefore cached by
content hash and never refetched, which is the same guarantee by a different mechanism.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import geopandas as gpd
import httpx
import shapely
from pyproj import Geod
from shapely import make_valid, union_all
from shapely.geometry import MultiPolygon, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from census.fetch import USER_AGENT, FetchError
from census.model import Confidence, Evidence, Finding, Proposal, Severity, now_iso

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T02"
NAME = "point-in-polygon: lat/lon inside the claimed country"
DIMENSION = "D3-LOCATION"

REPO = Path(__file__).resolve().parents[4]

#: One URL, verified with a real request on 2026-09-20: 200, 4,930,492 bytes,
#: Last-Modified Fri, 13 May 2022 05:20:49 GMT, sha256 ce1ac7036499a0ed... The
#: naturalearthdata.com direct download answers 500 on the same day and is therefore not
#: tried at runtime - a mirror list would only hide which one actually served the data.
NE_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
NE_ARCHIVE = "ne_10m_admin_0_countries.zip"
NE_SHAPEFILE = "ne_10m_admin_0_countries.shp"
CACHE_DIRNAME = "naturalearth"

#: The same release's admin-0 *map units* (v5.1.1 like the countries file), which split the United
#: Kingdom into its four geo units (GEOUNIT England/Scotland/Wales/Northern Ireland, GU_A3
#: ENG/SCT/WLS/NIR). Verified with a live request on 2026-09-22: 200, 5,003,719 bytes,
#: Last-Modified Fri, 13 May 2022, sha256 45bebe2aaf8bf42b.... Not used by T02 itself; the
#: mechanical UK lane (`scripts/remediation/mechanical/uk_parts.py`) reads it.
NE_MAP_UNITS_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_map_units.zip"
NE_MAP_UNITS_ARCHIVE = "ne_10m_admin_0_map_units.zip"
NE_MAP_UNITS_SHAPEFILE = "ne_10m_admin_0_map_units.shp"
MAP_UNITS_DIRNAME = "naturalearth_map_units"

#: Fields carrying the feature's own name and ISO code. POSTAL is deliberately excluded:
#: it collides across unrelated features (Northern Cyprus is `CN`, as is China).
ISO_FIELDS = ("ISO_A2_EH", "ISO_A2", "ISO_A3_EH", "ISO_A3", "WB_A2")
NAME_FIELDS = ("ADMIN", "NAME", "BRK_NAME", "NAME_LONG")

#: Natural Earth's own marks for ground whose owner is contested (Palestine, Gibraltar,
#: the Falklands). A sovereignty widening must not absorb these into a pass.
CONTESTED_TYPES = frozenset({"Disputed", "Indeterminate", "Breakaway"})

#: Metres. 1000 m is the plan's §9.5 and T01's tolerance for "the same place".
TOLERANCE_M = 1000.0
COSMETIC_MAX_M = 25_000.0
MODERATE_MAX_M = 250_000.0

#: WGS84, for the nearest-boundary distance. Degrees are not a distance on a sphere.
GEOD = Geod(ellps="WGS84")

log = logging.getLogger("census.t02")


# --------------------------------------------------------------------- geography
@dataclass(frozen=True)
class _Feature:
    """One Natural Earth admin-0 feature."""

    admin: str  #: ADMIN - the published name
    sovereign: str  #: SOVEREIGNT - itself for a sovereign state
    kind: str  #: TYPE - Country, Dependency, Disputed, ...
    name_keys: tuple[str, ...]  #: folded own-name spellings
    iso_codes: tuple[str, ...]  #: ISO_A2/ISO_A3/WB_A2, sentinels removed
    geom: BaseGeometry

    @property
    def is_sovereign(self) -> bool:
        return self.admin == self.sovereign


@dataclass(frozen=True)
class _Claim:
    """The reference geometry a site's `country` string resolves to."""

    geom: BaseGeometry  #: matched features, widened by sovereignty
    matched: tuple[str, ...]  #: ADMIN names matched from the string
    territories: tuple[str, ...]  #: ADMIN names added by the sovereignty rule
    via: str  #: how it resolved, for the finding's evidence


def _fold(name: str) -> str:
    """Casefold a place name and drop what Natural Earth and we spell differently.

    Diacritics (`Türkiye`), punctuation (`St. Pierre`) and hyphenation
    (`Guinea-Bissau`) are the only differences this folds, so that one spelling rule
    covers both sides of the comparison instead of a table of exceptions.
    """
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    for ch in ".-'’":
        plain = plain.replace(ch, " ")
    return " ".join(plain.casefold().split())


def _strip_qualifier(country: str) -> str:
    """`Georgia (country)` -> `Georgia`: a parenthetical is a disambiguator, not a name."""
    stripped = country.strip()
    if stripped.endswith(")") and "(" in stripped:
        return stripped[: stripped.rindex("(")].strip()
    return stripped


def _text(value: Any) -> str:
    """A shapefile attribute as text, with the empty sentinels dropped."""
    if value is None:
        return ""
    out = str(value).strip()
    return "" if out.lower() in ("nan", "none") else out


def _severity(distance_m: float) -> Severity:
    """Grade a gap by its measured size - the whole point of a non-binary test."""
    if distance_m <= COSMETIC_MAX_M:
        return Severity.COSMETIC
    if distance_m <= MODERATE_MAX_M:
        return Severity.MODERATE
    return Severity.SEVERE


def _wrap_lon(lon: float) -> float:
    """A longitude inside [-180, 180), so `pyproj` measures the short way round."""
    return ((lon + 180.0) % 360.0) - 180.0


def _nearest_m(geom: BaseGeometry, lon: float, lat: float) -> tuple[float, float, float]:
    """Metres to the nearest point of `geom`, honouring the antimeridian.

    The nearest point is taken over three placements of the geometry, so a point at
    lon -179.5 measures against a polygon part drawn at +179.5 (Fiji: 42 km, where a
    single planar measurement would return ~39,000 km), and the shortest geodesic
    distance of the three wins.
    """
    pt = Point(lon, lat)
    best: tuple[float, float, float] | None = None
    for shift in (-360.0, 0.0, 360.0):
        placed = geom if shift == 0.0 else shapely.affinity.translate(geom, xoff=shift)
        near = nearest_points(placed, pt)[0]
        metres = GEOD.inv(lon, lat, _wrap_lon(near.x), near.y)[2]
        if best is None or metres < best[0]:
            best = (metres, _wrap_lon(near.x), near.y)
    assert best is not None  # the three-shift loop always assigns
    return best


def _polygonal(geom: BaseGeometry) -> BaseGeometry | None:
    """The polygon parts of a geometry, made valid, or None when there are none.

    `make_valid` is not a fallback: Natural Earth ships self-intersecting rings (the
    classic Antarctica/Netherlands cases), and an invalid polygon answers `covers`
    unpredictably. Nothing is repaired silently into a *different* shape - only the
    polygon parts are kept, and a feature with no polygon at all is dropped and logged.
    """
    fixed = geom if geom.is_valid else make_valid(geom)
    if fixed.geom_type == "GeometryCollection":
        parts: list[BaseGeometry] = []
        for part in fixed.geoms:
            parts.extend(list(part.geoms) if part.geom_type == "MultiPolygon" else [part])
        fixed = MultiPolygon([p for p in parts if p.geom_type == "Polygon"])
    if fixed.geom_type not in ("Polygon", "MultiPolygon") or fixed.is_empty:
        return None
    return fixed


class _Atlas:
    """Natural Earth's countries, indexed for resolving and for locating a point."""

    def __init__(self, features: list[_Feature]) -> None:
        if not features:
            raise RuntimeError("no Natural Earth features were loaded")
        self.features = features
        self._by_iso: dict[str, list[int]] = defaultdict(list)
        self._by_name: dict[str, list[int]] = defaultdict(list)
        self._by_sovereign: dict[str, list[int]] = defaultdict(list)
        for i, feature in enumerate(features):
            for code in feature.iso_codes:
                self._by_iso[code.upper()].append(i)
            for key in feature.name_keys:
                self._by_name[key].append(i)
            self._by_sovereign[_fold(feature.sovereign)].append(i)
        self._tree = STRtree([f.geom for f in features])
        self._cache: dict[str, _Claim | None] = {}

    def claim(self, country: str) -> _Claim | None:
        """The geometry `country` names, or None when nothing in Natural Earth matches."""
        if country not in self._cache:
            self._cache[country] = self._resolve(country)
        return self._cache[country]

    def _resolve(self, country: str) -> _Claim | None:
        key = _strip_qualifier(country)
        iso = _project_iso(key)
        via = f"pipeline/utils/country_lookup.py:{iso}"
        idxs = self._by_iso.get(iso) if iso else None
        if not idxs:
            via = f"naturalearth:name={_fold(key)}"
            idxs = self._by_name.get(_fold(key))
        if not idxs:
            return None
        matched = [self.features[i] for i in sorted(set(idxs))]
        geom = union_all([f.geom for f in matched])
        # A claim naming a sovereign state covers everything it is sovereign over:
        # otherwise `France` would be "wrong" for the Marquesas for no defensible reason.
        extra: list[_Feature] = []
        for sovereign in sorted({f.sovereign for f in matched if f.is_sovereign}):
            for i in self._by_sovereign[_fold(sovereign)]:
                candidate = self.features[i]
                if i not in set(idxs) and candidate.kind not in CONTESTED_TYPES:
                    extra.append(candidate)
        if extra:
            geom = union_all([geom, *[f.geom for f in extra]])
        return _Claim(
            geom=geom,
            matched=tuple(sorted({f.admin for f in matched})),
            territories=tuple(sorted({f.admin for f in extra})),
            via=via,
        )

    def containing(self, lon: float, lat: float) -> list[str]:
        """ADMIN names of the features whose polygon covers the point (usually 0 or 1)."""
        pt = Point(lon, lat)
        return sorted(
            {
                self.features[int(i)].admin
                for i in self._tree.query(pt)
                if self.features[int(i)].geom.covers(pt)
            }
        )


def _project_iso(country: str) -> str | None:
    """The project's own country -> ISO code mapping, or None when it has none.

    `normalize_country` returns a lowercased name when it does not know a country and the
    uppercased input when it looks like a code, so only a 2-letter answer counts here.
    """
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.utils.country_lookup import normalize_country

    iso = normalize_country(country)
    if len(iso) == 2 and iso.isalpha():
        return iso.upper()
    return None


def _load_features(shapefile: Path) -> list[_Feature]:
    """Read the unpacked Natural Earth shapefile into features."""
    frame = gpd.read_file(str(shapefile))
    features: list[_Feature] = []
    for row in frame.itertuples():
        geom = _polygonal(row.geometry)
        if geom is None:
            log.warning("T02: dropping non-polygonal Natural Earth feature %s", _text(row.ADMIN))
            continue
        iso = tuple(
            sorted(
                {
                    code.upper()
                    for field in ISO_FIELDS
                    if (code := _text(getattr(row, field))) and not code.startswith("-")
                }
            )
        )
        admin = _text(row.ADMIN)
        keys = {_fold(_text(getattr(row, field))) for field in NAME_FIELDS}
        keys |= {_fold(alt) for alt in _text(row.NAME_ALT).split("|")}
        features.append(
            _Feature(
                admin=admin,
                sovereign=_text(row.SOVEREIGNT) or admin,
                kind=_text(row.TYPE),
                name_keys=tuple(sorted(k for k in keys if k)),
                iso_codes=iso,
                geom=geom,
            )
        )
    return features


# -------------------------------------------------------------------- collection
def _dataset_dir(cache: Path) -> Path:
    return Path(cache) / CACHE_DIRNAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(
    url: str, archive: Path, state_path: Path, fetched_at: str, member: str = NE_SHAPEFILE
) -> None:
    """Fetch the archive to `archive` and record what was fetched, or raise.

    Raises `FetchError` on anything that is not a 200 with a real ZIP body that contains
    `member`: an unreachable mirror is a hole in the census, never an empty result.
    """
    partial = archive.with_suffix(".part")
    with httpx.stream(
        "GET", url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=180.0
    ) as response:
        if response.status_code != 200:
            raise FetchError(f"{url}: HTTP {response.status_code} - the archive is not available")
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 16):
                handle.write(chunk)
    try:
        with zipfile.ZipFile(partial) as zf:
            members = zf.namelist()
            if member not in members:
                raise FetchError(f"{url}: archive has no {member} (members: {members[:5]})")
    except zipfile.BadZipFile as exc:
        partial.unlink(missing_ok=True)
        raise FetchError(f"{url}: response was not a ZIP archive ({exc})") from exc
    partial.replace(archive)
    state_path.write_text(
        json.dumps(
            {
                "url": url,
                "sha256": _sha256(archive),
                "bytes": archive.stat().st_size,
                "fetched_at": fetched_at,
                "members": members,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log.info("T02: fetched %s (%d bytes)", url, archive.stat().st_size)


def collect_archive(base: Path, url: str, archive_name: str, member: str) -> Path:
    """Download a Natural Earth archive into `base` once, unpack it, return `member`'s path.

    Idempotent: an archive whose sha256 matches the recorded one (`base/source.json`) is never
    refetched, and the unpack step is skipped when the member is already there.
    """
    base.mkdir(parents=True, exist_ok=True)
    archive = base / archive_name
    state_path = base / "source.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if archive.exists() and state.get("sha256") == _sha256(archive):
        log.info("T02: archive already cached (%s)", str(state.get("sha256"))[:16])
    else:
        _download(url, archive, state_path, now_iso(), member)

    target = base / member
    if not target.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(base)
        log.info("T02: unpacked %s into %s", archive_name, base)
    if not target.exists():
        raise FetchError(f"{archive} does not contain {member}")
    return target


def collect(ctx: Context) -> None:
    """Download the Natural Earth 10m admin-0 dataset into the cache and unpack it.

    Idempotent (see `collect_archive`). The only network call this module ever makes.
    """
    ctx.net()  # no Fetcher is a hard error: skipping the download would fake a clean run
    collect_archive(_dataset_dir(ctx.cache), NE_URL, NE_ARCHIVE, NE_SHAPEFILE)


def _atlas(ctx: Context) -> _Atlas:
    """The reference countries, read from the cache - never from the network."""
    shapefile = _dataset_dir(ctx.cache) / NE_SHAPEFILE
    if not shapefile.exists():
        raise FileNotFoundError(
            f"T02: {shapefile} is missing - run the census with --collect first "
            f"(collect() downloads {NE_URL})"
        )
    return _Atlas(_load_features(shapefile))


def _retrieved_at(ctx: Context) -> str | None:
    state_path = _dataset_dir(ctx.cache) / "source.json"
    if not state_path.exists():
        return None
    return str(json.loads(state_path.read_text(encoding="utf-8")).get("fetched_at"))


# --------------------------------------------------------------------- the check
def _coordinates(site: dict[str, Any]) -> tuple[float, float] | None:
    """(lat, lon) as floats, or None when the site carries no usable point."""
    lat, lon = site.get("lat"), site.get("lon")
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    if not isinstance(lat, int | float) or not isinstance(lon, int | float):
        return None
    if not (-90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0):
        return None
    return float(lat), float(lon)


def _claim_of(site: dict[str, Any]) -> str:
    return str(site.get("country") or "").strip()


def applies_to(site: dict[str, Any], ctx: Context) -> bool:
    """A site is tested when it claims a country and carries a usable point.

    Sites without either are `not_applicable`, never `pass`: "we had nothing to test" and
    "we tested it and it was fine" are different results.
    """
    return bool(_claim_of(site)) and _coordinates(site) is not None


def run(ctx: Context) -> list[Finding]:
    atlas = _atlas(ctx)
    retrieved = _retrieved_at(ctx)
    findings: list[Finding] = []

    for site in ctx.sites:
        country = _claim_of(site)
        coords = _coordinates(site)
        if not country or coords is None:
            continue  # applies_to() reports these as not_applicable
        lat, lon = coords
        sid = str(site["id"])

        claim = atlas.claim(country)
        if claim is None:
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/unmatched-country",
                    field="country",
                    severity=Severity.COSMETIC,
                    dimension=DIMENSION,
                    current_value=site.get("country"),
                    proposal=Proposal.REVIEW,
                    confidence=Confidence.UNVERIFIABLE,
                    note=f"{country!r} matches no Natural Earth admin-0 feature, so the point could "
                    "not be tested; our country vocabulary and Natural Earth's differ here",
                    evidence=[
                        Evidence(
                            source="naturalearth:ne_10m_admin_0_countries (ADMIN/NAME/NAME_ALT)",
                            url=NE_URL,
                            quote=f"no feature named {country!r} (folded: "
                            f"{_fold(_strip_qualifier(country))!r})",
                            retrieved_at=retrieved,
                        ),
                        Evidence(
                            source="snapshot:unified_sites.country", quote=f"country = {country!r}"
                        ),
                    ],
                )
            )
            continue

        if claim.geom.covers(Point(lon, lat)):
            continue
        distance_m, near_lon, near_lat = _nearest_m(claim.geom, lon, lat)
        if distance_m <= TOLERANCE_M:
            continue  # within the floor of what the polygon and the coordinate can produce

        containing = atlas.containing(lon, lat)
        where = ", ".join(containing) if containing else "no country polygon (open water)"
        resolved = f"{country!r} -> Natural Earth {'/'.join(claim.matched)}"
        if claim.territories:
            resolved += f", widened to the sovereign's territory: {', '.join(claim.territories)}"
        findings.append(
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/outside-polygon",
                field="country",
                severity=_severity(distance_m),
                dimension=DIMENSION,
                current_value=site.get("country"),
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note=f"point ({lat:.5f}, {lon:.5f}) lies {distance_m / 1000.0:.1f} km outside the "
                f"{'/'.join(claim.matched)} polygon (nearest boundary {near_lat:.5f}, "
                f"{near_lon:.5f}); Natural Earth places it in {where}. Either "
                "`country` or the coordinates are wrong - T02 cannot tell which, and Natural "
                "Earth draws de-facto borders and drops small islands",
                evidence=[
                    Evidence(
                        source=f"naturalearth:ne_10m_admin_0_countries ({'/'.join(claim.matched)})",
                        url=NE_URL,
                        quote=f"point outside by {distance_m / 1000.0:.2f} km; nearest boundary point "
                        f"({near_lat:.5f}, {near_lon:.5f}); contained in {where}",
                        retrieved_at=retrieved,
                    ),
                    Evidence(
                        source="snapshot:unified_sites.lat/lon", quote=f"lat = {lat}, lon = {lon}"
                    ),
                    Evidence(source=f"country resolved via {claim.via}", quote=resolved),
                ],
            )
        )

    return findings
