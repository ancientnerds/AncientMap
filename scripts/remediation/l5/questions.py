"""The L5 question - one per site - and the exact shape of its answer.

The prompt is a pure function of the site's production read (`population.READ.json`), so the
import can rebuild it and refuse an answer to any other prompt (`opus_handoff.read_answer`). The
rules it states are the owner's (HUMAN_ONLY_DECISIONS_2026-09-26, B1-L, B1-N, O6): this site is the
place its name designates at its stored point (a description or source about another place is
wrong, and rewritten by other lanes); a link names exactly this site - no type, no container, no
sibling - or it goes, and an item a duplicate row shares is kept when it names this site; a
replacement needs a source that names this very site, a rename takes a name of the site's own item
or article; a quote is verbatim text of a cited page, found by the machine.

`parse` checks the shape and the rules the answer itself can break (nothing is fetched); `decide.py`
checks what needs the pages and Wikipedia.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

_HERE = Path(__file__).resolve()
for _root in (_HERE.parents[3], _HERE.parents[1]):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from opus_audit import quotes as Q  # noqa: E402

from pipeline.lyra.prospector.wiki import CONTROL_RE, enwiki_title_from_url  # noqa: E402

STAGE = "l5"
ENWIKI = "https://en.wikipedia.org/wiki/"
ENTITY_DATA = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
QID_RE = re.compile(r"Q[1-9][0-9]*")
NAME_CHARS = 500

LINK_VERDICTS = ("KEEP", "REPLACE", "REMOVE")
URL_VERDICTS = ("KEEP", "REPLACE", "CLEAR")
NAME_VERDICTS = ("KEEP", "RENAME")
VERDICT_KEYS = frozenset({"verdict", "value", "why", "quotes"})


class AnswerError(ValueError):
    """The answer is not in its exact shape, or breaks a rule it can break on its own."""


@dataclass(frozen=True)
class Cell:
    """One verdict of an answer: what happens to one stored value, why, and its quotes."""

    verdict: str
    value: str | None
    why: str
    quotes: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Answer:
    site_id: str
    qid: Cell
    title: Cell
    source_url: Cell
    name: Cell | None


def article_url(title: str) -> str:
    """The English Wikipedia URL of a title, as the site's own `source_url` values spell it."""
    return ENWIKI + url_quote(title.replace(" ", "_"), safe="()',-._~:!*;@$")


def stored(site: Mapping[str, Any], kind: str) -> str:
    """The one stored value of an external-id kind (the export asks only sites with one each)."""
    values = [e["value"] for e in site["ext"] if e["kind"] == kind]
    if len(values) != 1:
        raise AnswerError(f"{site['site_id']}: {len(values)} {kind} rows - not a question L5 asks")
    return str(values[0])


def must_decide_source_url(site: Mapping[str, Any], qid: Cell, title: Cell) -> bool:
    """Both links go and the source_url is an English Wikipedia article: the daily refresh
    (`refresh_site_external_ids`) would resolve it and write the removed links back."""
    return (
        qid.verdict == "REMOVE"
        and title.verdict == "REMOVE"
        and str(site["source_url"] or "").startswith(ENWIKI)
    )


# ------------------------------------------------------------------------------------ the prompt
TEMPLATE = """You are an Opus reader of lane L5 of the Ancient Nerds sites remediation. One curated \
site of the map; decide its Wikidata item and its English Wikipedia article{name_part}. Research on \
the open web; read the pages you cite.

THE SITE, as the database holds it (read {read_at})
  id:           {site_id}
  name:         {name}
  country:      {country}
  point:        {lat}, {lon}
  type, period: {site_type}; {period}
  source_url:   {source_url}
  description (first {chars} characters):
{description}

ITS LINKS NOW
  wikidata_qid: {qid}  (https://www.wikidata.org/wiki/{qid})
  enwiki_title: {title}  ({title_url})
{sharers}
WHY THIS SITE IS ASKED
{why}
{earlier}
THE RULES (the owner's decisions B1-L, B1-N and O6 of 2026-09-26)
1. THIS site is the place the record's name designates at its stored point; where the description \
or source_url describe another place, they are wrong here (other lanes rewrite them). A link must \
name exactly this site: the item or article is about this site itself - not a type or genus \
("dolmen", "milecastle", "Asclepeion"), not a container (the town, park, island, region or larger \
complex it lies in), not a sibling (another monument of the same complex), not a namesake \
elsewhere. A record that is itself a group ("Dolmens of Sardinia") has no item of its own unless an \
item is exactly that group. Another curated site carrying the same item does not make it wrong: \
if both records are this one site (a duplicate), KEEP the item - which record stays is decided \
elsewhere.
2. KEEP a link that names exactly this site.
3. REPLACE a wrong link only with one that names exactly this site:
   - wikidata_qid: an item whose label, alias or description names this site. Cite \
https://www.wikidata.org/wiki/Special:EntityData/<QID>.json and quote from it verbatim (for \
example the label). The machine reads the item's coordinates there: a replacement more than 1 km \
from the stored point (or from its English article's coordinates) is not written.
   - enwiki_title: the exact title of an English Wikipedia article about exactly this site - not a \
redirect, not a section of another article. Cite https://en.wikipedia.org/wiki/<Title> and quote a \
sentence of it that names the site. The article's Wikidata item must be the item you keep or \
replace with.
4. Otherwise REMOVE the wrong link. A site with no item or article of its own keeps none.
5. source_url is KEEP - unless you REMOVE both links and the source_url is an English Wikipedia \
article: the daily refresh would derive the removed links from it again. Then REPLACE it with a \
page about exactly this site that is not an English Wikipedia article (quote that page), or CLEAR \
it (quote what shows the stored page is not about this site).
{name_rule}{quote_rule}. Every verdict except a KEEP of source_url{name_keep} carries at least one quote: \
verbatim text (whitespace may differ) of a page you cite by its URL. The machine fetches every \
cited URL and does not count a verdict whose quote it cannot find there. Never cite \
ancientnerds.com.

ANSWER with only this JSON object:
{{
 "site_id": "{site_id}",
 "wikidata_qid": {{"verdict": "KEEP | REPLACE | REMOVE", "value": null or "Q...", \
"why": "...", "quotes": [{{"source": "https://...", "quote": "..."}}]}},
 "enwiki_title": {{"verdict": "KEEP | REPLACE | REMOVE", "value": null or "Title", \
"why": "...", "quotes": [...]}},
 "source_url": {{"verdict": "KEEP | REPLACE | CLEAR", "value": null or "https://...", \
"why": "...", "quotes": [...]}}{name_json}
}}
"value" is the new value for REPLACE{rename}, and null otherwise.
"""

