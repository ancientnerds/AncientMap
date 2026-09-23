"""The owner cases, decided from data: B1 names, B1/B2 coordinates, B2 countries, duplicates.

Every function here is pure - a function of the export and the caches `collect.py` wrote - and every
record it returns carries its class **and the evidence the class was decided from**, so a reader can
check a verdict without re-running anything. Nothing here writes to production; the coordinate
verdicts become a plan in `coord_plan.py`, and the duplicate verdicts a list the scope lane reads.

## B1 names (the 631 `T01/name` and `T01/name-variant` findings)

The question HUMAN_ONLY B1 asks - "is the stored name wrong, or an alias?" - is answered by the linked
item's own names: every label, alias and wiki sitelink title in every language, plus the site's
English title. In this order, first match wins:

* **N1** the stored name *is* one of them (folded: accents, case and a bracketed suffix dropped);
* **N2** the same words once the generic ones ("site", "ruins", "archaeological", ...) are gone;
* **N3** one word set contains the other (a descriptive form: "Temple of Hibis" / "Hibis");
* **Q1** the item is a generic concept (lower-case English label and no coordinate: Q309 "history");
* **N6** a transliteration: a character ratio of at least 0.8 to one of the names;
* **Q2** the item is shared with other curated sites (a parent or a sibling, not this site);
* **Q3** the item has no coordinate at all;  **Q4** its coordinate is more than 5 km away;
* **N7** none of these: a residual to read (split by whether the item is a locality).

N1-N3 and N6 **keep** the stored name (no write), Q1-Q4 are a **wrong link** (an external-id repair,
`output/remediation/tools/qid_repair.py` wave 2), N7 is the short **review** list.

## B1/B2 coordinates

A coordinate is changed only when **two independent witnesses agree within the tolerance and the
stored point lies outside it**. The witnesses are Wikidata `P625` and the English article's primary
coordinates (OpenStreetMap was not reachable from this workstation, `collect.py`). Two witnesses are
*not* independent when one says it was imported from the other (`P625` referenced to English
Wikipedia) or when their points are the same point (within `COPY_M` or the item's own precision):
Petroglyph Beach's Wikidata and Wikipedia coordinates are both downtown Juneau (plan anti-pattern 9)
and count once. The tolerance
is T01's: 1000 m, floored by `P625`'s own precision. Before any witness is read, an item that is not
the site itself stops the case: an item shared with other curated sites, a settlement, administrative
unit or natural feature that contains the site, a linear or areal feature, or an item whose names do
not include the stored name (N1/N2). A museum-held object (`P189` find-spot plus `P195`/`P276`) is
judged against its **find-spot** - its own `P625` is the museum - and moved only when the stored point
is at the holding museum.

## B2 countries (the 117 `T02` findings)

The remaining-work map's classification: political lines already decided (B10), coastline and border
artefacts, the `Northern Ireland` vocabulary gap and the B9 rows, wrong countries (point and `P625`
agree), wrong coordinates (`P625` or the site's own description names the stored country), rows that
need a witness, and one value that is not a country.

## Duplicates

Two curated sites sharing one Wikidata item, within 2 km, **both** of whose names are names of that
item, are one site recorded twice (DUP). One name only is a part-of or synonym pair, neither is a
generic anchor, more than 2 km is a wrong item on one side. The survivor of a DUP group is the row with
more content links, then more sources, then the older `created_at`, then the lower id - the last step
only makes the rule total, it judges nothing.
"""

from __future__ import annotations

import difflib
import itertools
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from census.tests.t01_wikidata_claims import METRES_PER_DEGREE, SEVERE_M, TOLERANCE_M

from bcases import inputs

_TOOLS = inputs.REPO / "output" / "remediation" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import country_census as CC  # noqa: E402 - the boundary file and its spelling rules, never copied
from vlm_pilot.common import write_jsonl  # noqa: E402

from pipeline.utils.country_lookup import normalize_country  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402

WD = "https://www.wikidata.org/wiki/"
WP = "https://en.wikipedia.org/wiki/"

# ------------------------------------------------------------------------------------ vocabulary
#: Words that say what kind of place a name is, not which one - in the languages the curated names
#: use. Two names that differ only in these are the same name ("Olympia" / "Archaeological Site of
#: Olympia", the UNESCO form section 4.3 documents as correct). `d` and `l` are the elided French and
#: Italian articles a fold leaves behind ("tumulus d'Er Grah" / "Er-Grah Tumulus").
GENERIC = frozenset(
    """the of de del della di du des la le les el los las d l y e et und and a an ancient antique antik
    old archaeological archeological archaeologic archeologic arqueologico arqueologica archeologica
    archeologique arkeolojik site sites area park national ruins ruin remains city town complex oren
    yeri orenyeri tarihi alani kenti harabeleri zona sitio parque ciudad romana conjunto conservation
    """.split()
)

