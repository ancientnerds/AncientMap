"""The subject gate: is this English (or other-language) article about THIS site? A pure function.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, section
pipeline ("SUBJECT GATE") and failure_modes ("Wrong-subject article", "Directional-match trap").
Work item WB-A2. The verdict and the facts it was made from are recorded in the source's meta
(`model4.SubjectGate`); the verifier's V7 reads the verdict, the lane stage acts on it.

The facts, each recorded:

* `qid_match` - `pageprops.wikibase_item` equals the stored QID. Exact: a stored QID that Wikidata
  redirects elsewhere does not match, because the stored value is then stale data.
* `shared` - the stored QID or title, or the page's own item or title, is one that more than one
  curated site stores (`shared_qids`, `shared_titles`: plan4 derives them, GROUP BY ... HAVING
  count > 1).
* `concept` - the item is a class or a concept: it carries P279 (subclass of), in any rank that is
  not deprecated. `Q309` 'history' is one the rule catches.
* `place_item` - one of the item's P31 classes carries a place-level word in its English label
  (`PLACE_LEVEL_WORDS`, whole words: `ancient city`, `commune of France`, `human settlement`).
* `km` - the distance from the stored point to the article's primary coordinates, or to the item's
  P625 when the article has none. `None` when neither has coordinates.
* `name_score` - the directional name match: every stored name and alias against every Wikidata
  label and alias, rapidfuzz `token_sort_ratio`, the best pair. Never `token_set_ratio`, which
  reports 100 when one name's tokens are a subset of the other's ('Kilmartin' against 'Kilmartin
  Glen standing stones'). For a site that stores no QID the page title counts as a label too.
  `None` when there is nothing to compare.

The verdict, in this order - the first rule that fires decides:

1. A disambiguation page or a 'List of' title is refused: `none`.
2. A concept item: `wrong`.
3. Coordinates more than `WRONG_KM` away (`WRONG_KM_LINEAR` for a road, wall or aqueduct): `wrong`.
4. A shared anchor, or a place-level item for a site whose type is not a settlement type:
   `shared`.
5. A parent page: the page's item is another item than the stored one, and the page lies within
   the `wrong` radius (rule 3 has passed, so a known distance means it does). `shared`: only the
   sentences that name the site may be used (lane S). Without a known distance a mismatched page
   could be a namesake anywhere, so it stays `none`.
6. `own`: the QIDs match and the page lies within `max(OWN_KM, P625 precision)`; only when neither
   the article nor the item has coordinates may the name match (`NAME_MATCH_MIN`) stand in.
7. `own` for a site that stores **no** QID: its page's own item is the witness (the caller fetches
   it), and the page must lie within `max(OWN_KM, P625 precision)` **and** match a stored name
   (against the page title and the item's labels and aliases) - both, because the anchor a QID
   gives is missing. Without this rule no article could ever be a QID-less site's own, and the 13
   English and 39 other-language `source_url` sites the design sends to lanes W and T would all
   end in R or 0. The recorded `qid_match` stays `false`, so V6 can tell this `own` from the
   strong one.
8. Everything else: `none`.

`wrong` and `none` send the site to S1b (routes); `shared` sends it to lane S; `own` to lane W (or T
for an article in another language). The gate never fetches: its caller hands it the page, the
entity and the class labels, and a class the labels do not cover raises - the label pass must
cover every class, or the place-level test would silently pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from rapidfuzz import fuzz
from rapidfuzz import utils as fuzz_utils

from phase4 import model4 as M
from pipeline.utils.geo import haversine_distance
from pipeline.utils.text import normalize_name

#: The place-level P31 label words of the design (a municipality, a town, a region ...). The
#: design spells `neighbourhood`; Wikidata's English labels spell it `neighborhood` (Q123705), so
#: both spellings of the one word are listed.
PLACE_LEVEL_WORDS = frozenset(
    {
        "municipality",
        "village",
        "town",
        "city",
        "commune",
        "comune",
        "parish",
        "district",
        "county",
        "province",
        "region",
        "settlement",
        "locality",
        "neighbourhood",
        "neighborhood",
    }
)

#: A site_type is a settlement type when one of its `/`-separated parts is one of these: the
#: catalogue's `City/town/settlement`, `Settlement` and `City` (production, 2026-09-23).
SETTLEMENT_TYPE_PARTS = frozenset({"city", "town", "settlement", "village"})
#: The linear types the design gives the wider `wrong` radius: `Road/avenue/trackway`, `Road`,
#: `Wall`, `Reservoir/aqueduct/canal`, `Aqueduct`. `Megalithic walls` is a wall at one place.
LINEAR_TYPE_PARTS = frozenset({"road", "wall", "aqueduct"})

OWN_KM = 5.0
WRONG_KM = 25.0
WRONG_KM_LINEAR = 50.0
NAME_MATCH_MIN = 90.0

_LIST_TITLE = re.compile(r"Lists? of\b")
_WORD = re.compile(r"\w+")


def _type_parts(site_type: str | None) -> set[str]:
    return {part.strip().casefold() for part in (site_type or "").split("/")}


def is_settlement_type(site_type: str | None) -> bool:
    return bool(_type_parts(site_type) & SETTLEMENT_TYPE_PARTS)


def wrong_km(site_type: str | None) -> float:
    """The distance beyond which an article is about somewhere else."""
    return WRONG_KM_LINEAR if _type_parts(site_type) & LINEAR_TYPE_PARTS else WRONG_KM


def _fold(name: str) -> str:
    """Accents stripped and lowercased (`pipeline.utils.text.normalize_name`, the catalogue's own
    matching form), then rapidfuzz's default processing (non-alphanumerics to spaces)."""
    return fuzz_utils.default_process(
        normalize_name(name, remove_parentheses=False, remove_brackets=False)
    )


