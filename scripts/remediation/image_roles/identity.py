"""D17, stage A: whose Wikidata item and Wikipedia article are these - and what do the locals call it?

The picture research routes through a site's identity: its Wikidata item names an image (P18) and a
Commons category (P373), its article has a lead image, its item is what Commons structured data
points at. A wrong link routes a picture of another place to the page (Pukara, Vilcas Huaman,
Blaskovina, Sallachy Broch and three Gyeongju "Belt" sites are known cases), and 196 of the 952 sites
have no identity at all. So before any picture is looked for, two questions go to the **web verifier**
(Sonnet 5.5, high effort, `roles.ROLES["web_verifier"]`):

* **verify** - a site whose item or article might be wrong. The deterministic flags are the item's
  point more than 10 km from the site's point, or an English label (and aliases) that shares no word
  with the site's name (`verify_flags`); the item comes from `site_external_ids` through the entity
  store, never from WD1's older harvest. Batches of five sites.
* **research** - a site with no item and no article, and a site the first search found no file for
  under its curated name: find the item, the article, the Commons category and the local names, with
  the URL of every claim. Batches of four.

The prompts tell the agent to read the site's Wikipedia text from the shared cache first
(`output/remediation/final-2026-10-08/wiki_cache/`) and to fetch anything else live - a few requests,
a 403 or 429 is never a finding. Nothing here writes the database: the answer feeds the second search
pass (`merge_identity`), and an item the research found is the identity workstream's to write (D13).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from bcases.collect import claims_record  # noqa: E402
from identity import common as IC  # noqa: E402
from identity.entities import en_aliases  # noqa: E402

from image_roles import stage as SG  # noqa: E402
from image_roles.wiki_cache import WikiCache  # noqa: E402

VERIFY_BATCH = 5
RESEARCH_BATCH = 4
#: An item whose point is farther than this from the site's point is flagged (map section 3, stage A).
MAX_POINT_KM = 10.0
MAX_LOCAL_NAMES = 8
STATUSES = ("confirmed", "wrong", "unknown")
_QID = re.compile(r"Q[1-9][0-9]*")
_HTTPS = re.compile(r"https://\S+")


def verify_flags(site: Mapping[str, Any], entity: Mapping[str, Any] | None) -> list[str]:
    """Why the site's item might be wrong; empty when nothing is flagged.

    A site without an item has nothing to verify (it goes to the research). An item the store does not
    hold is flagged as such. The two measures are the map's: the item's point (`P625`) farther than
    `MAX_POINT_KM` from the site's point, and the English label and aliases sharing no significant
    word (`identity.common.tokens`) with the site's name."""
    if not site.get("qid"):
        return []
    if entity is None:
        return ["the item is in neither the harvest nor its delta"]
    record = claims_record(entity)
    flags: list[str] = []
    point = record["p625"]
    if point is not None:
        metres = IC.metres(
            {"lat": site["lat"], "lon": site["lon"]}, {"lat": point["lat"], "lon": point["lon"]}
        )
        if metres / 1000.0 > MAX_POINT_KM:
            flags.append(f"the item's point is {metres / 1000.0:.1f} km from the site's point")
    names = [record["en_label"] or "", *en_aliases(entity)]
    wanted = IC.tokens(str(site["name"]))
    if wanted and not any(IC.tokens(n) & wanted for n in names if n):
        flags.append(f"the item's label {record['en_label']!r} shares no word with the name")
    return flags


def verify_population(sites: Sequence[Mapping[str, Any]], entities: Any) -> list[dict[str, Any]]:
    """The sites to verify, each with its flags and the item's label and point."""
    out = []
    for site in sites:
        if not site.get("qid") or site.get("qid_conflict"):
            continue
        entity, _ = entities.get(site["qid"])
        flags = verify_flags(site, entity)
        if flags:
            record = claims_record(entity) if entity is not None else {}
            out.append(
                {
                    **site,
                    "flags": flags,
                    "item_label": record.get("en_label"),
                    "item_point": record.get("p625"),
                }
            )
    return out


