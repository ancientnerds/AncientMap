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

A matching name keeps the *name*; it does not prove the *link*. So the link is tested on its own as
well: `link_suspect` lists the wrong-link tests Q1, Q2 and Q4 the item meets whatever the name says.
On a kept name ("Dolmens of Sardinia" on Q101659 "dolmen", the class; "The Temple of Artemis" stored in
Greece on the Ephesus temple, 388 km away) that is a link to research - not part of wave 2, which
repairs only the rows whose name did not match.

## B1/B2 coordinates

A coordinate is changed only when **two independent witnesses agree within the tolerance and the
stored point lies outside it**. The witnesses are Wikidata `P625` and the English article's primary
coordinates (OpenStreetMap was not reachable from this workstation, `collect.py`). Two witnesses are
*not* independent - they count once - when

* one says it was imported from the other (`P625` referenced to English Wikipedia);
* one is the other **rounded or truncated** to the grid its own digits are written on (`grid_of`:
  whole arcminutes or arcseconds, or a number of decimals). Castro of Santa Trega's article gives
  41.8927, -8.8698 - its item's 41.89275, -8.869808 cut to four decimals - and Taq Kasra's article
  gives 33°05'37", 44°34'51", its item's 33.093722, 44.580722 rounded to whole arcseconds: one value
  written twice, whatever wiki it was imported from (P143 French or Russian Wikipedia);
* their points are the same point: within `SAME_POINT_M` (one arcsecond), one step of either
  witness's grid, or the P625's declared precision. Petroglyph Beach's Wikidata and Wikipedia
  coordinates are both downtown Juneau (plan anti-pattern 9) and count once.

A `P625` is the item's truthy one: a preferred statement when there is one (`collect._truthy`). The
tolerance is T01's: 1000 m, floored by `P625`'s own precision. Before any witness is read, an item
that is not the site itself stops the case: an item shared with other curated sites, a settlement,
administrative unit or natural feature that contains the site, a linear or areal feature, or an item
whose names do not include the stored name (N1/N2). A museum-held object (`P189` find-spot plus
`P195`/`P276`) is judged against its **find-spot** - its own `P625` is the museum - and moved only
when the stored point is at the holding museum.

The second wave (`web_witness.py`) adds a third kind, `web`: a page outside Wikipedia and its mirrors
whose coordinates were read from the live page. A web witness is named by its publisher, the host's
registered domain (`Witness.label`, "web:unesco.org"): two pages of one publisher count once, two of
different publishers may pair under the same independence test, a web witness comes last in
`PRIORITY`, and when two agreeing pairs name points further apart than the tolerance the case is
read, not moved. With three or more witnesses "are one" is followed through chains (`copy_groups`):
two pages that are each the item's point are one with each other too, so they never pair. With two
witnesses the chain is the pair itself, and the first wave's verdicts are unchanged.

## B2 countries (the 117 `T02` findings)