NAME_RULE = """6. The name: KEEP it unless this site's own item or article names it otherwise and \
the stored name is not a name of this site. RENAME only to the English label or an English alias of \
the item you keep or replace with, or to the title of the article you keep or replace with (a \
bracketed qualifier such as "(Mesoamerican site)" may be left off) - the machine checks the new \
name against that item and article - and quote a page with the new name in the quote. KEEP the \
name when another curated site carries the same item. Another language, a transliteration or a \
descriptive form of a right name is no reason to rename.
"""


def prompt(
    site: Mapping[str, Any],
    member: Mapping[str, Any],
    read: Mapping[str, Any],
    earlier: str | None = None,
) -> str:
    """The exact question for one site. Pure: the production read, the population record and, for
    a re-ask, why the earlier answer was held (`decide.py`)."""
    qid, title = stored(site, "wikidata_qid"), stored(site, "enwiki_title")
    others = [s for s in read["sharers"].get(qid, []) if str(s["site_id"]) != str(site["site_id"])]
    sharers = "".join(
        f"  also carried by the curated site {s['name']} ({s['site_id']}, point {s['lat']}, "
        f"{s['lon']}{', retired' if s['scope_status'] == 'retired' else ''})\n"
        for s in others
    )
    period = (
        f"{site['period_start']} ({site['period_name']})"
        if site["period_start"] is not None
        else "no date"
    )
    ask_name = bool(member["ask_name"])
    description = str(site["description"] or "(none)")
    return TEMPLATE.format(
        name_part=", and its name" if ask_name else "",
        read_at=read["read_at"],
        site_id=site["site_id"],
        name=site["name"],
        country=site["country"],
        lat=site["lat"],
        lon=site["lon"],
        site_type=site["site_type"],
        period=period,
        source_url=site["source_url"],
        chars=len(description),
        description="    " + description.replace("\n", "\n    "),
        qid=qid,
        title=title,
        title_url=article_url(title),
        sharers=sharers,
        why="\n".join(f"  - {line}" for line in member["why"]),
        earlier=(
            ""
            if earlier is None
            else f"\nAN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  {earlier}\n"
        ),
        name_rule=NAME_RULE if ask_name else "",
        quote_rule=7 if ask_name else 6,
        name_keep=" and of the name" if ask_name else "",
        name_json=(
            ',\n "name": {"verdict": "KEEP | RENAME", "value": null or "the new name", '
            '"why": "...", "quotes": [...]}'
            if ask_name
            else ""
        ),
        rename=" or RENAME" if ask_name else "",
    )


# ------------------------------------------------------------------------------------ the answer
def _normal(text: str) -> str:
    return Q.normalise(text).casefold()


def _cell(data: Any, key: str, verdicts: tuple[str, ...]) -> Cell:
    if not isinstance(data, dict) or set(data) != VERDICT_KEYS:
        raise AnswerError(f"{key}: not an object with exactly {sorted(VERDICT_KEYS)}")
    verdict, value, why, quotes = data["verdict"], data["value"], data["why"], data["quotes"]
    if verdict not in verdicts:
        raise AnswerError(f"{key}: verdict {verdict!r} is not one of {', '.join(verdicts)}")
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise AnswerError(f"{key}: value is neither null nor a non-empty string")
    if not isinstance(why, str) or not why.strip():
        raise AnswerError(f"{key}: why is empty")
    if not isinstance(quotes, list):
        raise AnswerError(f"{key}: quotes is not a list")
    checked = []
    for q in quotes:
        if not isinstance(q, dict) or set(q) != {"source", "quote"}:
            raise AnswerError(f"{key}: a quote is not {{source, quote}}: {q!r}")
        if not all(isinstance(q[k], str) and q[k].strip() for k in ("source", "quote")):
            raise AnswerError(f"{key}: a quote needs a source and a text")
        if not Q.is_url(q["source"]):
            raise AnswerError(
                f"{key}: a quote's source must be the URL of the page: {q['source']!r}"
            )
        refused = Q.not_fetchable(q["source"])
        if refused:
            raise AnswerError(f"{key}: {q['source']} is never fetched here ({refused})")
        checked.append({"source": q["source"], "quote": q["quote"]})
    return Cell(verdict, value, why, tuple(checked))


