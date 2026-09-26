"""Stage 2: pin a grounded name to a real-world entity — without laundering.

Paths, in order of trust:
  citation  the paper's own reference list links the article (free, exact)
  title     the name IS an English-Wikipedia title (after redirects)
  search    Wikidata wbsearchentities + enwiki sitelink filter + the existing
            _pick_wikidata_entity tiebreak (LLM only when 2+ candidates)

After EVERY path the code requires `_is_same_name(name, label)`. A search
engine will happily return a real QID, real coordinates and a real article
for the wrong building ("Sicyonian Treasury" -> Siphnian Treasury); the
name check is the one line that stops that card shipping. On failure the
entity is NOT attached and `note` names the rejected label so the reviewer
sees what was declined.

Rejection filters, each from a field the API actually returns:
  no P625 coordinates             -> not_a_place   (Smithsonian Institution)
  P625 precision >= 0.1 degrees   -> area_not_point (Texas: precision 1)
  P31 in the admin/region denylist -> region
  coordinates on another globe     -> off_earth
  passes_date_cutoff() False       -> out_of_scope (project scope rule)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pipeline.lyra.config import _get_settings
from pipeline.lyra.prospector.wiki import TitleResolution, resolve_titles
from pipeline.lyra.site_identifier import (
    _check_enwiki_sitelinks,
    _enrich_from_wikidata,
    _fetch_qid_labels,
    _fetch_wikipedia_summary,
    _parse_wikidata_time,
    _pick_wikidata_entity,
    _resolve_site_type_from_p31,
)
from pipeline.lyra.site_matcher import _is_same_name
from pipeline.lyra.site_researcher import _search_wikidata
from pipeline.normalizers.dates import passes_date_cutoff
from pipeline.utils.country_lookup import lookup_country

logger = logging.getLogger(__name__)

AREA_PRECISION_DEG = 0.1

# P31 values that are administrative or geographic REGIONS, never a site a
# person could excavate. Deliberately short and unambiguous — cities are left
# to the precision filter and the human, because "Jericho" is both a city
# and a tell.
REGION_P31 = {
    "Q6256": "country",
    "Q5107": "continent",
    "Q3624078": "sovereign state",
    "Q10864048": "first-level administrative division",
    "Q13220204": "second-level administrative division",
    "Q35657": "U.S. state",
    "Q1221156": "state of Germany",
    "Q82794": "geographic region",
    "Q1620908": "historical region",
    "Q46831": "mountain range",
    "Q165": "sea",
    "Q9430": "ocean",
    "Q23397": "lake",
    "Q4022": "river",
    "Q8502": "mountain",
    "Q8514": "desert",
}


@dataclass
class Resolution:
    name: str
    path: str = "none"  # citation | title | search | none
    verdict: str = (
        "unresolved"  # resolved | unresolved | not_a_place | area_not_point | region | off_earth
    )
    canonical_title: str | None = None
    qid: str | None = None
    label: str | None = None
    lat: float | None = None
    lon: float | None = None
    coord_precision: float | None = None
    country: str | None = None
    site_type: str | None = None
    period_start: int | None = None
    period_end: int | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    wikipedia_url: str | None = None
    instance_of: list[str] = field(default_factory=list)
    in_scope: bool = True
    note: str | None = None
    # True only when the entity APIs returned nothing for an id we hold — the
    # signal that Wikidata is degraded. A same-name rejection or a missing
    # article is a data outcome, not a failure, and must not trip the abort.
    infra_failed: bool = False

    @property
    def has_point(self) -> bool:
        return self.lat is not None and self.lon is not None


DESIGNATION_WORDS = (
    "national monument",
    "national park",
    "national historic",
    "state park",
    "protected area",
    "world heritage",
    "heritage site",
    "museum",
    "visitor cent",
)


def _is_designation(instance_of: list[str]) -> bool:
    """True when any P31 label names a modern designation, not a place type."""
    if not instance_of:
        return False
    labels = _fetch_qid_labels(instance_of)
    return any(w in label.lower() for label in labels.values() for w in DESIGNATION_WORDS)


class ResolverBudget:
    """Caps the LLM tiebreak calls a run may spend; everything else is free."""

    def __init__(self, max_llm_calls: int):
        self.max_llm_calls = max_llm_calls
        self.llm_calls = 0
        self.failures = 0
        self.attempted = 0


def resolve_names(
    names: list[str],
    *,
    cited_titles: list[str],
    budget: ResolverBudget,
) -> dict[str, Resolution]:
    """Resolve a batch of grounded names. One Wikipedia batch call for the
    direct-title path; per-name work only for what that leaves open."""
    settings = _get_settings()
    out: dict[str, Resolution] = {}
    if not names:
        return out

    cited = _resolve_cited(cited_titles)
    direct = resolve_titles(names)

    for name in names:
        budget.attempted += 1
        res = Resolution(name=name)
        hit = _citation_hit(name, cited)
        if hit is not None:
            res.path, res.canonical_title, res.qid = "citation", hit.canonical_title, hit.qid
        else:
            d = direct.get(name)
            if d is not None and d.exists and not d.disambiguation:
                res.path, res.canonical_title, res.qid = "title", d.canonical_title, d.qid
                if d.globe and d.globe != "earth":
                    res.verdict = "off_earth"
                    res.note = f"coordinates on {d.globe}"
                    out[name] = res
                    continue
            else:
                _search(name, res, budget, settings)
        if res.qid is None and res.canonical_title is None:
            res.verdict = "unresolved"
            out[name] = res
            continue
        _confirm_and_enrich(res)
        if res.infra_failed:
            budget.failures += 1
        out[name] = res
    return out


def _resolve_cited(titles: list[str]) -> list[TitleResolution]:
    if not titles:
        return []
    return [r for r in resolve_titles(titles).values() if r.exists and not r.disambiguation]


def _citation_hit(name: str, cited: list[TitleResolution]) -> TitleResolution | None:
    for r in cited:
        if _is_same_name(name, r.canonical_title or "") or _is_same_name(name, r.input_title):
            return r
    return None


def _search(name: str, res: Resolution, budget: ResolverBudget, settings) -> None:
    cands = _search_wikidata(name)
    if not cands:
        res.note = "no Wikidata search result"
        return
    sitelinks = _check_enwiki_sitelinks([c["qid"] for c in cands if c.get("qid")])
    for c in cands:
        c["has_wikipedia"] = sitelinks.get(c.get("qid"), False)
    with_wiki = [c for c in cands if c["has_wikipedia"]]
    if len(with_wiki) > 1:
        if budget.llm_calls >= budget.max_llm_calls:
            res.note = "tiebreak budget spent; left unresolved"
            return
        budget.llm_calls += 1
    qid = _pick_wikidata_entity(settings.model_identify, name, None, None, cands)
    if qid:
        res.path, res.qid = "search", qid
    else:
        res.note = "no Wikidata candidate with an English article"


def _confirm_and_enrich(res: Resolution) -> None:
    """Attach the entity only if its label is the same name; then filter."""
    enrich = _enrich_from_wikidata(res.qid) if res.qid else {}
    if res.qid and not enrich:
        # _enrich_from_wikidata swallows network errors and returns {} — this
        # is the only place a degraded Wikidata becomes visible.
        res.infra_failed = True
        res.note = f"Wikidata returned nothing for {res.qid}"
        res.verdict = "unresolved"
        return
    label = enrich.get("label_en") or enrich.get("wikipedia_title") or res.canonical_title
    title = enrich.get("wikipedia_title") or res.canonical_title
    if not (
        (label and _is_same_name(res.name, label)) or (title and _is_same_name(res.name, title))
    ):
        res.note = f'resolved via {res.path} to "{label or title}" — rejected by same-name check'
        res.qid = res.canonical_title = None
        res.verdict = "unresolved"
        return

    res.label = label
    res.canonical_title = title or res.canonical_title
    res.wikipedia_url = enrich.get("wikipedia_url")
    res.instance_of = enrich.get("instance_of", [])
    res.thumbnail_url = enrich.get("thumbnail_url")
    res.country = enrich.get("country")
    res.coord_precision = enrich.get("coord_precision")
    if "lat" in enrich and "lon" in enrich:
        res.lat, res.lon = float(enrich["lat"]), float(enrich["lon"])

    region = [q for q in res.instance_of if q in REGION_P31]
    if region:
        res.verdict = "region"
        res.note = f"P31 {region[0]} ({REGION_P31[region[0]]})"
        return
    if not res.has_point:
        res.verdict = "not_a_place"
        res.note = "no P625 coordinates on Wikidata"
        return
    if res.coord_precision is not None and res.coord_precision >= AREA_PRECISION_DEG:
        res.verdict = "area_not_point"
        res.note = f"P625 precision {res.coord_precision}° is an area centroid"
        return

    if res.instance_of:
        res.site_type = _resolve_site_type_from_p31(res.instance_of)
    for key in ("start_time", "inception_time"):
        if enrich.get(key):
            res.period_start = _parse_wikidata_time(enrich[key])
            break
    if enrich.get("end_time"):
        res.period_end = _parse_wikidata_time(enrich["end_time"])
    # Wikidata "inception" of a national monument or park is the year it was
    # DESIGNATED, not the occupation: Gila Cliff Dwellings (13th c.) carries
    # 1907, Mesa Verde 1906. Both came back out_of_scope on the first real
    # run. A post-1500 date on a designation-class entity is not a period.
    if (
        res.period_start is not None
        and res.period_start > 1500
        and _is_designation(res.instance_of)
    ):
        res.period_start = res.period_end = None
        res.note = "Wikidata inception is a designation date (monument/park), period left open"
    if not res.country:
        res.country = lookup_country(res.lat, res.lon)
    if res.canonical_title:
        summary = _fetch_wikipedia_summary(res.canonical_title)
        res.description = summary.get("description")
        res.thumbnail_url = res.thumbnail_url or summary.get("thumbnail_url")
    res.in_scope = passes_date_cutoff(
        {
            "period_start": res.period_start,
            "period_end": res.period_end,
            "lat": res.lat,
            "lon": res.lon,
            "country": res.country,
        }
    )
    res.verdict = "resolved"