def research_population(
    sites: Sequence[Mapping[str, Any]], found_nothing: Sequence[str]
) -> list[Mapping[str, Any]]:
    """The sites to research: no item and no article, or a first search that found no file."""
    asked = set(found_nothing)
    return [
        s
        for s in sites
        if (not s.get("qid") and not s.get("enwiki_title")) or str(s["site_id"]) in asked
    ]


# ------------------------------------------------------------------------------------ prompts
VERIFY_PROMPT_ID = "identity-verify-v1"
RESEARCH_PROMPT_ID = "identity-research-v1"

_ANSWER = """Return JSON only, no prose:
{{"sites": {{{labels}}}}}
where every site gets {{"qid": "<its Wikidata item, Q...>" | null, "qid_status": "confirmed" | "wrong" | "unknown", "enwiki_title": "<its English Wikipedia article title>" | null, "enwiki_status": "confirmed" | "wrong" | "unknown", "commons_category": "<its Commons category, without 'Category:'>" | null, "local_names": ["<names it is called in the local language or in other well-known forms>"], "evidence": ["<one https URL for every item, article or category you name>"], "note": "<what you checked, at most 40 words>"}}.
qid_status/enwiki_status: confirmed = the link given is this site; wrong = it is another place (then give the right item/article, or null); unknown = you could not decide. A null link with status unknown is a valid answer: do not guess. Every non-null qid, enwiki_title and commons_category needs a URL in "evidence" that shows it (the Wikidata item, the article, the Commons category page). At most {max_names} local names."""

_FILES = (
    "For each site first read its cached Wikipedia text where the entry names a file (JSON with "
    "resolved_title, revid and text), then fetch what else you need live: Wikidata, Wikipedia, "
    "Commons - a few requests per site; a 403 or 429 is never a finding, say so and use another "
    "source."
)

VERIFY_PROMPT = """You verify the identity links of archaeological sites. For each site below the database holds a Wikidata item and an English Wikipedia article; a check flagged the link as possibly wrong. Decide whether each link is this site - the same monument or place, not a namesake, a modern town around it, a museum or a part of a larger complex - and, while you are there, find the site's Commons category and its local names.

{files}

{sites}

{answer}"""

RESEARCH_PROMPT = """You research the identity of archaeological sites. For each site below the database holds no (reliable) Wikidata item or English Wikipedia article, or a search on Commons found no file under its name. Find, with evidence, the site's Wikidata item, its English Wikipedia article, its Commons category and its local names (the names that Commons files, other Wikipedias and local sources use). The name in the database may be broken, foreign-language or a record of the modern town: say so in the note when it is.

{files}

{sites}

{answer}"""


def _site_block(number: int, site: Mapping[str, Any], cache: WikiCache | None, flags: bool) -> str:
    lines = [
        f"S{number}: {site['name']} ({site.get('site_type') or 'type unknown'}, "
        f"{site.get('country') or 'country unknown'}; latitude {site['lat']}, longitude {site['lon']})",
        f"  site_id: {site['site_id']}",
        f"  description: {site.get('description') or 'none'}",
        f"  database item: {site.get('qid') or 'none'}; article: {site.get('enwiki_title') or 'none'}",
    ]
    if flags:
        lines.append(f"  flagged because: {'; '.join(site['flags'])}")
        if site.get("item_label"):
            lines.append(f"  the item's English label: {site['item_label']!r}")
    page = None if cache is None else cache.page(str(site["site_id"]))
    if page is not None and cache is not None:
        row = cache.pages[str(site["site_id"])]["en"]
        file = cache.root / Path(row["file"].replace("\\", "/"))
        lines.append(f"  cached Wikipedia text: {file.resolve().as_posix()}")
    return "\n".join(lines)