#: A class that names a modern settlement, an administrative unit or a natural feature: an item of
#: this class *contains* the site, and its point is not the site's point. Matched as whole words.
CONTAINER_WORDS = (
    "human settlement",
    "village",
    "town",
    "city",
    "municipality",
    "municipal unit",
    "commune",
    "comune",
    "frazione",
    "ortsteil",
    "region",
    "mountain",
    "hill",
    "island",
    "valley",
    "district",
    "peninsula",
    "bay",
    "locality",
    "urban area",
    "parish",
    "townland",
    "summit",
    "cadastral",
    "seat",
    "geographical feature",
    "mahalle",
    "subdivisions",
    "populated place",
    "neighborhood",
    "neighbourhood",
    "suburb",
    "province",
    "county",
    "oasis",
)
#: Words that make such a class a *site* again: "ancient city", "Roman city", "city walls",
#: "submerged settlement", "hill fort" are what the curated set records, not what contains it.
SITE_WORDS = (
    "ancient",
    "archaeological",
    "roman",
    "greek",
    "maya",
    "etruscan",
    "phoenician",
    "hittite",
    "prehistoric",
    "wall",
    "walls",
    "fort",
    "fortress",
    "hillfort",
    "ruins",
    "destroyed",
    "submerged",
    "abandoned",
    "deserted",
    "lost",
    "underground",
    "polis",
    "city-state",
    "kingdom",
    "tell",
    "tumulus",
)
#: A class whose point is an arbitrary spot on a line or an area: a road, a wall, a park.
LINEAR_OR_AREAL_WORDS = (
    "road",
    "trackway",
    "defensive wall",
    "walls",
    "aqueduct",
    "canal",
    "dyke",
    "limes",
    "national park",
    "protected area",
    "regional park",
    "natura 2000",
    "archaeological park",
    "world heritage site",
    "historical park",
    "transboundary",
    "grave field",
    "cultural landscape",
)

#: The distance a coordinate change must not be smaller than, and T01's severe edge (metres).
COPY_M = 5.0
#: Two curated sites on one item further apart than this are two places, not one (DUP rule).
DUP_MAX_M = 2000.0
#: A name finding whose item is further away than this is a wrong link (Q4).
FAR_KM = 5.0
#: A transliteration: the folded names are this similar (difflib ratio), N6.
TRANSLIT_RATIO = 0.8


def fold(name: str) -> str:
    """A comparable spelling: no accents, no case, no bracketed suffix, words single-spaced."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    text = re.sub(r"\(.*?\)", "", text)
    return " ".join(re.findall(r"[^\W_]+", text))


def tokens(name: str) -> frozenset[str]:
    """The words of a name that say which place it is."""
    return frozenset(fold(name).split()) - GENERIC


def squash(name: str) -> str:
    return fold(name).replace(" ", "")


def _has_word(label: str, words: Iterable[str]) -> bool:
    low = label.casefold()
    return any(re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", low) for w in words)


def is_container_class(label: str) -> bool:
    return _has_word(label, CONTAINER_WORDS) and not _has_word(label, SITE_WORDS)


def is_linear_or_areal_class(label: str) -> bool:
    return _has_word(label, LINEAR_OR_AREAL_WORDS)


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_distance(lat1, lon1, lat2, lon2)


def known_names(
    qid: str | None, names: Mapping[str, Any], extra: Mapping[str, str] | None = None
) -> dict[str, list[str]]:
    """`{name: [where it comes from]}` - the item's labels, aliases and sitelinks, plus `extra`."""
    out: dict[str, list[str]] = defaultdict(list)
    entity = names.get(qid or "") or {}
    for lang, value in sorted((entity.get("labels") or {}).items()):
        out[value].append(f"label:{lang}")
    for lang, values in sorted((entity.get("aliases") or {}).items()):
        for value in values:
            out[value].append(f"alias:{lang}")
    for site, value in sorted((entity.get("sitelinks") or {}).items()):
        out[value].append(f"sitelink:{site}")
    for value, where in (extra or {}).items():
        out[value].append(where)
    return dict(out)


def name_identity(stored: str, candidates: Mapping[str, list[str]]) -> tuple[str, str | None]:
    """(`N1`/`N2`/`N3`, the matching name) or (`none`, None). Candidates are read in sorted order so
    the reported match does not depend on hash order."""
    folded, words = fold(stored), tokens(stored)
    ordered = sorted(candidates)
    for name in ordered:
        if fold(name) == folded:
            return "N1", name
    for name in ordered:
        theirs = tokens(name)
        if theirs and words and theirs == words:
            return "N2", name
    for name in ordered:
        theirs = tokens(name)
        if theirs and words and (theirs <= words or words <= theirs):
            return "N3", name
    return "none", None


def shared_counts(sites: Mapping[str, Mapping[str, Any]]) -> Counter[str]:
    return Counter(str(s["qid"]) for s in sites.values() if s.get("qid"))


def p31_labels_of(qid: str, t01: Mapping[str, Any], labels: Mapping[str, Any]) -> list[str]:
    return [labels.get(q) or q for q in (t01.get(qid) or {}).get("instance_qids") or ()]


def _evidence(source: str, quote: str, url: str | None = None) -> dict[str, Any]:
    return {"source": source, "quote": quote, "url": url}


# ----------------------------------------------------------------------------------- B1 names
NAME_GROUP = {
    "N1": "keep",
    "N2": "keep",
    "N3": "keep",
    "N6": "keep",
    "Q1": "wrong-link",
    "Q2": "wrong-link",
    "Q3": "wrong-link",
    "Q4": "wrong-link",
    "N7": "review",
}