def _cites(cell: Cell, url: str) -> bool:
    return any(Q.canonical_url(q["source"])[0] == url for q in cell.quotes)


def parse(text: str, site: Mapping[str, Any], member: Mapping[str, Any]) -> Answer:
    """The answer to one site's question, in its exact shape, or `AnswerError`. Nothing fetched."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerError(f"not JSON: {exc}") from exc
    keys = {"site_id", "wikidata_qid", "enwiki_title", "source_url"}
    if member["ask_name"]:
        keys.add("name")
    if not isinstance(data, dict) or set(data) != keys:
        got = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"the answer carries {got}, not {sorted(keys)}")
    if data["site_id"] != site["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {site['site_id']}")
    qid = _cell(data["wikidata_qid"], "wikidata_qid", LINK_VERDICTS)
    title = _cell(data["enwiki_title"], "enwiki_title", LINK_VERDICTS)
    url = _cell(data["source_url"], "source_url", URL_VERDICTS)
    name = _cell(data["name"], "name", NAME_VERDICTS) if member["ask_name"] else None

    for key, cell in (("wikidata_qid", qid), ("enwiki_title", title)):
        if (cell.value is None) == (cell.verdict == "REPLACE"):
            raise AnswerError(f"{key}: a value goes with REPLACE and only with it")
        if not cell.quotes:
            raise AnswerError(f"{key}: a {cell.verdict} needs at least one quote")
        if cell.value is not None and cell.value == stored(site, key):
            raise AnswerError(f"{key}: {cell.value!r} is the stored value - that is KEEP")
    if qid.value is not None:
        if not QID_RE.fullmatch(qid.value):
            raise AnswerError(f"wikidata_qid: {qid.value!r} is not an item id")
        if not _cites(qid, ENTITY_DATA.format(qid.value)):
            raise AnswerError(f"wikidata_qid: a REPLACE cites {ENTITY_DATA.format(qid.value)}")
    if title.value is not None:
        if CONTROL_RE.search(title.value) or "#" in title.value or "|" in title.value:
            raise AnswerError(f"enwiki_title: {title.value!r} is not an article title")
        if not any(enwiki_title_from_url(q["source"]) == title.value for q in title.quotes):
            raise AnswerError(f"enwiki_title: a REPLACE cites {article_url(title.value)}")
    if title.verdict != "REMOVE" and qid.verdict == "REMOVE":
        raise AnswerError(
            "an article about exactly this site has a Wikidata item: keep or replace the item, "
            "or remove the article too"
        )

    if must_decide_source_url(site, qid, title):
        if url.verdict == "KEEP":
            raise AnswerError(
                "source_url: both links go and the source_url is an English Wikipedia article - "
                "REPLACE or CLEAR it (rule 5)"
            )
        if not url.quotes:
            raise AnswerError(f"source_url: a {url.verdict} needs at least one quote")
        if url.verdict == "CLEAR" and url.value is not None:
            raise AnswerError("source_url: CLEAR carries no value")
        if url.verdict == "REPLACE":
            if url.value is None or not Q.is_url(url.value) or CONTROL_RE.search(url.value):
                raise AnswerError("source_url: a REPLACE carries the new URL")
            if url.value.startswith(ENWIKI) or Q.not_fetchable(url.value):
                raise AnswerError(
                    f"source_url: {url.value} is an English Wikipedia article or not fetchable"
                )
            if not _cites(url, Q.canonical_url(url.value)[0]):
                raise AnswerError("source_url: a REPLACE quotes the new page")
    elif url.verdict != "KEEP" or url.value is not None:
        raise AnswerError("source_url: KEEP with value null unless both links go (rule 5)")

    if name is not None:
        if name.verdict == "KEEP" and name.value is not None:
            raise AnswerError("name: KEEP carries no value")
        if name.verdict == "RENAME":
            new = name.value
            if new is None or new != new.strip() or len(new) > NAME_CHARS or CONTROL_RE.search(new):
                raise AnswerError(f"name: {new!r} is not a name (trimmed, {NAME_CHARS} characters)")
            if new == site["name"]:
                raise AnswerError("name: the new name is the stored name - that is KEEP")
            if not name.quotes or not any(_normal(new) in _normal(q["quote"]) for q in name.quotes):
                raise AnswerError("name: a RENAME quotes a page with the new name in the quote")
    return Answer(site["site_id"], qid, title, url, name)
