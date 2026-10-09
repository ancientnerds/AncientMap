"""D13: re-target the records that describe a modern town or village to the ancient site.

Owner decision D13 (2026-10-08): a record whose name, Wikidata item, Wikipedia article, description
and gallery describe the modern town around an ancient site is **re-targeted to the ancient site**;
the old name stays a searchable alias. The funnel (`funnel.py`, 600 records) only chose what to ask;
this module asks it.

**The question** (stage `retarget-web`, role `web_verifier`, Sonnet): what does this record designate
at its stored point, and what is the ancient feature? One verdict per record:

* `KEEP`     - the record's subject at its stored point is the ancient site itself;
* `RETARGET` - the ancient site is another nameable thing: `target` carries its name, Wikidata item,
               English Wikipedia article, `source_url` and coordinates, **each with a quote**;
* `RETIRE`   - no ancient feature at or near the point (the scope lane takes it from there);
* `MERGE`    - the ancient site is already another record of the map (D14).

**The machine checks** are L5's gates (`l5/decide.py`, reused through its public seam) applied to
the target: every quote found in the page it cites; the article exists on English Wikipedia under
exactly that title, is no redirect and no disambiguation page, and is the item given (the daily
refresh's fixed point); the item's `P625` or its article's coordinates lie within 1 km of the
coordinates given; the name is an English label or alias of the item or the article's title; the
`source_url` is the article or another page about the site, never another Wikipedia title; no other
visible record carries the item (that is a MERGE question). The coordinates must lie within
`MAX_MOVE_M` of the stored point: further away is a coordinate question, not a re-target. An answer
that fails a gate is **held** with its reason and asked again (two re-asks at most).

**The re-check** (stage `retarget-recheck`, role `adversarial`, Opus) asks every decided verdict that
is not `KEEP` again, adversarially, with the proposal and its evidence in front of it: `CONFIRM` or
`REJECT`. A site is final only when both stages agree; a rejection goes to the owner list.

The write chain of a final `RETARGET` is `retarget_plan.py`'s.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (
    str(REPO),
    str(_HERE.parents[1]),
    str(REPO / "output" / "remediation" / "tools"),
):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import qid_repair as QR  # noqa: E402
from bcases.collect import claims_record  # noqa: E402
from l5 import decide as L5D  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from identity import answers as A  # noqa: E402
from identity import common, export  # noqa: E402
from identity.prompts import (  # noqa: E402
    cache_entries,
    cache_section,
    earlier_section,
    wiki_cache_dir,
)
from identity.rounds import (  # noqa: E402
    DECIDED,
    HELD,
    AnswerError,
    Env,
    Outcome,
    Question,
    StageSpec,
)
from pipeline.lyra.prospector.wiki import CONTROL_RE, enwiki_title_from_url  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402

LANE = "retarget"
WEB, RECHECK = "retarget-web", "retarget-recheck"
KEEP, RETARGET, RETIRE, MERGE = "KEEP", "RETARGET", "RETIRE", "MERGE"
VERDICTS = (KEEP, RETARGET, RETIRE, MERGE)
CONFIRM, REJECT = "CONFIRM", "REJECT"
RECHECK_VERDICTS = (CONFIRM, REJECT)
ENWIKI = "https://en.wikipedia.org/wiki/"
ENTITY_DATA = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
QID_RE = re.compile(r"Q[1-9][0-9]*")
NAME_CHARS = 500
#: L5's position gate: the item (or its article) must lie within 1 km of the coordinates given.
GATE_M = QR.GATE_M
#: The ancient site may lie this far from the stored point of a modern-town record. Further away,
#: the record's point is a coordinate question (lane wd5), not a re-target.
MAX_MOVE_M = 25_000.0
#: Merge candidates: curated records within this distance whose names look alike (the export's pairs).
ANSWER_KEYS = frozenset({"site_id", "verdict", "why", "quotes", "target", "merge_with"})
TARGET_KEYS = ("name", "qid", "enwiki_title", "source_url", "coordinates")
RECHECK_KEYS = frozenset({"site_id", "verdict", "why", "quotes"})


def article_url(title: str) -> str:
    """The English Wikipedia URL of a title, as the site's own `source_url` values spell it."""
    return ENWIKI + url_quote(title.replace(" ", "_"), safe="()',-._~:!*;@$")