def classify_name(
    finding: Mapping[str, Any],
    site: Mapping[str, Any],
    *,
    census_enwiki: str | None,
    names: Mapping[str, Any],
    t01: Mapping[str, Any],
    labels: Mapping[str, Any],
    shared: Mapping[str, int],
) -> dict[str, Any]:
    """One B1 name finding: keep the stored name, repair the link, or read it.

    Decided against the links the census compared (`census_enwiki`, and `shared` counted over the
    census's items): a link repaired since is the record's `state`, not a different question.
    """
    qid = inputs.qid_of_finding(finding)
    stored = str(site["name"])
    extra = {census_enwiki: "enwiki_title"} if census_enwiki else {}
    candidates = known_names(qid, names, extra)
    claims = t01.get(qid) or {}
    en_label = claims.get("en_label")
    distance = (
        None
        if claims.get("lat") is None
        else km(site["lat"], site["lon"], claims["lat"], claims["lon"])
    )
    cls, hit = name_identity(stored, candidates)
    ratio = None
    if cls == "none":
        own = {name for name, where in candidates.items() if where != ["enwiki_title"]}
        ratio = max(
            (difflib.SequenceMatcher(None, squash(stored), squash(n)).ratio() for n in own),
            default=0.0,
        )
        nocoord = claims.get("lat") is None
        if nocoord and (en_label or "")[:1].islower():
            cls = "Q1"
        elif ratio >= TRANSLIT_RATIO:
            cls = "N6"
            hit = max(
                sorted(own),
                key=lambda n: difflib.SequenceMatcher(None, squash(stored), squash(n)).ratio(),
            )
        elif shared.get(qid, 0) > 1:
            cls = "Q2"
        elif nocoord:
            cls = "Q3"
        elif distance is not None and distance > FAR_KM:
            cls = "Q4"
        else:
            cls = "N7"
    p31 = p31_labels_of(qid, t01, labels)
    evidence = [
        _evidence("snapshot:unified_sites.name", f"name = {finding['current_value']!r}"),
        _evidence("wikidata:en label", f"en label = {en_label!r}", f"{WD}{qid}"),
    ]
    if hit is not None:
        evidence.append(
            _evidence(
                "wikidata:names",
                f"{hit!r} is {', '.join(candidates.get(hit, []))} of {qid}",
                f"{WD}{qid}",
            )
        )
    if cls in ("Q1", "Q3"):
        evidence.append(_evidence("wikidata:P625", f"{qid} has no P625", f"{WD}{qid}"))
    if cls == "Q2":
        evidence.append(
            _evidence(
                "production:site_external_ids", f"{qid} is linked by {shared[qid]} curated sites"
            )
        )
    if cls == "Q4":
        evidence.append(
            _evidence(
                "wikidata:P625", f"P625 is {distance:.2f} km from the stored point", f"{WD}{qid}"
            )
        )
    record = {
        "site_id": finding["site_id"],
        "test_id": finding["test_id"],
        "name": stored,
        "snapshot_name": finding["current_value"],
        "qid": qid,
        "qid_now": site.get("qid"),
        "en_label": en_label,
        "class": cls,
        "group": NAME_GROUP[cls],
        "match": hit,
        "char_ratio": None if ratio is None else round(ratio, 3),
        "p625_km": None if distance is None else round(distance, 3),
        "shared_by": shared.get(qid, 0),
        "p31": p31,
        "evidence": evidence,
    }
    if cls == "N7":
        record["n7"] = (
            "anchor-is-locality" if any(map(is_container_class, p31)) else "anchor-is-a-site"
        )
    if site.get("qid") != qid:
        record["state"] = f"link changed since the census: {qid} -> {site.get('qid')}"
    if stored != finding["current_value"]:
        record["state"] = (
            f"name changed since the census: {finding['current_value']!r} -> {stored!r}"
        )
    return record


# ------------------------------------------------------------------------------- the witnesses
@dataclass(frozen=True)
class Witness:
    """One independent statement of where an item is."""

    kind: str  #: "wikidata" or "enwiki"
    lat: float
    lon: float
    url: str
    quote: str
    precision_m: float = 0.0
    #: The kind of witness this one says it was copied from ("enwiki" for a P625 imported from it).
    derived_from: str | None = None


def precision_m(precision: Any) -> float:
    """Half of Wikidata's P625 precision in metres - the value's own uncertainty (T01's floor)."""
    if isinstance(precision, int | float) and not isinstance(precision, bool):
        return float(precision) * METRES_PER_DEGREE / 2.0
    return 0.0


def _p625_from_enwiki(references: Mapping[str, Sequence[str]]) -> bool:
    """Whether a P625 says it was imported from English Wikipedia (P143 Q328, or its import URL)."""
    if "Q328" in (references.get("P143") or ()):
        return True
    return any("en.wikipedia.org" in url for url in references.get("P4656") or ())


def witnesses(
    qid: str,
    *,
    claims: Mapping[str, Any],
    enwiki: Mapping[str, Any],
    extra_titles: Sequence[str] = (),
) -> tuple[list[Witness], list[str]]:
    """The witnesses for one item, and the notes on every witness that was not usable."""
    notes: list[str] = []
    record = claims.get(qid)
    if record is None:
        raise inputs.InputError(f"{qid} is not in the witness claims - run `collect` again")
    out: list[Witness] = []
    p625 = record.get("p625")
    if p625 is None:
        notes.append(f"{qid} has no P625")
    elif p625.get("globe") not in (None, "Q2"):
        notes.append(f"{qid} P625 is on globe {p625['globe']}")
    else:
        refs = p625.get("references") or {}
        from_en = _p625_from_enwiki(refs)
        out.append(
            Witness(
                "wikidata",
                p625["lat"],
                p625["lon"],
                f"{WD}{qid}",
                f"P625 = {p625['lat']:.6f}, {p625['lon']:.6f} (precision {p625.get('precision')})"
                + (" imported from English Wikipedia" if from_en else ""),
                precision_m(p625.get("precision")),
                "enwiki" if from_en else None,
            )
        )
    titles = [t for t in (record.get("enwiki"), *extra_titles) if t]
    page = None
    for title in titles:
        candidate = enwiki.get(title)
        if candidate is None:
            raise inputs.InputError(f"enwiki {title!r} is not in the cache - run `collect` again")
        if candidate.get("wikibase_item") == qid and not candidate.get("missing"):
            page = candidate
            break
    if page is None:
        notes.append(f"no English article of {qid} among {titles}")
    elif page.get("lat") is None or (page.get("globe") or "earth") != "earth":
        notes.append(f"enwiki {page['title']!r} carries no Earth coordinates")
    else:
        out.append(
            Witness(
                "enwiki",
                page["lat"],
                page["lon"],
                WP + str(page["title"]).replace(" ", "_"),
                f"enwiki {page['title']!r} coordinates = {page['lat']:.6f}, {page['lon']:.6f}",
            )
        )
    return out, notes