def name_score(names: Iterable[str], labels: Iterable[str]) -> float | None:
    """The best `token_sort_ratio` of any stored name against any label. `None` for no pair."""
    folded_names = [_fold(name) for name in names if _fold(name)]
    folded_labels = [_fold(label) for label in labels if _fold(label)]
    if not folded_names or not folded_labels:
        return None
    return max(fuzz.token_sort_ratio(a, b) for a in folded_names for b in folded_labels)


def _statements(entity: Mapping[str, Any], pid: str) -> list[Mapping[str, Any]]:
    """The item's statements of one property that are not deprecated."""
    claims = entity.get("claims") or {}
    return [s for s in claims.get(pid, []) if s.get("rank") != "deprecated"]


def _value(statement: Mapping[str, Any]) -> Any:
    snak = statement.get("mainsnak") or {}
    if snak.get("snaktype") != "value":
        return None
    return (snak.get("datavalue") or {}).get("value")


def p31_classes(entity: Mapping[str, Any]) -> tuple[str, ...]:
    """The item's P31 (instance of) classes, in statement order, without repeats."""
    classes: list[str] = []
    for statement in _statements(entity, "P31"):
        value = _value(statement)
        if isinstance(value, Mapping) and isinstance(value.get("id"), str):
            if value["id"] not in classes:
                classes.append(value["id"])
    return tuple(classes)


def entity_labels(entity: Mapping[str, Any]) -> tuple[str, ...]:
    """Every label and alias the entity carries, in any language it was fetched with."""
    labels = [v["value"] for v in (entity.get("labels") or {}).values() if v.get("value")]
    for aliases in (entity.get("aliases") or {}).values():
        labels.extend(a["value"] for a in aliases if a.get("value"))
    return tuple(labels)


def _p625(entity: Mapping[str, Any]) -> tuple[float, float, float | None] | None:
    """The item's best coordinate (preferred rank first): lat, lon and precision in degrees."""
    statements = _statements(entity, "P625")
    best = [s for s in statements if s.get("rank") == "preferred"] or statements
    for statement in best:
        value = _value(statement)
        if isinstance(value, Mapping) and value.get("latitude") is not None:
            precision = value.get("precision")
            return (
                float(value["latitude"]),
                float(value["longitude"]),
                None if precision is None else float(precision),
            )
    return None


