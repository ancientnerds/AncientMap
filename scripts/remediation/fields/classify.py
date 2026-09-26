"""WD1 step 2: a deterministic status for each structured field of each curated site.

FINISH_PLAN_2026-09-26 workstream WD, lane WD1: coordinates, period_start (-> period_name), site_type,
source_url. Nothing here calls a model or the network: the inputs are the shared harvest
(`harvest.py`: SITES.jsonl, entities/, CLASSES.json, enwiki/, urls/), a read-only export of the
stored fields (`export`: STORED.jsonl, taken right after the harvest's export and refused if the two
disagree on a site's point or URL) and the pinned P31 table (`p31_site_types.json`).

Every field gets one status:

* **CONFIRMED** - the machine sources agree with the stored value (rules below). Nobody is asked -
  unless the field is flagged (below).
* **CONFLICT** - a machine source contradicts it, or says the source is about something else.
* **MISSING** - no machine source can confirm or contradict the stored value, or the column is
  empty (an empty field is asked too: owner decision O6 and HUMAN_ONLY_DECISIONS B3 - a field gets
  a sourced value or stays empty, so a researcher looks for one).

**Flags.** An earlier reading may already have found a field wrong where the machine sees nothing:
the stage-1 measurement of the acceptance `draw-2026-09-25b` (its counted WRONG verdicts) and the 21
"both wrong" cells of HUMAN_ONLY B13 (`seeds.py` builds SEEDS.jsonl from them). A flagged field is
asked whatever its status, and the question shows the earlier finding.

A site with any field in CONFLICT or MISSING, or flagged, goes to the Opus handoff (`handoff.py`),
with exactly those fields. Retired sites (`scope_status = 'retired'`) are not classified: they are
hidden everywhere, and nothing of theirs is written.

**The item's identity first.** The site's item comes from `site_external_ids`, which was derived
from the stored source_url - so an item can be the island, the town or the hill the site lies on
(the stage-1 measurement of 2026-09-26 found source URLs on the island or town article). When the
item is an instance of a *container* class of the table (a settlement, an administrative unit, a
natural feature, a museum) and none of its classes holds the stored type, the item is in doubt:
its point, its dates and its article are then not evidence about the site - coordinates and
source_url are CONFLICT (`identity`), and its dates are not read (period MISSING).

**coordinates.** The witnesses are the item's P625 (the first truthy statement, a preferred one
first - `bcases.collect.claims_record`; Earth only) and the primary coordinates of the item's
English article. Each has a tolerance: 1 km, or half the P625's stated precision in metres when that
is larger (`census/tests/t01_wikidata_claims.py`, the rule T01 measured with). CONFIRMED when both
witnesses exist, the stored point lies within each one's tolerance, and the two lie within
tolerance of each other; CONFLICT when a witness is farther away or the two disagree (or on identity
doubt), and when another curated site that is not retired holds exactly the same point (a
placeholder: HUMAN_ONLY counted 34 sites on 12 such points on 2026-09-26, the Kilmartin Glen cairns,
the Gyeongju belts); MISSING when there is no witness, or one only that the stored point agrees
with (the stored point is often a copy of the one P625, so it confirms nothing - the spec's rule,
"Wikidata's and Wikipedia's points agree"). The columns are NOT NULL: a coordinate is corrected,
never cleared (FIELD_CONTRACT section 3).

**period_start.** The item's earliest dated start: every value of P571 (inception) and P580 (start
time), and the P1319 (earliest date) qualifiers on them, each read with its precision as a span of
years (a year exactly; a decade, century or millennium as that many years either side, generously;
anything coarser is not read, and neither is a date from 1500 AD on - `MODERN`). The span's buckets
(`pipeline.utils.text.categorize_period`, the period-name lane's rule) against the stored value's
bucket: the same bucket - CONFIRMED; the span lies wholly in other buckets - CONFLICT; the span
straddles the stored bucket - MISSING. No date - MISSING. An empty stored value with a date is
CONFLICT (a value to source), without one MISSING. `period_name` is not asked: it is the bucket of
`period_start` (`GOLD_STANDARD.md:79`), derived by the write plan.

**site_type.** The item's P31 classes through the pinned table (`p31_site_types.json`): each class
is `site` (a kind of site: the canonical types it is consistent with), `generic` (archaeological
site, ruins, heritage listing: consistent with the generic types only) or `container`. CONFIRMED
when the stored type is one a class names; CONFLICT when a `site` class names others (or on identity
doubt); MISSING when only generic classes speak and none names the stored type, or there is no item.
A class the table does not hold stops the classification (`TableError`): the table is completed and
re-pinned first, so no class is ever read as silent.

**source_url.** The harvest's record of the stored URL (`harvest.url_kind`). A URL that is
a section link (the URL's own `#fragment`) - CONFLICT, whatever the page. A Wikipedia article:
missing, invalid, a disambiguation page, a redirect into a section, another item's article, or a
redirect whose target title does not name the site (`names_it`: a distinctive word of the name,
the whole name when it has none, or the item's English label or an alias) - CONFLICT; the item's
own article (the sitelink of that wiki, or the page whose item is the site's) - CONFIRMED. Another
page: 404/410 - CONFLICT; redirected to another page - CONFLICT; served, with a <title> that names
the site - CONFIRMED; otherwise (403, 5xx, a network error, a title that names nothing) - MISSING.
A search or translation URL, a malformed or non-public one - CONFLICT. Empty - MISSING.

Inputs in `--out` (default `output/remediation/fields/wd1/`): STORED.jsonl (`export`) and
SEEDS.jsonl (`seeds.py build`; it may hold no line, it may not be absent). Output: CLASSIFIED.jsonl
(one line per site not retired - or per site of the chosen `--part`, `PARTS`: every field's status,
the stored value, the machine evidence, the reason and the flags) and COUNTS.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from bcases.classify import fold  # noqa: E402 - the name folding of the owner-case classifier
from bcases.collect import claims_record  # noqa: E402 - the truthy P625, never copied
from bcases.web_witness import distinctive_words  # noqa: E402 - the words that say which place
from census.tests.t01_wikidata_claims import METRES_PER_DEGREE, TOLERANCE_M  # noqa: E402
from mechanical.plan import _claims, psql_json_reader  # noqa: E402

from fields import harvest as H  # noqa: E402
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402
from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

CONFIRMED, CONFLICT, MISSING = "CONFIRMED", "CONFLICT", "MISSING"
ASKED = frozenset({CONFLICT, MISSING})
#: The fields WD1 decides, in the order a question lists them.
FIELDS = ("coordinates", "period_start", "site_type", "source_url")

TABLE = _HERE.parent / "p31_site_types.json"
#: sha256 of the table's LF text. The table is reviewed data: a changed table is refused until this
#: pin is moved with it, in one reviewed commit.
TABLE_SHA256 = "21c144ca000691f021cb13c62ee70429447fa6284ac5c012a75868ae6f0008b2"
#: `other`: the item is no place at all - an object, a person, a deity, a concept, a Wikimedia page.
KINDS = frozenset({"site", "generic", "container", "other"})
#: The kinds that put the item's identity in doubt unless the stored type is one they list.
PLACES = frozenset({"container", "other"})

DEFAULT_OUT = REPO / "output" / "remediation" / "fields" / "wd1"
STORED_FILE = "STORED.jsonl"
SEEDS_FILE = "SEEDS.jsonl"
CLASSIFIED_FILE = "CLASSIFIED.jsonl"
COUNTS_FILE = "COUNTS.json"

P_INCEPTION, P_START, P_EARLIEST = "P571", "P580", "P1319"
#: Wikidata time precision -> years either side of the stated year (9 = the year itself). Coarser
#: than a millennium (6) is not read: a ten-thousand-year span decides no bucket.
PRECISION_SPAN = {9: 0, 8: 9, 7: 99, 6: 999}
#: A start the item dates from this year on is not read. The curated scope ends at 1500 AD
#: (medieval sites are out; the Americas and Oceania run to 1500 AD - owner decisions E3 and O7),
#: so such a date is the item's designation, park or museum (Paphos Archaeological Park, P571
#: 1962 - seen in the 2026-09-26 sample), never the site's start.
MODERN = 1500
_TIME = re.compile(r"([+-])(\d+)-\d\d-\d\dT")
EARTH = "Q2"
BUCKETS = [name for name, _low, _high in PERIOD_BUCKETS]

STORED_SQL = """\
SELECT u.id::text AS site_id, u.name, u.lat::text AS lat_text, u.lon::text AS lon_text,
       u.period_start, u.period_end, u.period_name, u.site_type, u.source_url, u.scope_status
  FROM unified_sites u
 WHERE u.source_id = 'ancient_nerds'
 ORDER BY u.id"""


class ClassifyError(RuntimeError):
    """The inputs cannot be classified as they are. Nothing is written."""


class TableError(ClassifyError):
    """The P31 table is not the pinned one, is malformed, or lacks a class the harvest holds."""


# ------------------------------------------------------------------------------ the P31 table
@dataclass(frozen=True)
class ClassEntry:
    qid: str
    label: str
    kind: str
    types: tuple[str, ...]


def table_sha256(path: Path = TABLE) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def parse_table(text: str) -> dict[str, ClassEntry]:
    """The table's classes, each checked: a kind of `KINDS`, canonical types that are fixed points
    of `normalize_site_type` (FIELD_CONTRACT 2.1), a `generic` or `container` class with types."""
    data = json.loads(text)
    entries: dict[str, ClassEntry] = {}
    for qid, row in data["classes"].items():
        if not re.fullmatch(r"Q[1-9][0-9]*", qid):
            raise TableError(f"{qid!r} is not a class id")
        if set(row) != {"label", "kind", "types"} or row["kind"] not in KINDS:
            raise TableError(f"{qid}: {row!r} is not a table row")
        types = tuple(row["types"])
        for name in types:
            if name not in CANONICAL_TYPES or normalize_site_type(name) != name:
                raise TableError(f"{qid}: {name!r} is not a canonical type")
        if len(set(types)) != len(types):
            raise TableError(f"{qid}: a type is listed twice")
        entries[qid] = ClassEntry(qid, str(row["label"]), row["kind"], types)
    return entries


def load_table(path: Path = TABLE, *, pin: str = TABLE_SHA256) -> dict[str, ClassEntry]:
    digest = table_sha256(path)
    if digest != pin:
        raise TableError(
            f"{path} is not the pinned table (sha256 {digest[:16]}, pinned {pin[:16]}): review "
            "the change and move TABLE_SHA256 with it"
        )
    return parse_table(path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"))


def unmapped_classes(
    classes_of: Mapping[str, Sequence[str]], table: Mapping[str, ClassEntry]
) -> dict[str, int]:
    """Every P31 class the harvested items name that the table lacks, with how many items name it."""
    missing = Counter(c for classes in classes_of.values() for c in classes if c not in table)
    return dict(sorted(missing.items(), key=lambda kv: (-kv[1], kv[0])))


# ------------------------------------------------------------------------------ small readers
def _has_phrase(phrase: str, hay: str) -> bool:
    """Whether the folded `phrase` stands in the folded `hay` as whole words (both single-spaced)."""
    return bool(phrase) and re.search(r"(?<!\S)" + re.escape(phrase) + r"(?!\S)", hay) is not None


def names_it(name: str, text: str | None, also: Sequence[str] = ()) -> bool:
    """Whether `text` names the site, everything folded the owner-case classifier's way
    (`bcases.classify.fold`): it holds a distinctive word of the stored name as a whole word, or -
    when the name has none (every word generic or a type word: "Huaca del Sol", "Seven Barrows",
    169 live sites on 2026-09-26) - the whole name as a phrase; or it holds one of `also` (the
    item's own English label and aliases, `item_names`) as a phrase."""
    if not text:
        return False
    hay = fold(text, keep_parentheses=True)
    words = distinctive_words(name)
    if words:
        if any(_has_phrase(word, hay) for word in words):
            return True
    elif _has_phrase(fold(name), hay):
        return True
    return any(_has_phrase(fold(other), hay) for other in also)


def item_names(entity: Mapping[str, Any] | None, who: Identity) -> list[str]:
    """The item's English label and aliases, in Wikidata's order - none when there is no item or
    it is in doubt (the island's label names the island)."""
    if entity is None or who.doubt:
        return []
    label = ((entity.get("labels") or {}).get("en") or {}).get("value")
    aliases = [a.get("value") for a in (entity.get("aliases") or {}).get("en") or ()]
    out: list[str] = []
    for value in (label, *aliases):
        if isinstance(value, str) and value.strip() and value not in out:
            out.append(value)
    return out


def bucket(year: int) -> str:
    return str(categorize_period(year))


def year_span(value: Mapping[str, Any]) -> tuple[int, int] | None:
    """A Wikidata time value as the span of years it can mean, or None when too coarse."""
    match = _TIME.match(str(value.get("time") or ""))
    span = PRECISION_SPAN.get(int(value.get("precision") or 0))
    if match is None or span is None:
        return None
    year = int(match[2]) * (-1 if match[1] == "-" else 1)
    return year - span, year + span


def start_dates(entity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every readable start of the item: P571 and P580 values and their P1319 qualifiers."""
    out: list[dict[str, Any]] = []
    for prop in (P_INCEPTION, P_START):
        for statement in _claims(entity, prop):
            values = [(prop, ((statement.get("mainsnak") or {}).get("datavalue") or {}))]
            for snak in (statement.get("qualifiers") or {}).get(P_EARLIEST) or ():
                values.append((f"{prop}/{P_EARLIEST}", snak.get("datavalue") or {}))
            for source, datavalue in values:
                value = datavalue.get("value")
                if not isinstance(value, dict):
                    continue
                span = year_span(value)
                if span is not None:
                    out.append({"property": source, "time": value["time"], "span": list(span)})
    return out


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return haversine_distance(a[0], a[1], b[0], b[1])


def url_form(url: str) -> str:
    """The URL as httpx sends and records it: host lower-cased, a non-ASCII character or a space
    percent-encoded, everything already encoded left as it is. Every stored source_url had this
    form on 2026-09-26 (4,884 of 4,884 not retired)."""
    return str(httpx.URL(url))


def same_page(asked: str, final: str) -> bool:
    """Whether a redirect only normalised the URL: scheme, a `www.`, host case, a trailing slash, or
    the percent-encoding of the path and query (httpx records `G%C3%B6bekli_Tepe` for a request of
    `Göbekli_Tepe`, and a server may serve `King%27s` for `King's`)."""

    def key(url: str) -> tuple[str, str, str]:
        parts = urlsplit(url_form(url))
        host = (parts.hostname or "").lower().removeprefix("www.")
        return host, unquote(parts.path).rstrip("/") or "/", unquote(parts.query)

    return key(asked) == key(final)


# ------------------------------------------------------------------------------ the fields
@dataclass(frozen=True)
class Status:
    """A field's machine status. `flags` are the earlier findings that ask the field whatever its
    status (SEEDS.jsonl)."""

    status: str
    reason: str
    stored: Any
    evidence: Mapping[str, Any]
    flags: tuple[str, ...] = ()

    @property
    def asked(self) -> bool:
        return self.status in ASKED or bool(self.flags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "stored": self.stored,
            "evidence": dict(self.evidence),
            "flags": list(self.flags),
        }


@dataclass(frozen=True)
class Identity:
    """Whether the item is taken to be the site: a container class none of whose classes holds
    the stored type puts it in doubt."""

    doubt: bool
    containers: tuple[str, ...]


def identity(site_type: str | None, entries: Sequence[ClassEntry]) -> Identity:
    containers = tuple(e.label for e in entries if e.kind in PLACES)
    held = site_type is not None and any(site_type in e.types for e in entries)
    return Identity(bool(containers) and not held, containers)


def classify_coordinates(
    stored: tuple[float, float],
    entity: Mapping[str, Any] | None,
    article: Mapping[str, Any] | None,
    who: Identity,
    stacked: int,
) -> Status:
    """`stacked`: how many other curated sites that are not retired hold exactly this point."""
    shown = f"{stored[0]}, {stored[1]}"
    witnesses: list[dict[str, Any]] = []
    if entity is not None:
        p625 = claims_record(entity)["p625"]
        if p625 is not None and p625["globe"] in (EARTH, None):
            precision = p625["precision"]
            tolerance = TOLERANCE_M
            if isinstance(precision, int | float):
                tolerance = max(TOLERANCE_M, float(precision) * METRES_PER_DEGREE / 2.0)
            witnesses.append(
                {"source": "wikidata P625", "point": [p625["lat"], p625["lon"]], "tol_m": tolerance}
            )
    if article is not None and article.get("lat") is not None:
        if (article.get("globe") or "earth").lower() == "earth":
            witnesses.append(
                {
                    "source": "enwiki coordinates",
                    "point": [article["lat"], article["lon"]],
                    "tol_m": TOLERANCE_M,
                }
            )
    for w in witnesses:
        w["km_from_stored"] = round(km(stored, (w["point"][0], w["point"][1])), 3)
    evidence = {"witnesses": witnesses, "stacked": stacked}
    if who.doubt:
        return Status(
            CONFLICT,
            f"identity: the item is a {', '.join(who.containers)}, not the site",
            shown,
            evidence,
        )
    if stacked:
        return Status(
            CONFLICT,
            f"stacked: {stacked} other curated site(s) hold exactly this point - a placeholder",
            shown,
            evidence,
        )
    if not witnesses:
        return Status(MISSING, "no source point", shown, evidence)
    far = [w for w in witnesses if w["km_from_stored"] * 1000.0 > w["tol_m"]]
    if far:
        worst = max(far, key=lambda w: w["km_from_stored"])
        return Status(
            CONFLICT,
            f"stored point {worst['km_from_stored']} km from {worst['source']}",
            shown,
            evidence,
        )
    if len(witnesses) == 1:
        return Status(
            MISSING,
            f"one source point only ({witnesses[0]['source']}, within its tolerance): the stored "
            "point may be a copy of it",
            shown,
            evidence,
        )
    apart = km(tuple(witnesses[0]["point"]), tuple(witnesses[1]["point"]))  # type: ignore[arg-type]
    if apart * 1000.0 > max(w["tol_m"] for w in witnesses):
        return Status(CONFLICT, f"wikidata and enwiki disagree by {apart:.3f} km", shown, evidence)
    return Status(CONFIRMED, "within tolerance of both source points", shown, evidence)


def spanned_buckets(low: int, high: int) -> list[str]:
    """Every bucket a year of `low..high` falls in, in order: the buckets are contiguous, so the
    ones between the two ends' buckets."""
    first, last = BUCKETS.index(bucket(low)), BUCKETS.index(bucket(high))
    return BUCKETS[first : last + 1]


def classify_period(stored: int | None, entity: Mapping[str, Any] | None, who: Identity) -> Status:
    found = [] if entity is None or who.doubt else start_dates(entity)
    dates = [d for d in found if d["span"][0] < MODERN]
    evidence: dict[str, Any] = {"dates": dates, "modern": [d for d in found if d not in dates]}
    if not dates:
        if stored is None:
            return Status(MISSING, "empty, and the item gives no dated start", None, evidence)
        why = "identity: the item's dates are not the site's" if who.doubt else "no dated start"
        return Status(MISSING, why, stored, evidence)
    earliest = min(dates, key=lambda d: d["span"][0])
    spanned = spanned_buckets(*earliest["span"])
    said = f"{earliest['property']} {earliest['time']}"
    evidence.update(earliest=earliest, buckets=spanned)
    if stored is None:
        return Status(CONFLICT, f"empty; the item dates its start {said}", None, evidence)
    mine = bucket(stored)
    evidence["stored_bucket"] = mine
    if spanned == [mine]:
        return Status(CONFIRMED, f"{said} in {mine}", stored, evidence)
    if mine not in spanned:
        return Status(
            CONFLICT, f"{said} lies in {', '.join(spanned)}, not {mine}", stored, evidence
        )
    return Status(MISSING, f"{said} spans {', '.join(spanned)}: inconclusive", stored, evidence)


def classify_site_type(
    stored: str | None, entries: Sequence[ClassEntry] | None, who: Identity
) -> Status:
    """The stored type against the item's classes. A `site` class speaks first: when the item has
    one, the stored type must be one the specific (or place) classes name - a generic type there is
    a downgrade (`GOLD_STANDARD.md` section 4: "a downgrade to 'Ruin'/'Archaeological site'" is
    wrong). Without one, a generic or place class can confirm only the types it lists."""
    if entries is None:
        return Status(MISSING, "no item", stored, {"classes": []})
    evidence: dict[str, Any] = {
        "classes": [{"qid": e.qid, "label": e.label, "kind": e.kind} for e in entries]
    }
    if who.doubt:
        return Status(
            CONFLICT, f"identity: the item is a {', '.join(who.containers)}", stored, evidence
        )
    specific = [e for e in entries if e.kind == "site"]
    places = [e for e in entries if e.kind in PLACES]
    speaking = (
        specific + places if specific else places + [e for e in entries if e.kind == "generic"]
    )
    named = sorted({t for e in speaking for t in e.types})
    evidence["types"] = named
    if stored is not None and stored in named:
        return Status(CONFIRMED, f"{stored!r} is a type the item's classes name", stored, evidence)
    if specific:
        labels = ", ".join(e.label for e in specific)
        return Status(
            CONFLICT,
            f"the item is a {labels}: {', '.join(named)}, not {stored!r}",
            stored,
            evidence,
        )
    if stored is None:
        return Status(MISSING, "empty, and no specific class names a type", None, evidence)
    why = "only generic classes, none names the stored type" if entries else "the item has no class"
    return Status(MISSING, why, stored, evidence)


def classify_source_url(
    site: Mapping[str, Any],
    record: Mapping[str, Any],
    entity: Mapping[str, Any] | None,
    who: Identity,
) -> Status:
    url, kind = record["source_url"], record["kind"]
    name, qid = str(site["name"]), site["qid"]
    also = item_names(entity, who)
    evidence = {k: v for k, v in record.items() if k not in ("site_id", "source_url")}

    def status(value: str, reason: str) -> Status:
        return Status(value, reason, url, evidence)

    if kind == H.URL_NONE:
        return status(MISSING, "empty: the site names no source page")
    if kind in (H.URL_NOT_A_SOURCE, H.URL_MALFORMED, H.URL_NOT_PUBLIC):
        return status(CONFLICT, f"{kind}: not a page about a site")
    if urlsplit(url).fragment:
        return status(
            CONFLICT, f"a section link (#{urlsplit(url).fragment}), not the page's own URL"
        )
    if kind == H.URL_WIKIPEDIA:
        if record["missing"] or record["invalid"]:
            return status(CONFLICT, "dead: the article does not exist")
        if record["disambiguation"]:
            return status(CONFLICT, "a disambiguation page")
        if record["fragment"]:
            return status(
                CONFLICT,
                f"redirects into a section: {record['resolved_title']}#{record['fragment']}",
            )
        page_item = record["wikibase_item"]
        if qid is not None and page_item is not None and page_item != qid:
            return status(CONFLICT, f"another item's article ({page_item}, the site's is {qid})")
        if record["redirected"] and not names_it(name, record["resolved_title"], also):
            return status(CONFLICT, f"redirects to another article: {record['resolved_title']}")
        if who.doubt:
            return status(CONFLICT, f"identity: the article is the {', '.join(who.containers)}'s")
        sitelink = None
        if entity is not None:
            sitelink = ((entity.get("sitelinks") or {}).get(f"{record['lang']}wiki") or {}).get(
                "title"
            )
        if qid is not None and (page_item == qid or sitelink == record["resolved_title"]):
            return status(CONFIRMED, "the item's own article")
        return status(MISSING, "an article no item of the site confirms")
    # a web page
    code = record.get("status")
    if code in (404, 410):
        return status(CONFLICT, f"dead: HTTP {code}")
    if code is None or not 200 <= int(code) < 300:
        return status(MISSING, f"not readable by machine: {record.get('error') or f'HTTP {code}'}")
    if not same_page(url, str(record["final_url"])):
        return status(CONFLICT, f"redirects to another page: {record['final_url']}")
    if names_it(name, record.get("page_title"), also):
        return status(CONFIRMED, "a page whose title names the site")
    return status(MISSING, "a page whose title names nothing of the site")


# ------------------------------------------------------------------------------ one site
def classify_site(
    site: Mapping[str, Any],
    stored: Mapping[str, Any],
    *,
    entity: Mapping[str, Any] | None,
    article: Mapping[str, Any] | None,
    url_record: Mapping[str, Any],
    table: Mapping[str, ClassEntry],
    stacked: int,
    flags: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """One site's line of CLASSIFIED.jsonl. Pure: every input is given. `stacked`: how many other
    live curated sites hold exactly this point; `flags`: the site's earlier findings per field."""
    entries = None
    if entity is not None:
        entries = [table[c] for c in H.item_ids(entity, H.P_INSTANCE)]
    site_type = stored["site_type"]
    who = identity(site_type, entries or [])
    point = (float(stored["lat_text"]), float(stored["lon_text"]))
    fields = {
        "coordinates": classify_coordinates(point, entity, article, who, stacked),
        "period_start": classify_period(stored["period_start"], entity, who),
        "site_type": classify_site_type(site_type, entries, who),
        "source_url": classify_source_url(site, url_record, entity, who),
    }
    unknown = set(flags) - set(FIELDS)
    if unknown:
        raise ClassifyError(f"{site['site_id']}: flags for {sorted(unknown)}, not a WD1 field")
    fields = {
        name: replace(status, flags=tuple(flags.get(name, ()))) for name, status in fields.items()
    }
    start = stored["period_start"]
    return {
        "site_id": site["site_id"],
        "name": site["name"],
        "country": site["country"],
        "qid": site["qid"],
        "enwiki": None if entity is None else H.enwiki_sitelink(entity),
        "scope_status": stored["scope_status"],
        "identity": {"doubt": who.doubt, "containers": list(who.containers)},
        "item_names": item_names(entity, who),
        "period_name": {
            "stored": stored["period_name"],
            "bucket_of_stored_start": None if start is None else bucket(int(start)),
        },
        "period_end": stored["period_end"],
        "fields": {name: status.to_dict() for name, status in fields.items()},
        "asked": [name for name in FIELDS if fields[name].asked],
    }


# ------------------------------------------------------------------------------ the run
def export_stored(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    rows = reader(STORED_SQL)
    if not rows:
        raise ClassifyError("the stored-field export returned no curated site")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    tmp = out / (STORED_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / STORED_FILE)
    return len(rows)


def read_stored(out: Path) -> dict[str, dict[str, Any]]:
    path = out / STORED_FILE
    if not path.exists():
        raise ClassifyError(f"{path} is missing - run `classify.py export` first")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {str(row["site_id"]): row for row in rows}


SEED_KEYS = ("site_id", "field", "source", "finding")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


def read_seeds(out: Path) -> dict[str, dict[str, list[str]]]:
    """SEEDS.jsonl (`seeds.py build`) as `{site_id: {field: ["<source>: <finding>", ...]}}`. The
    file must exist - a classification without it would ask none of the known-wrong fields."""
    path = out / SEEDS_FILE
    if not path.exists():
        raise ClassifyError(f"{path} is missing - run `seeds.py build` first")
    seeds: dict[str, dict[str, list[str]]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        seed = json.loads(raw)
        if tuple(seed) != SEED_KEYS or seed["field"] not in FIELDS:
            raise ClassifyError(f"{path}:{number} is not a seed of a WD1 field: {raw[:120]}")
        if not _UUID.match(str(seed["site_id"])) or not str(seed["finding"]).strip():
            raise ClassifyError(f"{path}:{number} names no site or no finding")
        text = f"{seed['source']}: {seed['finding']}"
        seeds.setdefault(seed["site_id"], {}).setdefault(seed["field"], []).append(text)
    return seeds


def stacked_points(stored: Mapping[str, Mapping[str, Any]]) -> Counter[tuple[float, float]]:
    """How many curated sites that are not retired hold each exact point."""
    return Counter(
        (float(row["lat_text"]), float(row["lon_text"]))
        for row in stored.values()
        if row["scope_status"] != "retired"
    )


def _agrees(site: Mapping[str, Any], stored: Mapping[str, Any]) -> bool:
    return (
        float(stored["lat_text"]) == float(site["lat"])
        and float(stored["lon_text"]) == float(site["lon"])
        and stored["source_url"] == site["source_url"]
    )


#: A run takes every site (`all`) or one of two disjoint parts, each a run of its own (its own
#: --out, rounds and waves): `conflict` - the sites with a field a machine source contradicts or an
#: earlier reading flagged; `rest` - every other site, the unasked ones included (a label off its
#: start is written by the rest's wave). Measured 2026-09-26: 4,752 of 4,926 sites are asked, most
#: only because no machine source dates their start; the parts let the contradicted ones be decided
#: and written first.
PARTS = ("all", "conflict", "rest")


def in_conflict_part(line: Mapping[str, Any]) -> bool:
    return any(f["status"] == CONFLICT or f["flags"] for f in line["fields"].values())


def pilot_lines(
    lines: Sequence[Mapping[str, Any]], size: int, seed: int
) -> list[Mapping[str, Any]]:
    """A part's pilot: `size` of its asked sites drawn reproducibly (`random.Random(seed)` over the
    ids in order), in id order. The draw is proportional, so the countries with the most questions
    (England: about a fifth of them on 2026-09-26) are in it as they are in the part."""
    asked = sorted((line for line in lines if line["asked"]), key=lambda line: line["site_id"])
    if size > len(asked):
        raise ClassifyError(f"a pilot of {size} from {len(asked)} asked sites")
    chosen = set(random.Random(seed).sample([line["site_id"] for line in asked], size))  # noqa: S311
    return [line for line in asked if line["site_id"] in chosen]


def _pilot_sites(run: Path) -> set[str]:
    path = run / CLASSIFIED_FILE
    if not path.exists():
        raise ClassifyError(f"{path} is missing - classify the pilot first (`--pilot`)")
    return {json.loads(raw)["site_id"] for raw in path.read_text(encoding="utf-8").splitlines()}


def classify_all(
    root: Path,
    out: Path,
    *,
    table: Mapping[str, ClassEntry],
    part: str,
    pilot: tuple[int, int] | None = None,
    without: Path | None = None,
) -> dict[str, Any]:
    """CLASSIFIED.jsonl and COUNTS.json of one part - or of its pilot (`pilot`: a sample of
    `(size, seed)` of its asked sites), or of the part less a pilot run's sites (`without`)."""
    if part not in PARTS:
        raise ClassifyError(f"{part!r} is not one of {PARTS}")
    sites = H.read_sites(root)
    stored = read_stored(out)
    seeds = read_seeds(out)
    points = stacked_points(stored)
    entities = {s["qid"]: H.load_entity(root, s["qid"]) for s in sites if s["qid"] is not None}
    missing = unmapped_classes(
        {qid: H.item_ids(e, H.P_INSTANCE) for qid, e in entities.items()}, table
    )
    if missing:
        labels = json.loads((root / H.CLASSES_FILE).read_text(encoding="utf-8"))
        shown = [f"{q} {labels.get(q, {}).get('label')!r} x{n}" for q, n in missing.items()]
        raise TableError(
            f"{len(missing)} P31 class(es) are not in the table - add, review, re-pin: "
            + "; ".join(shown[:40])
        )
    lines, retired = [], 0
    for site in sites:
        row = stored.get(site["site_id"])
        if row is None:
            raise ClassifyError(f"{site['site_id']} is in the harvest but not in {STORED_FILE}")
        if not _agrees(site, row):
            raise ClassifyError(
                f"{site['site_id']}: the harvest and {STORED_FILE} disagree on its point or URL - "
                "export both again, one right after the other"
            )
        if row["scope_status"] == "retired":
            retired += 1
            continue
        entity = entities.get(site["qid"]) if site["qid"] else None
        point = (float(row["lat_text"]), float(row["lon_text"]))
        lines.append(
            classify_site(
                site,
                row,
                entity=entity,
                article=H.load_enwiki(root, site["qid"]) if site["qid"] else None,
                url_record=H.load_url(root, site),
                table=table,
                stacked=points[point] - 1,
                flags=seeds.get(site["site_id"], {}),
            )
        )
    classified = {line["site_id"] for line in lines}
    if part != "all":
        lines = [line for line in lines if in_conflict_part(line) == (part == "conflict")]
    taken: set[str] = set()
    if without is not None:
        taken = _pilot_sites(without)
        lines = [line for line in lines if line["site_id"] not in taken]
    if pilot is not None:
        lines = pilot_lines(lines, *pilot)
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n" for line in lines)
    (out / CLASSIFIED_FILE).write_text(text, encoding="utf-8", newline="\n")
    counts = count(lines)
    counts["part"] = part
    counts["pilot"] = None if pilot is None else {"size": pilot[0], "seed": pilot[1]}
    counts["without"] = (
        None if without is None else {"run": without.as_posix(), "sites": len(taken)}
    )
    counts["retired_not_classified"] = retired
    counts["seeds"] = {
        "sites": len(seeds),
        "cells": sum(len(by_field) for by_field in seeds.values()),
        "sites_not_classified": sorted(set(seeds) - classified),
    }
    counts["table_sha256"] = table_sha256()
    (out / COUNTS_FILE).write_text(
        json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return counts


def count(lines: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    lines = list(lines)
    per_field = {
        name: dict(sorted(Counter(line["fields"][name]["status"] for line in lines).items()))
        for name in FIELDS
    }
    asked = [line for line in lines if line["asked"]]
    return {
        "sites": len(lines),
        "per_field": per_field,
        "sites_asked": len(asked),
        "fields_asked": sum(len(line["asked"]) for line in asked),
        "asked_field_sets": dict(
            sorted(Counter("+".join(line["asked"]) for line in asked).items())
        ),
        "identity_doubt": sum(1 for line in lines if line["identity"]["doubt"]),
        "flagged": {
            name: sum(1 for line in lines if line["fields"][name]["flags"]) for name in FIELDS
        },
        "flagged_only": {
            name: sum(
                1
                for line in lines
                if line["fields"][name]["flags"] and line["fields"][name]["status"] not in ASKED
            )
            for name in FIELDS
        },
        "stacked_points": sum(
            1 for line in lines if line["fields"]["coordinates"]["evidence"]["stacked"]
        ),
        "period_name_not_bucket_of_start": sum(
            1
            for line in lines
            if line["period_name"]["stored"] != line["period_name"]["bucket_of_stored_start"]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=H.DEFAULT_ROOT, help="the harvest")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="STORED.jsonl from production (one read-only SELECT)")
    run = sub.add_parser("classify", help="CLASSIFIED.jsonl and COUNTS.json, from files only")
    run.add_argument("--part", choices=PARTS, required=True, help="every site or one part")
    cut = run.add_mutually_exclusive_group()
    cut.add_argument("--pilot", type=int, help="a pilot: this many of the part's asked sites")
    cut.add_argument("--without", type=Path, help="the part less this pilot run's sites")
    run.add_argument("--seed", type=int, help="the pilot's draw (with --pilot)")
    sub.add_parser("unmapped", help="the P31 classes the table lacks, with labels and counts")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            print(json.dumps({"stored": export_stored(args.out, reader=psql_json_reader())}))
        elif args.command == "classify":
            if (args.pilot is None) != (args.seed is None):
                parser.error("--pilot and --seed go together")
            result = classify_all(
                args.root,
                args.out,
                table=load_table(),
                part=args.part,
                pilot=None if args.pilot is None else (args.pilot, args.seed),
                without=args.without,
            )
            print(json.dumps(result, indent=1, sort_keys=True))
        else:
            sites = H.read_sites(args.root)
            classes_of = {
                s["qid"]: H.item_ids(H.load_entity(args.root, s["qid"]), H.P_INSTANCE)
                for s in sites
                if s["qid"] is not None
            }
            labels = json.loads((args.root / H.CLASSES_FILE).read_text(encoding="utf-8"))
            # the table as it stands, unpinned: this lists what to add before the pin moves
            table = parse_table(TABLE.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"))
            rows = [
                {"qid": q, "items": n, **labels.get(q, {})}
                for q, n in unmapped_classes(classes_of, table).items()
            ]
            print(json.dumps(rows, ensure_ascii=False, indent=1))
    except (ClassifyError, H.HarvestError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