def _m(a: Witness | tuple[float, float], b: Witness | tuple[float, float]) -> float:
    pa = (a.lat, a.lon) if isinstance(a, Witness) else a
    pb = (b.lat, b.lon) if isinstance(b, Witness) else b
    return km(pa[0], pa[1], pb[0], pb[1]) * 1000.0


def independent(a: Witness, b: Witness) -> bool:
    """Two witnesses count twice only if neither copied the other and they are not the same point."""
    if a.derived_from == b.kind or b.derived_from == a.kind:
        return False
    return _m(a, b) > max(COPY_M, a.precision_m, b.precision_m)


def tolerance_m(ws: Sequence[Witness]) -> float:
    return max([TOLERANCE_M, *(w.precision_m for w in ws)])


#: Which of two agreeing witnesses the site moves to: the item's own statement first.
PRIORITY = {"wikidata": 0, "enwiki": 1}


def _why_no_pair(ws: Sequence[Witness], tol: float) -> str:
    """Why no two independent witnesses agree - in the words the owner's list quotes."""
    if not ws:
        return "no witness: no P625 and no English article with coordinates"
    if len(ws) == 1:
        return f"one witness only ({ws[0].kind})"
    a, b = ws[0], ws[1]
    if a.derived_from == b.kind or b.derived_from == a.kind:
        return "the two witnesses are one: P625 says it was imported from English Wikipedia"
    if not independent(a, b):
        return f"the two witnesses are one: the same point ({_m(a, b):.0f} m apart)"
    return f"the two witnesses disagree: {_m(a, b) / 1000:.2f} km apart (tolerance {tol:.0f} m)"


def weigh(stored: tuple[float, float], ws: Sequence[Witness]) -> dict[str, Any]:
    """The verdict on one stored point: `move`, `stored-agrees` or `review`, with the numbers.

    `stored-agrees` says only that a witness puts the site where it is stored - the curated point may
    well have been taken from that witness, so it is a reason not to move it, not a proof that it is
    right.
    """
    tol = tolerance_m(ws)
    ordered = sorted(ws, key=lambda w: PRIORITY[w.kind])
    pairs = [
        (a, b)
        for a, b in itertools.combinations(ordered, 2)
        if independent(a, b) and _m(a, b) <= tol
    ]
    near = [w for w in ordered if _m(stored, w) <= tol]
    distances = {w.kind: round(_m(stored, w), 1) for w in ordered}
    base = {"tolerance_m": round(tol, 1), "stored_to_witness_m": distances}
    if pairs and not near:
        a, b = pairs[0]
        return {
            **base,
            "verdict": "move",
            "to": a,
            "agreeing": [a.kind, b.kind],
            "agreement_m": round(_m(a, b), 1),
            "reason": f"{a.kind} and {b.kind} agree within {_m(a, b):.0f} m (independent), "
            f"the stored point is {_m(stored, a) / 1000:.2f} km away",
        }
    if near and (not pairs or all(w in near for w in pairs[0])):
        return {
            **base,
            "verdict": "stored-agrees",
            "reason": "the stored point lies within the tolerance of "
            + ", ".join(w.kind for w in near)
            + " - no change is planned",
        }
    if pairs:
        return {
            **base,
            "verdict": "review",
            "reason": f"{pairs[0][0].kind} and {pairs[0][1].kind} agree elsewhere, but "
            + ", ".join(w.kind for w in near)
            + " puts the site at the stored point",
        }
    return {**base, "verdict": "review", "reason": _why_no_pair(ordered, tol)}


def item_gate(
    qid: str,
    site: Mapping[str, Any],
    *,
    claims: Mapping[str, Any],
    labels: Mapping[str, Any],
    names: Mapping[str, Any],
    shared: Mapping[str, int],
) -> tuple[str | None, list[str]]:
    """Why the item's point cannot be the site's point (a class), or None; and the P31 labels."""
    record = claims[qid]
    p31 = [labels.get(q) or q for q in record.get("p31") or ()]
    if shared.get(qid, 0) > 1:
        return "shared-item", p31
    if any(map(is_container_class, p31)):
        return "container-item", p31
    if any(map(is_linear_or_areal_class, p31)):
        return "linear-or-areal-item", p31
    extra = {str(site["enwiki"]): "enwiki_title"} if site.get("enwiki") else {}
    identity, _ = name_identity(str(site["name"]), known_names(qid, names, extra))
    if identity not in ("N1", "N2"):
        return "item-is-not-the-site", p31
    return None, p31


def museum_object(qid: str, claims: Mapping[str, Any]) -> tuple[str, list[str]] | None:
    """(find-spot item, holding items) for a museum-held object; None for anything else."""
    record = claims[qid]
    holders = [*(record.get("p195") or ()), *(record.get("p276") or ())]
    if len(record.get("p189") or ()) == 1 and holders:
        return record["p189"][0], holders
    return None


# --------------------------------------------------------------------------- B1/B2 coordinates
def coordinate_items(
    sites: Mapping[str, Mapping[str, Any]],
    t01: Iterable[Mapping[str, Any]],
    t02: Iterable[Mapping[str, Any]],
) -> set[str]:
    """The items whose witnesses `collect` fetches: T01 coordinate findings' and every T02 site's."""
    wanted: set[str] = set()
    for finding in t01:
        if finding["test_id"] == "T01/coords":
            wanted.add(inputs.qid_of_finding(finding))
            qid = sites[finding["site_id"]].get("qid")
            if qid:
                wanted.add(str(qid))
    for finding in t02:
        qid = sites[finding["site_id"]].get("qid")
        if qid:
            wanted.add(str(qid))
    return wanted