def _article_point(page: Mapping[str, Any]) -> tuple[float, float] | None:
    for point in page.get("coordinates") or []:
        if point.get("primary") is True:
            return float(point["lat"]), float(point["lon"])
    return None


def _precision_km(precision_degrees: float) -> float:
    """A coordinate precision in degrees as a distance on the ground, along a meridian."""
    return haversine_distance(0.0, 0.0, precision_degrees, 0.0)


def subject_gate(
    site: M.PlanSite,
    *,
    page: Mapping[str, Any],
    entity: Mapping[str, Any] | None,
    class_labels: Mapping[str, str],
    shared_qids: frozenset[str],
    shared_titles: frozenset[str],
) -> M.SubjectGate:
    """The recorded facts and the verdict for one article of one site (module docstring).

    `page` is one page object of the MediaWiki query answer (`formatversion=2`); `entity` is the
    stored QID's Wikidata entity - or, for a site that stores no QID, the page's own item (rule 7),
    or `None` when the page names none. A page the answer marks `missing` has no subject to judge
    and raises.
    """
    if page.get("missing") or not isinstance(page.get("title"), str):
        raise ValueError(f"{site.site_id}: a missing page has no subject to judge: {page!r}")
    title = page["title"]
    pageprops = page.get("pageprops") or {}
    item = pageprops.get("wikibase_item")
    qid_match = site.wikidata_qid is not None and item == site.wikidata_qid
    shared = bool(
        {site.wikidata_qid, item} & shared_qids or {site.enwiki_title, title} & shared_titles
    )
    concept = entity is not None and bool(_statements(entity, "P279"))
    place_item = False
    p625 = None
    labels: tuple[str, ...] = ()
    if entity is not None:
        if site.wikidata_qid is None and entity.get("id") != item:
            raise ValueError(
                f"{site.site_id}: a site without a QID is judged on its page's item {item}, "
                f"not on {entity.get('id')}"
            )
        uncovered = [cls for cls in p31_classes(entity) if cls not in class_labels]
        if uncovered:
            raise ValueError(f"{site.site_id}: no class label for P31 {uncovered}")
        place_item = any(
            set(_WORD.findall(class_labels[cls].casefold())) & PLACE_LEVEL_WORDS
            for cls in p31_classes(entity)
        )
        p625 = _p625(entity)
        labels = entity_labels(entity)
    point = _article_point(page)
    if point is None and p625 is not None:
        point = (p625[0], p625[1])
    km = None if point is None else haversine_distance(site.lat, site.lon, point[0], point[1])
    own_km = OWN_KM
    if p625 is not None and p625[2] is not None:
        own_km = max(OWN_KM, _precision_km(p625[2]))
    if site.wikidata_qid is None:
        labels = (title, *labels)
    score = name_score((site.name, *site.aliases), labels)

    if "disambiguation" in pageprops or _LIST_TITLE.match(title):
        verdict = M.SubjectVerdict.NONE
    elif concept:
        verdict = M.SubjectVerdict.WRONG
    elif km is not None and km > wrong_km(site.site_type):
        verdict = M.SubjectVerdict.WRONG
    elif shared or (place_item and not is_settlement_type(site.site_type)):
        verdict = M.SubjectVerdict.SHARED
    elif site.wikidata_qid is not None and item is not None and not qid_match:
        verdict = M.SubjectVerdict.SHARED if km is not None else M.SubjectVerdict.NONE
    elif qid_match and km is not None:
        verdict = M.SubjectVerdict.OWN if km <= own_km else M.SubjectVerdict.NONE
    elif qid_match and score is not None and score >= NAME_MATCH_MIN:
        verdict = M.SubjectVerdict.OWN
    elif (
        site.wikidata_qid is None
        and entity is not None
        and km is not None
        and km <= own_km
        and score is not None
        and score >= NAME_MATCH_MIN
    ):
        verdict = M.SubjectVerdict.OWN
    else:
        verdict = M.SubjectVerdict.NONE
    return M.SubjectGate(
        qid_match=qid_match,
        shared=shared,
        concept=concept,
        place_item=place_item,
        km=None if km is None else round(km, 3),
        name_score=None if score is None else round(float(score), 1),
        verdict=verdict,
    )