def build_questions(
    sites: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    cache: WikiCache | None,
    batch_size: int | None = None,
) -> list[SG.Question]:
    """The identity questions of one mode, `verify` or `research`, batch ids `idv-NNNN`/`idr-NNNN`."""
    if mode not in ("verify", "research"):
        raise SG.StageError(f"mode {mode!r} is not 'verify' or 'research'")
    size = batch_size or (VERIFY_BATCH if mode == "verify" else RESEARCH_BATCH)
    template = VERIFY_PROMPT if mode == "verify" else RESEARCH_PROMPT
    prefix = "idv" if mode == "verify" else "idr"
    questions = []
    for start in range(0, len(sites), size):
        chunk = sites[start : start + size]
        batch_id = f"{prefix}-{start // size + 1:04d}"
        blocks = [
            _site_block(n, site, cache, flags=mode == "verify") for n, site in enumerate(chunk, 1)
        ]
        labels = ", ".join(f'"{site["site_id"]}": "..."' for site in chunk)
        prompt = template.format(
            files=_FILES,
            sites="\n\n".join(blocks),
            answer=_ANSWER.format(labels=labels, max_names=MAX_LOCAL_NAMES),
        )
        meta = {
            "mode": mode,
            "sites": [
                {
                    "site_id": str(s["site_id"]),
                    "qid": s.get("qid"),
                    "enwiki_title": s.get("enwiki_title"),
                }
                for s in chunk
            ],
        }
        questions.append(SG.Question(batch_id, batch_id, prompt, meta))
    return questions


# ------------------------------------------------------------------------------------ answers
SITE_KEYS = frozenset(
    {
        "qid",
        "qid_status",
        "enwiki_title",
        "enwiki_status",
        "commons_category",
        "local_names",
        "evidence",
        "note",
    }
)


def _optional_text(value: Any, key: str) -> str | None:
    if value is None:
        return None
    return SG.text_field(value, key, longest=200)