def enwiki_titles(
    sites: Mapping[str, Mapping[str, Any]], claims: Mapping[str, Any], items: Iterable[str]
) -> set[str]:
    """Every English article a coordinate witness may be read from."""
    items = set(items)
    titles = {str(r["enwiki"]) for r in claims.values() if r.get("enwiki")}
    titles |= {
        str(s["enwiki"]) for s in sites.values() if s.get("enwiki") and s.get("qid") in items
    }
    return titles


def classify_coordinate(
    site: Mapping[str, Any],
    qid: str | None,
    *,
    origin: str,
    claims: Mapping[str, Any],
    labels: Mapping[str, Any],
    names: Mapping[str, Any],
    enwiki: Mapping[str, Any],
    shared: Mapping[str, int],
) -> dict[str, Any]:
    """One coordinate case: `move` (planned), `stored-agrees`, `not-comparable` or `review`."""
    stored = (float(site["lat"]), float(site["lon"]))
    record: dict[str, Any] = {
        "site_id": site["id"],
        "name": site["name"],
        "country": site["country"],
        "origin": origin,
        "qid": qid,
        "stored": [stored[0], stored[1]],
        "lat_text": site["lat_text"],
        "lon_text": site["lon_text"],
        "geom_text": site["geom_text"],
    }
    if qid is None:
        return {**record, "verdict": "review", "reason": "no Wikidata item: no witness to ask"}
    museum = museum_object(qid, claims)
    extra: Sequence[str] = (str(site["enwiki"]),) if site.get("enwiki") else ()
    if museum is not None:
        found_at, holders = museum
        at = [h for h in holders if _at_holder(stored, (claims.get(h) or {}).get("p625"))]
        ws, notes = witnesses(found_at, claims=claims, enwiki=enwiki)
        verdict = weigh(stored, ws)
        record.update(
            museum={"find_spot": found_at, "holders": holders, "stored_at_holder": at},
            witnesses=[_witness_json(w) for w in ws],
            witness_notes=notes,
        )
        if verdict["verdict"] == "move" and not at:
            verdict = {
                **verdict,
                "verdict": "review",
                "reason": "a museum object whose stored point is not at its holding museum: "
                "the stored point may be the precise find-spot",
            }
        verdict["rule"] = "museum-find-spot"
        return _finish(record, verdict)
    gate, p31 = item_gate(qid, site, claims=claims, labels=labels, names=names, shared=shared)
    record["p31"] = p31
    if gate is not None:
        return {**record, "verdict": "not-comparable", "class": gate, "reason": _GATE_REASON[gate]}
    ws, notes = witnesses(qid, claims=claims, enwiki=enwiki, extra_titles=extra)
    record.update(witnesses=[_witness_json(w) for w in ws], witness_notes=notes)
    verdict = weigh(stored, ws)
    verdict["rule"] = "two-independent-witnesses"
    return _finish(record, verdict)


_GATE_REASON = {
    "shared-item": "the item is linked by other curated sites too: its point is not this site's",
    "container-item": "the item is a settlement, administrative unit or natural feature that "
    "contains the site",
    "linear-or-areal-item": "the item is a linear or areal feature: its point is an arbitrary spot",
    "item-is-not-the-site": "the stored name is not a name of the item (N1/N2): the item may be the "
    "site's parent or a part of it",
}


def _witness_json(w: Witness) -> dict[str, Any]:
    return {
        "kind": w.kind,
        "lat": w.lat,
        "lon": w.lon,
        "url": w.url,
        "quote": w.quote,
        "precision_m": round(w.precision_m, 1),
        "derived_from": w.derived_from,
    }


def _at_holder(stored: tuple[float, float], p625: Mapping[str, Any] | None) -> bool:
    """Whether the stored point is the holding museum's point (within its tolerance)."""
    if p625 is None:
        return False
    tolerance = max(TOLERANCE_M, precision_m(p625.get("precision")))
    return _m(stored, (p625["lat"], p625["lon"])) <= tolerance