The remaining-work map's classification: political lines already decided (B10), coastline and border
artefacts, the `Northern Ireland` vocabulary gap and the B9 rows, wrong countries (point and `P625`
agree), wrong coordinates (`P625` or the site's own description names the stored country), rows that
need a witness, and one value that is not a country. A site whose point and `P625` agree on the
neighbouring country is transboundary, not wrong, when `P17` **or its own description** names both
countries: the Côa Valley and Siega Verde rock art spans Portugal and Spain, and writing either one
alone would be wrong.

## Duplicates

Two curated sites sharing one Wikidata item, within 2 km, **both** of whose names are names of that
item, are one site recorded twice (DUP). One name only is a part-of or synonym pair, neither is a
generic anchor, more than 2 km is a wrong item on one side. The survivor of a DUP group is the row with
more content links, then more sources, then the older `created_at`, then the lower id - the last step
only makes the rule total, it judges nothing. A group whose rows name **different countries** is held
back for the owner (`DUPLICATES_HELD.jsonl`): retiring one row would settle a country line, and Banias
(Syria) / Caesarea Philippi (Israel) is the Golan line the owner decided to leave (B10).
"""

from __future__ import annotations

import difflib
import itertools
import json
import math
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from census.tests.t01_wikidata_claims import METRES_PER_DEGREE, SEVERE_M, TOLERANCE_M

from bcases import inputs

_TOOLS = inputs.REPO / "output" / "remediation" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import country_census as CC  # noqa: E402 - the boundary file and its spelling rules, never copied
from vlm_pilot.common import write_jsonl  # noqa: E402

from pipeline.utils.country_lookup import normalize_country  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402
from pipeline.utils.text import normalize_name  # noqa: E402

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

#: One arcsecond of latitude in metres: two witnesses closer than this are one point, whatever their
#: grids - the commonest grid a coordinate is written on cannot tell them apart.
SAME_POINT_M = METRES_PER_DEGREE / 3600.0
#: The grids a coordinate is written on, coarsest first: whole degrees, tenths, arcminutes,
#: hundredths, thousandths, arcseconds, then decimals down to the eight the Wikipedia API prints.
GRIDS = (1.0, 0.1, 1 / 60, 0.01, 0.001, 1 / 3600, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8)
#: How close to a grid line a value lies on it: a thousandth of the grid's step, and never more than
#: the last digit the Wikipedia API prints (1e-8 degrees, about a millimetre) - enough for float
#: noise and for the API's eight-decimal print of a whole arcsecond (33.09361111 is 33°05'37"), not
#: enough to put 0°00'01" on the whole-degree grid.
ON_GRID = 1e-3
ON_GRID_MAX = 1e-8
#: Two curated sites on one item further apart than this are two places, not one (DUP rule).
DUP_MAX_M = 2000.0
#: A name finding whose item is further away than this is a wrong link (Q4).
FAR_KM = 5.0
#: A transliteration: the folded names are this similar (difflib ratio), N6.
TRANSLIT_RATIO = 0.8


def fold(name: str, *, keep_parentheses: bool = False) -> str:
    """A comparable spelling: no accents, no case, no bracketed suffix, words single-spaced.

    The accents and the bracketed suffix go the project's way (`normalize_name`); square brackets
    stay, as they did when the verdicts were measured, and `casefold` adds what `lower` leaves.
    `keep_parentheses` folds a running text rather than a name: a page's "(El Tintal)" is words to
    find, not a suffix to drop (`web_witness`'s identity check).
    """
    text = normalize_name(
        name, remove_parentheses=not keep_parentheses, remove_brackets=False
    ).casefold()
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
    nocoord = claims.get("lat") is None
    # The wrong-link tests, each a property of the link alone - the name is not asked here.
    link = {
        "Q1": nocoord and (en_label or "")[:1].islower(),
        "Q2": shared.get(qid, 0) > 1,
        "Q3": nocoord,
        "Q4": distance is not None and distance > FAR_KM,
    }
    cls, hit = name_identity(stored, candidates)
    ratio = None
    if cls == "none":
        own = {name for name, where in candidates.items() if where != ["enwiki_title"]}
        ratio = max(
            (difflib.SequenceMatcher(None, squash(stored), squash(n)).ratio() for n in own),
            default=0.0,
        )
        if link["Q1"]:
            cls = "Q1"
        elif ratio >= TRANSLIT_RATIO:
            cls = "N6"
            hit = max(
                sorted(own),
                key=lambda n: difflib.SequenceMatcher(None, squash(stored), squash(n)).ratio(),
            )
        elif link["Q2"]:
            cls = "Q2"
        elif link["Q3"]:
            cls = "Q3"
        elif link["Q4"]:
            cls = "Q4"
        else:
            cls = "N7"
    # A kept name says nothing about the link: the tests that make a link wrong on their own (a
    # generic concept, an item shared with other sites, one more than 5 km away) are reported.
    suspect = [q for q in ("Q1", "Q2", "Q4") if link[q]] if NAME_GROUP[cls] == "keep" else []
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
    shown = {cls, *suspect}
    if shown & {"Q1", "Q3"}:
        evidence.append(_evidence("wikidata:P625", f"{qid} has no P625", f"{WD}{qid}"))
    if "Q2" in shown:
        evidence.append(
            _evidence(
                "production:site_external_ids", f"{qid} is linked by {shared[qid]} curated sites"
            )
        )
    if "Q4" in shown:
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
        "link_suspect": suspect,
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

    kind: str  #: "wikidata", "enwiki" or "web" (a page read by `web_witness.py`)
    lat: float
    lon: float
    url: str
    quote: str
    precision_m: float = 0.0
    #: The kind of witness this one says it was copied from ("enwiki" for a P625 imported from it).
    derived_from: str | None = None
    #: The grid the value's digits are written on, in degrees (`grid_of`): what a copy of it may have
    #: been rounded to. 0 when the digits lie on no grid of `GRIDS`.
    step: float = 0.0

    @property
    def label(self) -> str:
        """How a verdict names this witness: its kind, and for a web page its publisher as well
        (`web_host`) - two pages are two witnesses only when two publishers wrote them
        ("web:unesco.org")."""
        return f"web:{web_host(self.url)}" if self.kind == "web" else self.kind


#: Second-level labels a country's registry shares out ("co.uk", "gov.pk", "or.th"): under one of
#: them the publisher is the label before it. A shared level missing here names a wider domain
#: ("bel.tr") and so groups more hosts into one witness, never fewer - the safe direction.
SHARED_SECOND_LEVEL = frozenset(
    {"ac", "co", "com", "edu", "go", "gob", "gov", "gv", "mil", "ne", "net", "or", "org"}
)


def web_host(url: str) -> str:
    """The publisher a web witness is named by: its host's registered domain, lower case - the last
    two labels, or three under a country code's shared second level (`SHARED_SECOND_LEVEL`).
    `www.x.org`, `x.org` and `whc.x.org` are one publisher, so their pages are one witness."""
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"{url!r} names no host")
    labels = host.rstrip(".").split(".")
    shared = len(labels) > 2 and len(labels[-1]) == 2 and labels[-2] in SHARED_SECOND_LEVEL
    return ".".join(labels[-3:] if shared else labels[-2:])


def label_of(witness: Mapping[str, Any]) -> str:
    """`Witness.label` of a witness as `_witness_json` wrote it."""
    return str(witness["label"]) if witness["kind"] == "web" else str(witness["kind"])


def precision_m(precision: Any) -> float:
    """Half of Wikidata's P625 precision in metres - the value's own uncertainty (T01's floor)."""
    if isinstance(precision, int | float) and not isinstance(precision, bool):
        return float(precision) * METRES_PER_DEGREE / 2.0
    return 0.0


def _slack(step: float) -> float:
    """`ON_GRID` in units of `step`: how far from a grid line a value may lie and still be on it."""
    return min(ON_GRID * step, ON_GRID_MAX) / step


def _on_grid(value: float, step: float) -> bool:
    units = value / step
    return abs(units - round(units)) <= _slack(step)


def grid_of(lat: float, lon: float) -> float:
    """The coarsest grid (`GRIDS`) both values lie on - the digits the point is written in: 41.8927,
    -8.8698 is four decimals; 33.09361111, 44.58083333 is whole arcseconds. 0 when on none."""
    return next((step for step in GRIDS if _on_grid(lat, step) and _on_grid(lon, step)), 0.0)


def grid_name(step: float) -> str:
    """How a grid of `GRIDS` reads in a reason: "whole arcseconds", "4 decimals"."""
    named = {1.0: "whole degrees", 1 / 60: "whole arcminutes", 1 / 3600: "whole arcseconds"}
    if step in named:
        return named[step]
    decimals = round(-math.log10(step))
    return "1 decimal" if decimals == 1 else f"{decimals} decimals"


def _rounds_to(value: float, rounded: float, step: float) -> bool:
    """Whether `rounded` is `value` rounded, truncated, floored or ceiled to a grid of `step`: it lies
    on that grid, on one of the two grid lines around `value` (on `value` itself if that is one)."""
    if not _on_grid(rounded, step):
        return False
    units, slack = value / step, _slack(step)
    return math.floor(units + slack) <= round(rounded / step) <= math.ceil(units - slack)


def rounded_copy(a: Witness, b: Witness) -> str | None:
    """How one witness is the other cut to its own grid ("enwiki is wikidata rounded to 4 decimals"),
    or None. Rounded, truncated or floored, in both coordinates: one value written twice. Two equal
    points are no rounding of each other - they are one point, and `same_point_m` says so."""
    if (a.lat, a.lon) == (b.lat, b.lon):
        return None
    for coarse, fine in ((a, b), (b, a)):
        if (
            coarse.step
            and _rounds_to(fine.lat, coarse.lat, coarse.step)
            and _rounds_to(fine.lon, coarse.lon, coarse.step)
        ):
            return f"{coarse.kind} is {fine.kind} rounded to {grid_name(coarse.step)}"
    return None


def same_point_m(a: Witness, b: Witness) -> float:
    """The distance under which two witnesses are one point: one arcsecond, one step of the grid
    either is written on, or a P625's declared precision - whichever is widest."""
    return max(
        SAME_POINT_M,
        *(w.step * METRES_PER_DEGREE for w in (a, b)),
        *(2.0 * w.precision_m for w in (a, b)),
    )


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
        several = p625["statements"] > 1
        out.append(
            Witness(
                "wikidata",
                p625["lat"],
                p625["lon"],
                f"{WD}{qid}",
                f"P625 = {p625['lat']:.6f}, {p625['lon']:.6f} (precision {p625.get('precision')})"
                + (" imported from English Wikipedia" if from_en else "")
                + (
                    f" - the {p625['rank']}-rank one of {p625['statements']} P625 statements"
                    if several
                    else ""
                ),
                precision_m(p625.get("precision")),
                "enwiki" if from_en else None,
                grid_of(p625["lat"], p625["lon"]),
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
        step = grid_of(page["lat"], page["lon"])
        out.append(
            Witness(
                "enwiki",
                page["lat"],
                page["lon"],
                WP + str(page["title"]).replace(" ", "_"),
                f"enwiki {page['title']!r} coordinates = {page['lat']}, {page['lon']}"
                + (f" (given to {grid_name(step)})" if step else ""),
                step=step,
            )
        )
    return out, notes


def _m(a: Witness | tuple[float, float], b: Witness | tuple[float, float]) -> float:
    pa = (a.lat, a.lon) if isinstance(a, Witness) else a
    pb = (b.lat, b.lon) if isinstance(b, Witness) else b
    return km(pa[0], pa[1], pb[0], pb[1]) * 1000.0


def independent(a: Witness, b: Witness) -> bool:
    """Two witnesses count twice only if they come from two sources (two web pages of one publisher are
    one), neither says it copied the other, neither is the other rounded to its own grid, and they
    are not the same point."""
    if a.label == b.label:
        return False
    if a.derived_from == b.kind or b.derived_from == a.kind:
        return False
    if rounded_copy(a, b) is not None:
        return False
    return _m(a, b) > same_point_m(a, b)


def copy_groups(ws: Sequence[Witness]) -> list[int]:
    """The group of each witness: two that are one (not `independent`) share a group, and so do two
    joined through a chain of such pairs - two pages that are each the item's point are one with each
    other as well, even where neither is the other's rounding. The group is the lowest index in it."""
    group = list(range(len(ws)))

    def root(i: int) -> int:
        while group[i] != i:
            i = group[i]
        return i

    for i, j in itertools.combinations(range(len(ws)), 2):
        if not independent(ws[i], ws[j]):
            low, high = sorted((root(i), root(j)))
            group[high] = low
    return [root(i) for i in range(len(ws))]


def tolerance_m(ws: Sequence[Witness]) -> float:
    return max([TOLERANCE_M, *(w.precision_m for w in ws)])


#: Which of two agreeing witnesses the site moves to: the item's own statement first, a web page last.
PRIORITY = {"wikidata": 0, "enwiki": 1, "web": 2}


def _pair_state(a: Witness, b: Witness, tol: float, via: Sequence[Witness] = ()) -> str:
    """Why two witnesses are no agreeing pair: "are one: <how>" or "disagree: <how far>". `via` are
    the other witnesses of their copy group when they share one (`copy_groups`)."""
    if a.label == b.label:
        return f"are one: both are {a.label}"
    if a.derived_from == b.kind or b.derived_from == a.kind:
        return "are one: P625 says it was imported from English Wikipedia"
    copy = rounded_copy(a, b)
    if copy is not None:
        return f"are one: {copy}"
    if not independent(a, b):
        return (
            f"are one: the same point ({_m(a, b):.0f} m apart, within {same_point_m(a, b):.0f} m)"
        )
    if via:
        return "are one: both are one with " + " and ".join(w.label for w in via)
    return f"disagree: {_m(a, b) / 1000:.2f} km apart (tolerance {tol:.0f} m)"


def _why_no_pair(ws: Sequence[Witness], tol: float) -> str:
    """Why no two independent witnesses agree - in the words the owner's list quotes. With more
    than two witnesses (a web page joined the item's two) every pair is named."""
    if not ws:
        return "no witness: no P625 and no English article with coordinates"
    if len(ws) == 1:
        return f"one witness only ({ws[0].label})"
    if len(ws) == 2:
        return f"the two witnesses {_pair_state(ws[0], ws[1], tol)}"
    groups = copy_groups(ws)
    return f"no two of the {len(ws)} witnesses are independent and agree: " + "; ".join(
        f"{ws[i].label} and {ws[j].label} "
        + _pair_state(
            ws[i],
            ws[j],
            tol,
            [
                w
                for k, w in enumerate(ws)
                if k not in (i, j) and groups[k] == groups[i] == groups[j]
            ],
        )
        for i, j in itertools.combinations(range(len(ws)), 2)
    )


def weigh(stored: tuple[float, float], ws: Sequence[Witness]) -> dict[str, Any]:
    """The verdict on one stored point: `move`, `stored-agrees` or `review`, with the numbers.

    `stored-agrees` says only that a witness puts the site where it is stored - the curated point may
    well have been taken from that witness, so it is a reason not to move it, not a proof that it is
    right. With three or more witnesses, one that stands alone does not stop a move two others agree
    on (the third witness decides between two that disagree), but two agreeing pairs whose points lie
    further apart than the tolerance do: which of them is the site is a question to read.
    """
    tol = tolerance_m(ws)
    ordered = sorted(ws, key=lambda w: PRIORITY[w.kind])
    groups = copy_groups(ordered)
    pairs = [
        (ordered[i], ordered[j])
        for i, j in itertools.combinations(range(len(ordered)), 2)
        if groups[i] != groups[j] and _m(ordered[i], ordered[j]) <= tol
    ]
    near = [w for w in ordered if _m(stored, w) <= tol]
    distances = {w.label: round(_m(stored, w), 1) for w in ordered}
    if len(distances) != len(ordered):
        raise ValueError(f"two witnesses share one label: {[w.label for w in ordered]}")
    base = {"tolerance_m": round(tol, 1), "stored_to_witness_m": distances}
    if pairs and not near:
        a, b = pairs[0]
        clash = [
            f"{c.label} and {d.label}" for c, d in pairs[1:] if _m(a, c) > tol or _m(a, d) > tol
        ]
        if clash:
            return {
                **base,
                "verdict": "review",
                "reason": f"{a.label} and {b.label} agree, but so do "
                + ", ".join(clash)
                + " on a point further than the tolerance from theirs",
            }
        return {
            **base,
            "verdict": "move",
            "to": a,
            "agreeing": [a.label, b.label],
            "agreement_m": round(_m(a, b), 1),
            "reason": f"{a.label} and {b.label} agree within {_m(a, b):.0f} m (independent), "
            f"the stored point is {_m(stored, a) / 1000:.2f} km away",
        }
    if near and (not pairs or all(w in near for w in pairs[0])):
        return {
            **base,
            "verdict": "stored-agrees",
            "reason": "the stored point lies within the tolerance of "
            + ", ".join(w.label for w in near)
            + " - no change is planned",
        }
    if pairs:
        return {
            **base,
            "verdict": "review",
            "reason": f"{pairs[0][0].label} and {pairs[0][1].label} agree elsewhere, but "
            + ", ".join(w.label for w in near)
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
    web: Sequence[Witness] = (),
) -> dict[str, Any]:
    """One coordinate case: `move` (planned), `stored-agrees`, `not-comparable` or `review`.

    `web` are the site's web witnesses (`web_witness.py`, the second wave): weighed with the item's
    own under the same rule. A museum object's web witnesses join its find-spot's, and it still moves
    only when stored at its museum; a site without an item has its web witnesses alone.
    """
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
        if not web:
            return {**record, "verdict": "review", "reason": "no Wikidata item: no witness to ask"}
        record.update(
            witnesses=[_witness_json(w) for w in web],
            witness_notes=["no Wikidata item: the web witnesses alone"],
        )
        verdict = weigh(stored, web)
        verdict["rule"] = "two-independent-witnesses"
        return _finish(record, verdict)
    museum = museum_object(qid, claims)
    extra: Sequence[str] = (str(site["enwiki"]),) if site.get("enwiki") else ()
    if museum is not None:
        found_at, holders = museum
        at = [h for h in holders if _at_holder(stored, (claims.get(h) or {}).get("p625"))]
        ws, notes = witnesses(found_at, claims=claims, enwiki=enwiki)
        ws = [*ws, *web]
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
    ws = [*ws, *web]
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
    """A witness as a verdict records it; a web witness carries its label (`label_of`) as well."""
    out = {
        "kind": w.kind,
        "lat": w.lat,
        "lon": w.lon,
        "url": w.url,
        "quote": w.quote,
        "precision_m": round(w.precision_m, 1),
        "derived_from": w.derived_from,
        "grid": grid_name(w.step) if w.step else None,
    }
    if w.kind == "web":
        out["label"] = w.label
    return out


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
        verdict["new"] = {"lat": to.lat, "lon": to.lon, "from": to.label, "url": to.url}
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
    "c2": "leave - Natural Earth generalisation (coast, small island, border straddle) or a "
    "transboundary site (P17 or its own description names both countries)",
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
            # Point and P625 agree on the neighbour - but a site whose own text names both countries
            # spans the border (the Coa Valley and Siega Verde), and neither country alone is right.
            cls = "c2" if desc_stored and desc_ne else "b"
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
) -> tuple[list[dict[str, Any]], list[list[str]], list[dict[str, Any]]]:
    """DUP pairs joined into groups: one survivor each. A group in which some pair is not DUP is
    returned apart, unresolved - transitivity does not make two places one. A group whose rows name
    different countries is held for the owner: retiring a row would decide which country is right,
    and that is a country question (B10 left the Golan line as it is), not a duplicate one."""
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
    held: list[dict[str, Any]] = []
    for members in sorted(groups.values()):
        if any(frozenset(pair) not in dup_set for pair in itertools.combinations(members, 2)):
            unresolved.append(members)
            continue
        ranked = sorted(members, key=lambda s: survivor_key(sites[s]))
        survivor = ranked[0]
        countries = sorted({str(sites[s]["country"]) for s in members})
        if len(countries) > 1:
            held.append(
                {
                    "site_ids": members,
                    "names": [sites[s]["name"] for s in members],
                    "countries": countries,
                    "survivor_by_rule": survivor,
                    "reason": "the rows name different countries: retiring one decides the "
                    "country - the owner's (B10), not the scope lane's",
                    "lines": [duplicate_line(lo, survivor, sites, dup) for lo in ranked[1:]],
                }
            )
            continue
        for loser in ranked[1:]:
            lines.append(duplicate_line(loser, survivor, sites, dup))
    return lines, unresolved, held


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
    dup_lines, unresolved, held = duplicate_groups(pairs, sites)
    stacks = stacked(sites)

    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "names.jsonl", name_rows)
    write_jsonl(out / "coords.jsonl", coord_rows)
    write_jsonl(out / "b2.jsonl", b2_rows)
    write_jsonl(out / "dup_pairs.jsonl", pairs)
    write_jsonl(out / "stacked.jsonl", stacks)
    write_jsonl(out / "DUPLICATES.jsonl", dup_lines)
    write_jsonl(out / "DUPLICATES_HELD.jsonl", held)
    counts = summarise(name_rows, coord_rows, b2_rows, pairs, dup_lines, unresolved, held, stacks)
    (out / "COUNTS.json").write_text(
        json.dumps(counts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return counts


def summarise(
    name_rows: Sequence[Mapping[str, Any]],
    coord_rows: Sequence[Mapping[str, Any]],
    b2_rows: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    dup_lines: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Sequence[str]],
    held: Sequence[Mapping[str, Any]],
    stacks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """`COUNTS.json`: every key a JSON key, so the counts `write_all` returns are the ones it writes."""
    suspect = [r for r in name_rows if r["link_suspect"]]
    return {
        "names": dict(sorted(Counter(r["class"] for r in name_rows).items())),
        "names_by_group": dict(sorted(Counter(r["group"] for r in name_rows).items())),
        "names_n7": dict(Counter(r["n7"] for r in name_rows if r["class"] == "N7")),
        "names_keep_link_suspect": {
            **dict(sorted(Counter(q for r in suspect for q in r["link_suspect"]).items())),
            "any": len(suspect),
        },
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
        # string keys: the counts returned must be the counts written (JSON has no boolean keys)
        "b2_state": dict(
            sorted(
                Counter(
                    "open" if r["state"] == "open" else "written since the census" for r in b2_rows
                ).items()
            )
        ),
        "pairs": dict(sorted(Counter(p["class"] for p in pairs).items())),
        "duplicates": {
            "losers": len(dup_lines),
            "unresolved_groups": len(unresolved),
            "held_groups": len(held),
        },
        "stacked": {"groups": len(stacks), "sites": sum(len(s["site_ids"]) for s in stacks)},
    }