def _parse_site(site_id: str, given: Mapping[str, Any], asked: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(given, dict) or set(given) != SITE_KEYS:
        raise SG.AnswerShapeError(f"{site_id}: must carry exactly {sorted(SITE_KEYS)}")
    for key in ("qid_status", "enwiki_status"):
        if given[key] not in STATUSES:
            raise SG.AnswerShapeError(
                f"{site_id}: {key} {given[key]!r} is not one of {list(STATUSES)}"
            )
    qid = given["qid"]
    if qid is not None and not (isinstance(qid, str) and _QID.fullmatch(qid)):
        raise SG.AnswerShapeError(f"{site_id}: qid {qid!r} is no Wikidata item id")
    title = _optional_text(given["enwiki_title"], f"{site_id} enwiki_title")
    category = _optional_text(given["commons_category"], f"{site_id} commons_category")
    if category is not None and category.lower().startswith("category:"):
        raise SG.AnswerShapeError(f"{site_id}: commons_category is named without 'Category:'")
    names = given["local_names"]
    if (
        not isinstance(names, list)
        or len(names) > MAX_LOCAL_NAMES
        or not all(isinstance(n, str) and n.strip() and len(n) <= 120 for n in names)
    ):
        raise SG.AnswerShapeError(
            f"{site_id}: local_names must be a list of at most {MAX_LOCAL_NAMES} names"
        )
    evidence = given["evidence"]
    if not isinstance(evidence, list) or not all(
        isinstance(u, str) and _HTTPS.fullmatch(u) for u in evidence
    ):
        raise SG.AnswerShapeError(f"{site_id}: evidence must be a list of https URLs")
    if (qid or title or category) and not evidence:
        raise SG.AnswerShapeError(f"{site_id}: an item, article or category needs an evidence URL")
    if given["qid_status"] == "confirmed" and qid != asked["qid"]:
        raise SG.AnswerShapeError(f"{site_id}: 'confirmed' must name the item the database holds")
    if given["enwiki_status"] == "confirmed" and title != asked["enwiki_title"]:
        raise SG.AnswerShapeError(
            f"{site_id}: 'confirmed' must name the article the database holds"
        )
    if given["qid_status"] == "wrong" and qid == asked["qid"]:
        raise SG.AnswerShapeError(f"{site_id}: a 'wrong' item is replaced by another or by null")
    return {
        "qid": qid,
        "qid_status": given["qid_status"],
        "enwiki_title": title,
        "enwiki_status": given["enwiki_status"],
        "commons_category": category,
        "local_names": [n.strip() for n in names],
        "evidence": list(evidence),
        "note": SG.text_field(given["note"], f"{site_id} note"),
    }


def parse(meta: Mapping[str, Any], text: str) -> dict[str, Any]:
    """`{"sites": {site id: the verdict on its identity}}` for exactly the question's sites."""
    data = SG.json_object(text, frozenset({"sites"}))
    asked = {s["site_id"]: s for s in meta["sites"]}
    given = data["sites"]
    if not isinstance(given, dict) or set(given) != set(asked):
        raise SG.AnswerShapeError(f"'sites' must answer exactly {sorted(asked)}")
    return {"sites": {sid: _parse_site(sid, given[sid], asked[sid]) for sid in asked}}


VERIFY_SPEC = SG.Spec(
    name="identity-verify",
    role="web_verifier",
    prompt_id=VERIFY_PROMPT_ID,
    questions_file="QUESTIONS_IDENTITY_VERIFY.jsonl",
    export_file="EXPORT_IDENTITY_VERIFY.json",
    result_file="IDENTITY_VERIFY.jsonl",
    parse=parse,
    what="are the database's Wikidata item and Wikipedia article this site?",
    web=True,
)
RESEARCH_SPEC = SG.Spec(
    name="identity-research",
    role="web_verifier",
    prompt_id=RESEARCH_PROMPT_ID,
    questions_file="QUESTIONS_IDENTITY_RESEARCH.jsonl",
    export_file="EXPORT_IDENTITY_RESEARCH.json",
    result_file="IDENTITY_RESEARCH.jsonl",
    parse=parse,
    what="find the site's Wikidata item, article, Commons category and local names",
    web=True,
)


# ------------------------------------------------------------------------------------- merging
def identity_rows(results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """`{site id: the verdict}` over every imported identity answer; a site answered twice is
    refused (a verify and a research answer for one site are two stages, not two truths)."""
    out: dict[str, dict[str, Any]] = {}
    for row in results:
        for site_id, verdict in row["sites"].items():
            if site_id in out:
                raise SG.StageError(f"{site_id}: the identity stage answered this site twice")
            out[site_id] = {**verdict, "answered_by": row["answered_by"], "model": row["model"]}
    return out


def _resolved(held: str | None, status: str, proposed: str | None) -> str | None:
    """The link a site is routed through after an answer: the answer's when it says the database's
    is wrong (possibly none), the one it proposes with evidence when it could not decide, else the
    database's. A `confirmed` link proposes the database's own (the parser requires it)."""
    if status == "wrong":
        return proposed
    return proposed if proposed is not None else held


def merge_identity(
    sites: Sequence[Mapping[str, Any]], answers: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The population with the identity answers applied, for the second search pass.

    The item and the article follow `_resolved`; the Commons category and the local names are added.
    `identity_changed` says the item or article differs from the database's - writing those is the
    identity workstream's (D13), not this lane's."""
    out = []
    for site in sites:
        merged = dict(site)
        verdict = answers.get(str(site["site_id"]))
        if verdict is not None:
            merged["qid"] = _resolved(site.get("qid"), verdict["qid_status"], verdict["qid"])
            merged["enwiki_title"] = _resolved(
                site.get("enwiki_title"), verdict["enwiki_status"], verdict["enwiki_title"]
            )
            merged["commons_category"] = verdict["commons_category"]
            merged["local_names"] = verdict["local_names"]
            merged["identity_evidence"] = verdict["evidence"]
            merged["identity_changed"] = (merged["qid"], merged["enwiki_title"]) != (
                site.get("qid"),
                site.get("enwiki_title"),
            )
        out.append(merged)
    return out