def _normal(text: str) -> str:
    return Q.normalise(text).casefold()


# ------------------------------------------------------------------------------------ the contexts
def merge_candidates(
    site_id: str,
    shared: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """The records a MERGE may name: those carrying one of this record's items (`shared_with`) and
    those within 300 m with a similar name (the export's `pairs`), nearest first."""
    found: dict[str, dict[str, Any]] = {}
    for other in shared:
        found[str(other["id"])] = {
            "id": str(other["id"]),
            "name": other["name"],
            "why": "carries the same Wikidata item",
            "metres": None,
        }
    for pair in pairs:
        if site_id not in (pair["a"], pair["b"]):
            continue
        other = pair["b"] if pair["a"] == site_id else pair["a"]
        entry = found.setdefault(
            other,
            {"id": other, "name": names.get(other, "?"), "why": "", "metres": pair["metres"]},
        )
        entry["metres"] = pair["metres"]
        entry["why"] = (entry["why"] + "; " if entry["why"] else "") + (
            f"{pair['metres']:.0f} m away with a similar name (trigram {pair['similarity']})"
        )
    return sorted(found.values(), key=lambda c: (c["metres"] is None, c["metres"] or 0, c["id"]))


def site_context(
    row: Mapping[str, Any],
    funnel: Mapping[str, Any],
    ext: Mapping[str, Sequence[str]],
    candidates: Sequence[Mapping[str, Any]],
    cache: Sequence[Mapping[str, str]],
    exported_at: str,
) -> dict[str, Any]:
    """Everything the web question is a function of, JSON-able and stored with the round."""
    return {
        "site_id": row["id"],
        "exported_at": exported_at,
        "name": row["name"],
        "country": row["country"],
        "site_type": row["site_type"],
        "lat": row["lat"],
        "lon": row["lon"],
        "period_start": row["period_start"],
        "period_name": row["period_name"],
        "source_url": row["source_url"],
        "scope_status": row["scope_status"],
        "description_lane": row["description_lane"],
        "description": row["description"],
        "description_chars": row["description_chars"],
        "qids": list(ext.get("wikidata_qid", [])),
        "enwiki": list(ext.get("enwiki_title", [])),
        "why": {
            "tier": funnel["tier"],
            "p31": funnel["p31"],
            "p31_modern": funnel["p31_modern"],
            "sentence1": funnel["sentence1"],
            "opening_match": funnel["opening_match"],
            "shared_with": funnel["shared_with"],
        },
        "merge_candidates": list(candidates),
        "cache": list(cache),
    }


def web_questions(
    run: Path,
    *,
    root: Path | None = None,
    sites: Sequence[str] | None = None,
    exclude: Sequence[str] = (),
) -> list[Question]:
    """One question per funnel record (or the `sites` asked for), from the discovery's files."""
    exported = export.load_export(run / common.EXPORT_FILE)
    funnel = {r["id"]: r for r in common.read_jsonl(run / "IDENTITY_FUNNEL.jsonl")}
    wanted = list(funnel) if sites is None else list(sites)
    unknown = [s for s in wanted if s not in funnel]
    if unknown:
        raise common.IdentityError(f"{len(unknown)} site(s) are not in the funnel: {unknown[:3]}")
    by_id = common.rows_by_id(exported.shown)
    names = {sid: row["name"] for sid, row in by_id.items()}
    ext: dict[str, dict[str, list[str]]] = {}
    for e in exported.ext_ids:
        ext.setdefault(e["site_id"], {}).setdefault(e["kind"], []).append(e["value"])
    cache = cache_entries(wiki_cache_dir(root))
    skip = set(exclude)
    return [
        Question(
            sid,
            site_context(
                by_id[sid],
                funnel[sid],
                ext.get(sid, {}),
                merge_candidates(sid, funnel[sid]["shared_with"], exported.pairs, names),
                cache.get(sid, []),
                exported.exported_at,
            ),
        )
        for sid in wanted
        if sid not in skip
    ]


def holders_of(exported: export.Export) -> dict[str, list[dict[str, Any]]]:
    """`qid -> [{site_id, name, scope_status}]` over the shown records: who carries each item."""
    by_id = common.rows_by_id(exported.shown)
    held: dict[str, list[dict[str, Any]]] = {}
    for e in exported.ext_ids:
        if e["kind"] == "wikidata_qid" and e["site_id"] in by_id:
            row = by_id[e["site_id"]]
            held.setdefault(e["value"], []).append(
                {"site_id": row["id"], "name": row["name"], "scope_status": row["scope_status"]}
            )
    return held


def pilot_sites(questions: Sequence[Question], count: int) -> list[str]:
    """`count` sites spread evenly over the funnel's order (best tier first): the pilot is not the
    first twenty, which would all be one tier."""
    if count < 1 or count > len(questions):
        raise common.IdentityError(f"a pilot of {count} sites from {len(questions)} questions")
    step = len(questions) / count
    return [questions[int(i * step)].site_id for i in range(count)]


# -------------------------------------------------------------------------------------- the prompt
WEB_TEMPLATE = """You are a web verifier of the identity pass (owner decision D13) of the Ancient \
Nerds final repair. One curated record of a map of ancient sites; decide what it designates at its \
stored point and whether that is the ancient site. Research on the open web; read the pages you cite.

THE RECORD, as the database holds it (read {exported_at})
  id:           {site_id}
  name:         {name}
  country:      {country}
  point:        {lat}, {lon}
  type, period: {site_type}; {period}
  source_url:   {source_url}
  Wikidata:     {qids}
  Wikipedia:    {titles}
  description (first {chars} of {total} characters):
{description}

WHY THIS RECORD IS ASKED (a funnel chooses the questions, never the answers)
{why}
{candidates}{cache}{earlier}
THE QUESTION
The map shows ancient sites: ruins, monuments, burial grounds, rock art, caves. Some records were \
filled from the Wikipedia article or the Wikidata item of the modern town, village, municipality or \
region that lies around the site, so their name, ids, description and images describe the modern \
place. Decide ONE verdict:
  KEEP      the record's subject at its stored point IS the ancient site (an ancient city whose name \
the modern settlement also bears, a site whose own article opens as a village, is a KEEP).
  RETARGET  the ancient site is another nameable thing with its own Wikidata item and English \
Wikipedia article. Give its name, item, article, source_url and coordinates, each with a quote.
  RETIRE    nothing ancient is designated at or near the stored point: the record is the modern \
place only.
  MERGE     the ancient site is already another record of the map (the candidates above): this \
record duplicates it. Give that record's id.

THE RULES (L5's, applied to a target)
1. A target names exactly the ancient site: the item and the article are about it - not the town, \
region, park or larger complex it lies in, not a type, not a sibling monument, not a namesake \
elsewhere. The item must not be one of this record's current items, and no other record of the map \
may carry it (that is a MERGE).
2. qid: an item whose label, alias or description names the ancient site. Cite \
https://www.wikidata.org/wiki/Special:EntityData/<QID>.json and quote from it verbatim (for example \
the label). The machine reads its coordinates (P625), or its article's: they must lie within 1 km of \
the coordinates you give.
3. enwiki_title: the exact title of an English Wikipedia article about exactly the ancient site - \
not a redirect, not a disambiguation page, not a section of another article. Cite \
https://en.wikipedia.org/wiki/<Title> and quote a sentence that names the site. The article's \
Wikidata item must be the qid you give.
4. name: the English label or an English alias of that item, or the article's title (a bracketed \
qualifier such as "(Roman fort)" may be left off). Quote a page that holds the name.
5. source_url: the article's URL, or another page about exactly the ancient site. If it is an \
English Wikipedia URL, its title is the enwiki_title you give. It is not the record's current \
source_url. Quote that page.
6. coordinates: decimal degrees of the ancient site, within {max_km} km of the stored point. Quote a \
page that states them.
7. Every verdict carries at least one quote: verbatim text (whitespace may differ) of a page you \
cite by its URL. The machine fetches every cited URL and does not count a verdict whose quote it \
cannot find there. Never cite ancientnerds.com.

ANSWER with only this JSON object:
{{
 "site_id": "{site_id}",
 "verdict": "KEEP | RETARGET | RETIRE | MERGE",
 "why": "one or two sentences",
 "quotes": [{{"url": "https://...", "quote": "..."}}],
 "target": null,
 "merge_with": null
}}
For RETARGET "target" is
 {{"name": {{"value": "...", "quotes": [...]}},
  "qid": {{"value": "Q...", "quotes": [...]}},
  "enwiki_title": {{"value": "Title", "quotes": [...]}},
  "source_url": {{"value": "https://...", "quotes": [...]}},
  "coordinates": {{"lat": 0.0, "lon": 0.0, "quotes": [...]}}}}
and "quotes" at the top shows that the record is not the ancient site. For MERGE "merge_with" is the \
id of the record that already is the ancient site; otherwise both are null.
"""

RECHECK_TEMPLATE = """You are the adversarial reviewer of the identity pass (owner decision D13) of \
the Ancient Nerds final repair. A web verifier proposed to change one curated record of a map of \
ancient sites; a wrong change is written to production and shown to every visitor, so try to REFUTE \
it before you confirm it. Research on the open web with your own searches; do not trust the \
proposal's quotes, read the pages.

THE RECORD NOW (read {exported_at})
  id: {site_id}   name: {name}   country: {country}   point: {lat}, {lon}
  type, period: {site_type}; {period}
  source_url: {source_url}
  Wikidata: {qids}   Wikipedia: {titles}
  description: {description}
{cache}
THE PROPOSAL (verdict {verdict})
  why: {why}
{proposal}
{earlier}
THE QUESTION
{question}
Answer CONFIRM only when you found, on pages you read yourself, that the proposal is right in every \
part. Answer REJECT when any part is wrong, unproven, or about another place (say which). Every \
CONFIRM carries at least one quote: verbatim text of a page you cite by its URL; the machine fetches \
it and does not count a confirmation whose quote it cannot find. Never cite ancientnerds.com.

ANSWER with only this JSON object:
{{"site_id": "{site_id}", "verdict": "CONFIRM | REJECT", "why": "one or two sentences", \
"quotes": [{{"url": "https://...", "quote": "..."}}]}}
"""

QUESTIONS = {
    RETARGET: (
        "Is the proposed target exactly the ancient site this record should designate - the item, "
        "the article, the name, the source_url and the coordinates - and is the record as it stands "
        "(the modern place) NOT that site?"
    ),
    RETIRE: (
        "Is it true that nothing ancient is designated at or near the stored point, so that the "
        "record should leave the map? Look for a ruin, monument, burial ground or find spot at the "
        "place; a record about an ancient site that merely sits in a modern town is no retirement."
    ),
    MERGE: (
        "Is the record named in merge_with the same ancient site as this record, so that one of the "
        "two is a duplicate? Two monuments of one complex are not the same site."
    ),
}


def _period(ctx: Mapping[str, Any]) -> str:
    start = ctx["period_start"]
    return "no date" if start is None else f"{start} ({ctx['period_name']})"


def _why_lines(ctx: Mapping[str, Any]) -> str:
    why = ctx["why"]
    if why["tier"] == "calibration":
        lines = ["  - a calibration case: decide as for any record"]
    else:
        lines = [f"  - funnel tier {why['tier']}"]
    if why["p31_modern"]:
        lines.append(
            f"  - its Wikidata item is an instance of: {', '.join(why['p31'])} "
            f"(modern settlement classes: {', '.join(why['p31_modern'])})"
        )
    if why["opening_match"]:
        lines.append(
            f'  - the description opens: "{why["sentence1"]}" (reads as a {why["opening_match"]})'
        )
    for other in why["shared_with"]:
        lines.append(f"  - another record carries the same item: {other['name']} ({other['id']})")
    return "\n".join(lines)


def _candidates(ctx: Mapping[str, Any]) -> str:
    if not ctx["merge_candidates"]:
        return ""
    lines = [f"  - {c['name']} ({c['id']}): {c['why']}" for c in ctx["merge_candidates"]]
    return "\nRECORDS A MERGE MAY NAME\n" + "\n".join(lines) + "\n"


def render_web(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    """The exact web question for one record. Pure: the stored context and, for a re-ask, why the
    earlier answer was held."""
    description = str(ctx["description"] or "(none)")
    return WEB_TEMPLATE.format(
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        lat=ctx["lat"],
        lon=ctx["lon"],
        site_type=ctx["site_type"],
        period=_period(ctx),
        source_url=ctx["source_url"],
        qids=", ".join(f"{q} (https://www.wikidata.org/wiki/{q})" for q in ctx["qids"]) or "none",
        titles=", ".join(f"{t} ({article_url(t)})" for t in ctx["enwiki"]) or "none",
        chars=len(description),
        total=ctx["description_chars"],
        description="    " + description.replace("\n", "\n    "),
        why=_why_lines(ctx),
        candidates=_candidates(ctx),
        cache=cache_section(ctx),
        earlier=earlier_section(earlier),
        max_km=int(MAX_MOVE_M / 1000),
    )


# ------------------------------------------------------------------------------------ the answer
@dataclass(frozen=True)
class Cell:
    """One value of a target and the quotes behind it."""

    value: str
    quotes: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Target:
    name: Cell
    qid: Cell
    enwiki_title: Cell
    source_url: Cell
    lat: float
    lon: float
    coordinate_quotes: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Answer:
    site_id: str
    verdict: str
    why: str
    quotes: tuple[dict[str, str], ...]
    target: Target | None
    merge_with: str | None


def _cell(data: Any, key: str) -> Cell:
    cell = A.exact(data, {"value", "quotes"}, f"target.{key}")
    return Cell(
        A.text_of(cell["value"], f"target.{key}.value"),
        A.quotes_of(cell["quotes"], f"target.{key}", minimum=1),
    )


def _number(value: Any, what: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise AnswerError(f"{what} is not a number in [{low}, {high}]")
    return float(value)


def parse_target(data: Any, ctx: Mapping[str, Any]) -> Target:
    """The target of a RETARGET, in its exact shape and with every rule it can break on its own."""
    obj = A.exact(data, set(TARGET_KEYS), "target")
    name, qid, title, url = (
        _cell(obj[k], k) for k in ("name", "qid", "enwiki_title", "source_url")
    )
    place = A.exact(obj["coordinates"], {"lat", "lon", "quotes"}, "target.coordinates")
    lat = _number(place["lat"], "target.coordinates.lat", -90, 90)
    lon = _number(place["lon"], "target.coordinates.lon", -180, 180)
    place_quotes = A.quotes_of(place["quotes"], "target.coordinates", minimum=1)

    if not QID_RE.fullmatch(qid.value):
        raise AnswerError(f"target.qid: {qid.value!r} is not an item id")
    if qid.value in ctx["qids"]:
        raise AnswerError(f"target.qid: {qid.value} is the record's own item - that is KEEP")
    if not A.cites(qid.quotes, ENTITY_DATA.format(qid.value)):
        raise AnswerError(f"target.qid: a quote cites {ENTITY_DATA.format(qid.value)}")
    if CONTROL_RE.search(title.value) or "#" in title.value or "|" in title.value:
        raise AnswerError(f"target.enwiki_title: {title.value!r} is not an article title")
    if title.value in ctx["enwiki"]:
        raise AnswerError(f"target.enwiki_title: {title.value!r} is the record's own article")
    if not any(enwiki_title_from_url(q["url"]) == title.value for q in title.quotes):
        raise AnswerError(f"target.enwiki_title: a quote cites {article_url(title.value)}")
    if len(name.value) > NAME_CHARS:
        raise AnswerError(f"target.name: longer than {NAME_CHARS} characters")
    if not any(_normal(name.value) in _normal(q["quote"]) for q in name.quotes):
        raise AnswerError("target.name: a quote holds the name word for word")
    if url.value == ctx["source_url"]:
        raise AnswerError("target.source_url: it is the record's current source_url")
    if not A.cites(url.quotes, url.value):
        raise AnswerError("target.source_url: a quote cites the page given")
    if url.value.startswith(ENWIKI) and enwiki_title_from_url(url.value) != title.value:
        raise AnswerError(
            "target.source_url: an English Wikipedia URL names the article given as enwiki_title - "
            "the daily refresh derives the item and the title from it"
        )
    return Target(name, qid, title, url, lat, lon, place_quotes)


def parse_web(text: str, ctx: Mapping[str, Any]) -> Answer:
    """The web answer in its exact shape; every rule it can break on its own. Nothing is fetched."""
    data = A.load_object(text, ANSWER_KEYS)
    if data["site_id"] != ctx["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {ctx['site_id']}")
    verdict = data["verdict"]
    if verdict not in VERDICTS:
        raise AnswerError(f"verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
    why = A.text_of(data["why"], "why", max_chars=600)
    quotes = A.quotes_of(data["quotes"], "quotes", minimum=1)
    target = merge = None
    if verdict == RETARGET:
        if data["merge_with"] is not None:
            raise AnswerError("merge_with is null unless the verdict is MERGE")
        target = parse_target(data["target"], ctx)
    else:
        if data["target"] is not None:
            raise AnswerError("target is null unless the verdict is RETARGET")
        if verdict == MERGE:
            merge = data["merge_with"]
            allowed = [c["id"] for c in ctx["merge_candidates"]]
            if merge not in allowed:
                raise AnswerError(f"merge_with {merge!r} is none of the candidates {allowed}")
        elif data["merge_with"] is not None:
            raise AnswerError("merge_with is null unless the verdict is MERGE")
    return Answer(ctx["site_id"], verdict, why, quotes, target, merge)


def cited_web(answer: Answer, ctx: Mapping[str, Any]) -> set[str]:
    groups = [answer.quotes]
    if answer.target is not None:
        t = answer.target
        groups += [t.name.quotes, t.qid.quotes, t.enwiki_title.quotes, t.source_url.quotes]
        groups.append(t.coordinate_quotes)
    return A.urls_of(*groups)


def titles_web(answer: Answer, ctx: Mapping[str, Any]) -> set[str]:
    return {answer.target.enwiki_title.value} if answer.target is not None else set()


# ------------------------------------------------------------------------------------ the decision
class Hold(Exception):
    """One gate failed; the message is the site's hold reason."""


def _metres(lat: float, lon: float, other_lat: float, other_lon: float) -> float:
    return 1000.0 * haversine_distance(lat, lon, other_lat, other_lon)


def attested_names(entity: Mapping[str, Any], title: str) -> set[str]:
    """The names a target may take: the English label and aliases of its item, and its article's
    title with and without a bracketed qualifier (L5's rule for a rename)."""
    names = {v["value"] for code, v in entity["labels"].items() if L5D.is_english(code)} | {
        a["value"]
        for code, values in entity["aliases"].items()
        if L5D.is_english(code)
        for a in values
    }
    return names | {title, L5D.QUALIFIER.sub("", title)}


def _quotes_found(
    key: str, quotes: Sequence[Mapping[str, str]], site_id: str, library: Q.Library
) -> list[dict[str, str]]:
    counted, noted, reason = A.check_quotes(quotes, site_id, library)
    if not counted:
        raise Hold(f"{key}: a quote does not count ({reason})")
    return noted


def check_target(
    target: Target,
    ctx: Mapping[str, Any],
    env: Env,
    holders: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Every machine gate of a target, in order; the first failure raises `Hold`. Returns the
    record of what was proven (quote outcomes, notes, the item's facts)."""
    sid = ctx["site_id"]
    cells: dict[str, dict[str, Any]] = {}
    for key, cell in (
        ("name", target.name),
        ("qid", target.qid),
        ("enwiki_title", target.enwiki_title),
        ("source_url", target.source_url),
    ):
        cells[key] = {
            "value": cell.value,
            "quotes": _quotes_found(f"target.{key}", cell.quotes, sid, env.library),
            "note": "",
        }
    cells["coordinates"] = {
        "lat": target.lat,
        "lon": target.lon,
        "quotes": _quotes_found("target.coordinates", target.coordinate_quotes, sid, env.library),
        "note": "",
    }
    item, title = target.qid.value, target.enwiki_title.value
    cells["enwiki_title"]["note"] = L5D.article_check(title, env.titles, item)
    entity = L5D.entity_page(env.library, item, "target.qid")
    record = claims_record(entity)
    proofs = []
    if record["p625"] is not None:
        proofs.append(
            ("P625", _metres(target.lat, target.lon, record["p625"]["lat"], record["p625"]["lon"]))
        )
    article = env.titles[title]
    if article["lat"] is not None:
        proofs.append(
            ("the article", _metres(target.lat, target.lon, article["lat"], article["lon"]))
        )
    placed = [(what, m) for what, m in proofs if m <= GATE_M]
    if not placed:
        seen = ", ".join(f"{what} {m:.0f} m" for what, m in proofs) or "no coordinates"
        raise Hold(
            f"target.qid: {item} is not proven at the coordinates given ({seen}; the gate is "
            f"{GATE_M:.0f} m)"
        )
    what, metres = min(placed, key=lambda p: p[1])
    cells["qid"]["note"] = (
        f"{item} ({record['en_label']!r}): {what} {metres:.0f} m from the point given"
    )
    if _normal(target.name.value) not in {_normal(n) for n in attested_names(entity, title)}:
        shown = ", ".join(repr(n) for n in sorted(attested_names(entity, title))[:8])
        raise Hold(
            f"target.name: {target.name.value!r} is no English label or alias of {item} and no "
            f"title of {title!r} ({shown or 'none'})"
        )
    cells["name"]["note"] = f"{target.name.value!r} is a name of {item}"
    moved = _metres(float(ctx["lat"]), float(ctx["lon"]), target.lat, target.lon)
    if moved > MAX_MOVE_M:
        raise Hold(
            f"target.coordinates: {moved / 1000:.1f} km from the stored point, more than "
            f"{MAX_MOVE_M / 1000:.0f} km - a coordinate question, not a re-target"
        )
    others = [
        h for h in holders.get(item, []) if h["site_id"] != sid and h["scope_status"] != "retired"
    ]
    if others:
        named = ", ".join(f"{h['name']} ({h['site_id']})" for h in others)
        raise Hold(f"target.qid: {item} is carried by {named} - that is a MERGE, not a re-target")
    cells["coordinates"]["note"] = f"{moved:.0f} m from the stored point"
    label = (entity.get("labels") or {}).get("en", {}).get("value")
    description = (entity.get("descriptions") or {}).get("en", {}).get("value")
    return {
        "cells": cells,
        "facts": {
            "label": label,
            "description": description,
            "p625": record["p625"] and {"lat": record["p625"]["lat"], "lon": record["p625"]["lon"]},
            "article": title,
            "moved_m": round(moved),
        },
    }


def decide_web(
    answer: Answer,
    ctx: Mapping[str, Any],
    env: Env,
    holders: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Outcome:
    """Every machine check of one parsed web answer; the first failure holds the site."""
    data: dict[str, Any] = {
        "verdict": answer.verdict,
        "why": answer.why,
        "merge_with": answer.merge_with,
        "quotes": [],
        "target": None,
        "facts": None,
    }
    try:
        data["quotes"] = _quotes_found("quotes", answer.quotes, ctx["site_id"], env.library)
        if answer.target is not None:
            proof = check_target(answer.target, ctx, env, holders)
            data["target"], data["facts"] = proof["cells"], proof["facts"]
    except Hold as exc:
        return Outcome(HELD, str(exc), data)
    except L5D.Held as exc:  # a page read or an article gate of l5/decide.py
        return Outcome(HELD, str(exc), data)
    return Outcome(DECIDED, "", data)


def web_spec(holders: Mapping[str, Sequence[Mapping[str, Any]]]) -> StageSpec:
    """The web stage; `holders` is who carries each item now (`holders_of`)."""
    return StageSpec(
        lane=LANE,
        stage=WEB,
        role="web_verifier",
        render=render_web,
        parse=parse_web,
        decide=lambda a, c, e: decide_web(a, c, e, holders),
        cited=cited_web,
        titles=titles_web,
        per_batch=5,
        guidance=(
            "Your first duty is the quotes: a verdict whose quote the machine cannot find in the "
            "cited page is not counted and the record is asked again."
        ),
    )


# -------------------------------------------------------------------------------------- the re-check
def proposal_of(decision: Mapping[str, Any]) -> dict[str, Any]:
    """What the web stage proposed, as the re-check is shown it: verdict, why, the evidence quotes,
    the target's values and the machine's notes and facts."""
    data = decision["data"]
    return {
        "verdict": data["verdict"],
        "why": data["why"],
        "merge_with": data["merge_with"],
        "quotes": [{"url": q["url"], "quote": q["quote"]} for q in data["quotes"]],
        "target": data["target"],
        "facts": data["facts"],
    }


def recheck_questions(
    web_questions_: Sequence[Question], decisions: Mapping[str, Mapping[str, Any]]
) -> list[Question]:
    """The re-check asks every decided web verdict that is not KEEP, with its proposal."""
    out = []
    for q in web_questions_:
        decision = decisions.get(q.site_id)
        if decision is None or decision["status"] != DECIDED or decision["data"]["verdict"] == KEEP:
            continue
        out.append(Question(q.site_id, {**q.context, "proposal": proposal_of(decision)}))
    return out


def _proposal_text(proposal: Mapping[str, Any]) -> str:
    lines = []
    if proposal["merge_with"]:
        lines.append(f"  merge_with: {proposal['merge_with']}")
    target = proposal["target"]
    if target is not None:
        for key in ("name", "qid", "enwiki_title", "source_url"):
            lines.append(
                f"  target.{key}: {target[key]['value']}  ({target[key]['note'] or 'checked'})"
            )
        c = target["coordinates"]
        lines.append(f"  target.coordinates: {c['lat']}, {c['lon']}  ({c['note']})")
        facts = proposal["facts"]
        lines.append(
            f"  the item's own label and description: {facts['label']!r}, {facts['description']!r}; "
            f"its P625: {facts['p625']}"
        )
    quotes = [f'  quote: "{q["quote"]}" - {q["url"]}' for q in proposal["quotes"]]
    return "\n".join([*lines, *quotes])


def render_recheck(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    proposal = ctx["proposal"]
    return RECHECK_TEMPLATE.format(
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        lat=ctx["lat"],
        lon=ctx["lon"],
        site_type=ctx["site_type"],
        period=_period(ctx),
        source_url=ctx["source_url"],
        qids=", ".join(ctx["qids"]) or "none",
        titles=", ".join(ctx["enwiki"]) or "none",
        description=" ".join(str(ctx["description"] or "(none)").split()),
        cache=cache_section(ctx),
        verdict=proposal["verdict"],
        why=proposal["why"],
        proposal=_proposal_text(proposal),
        earlier=earlier_section(earlier),
        question=QUESTIONS[proposal["verdict"]],
    )


@dataclass(frozen=True)
class Review:
    site_id: str
    verdict: str
    why: str
    quotes: tuple[dict[str, str], ...]


def parse_recheck(text: str, ctx: Mapping[str, Any]) -> Review:
    data = A.load_object(text, RECHECK_KEYS)
    if data["site_id"] != ctx["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {ctx['site_id']}")
    if data["verdict"] not in RECHECK_VERDICTS:
        raise AnswerError(f"verdict {data['verdict']!r} is not CONFIRM or REJECT")
    why = A.text_of(data["why"], "why", max_chars=600)
    quotes = A.quotes_of(data["quotes"], "quotes", minimum=1 if data["verdict"] == CONFIRM else 0)
    return Review(ctx["site_id"], data["verdict"], why, quotes)


def decide_recheck(review: Review, ctx: Mapping[str, Any], env: Env) -> Outcome:
    data: dict[str, Any] = {
        "verdict": review.verdict,
        "why": review.why,
        "proposed": ctx["proposal"]["verdict"],
        "quotes": [],
    }
    try:
        data["quotes"] = _quotes_found("quotes", review.quotes, ctx["site_id"], env.library)
    except Hold as exc:
        return Outcome(HELD, str(exc), data)
    return Outcome(DECIDED, "", data)


def recheck_spec() -> StageSpec:
    return StageSpec(
        lane=LANE,
        stage=RECHECK,
        role="adversarial",
        render=render_recheck,
        parse=parse_recheck,
        decide=decide_recheck,
        cited=lambda r, c: A.urls_of(r.quotes),
        titles=lambda r, c: set(),
        per_batch=5,
        guidance="You are not told the proposal is right. Look for the reason it is wrong.",
    )


# --------------------------------------------------------------------------------------- the result
FINAL_KEEP, FINAL_CONFIRMED = "keep", "confirmed"
FINAL_REJECTED, FINAL_WAITING, FINAL_HELD = "rejected", "waiting-for-recheck", "held"


def final_state(
    web: Mapping[str, Mapping[str, Any]], recheck: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Where every asked site stands: `keep` (decided KEEP), `confirmed` (decided non-KEEP verdict
    that the re-check confirmed), `rejected` (re-check decided REJECT), `waiting-for-recheck`, or
    `held` (a web answer still held after the rounds). Sorted by site."""
    out = []
    for sid, decision in sorted(web.items()):
        if decision["status"] != DECIDED:
            state, verdict = FINAL_HELD, None
        else:
            verdict = decision["data"]["verdict"]
            second = recheck.get(sid)
            if verdict == KEEP:
                state = FINAL_KEEP
            elif second is None or second["status"] != DECIDED:
                state = FINAL_WAITING
            elif second["data"]["verdict"] == CONFIRM:
                state = FINAL_CONFIRMED
            else:
                state = FINAL_REJECTED
        out.append({"site_id": sid, "verdict": verdict, "state": state})
    return out