def _finish(record: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    """The record with its verdict; only a `move` names the point it moves to."""
    to = verdict.pop("to", None)
    if verdict["verdict"] == "move":
        verdict["new"] = {"lat": to.lat, "lon": to.lon, "from": to.kind, "url": to.url}
        verdict["moved_km"] = round(_m(tuple(record["stored"]), to) / 1000.0, 3)
    return {**record, **verdict}


def k_class(
    finding: Mapping[str, Any],
    site: Mapping[str, Any],
    *,
    t01: Mapping[str, Any],
    labels: Mapping[str, Any],
    shared: Mapping[str, int],
) -> str:
    """The remaining-work map's K class of a T01 coordinate finding (a report, not a gate)."""
    qid = inputs.qid_of_finding(finding)
    claims = t01[qid]
    p31 = p31_labels_of(qid, t01, labels)
    if shared.get(qid, 0) > 1:
        return "K3-shared-item"
    if any(map(is_container_class, p31)):
        return "K1-container-item"
    if any(map(is_linear_or_areal_class, p31)):
        return "K2-linear-or-areal-item"
    distance = km(site["lat"], site["lon"], claims["lat"], claims["lon"]) * 1000.0
    return "K5-over-10km" if distance > SEVERE_M else "K4-1-to-10km"


# ----------------------------------------------------------------------------------- B2 country
#: Natural Earth features whose line the owner decided to leave (B10, 2026-09-21).
POLITICAL_FEATURES = frozenset(
    {"Northern Cyprus", "Akrotiri Sovereign Base Area", "Cyprus No Mans Area", "Kosovo"}
)
#: (stored, contained-in) pairs of the same decision, folded.
POLITICAL_PAIRS = frozenset(
    {("ukraine", "russia"), ("syria", "israel"), ("israel", "palestine"), ("serbia", "kosovo")}
)


def in_crimea(lat: float, lon: float) -> bool:
    """The Crimean peninsula's box - Natural Earth draws it inside Russia (B10: stays Ukraine)."""
    return 44.3 < lat < 46.3 and 32.4 < lon < 36.7


def country_after_move(
    stored_country: str, lat: float, lon: float, atlas: tuple[Any, Any, Any]
) -> dict[str, Any]:
    """Whether the stored country still names the polygon the moved point lies in.

    A move is a coordinate change only; a country it contradicts is a follow-up for the country
    lanes, reported here so the plan does not create a T02 finding silently. The Crimean rows keep
    `Ukraine` by the owner's B10 decision although Natural Earth draws Crimea inside Russia.
    """
    names_, geoms, tree = atlas
    polygons = CC.country_at(names_, geoms, tree, lat, lon)
    agrees = CC.canonical(stored_country) in {CC.canonical(p) for p in polygons}
    note = None
    if not agrees and CC.fold(stored_country) == "ukraine" and in_crimea(lat, lon):
        agrees, note = True, "Crimea: stays Ukraine by the B10 decision"
    return {"stored": stored_country, "polygon": polygons, "agrees": agrees, "note": note}


B2_ROUTE = {
    "c1": "leave - political line decided in B10",
    "c2": "leave - Natural Earth generalisation (coast, small island, border straddle)",
    "c3": "leave - the value is right; T02's boundary file has no 'Northern Ireland' feature",
    "b-ni": "B9 decided 'Northern Ireland' - the mechanical UK lane",
    "b": "wrong country: point and P625 agree - a mechanical country-by-coordinates lane",
    "a": "wrong coordinate - the coordinate plan (two independent witnesses)",
    "x": "needs a witness - the coordinate plan's witnesses, else the owner",
    "d": "not a country - the owner (international waters, HUMAN_ONLY B2)",
}


def classify_b2(
    finding: Mapping[str, Any],
    site: Mapping[str, Any],
    *,
    t01: Mapping[str, Any],
    p17_labels: Mapping[str, Any],
    atlas: tuple[Any, Any, Any],
) -> dict[str, Any]:
    """One T02 finding, by the remaining-work map's rules (first match wins)."""
    quote = finding["evidence"][0]["quote"]
    match = re.search(r"outside by ([\d.]+) km", quote)
    outside = float(match.group(1)) if match else None
    match = re.search(r"contained in (.*)$", quote)
    ne = match.group(1) if match else ""
    snap, now = str(finding["current_value"]), site.get("country")
    qid = site.get("qid")
    claims = t01.get(qid or "") or {}
    p17 = [p17_labels.get(q) or q for q in claims.get("country_qids") or ()]
    p17_iso = {normalize_country(x) for x in p17} - {None}
    wd_km = (
        None
        if claims.get("lat") is None
        else km(site["lat"], site["lon"], claims["lat"], claims["lon"])
    )
    names_, geoms, tree = atlas
    wd_in = (
        CC.country_at(names_, geoms, tree, claims["lat"], claims["lon"])
        if claims.get("lat") is not None
        else []
    )
    stored_iso = normalize_country(snap)
    ne_iso = normalize_country(ne) if ne and "polygon" not in ne else None
    description = str(site.get("description") or "")
    desc_stored = bool(re.search(r"\b" + re.escape(snap) + r"\b", description))
    desc_ne = bool(
        ne and "polygon" not in ne and re.search(r"\b" + re.escape(ne) + r"\b", description)
    )
    f = CC.fold(snap)
    if (
        ne in POLITICAL_FEATURES
        or (f, CC.fold(ne)) in POLITICAL_PAIRS
        or (f == "ukraine" and in_crimea(site["lat"], site["lon"]))
        or (f == "cyprus" and "open water" in ne and len(p17) > 1)
    ):
        cls = "c1"
    elif f == "northern ireland":
        cls = "c3"
    elif f == "ireland" and ne == "United Kingdom":
        cls = "b-ni"
    elif f == "baltic sea":
        cls = "d"
    elif "open water" in ne:
        coast = (wd_km is not None and wd_km <= 1.0) or (outside is not None and outside <= 5)
        cls = "c2" if coast else "x"
    else:
        transboundary = len(p17_iso) > 1 and stored_iso in p17_iso and ne_iso in p17_iso
        if transboundary or (outside is not None and outside <= 2.0):
            cls = "c2"
        elif wd_km is not None and wd_km <= 5 and (ne_iso in p17_iso or not p17_iso):
            cls = "b"
        elif wd_km is not None and wd_in and CC.canonical(wd_in[0]) == CC.canonical(snap):
            cls = "a"
        elif stored_iso in p17_iso and desc_stored and not desc_ne:
            cls = "a"
        else:
            cls = "x"
    evidence = [
        _evidence("census:T02", quote),
        _evidence("wikidata:P17", f"P17 = {p17}", f"{WD}{qid}" if qid else None),
        _evidence(
            "wikidata:P625",
            "no P625"
            if wd_km is None
            else f"P625 {wd_km:.2f} km from the stored point, in {wd_in}",
            f"{WD}{qid}" if qid else None,
        ),
        _evidence(
            "production:description",
            f"names the stored country {snap!r}: {desc_stored}; names {ne!r}: {desc_ne}",
        ),
    ]
    return {
        "site_id": site["id"],
        "name": site["name"],
        "snapshot_country": snap,
        "country_now": now,
        "state": "open" if now == snap else f"written since the census: {snap!r} -> {now!r}",
        "class": cls,
        "route": B2_ROUTE[cls],
        "ne_contains": ne,
        "km_outside": outside,
        "qid": qid,
        "p17": p17,
        "p625_km": None if wd_km is None else round(wd_km, 2),
        "p625_in": wd_in,
        "evidence": evidence,
    }


# ----------------------------------------------------------------------------------- duplicates
def _dup_key(name: str) -> tuple[str, ...]:
    return tuple(sorted(tokens(name)))


def classify_pairs(
    sites: Mapping[str, Mapping[str, Any]], names: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Every pair of curated sites sharing one item, classed DUP / PART-OF / NEITHER / WRONG-ID."""
    by_item: dict[str, list[str]] = defaultdict(list)
    for sid in sorted(sites):
        if sites[sid].get("qid"):
            by_item[str(sites[sid]["qid"])].append(sid)
    out: list[dict[str, Any]] = []
    for qid, ids in sorted(by_item.items()):
        if len(ids) < 2:
            continue
        # A name made only of generic words ("Archaeological Site") names no place: never a match.
        item_names = {_dup_key(n) for n in known_names(qid, names)} - {()}
        for a, b in itertools.combinations(ids, 2):
            sa, sb = sites[a], sites[b]
            metres = _m((sa["lat"], sa["lon"]), (sb["lat"], sb["lon"]))
            in_a, in_b = _dup_key(sa["name"]) in item_names, _dup_key(sb["name"]) in item_names
            if metres > DUP_MAX_M:
                cls = "WRONG-ID"
            elif in_a and in_b:
                cls = "DUP"
            elif in_a or in_b:
                cls = "PART-OF"
            else:
                cls = "NEITHER"
            out.append(
                {
                    "class": cls,
                    "qid": qid,
                    "group_size": len(ids),
                    "a": a,
                    "b": b,
                    "a_name": sa["name"],
                    "b_name": sb["name"],
                    "a_is_item_name": in_a,
                    "b_is_item_name": in_b,
                    "distance_m": round(metres, 1),
                }
            )
    return out


def stacked(sites: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Groups of curated sites stored on the very same point - a placeholder, not a location."""
    at: dict[tuple[str, str], list[str]] = defaultdict(list)
    for sid in sorted(sites):
        at[(sites[sid]["lat_text"], sites[sid]["lon_text"])].append(sid)
    return [
        {
            "lat_text": lat,
            "lon_text": lon,
            "site_ids": ids,
            "names": [sites[i]["name"] for i in ids],
        }
        for (lat, lon), ids in sorted(at.items())
        if len(ids) > 1
    ]


def survivor_key(site: Mapping[str, Any]) -> tuple[int, int, str, str]:
    """Sort key, smallest survives: more content links, more sources, older row, lower id."""
    sources = int(site["n_ext"]) + (1 if site.get("source_url") else 0)
    return (-int(site["n_links"]), -sources, str(site["created_at"]), str(site["id"]))


def duplicate_groups(
    pairs: Sequence[Mapping[str, Any]], sites: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """DUP pairs joined into groups: one survivor each. A group in which some pair is not DUP is
    returned apart, unresolved - transitivity does not make two places one."""
    dup = [p for p in pairs if p["class"] == "DUP"]
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    for p in dup:
        parent[root(p["a"])] = root(p["b"])
    groups: dict[str, list[str]] = defaultdict(list)
    for sid in sorted({p["a"] for p in dup} | {p["b"] for p in dup}):
        groups[root(sid)].append(sid)
    dup_set = {frozenset((p["a"], p["b"])) for p in dup}
    lines: list[dict[str, Any]] = []
    unresolved: list[list[str]] = []
    for members in sorted(groups.values()):
        if any(frozenset(pair) not in dup_set for pair in itertools.combinations(members, 2)):
            unresolved.append(members)
            continue
        ranked = sorted(members, key=lambda s: survivor_key(sites[s]))
        survivor = ranked[0]
        for loser in ranked[1:]:
            lines.append(duplicate_line(loser, survivor, sites, dup))
    return lines, unresolved


def _decisive_step(loser: Mapping[str, Any], survivor: Mapping[str, Any]) -> str:
    for step, (lk, sk) in zip(
        ("more content links", "more sources", "older created_at", "lower id (tie-break)"),
        zip(survivor_key(loser), survivor_key(survivor), strict=True),
        strict=True,
    ):
        if lk != sk:
            return step
    raise ValueError(f"{loser['id']} and {survivor['id']} have the same survivor key")


def duplicate_line(
    loser: str,
    survivor: str,
    sites: Mapping[str, Mapping[str, Any]],
    dup: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """One line of `DUPLICATES.jsonl`: `loser_id`, `survivor_id`, `evidence` - nothing else."""
    lo, su = sites[loser], sites[survivor]
    pair = next(p for p in dup if {p["a"], p["b"]} == {loser, survivor})
    return {
        "loser_id": loser,
        "survivor_id": survivor,
        "evidence": [
            _evidence(
                "production:site_external_ids",
                f"both rows carry {pair['qid']}; {lo['name']!r} and {su['name']!r} are both names "
                f"of it (labels, aliases or sitelinks); {pair['distance_m']:.1f} m apart",
                f"{WD}{pair['qid']}",
            ),
            _evidence(
                "survivor rule",
                f"{su['name']!r} survives by {_decisive_step(lo, su)}: content links "
                f"{su['n_links']} vs {lo['n_links']}, sources {su['n_ext']}+url vs "
                f"{lo['n_ext']}+url, created {su['created_at']} vs {lo['created_at']}",
            ),
            _evidence(
                "follow-up",
                f"the loser carries {lo['n_img']} wiki_images and {lo['n_links']} content links "
                f"that are not moved by retiring it; country {lo['country']!r} vs survivor "
                f"{su['country']!r}",
            ),
        ],
    }


# ------------------------------------------------------------------------------------ the run
def write_all(data: Path, cache: Path, out: Path) -> dict[str, Any]:
    """Classify everything and write `output/remediation/bcases/`. Returns the counts."""
    sites = inputs.load_sites(cache)
    t01_findings = inputs.load_findings(data, "t01")
    t02_findings = inputs.load_findings(data, "t02")
    t01, p17_labels = inputs.load_t01_claims(data)
    only = inputs.coords_only_sites(data)
    names = inputs.read_cache(cache / inputs.NAMES_FILE)
    labels = inputs.read_cache(cache / inputs.P31_FILE)
    claims = inputs.read_cache(cache / inputs.CLAIMS_FILE)
    enwiki = inputs.read_cache(cache / inputs.ENWIKI_FILE)
    shared = shared_counts(sites)

    census = inputs.load_census_links(data)
    census_shared = Counter(
        link["wikidata_qid"] for link in census.values() if link.get("wikidata_qid")
    )
    name_rows = [
        classify_name(
            f,
            sites[f["site_id"]],
            census_enwiki=census.get(f["site_id"], {}).get("enwiki_title"),
            names=names,
            t01=t01,
            labels=labels,
            shared=census_shared,
        )
        for f in t01_findings
        if f["test_id"] in ("T01/name", "T01/name-variant")
    ]
    atlas = CC.load_countries()
    b2_rows = [
        classify_b2(f, sites[f["site_id"]], t01=t01, p17_labels=p17_labels, atlas=atlas)
        for f in t02_findings
    ]
    coord_rows: list[dict[str, Any]] = []
    for f in t01_findings:
        if f["test_id"] != "T01/coords":
            continue
        site = sites[f["site_id"]]
        row = classify_coordinate(
            site,
            site.get("qid"),
            origin="T01/coords",
            claims=claims,
            labels=labels,
            names=names,
            enwiki=enwiki,
            shared=shared,
        )
        row["k_class"] = k_class(f, site, t01=t01, labels=labels, shared=shared)
        row["coords_only"] = f["site_id"] in only
        coord_rows.append(row)
    seen = {r["site_id"] for r in coord_rows}
    for b2 in b2_rows:
        if b2["class"] in ("a", "x") and b2["site_id"] not in seen:
            site = sites[b2["site_id"]]
            row = classify_coordinate(
                site,
                site.get("qid"),
                origin=f"T02/{b2['class']}",
                claims=claims,
                labels=labels,
                names=names,
                enwiki=enwiki,
                shared=shared,
            )
            row["coords_only"] = False
            coord_rows.append(row)
    for row in coord_rows:
        if row["verdict"] == "move":
            row["country_after_move"] = country_after_move(
                str(row["country"]), row["new"]["lat"], row["new"]["lon"], atlas
            )
    pairs = classify_pairs(sites, names)
    dup_lines, unresolved = duplicate_groups(pairs, sites)
    stacks = stacked(sites)

    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "names.jsonl", name_rows)
    write_jsonl(out / "coords.jsonl", coord_rows)
    write_jsonl(out / "b2.jsonl", b2_rows)
    write_jsonl(out / "dup_pairs.jsonl", pairs)
    write_jsonl(out / "stacked.jsonl", stacks)
    write_jsonl(out / "DUPLICATES.jsonl", dup_lines)
    counts = {
        "names": dict(sorted(Counter(r["class"] for r in name_rows).items())),
        "names_by_group": dict(sorted(Counter(r["group"] for r in name_rows).items())),
        "names_n7": dict(Counter(r["n7"] for r in name_rows if r["class"] == "N7")),
        "coords_k_all": dict(
            sorted(Counter(r["k_class"] for r in coord_rows if "k_class" in r).items())
        ),
        "coords_k_285": dict(
            sorted(Counter(r["k_class"] for r in coord_rows if r.get("coords_only")).items())
        ),
        "coords_verdict": dict(sorted(Counter(r["verdict"] for r in coord_rows).items())),
        "coords_verdict_285": dict(
            sorted(Counter(r["verdict"] for r in coord_rows if r.get("coords_only")).items())
        ),
        "coords_review_reason": dict(
            sorted(
                Counter(
                    re.sub(r"[\d.]+ (k?m)", r"N \1", r["reason"])
                    for r in coord_rows
                    if r["verdict"] == "review"
                ).items()
            )
        ),
        "coords_not_comparable": dict(
            sorted(
                Counter(r["class"] for r in coord_rows if r["verdict"] == "not-comparable").items()
            )
        ),
        "moves_country_follow_up": sum(
            1
            for r in coord_rows
            if r["verdict"] == "move" and not r["country_after_move"]["agrees"]
        ),
        "b2": dict(sorted(Counter(r["class"] for r in b2_rows).items())),
        "b2_state": dict(sorted(Counter(r["state"] != "open" for r in b2_rows).items())),
        "pairs": dict(sorted(Counter(p["class"] for p in pairs).items())),
        "duplicates": {"losers": len(dup_lines), "unresolved_groups": len(unresolved)},
        "stacked": {"groups": len(stacks), "sites": sum(len(s["site_ids"]) for s in stacks)},
    }
    (out / "COUNTS.json").write_text(
        json.dumps(counts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return counts
