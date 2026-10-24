"""D57 step 2: the research handoff - what each new site's row will hold, quoted from its sources.

No model is called here. Every candidate (`candidates.chosen`) is one question in the opus_handoff
format (`opus_handoff.py`: `<handoff>/<batch>/MANIFEST.jsonl`, `<batch>/insert-research/<QID>.prompt.txt`,
the answer beside it), answered by an agent of the `field_researcher` role (`roles.ROLES`: Sonnet 5.5
high, calibrated on the WD1/WD3 rounds and the BP set) and recorded with `opus_handoff.py answer
--role field_researcher`. The orchestrator's cycle (`R=output/remediation/insert_site/<run>`,
`H=output/remediation/handoff/insert-<run>`):

    $I export --run $R --handoff $H-r0           one question per candidate, batches of `BATCH_SIZE`
    $I brief --run $R --handoff $H-r0 --batch-id B      the instruction of batch B's agent
    $I check-answer --run $R --handoff $H-r0 --batch-id B --label QID --text-file F
                                                 the answer's shape and every page-free check
    opus_handoff.py validate --dir $H-r0         every answer in, in shape, by a Claude model
    $I import --run $R                           parse, fetch every quoted page once, quote-check,
                                                 decide: ATTEMPTS.jsonl, DECISIONS.jsonl, REASK.json
    $I export-reask --run $R --handoff $H-r1     the fields without a counted answer, to new agents
                                                 (at most `MAX_ROUND` re-asks; answer, validate, import)

(`I="./.venv/Scripts/python.exe scripts/remediation/insert_site/run.py research"`.)

**The answer format is the fields lanes' own** (`fields/answers.py` under the `recheck` rule of lane
wd5: one quote from one source suffices, never ancientnerds.com or a Wikipedia mirror, a period word
is a date, a BP age is read, the quote may stay in its page's language), for `coordinates`,
`period_start`, `site_type` and `source_url`, every check of that module applied unchanged. The
"stored" value of those checks is the **seed** the candidate list read from Wikidata (the item's
point, its English article's URL; no seed for the type and the start), so `keep` confirms a seed with
a quote and `replace` gives another sourced value. Two fields a new row needs on top, in the same
block shape (`decision`, `value`, `quotes`, `reasoning`) and decided the same way:

* **name** - the English name the site is known by. A quote must hold it; it carries none of the D23
  name defects (`identity/names_triage.defects_of`: no comma qualifier, no parenthesis, no foreign
  prefix, Latin script, at most 40 characters; a digit is allowed - "KV62");
* **country** - one spelling the T05 census would not flag (`census/tests/t05_country_values`: a key
  of the frontend's flag map or of `NAME_TO_ISO`, not a hand-listed split such as `USA`), a part of
  the United Kingdom by its region (B9: `England`, `Scotland`, `Wales`, `Northern Ireland`), and a
  quote that names it. Whether the point lies in it is the plan's check (`plan.py`, D19's coast rule).

and `description_sources`: two to eight verbatim quotes about what the site is, for the description
lane that writes the page's text later (the insert writes no description). They are checked like
every other quote and stored in the row's `raw_data._insert_provenance`.

**A field counts** when its answer passes every page-free check and each of its quotes is found
verbatim in its page as fetched once by this run (`opus_audit/quotes.py`), and a `source_url` value
is a served page of its own (`fields/handoff.value_page`). A field without a counted answer is asked
again, of a new agent, at most `MAX_ROUND` times; then it is **exhausted** - `held` when its last
answer failed only on pages the checker could not read. What the plan makes of an exhausted or an
`unresolved` field is the plan's (a site without a sourced point, name, country or page is not
inserted; a start nobody can source is written `Undated`).
"""

from __future__ import annotations

import functools
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
import web_rules as WR  # noqa: E402
from acceptance.answers import AnswerError, _quotes, load_object  # noqa: E402
from acceptance.questions import RESEARCH, definitions  # noqa: E402
from bcases.classify import fold  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from census.tests import t05_country_values as T05  # noqa: E402 - the country vocabulary
from fields import answers as A  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import harvest as FH  # noqa: E402
from fields import rule as R  # noqa: E402
from identity.names_triage import defects_of  # noqa: E402 - D23's name defects
from mechanical.lane import UK_PARTS  # noqa: E402 - B9: the United Kingdom by its parts
from opus_audit import quotes as Q  # noqa: E402
from phase4.route_stage import wikipedia_title  # noqa: E402

from insert_site import candidates as C  # noqa: E402
from pipeline.utils.country_lookup import country_name_variants  # noqa: E402

STAGE = "insert-research"
ROLE = "field_researcher"
MODEL = RO.role(ROLE).model
#: The fields lanes' rule the four shared fields are parsed under: lane wd5's (one source, the
#: forbidden families, a period word, BP ages, every language). Its role is `ROLE`
#: (`fields/handoff.RULE_ROLE`), so an answer recorded under another role is refused at import.
RULE = R.RECHECK
SHARED_FIELDS = ("coordinates", "site_type", "period_start", "source_url")
OWN_FIELDS = ("name", "country")
FIELDS = ("name", "coordinates", "country", "site_type", "period_start", "source_url")
SOURCES = "description_sources"
MIN_SOURCES, MAX_SOURCES = 2, 8
#: What a question asks: its fields, and the description's sources (a pseudo-field of its own).
ASKABLE = (*FIELDS, SOURCES)
BATCH_SIZE = 6
MAX_ROUND = 2
#: A digit is no defect of a site's name here: "KV62" is the tomb's own designation (D23 lists the
#: digit for a numbered part, "Tumulus 3", which a new site never is).
ALLOWED_DEFECTS = frozenset({"digit"})
UNITED_KINGDOM = "United Kingdom"

ROUNDS_FILE = "ROUNDS.jsonl"
ATTEMPTS_FILE = "ATTEMPTS.jsonl"
DECISIONS_FILE = "DECISIONS.jsonl"
REASK_FILE = "REASK.json"
PAGES_DIR = "pages"
PAGES_INDEX = "PAGES.jsonl"
COUNTED, EXHAUSTED, HELD = "counted", "exhausted", "held"


class ResearchError(ValueError):
    """The step must not run on this state. Nothing was written by it."""


# ------------------------------------------------------------------------------------ the question
def question_line(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """The candidate as `fields/answers.check_shape` reads a site: its name and each field's
    "stored" value - the seed the candidate list read (no seed for the type and the start)."""
    point = candidate["p625"]
    return {
        "site_id": candidate["qid"],
        "name": candidate["label_en"],
        "fields": {
            "name": {"stored": candidate["label_en"]},
            "coordinates": {"stored": f"{point['lat']}, {point['lon']}"},
            "country": {"stored": None},
            "site_type": {"stored": None},
            "period_start": {"stored": None},
            "source_url": {"stored": candidate["enwiki_url"]},
        },
    }


_UNRESOLVED_COORDINATES = (
    "- unresolved: no source can be quoted for the site's point. The stored point stays - "
    "it cannot be emptied, every site stays on the map - and the site goes to the owner's "
    "list.\n"
)
#: What `unresolved` does in this lane, per field: said to the agent, so an answer is never given
#: for the sake of its consequence (the wd5 brief's rule, `fields/handoff._WD5_UNRESOLVED`).
UNRESOLVED_HERE = {
    "coordinates": (
        "- unresolved: no source can be quoted for the site's point. A site without a sourced "
        "point is not added in this lane: it goes to the owner's list.\n"
    ),
    "site_type": (
        "What unresolved does in this lane: the new site is added without a type and goes to the "
        "owner's list."
    ),
    "period_start": (
        'What unresolved does in this lane: the new site is added as "Undated", with no year.'
    ),
    "source_url": (
        "What unresolved does in this lane: a site without a sourced page is not added; it goes to "
        "the owner's list."
    ),
}

#: The four shared fields' rules: lane WD4's own texts, with wd5's readers of BP ages and of other
#: languages, and this lane's `unresolved` - every other sentence is the fields lanes' string.
FIELD_RULES = {
    "coordinates": HO._swap(
        HO.FIELD_RULES_WD4["coordinates"], _UNRESOLVED_COORDINATES, UNRESOLVED_HERE["coordinates"]
    )
    + HO._WD5_POINTS_ANY_LANGUAGE,
    "period_start": HO._swap(
        HO.FIELD_RULES_WD5["period_start"],
        HO._WD5_UNRESOLVED_PERIOD,
        "- unresolved: no source dates the start.\n",
    )
    + "\n"
    + UNRESOLVED_HERE["period_start"],
    "site_type": HO.FIELD_RULES_WD4["site_type"] + "\n" + UNRESOLVED_HERE["site_type"],
    "source_url": HO.FIELD_RULES_WD4["source_url"] + "\n" + UNRESOLVED_HERE["source_url"],
    "name": (
        "name is the English name the site is known by - the one a visitor searches for and the "
        "site's page is titled with. Not a translation of your own, not the name of the modern "
        "town, park or museum when the ancient site has a name of its own.\n"
        "- keep: a source names the site by the stored name. value = the stored name.\n"
        "- replace: the site is known by another English name. value = that name.\n"
        "- unresolved: no source names the site in English. A site without a name is not added.\n"
        "A quote must hold the name as you give it. The name carries no comma qualifier "
        '("Memphis, Egypt" is "Memphis"), no parenthesis, no foreign word for its kind '
        '("Templo", "Castello"), is written in the Latin script and has at most 40 characters.'
    ),
    "country": (
        "country is the present-day country the site lies in, spelled as this database spells "
        "countries: one of the spellings listed below, or - for a country no curated site has yet "
        "- its short English name. A site in the United Kingdom is spelled by its part: England, "
        "Scotland, Wales or Northern Ireland.\n"
        "- replace: a source places the site in the country (there is no stored country). value = "
        "the country.\n"
        "- unresolved: no source names the country. A site without a country has no page and is "
        "not added.\n"
        "A quote must name the country (any common English form of it). The machine also checks "
        "that the site's point lies in it."
    ),
}

SOURCES_RULE = (
    "description_sources are what the page's text will be written from later: two to eight "
    "verbatim quotes, each one contiguous passage of a page about this very site, that together "
    "say what the site is, where it is, when it was built or used and by whom. Prefer at least one "
    "page outside the English Wikipedia article (a heritage register, UNESCO, a museum, a "
    "university, an excavation report): the article is one witness. Never ancientnerds.com, an "
    "AI-written content farm or a Wikipedia mirror."
)

INTRO = (
    "You are a researcher of the D57 insert lane of a curated database of ancient sites. This "
    "question is about ONE site that is NOT in the database yet: owner decision D57 (2026-10-24) "
    "adds it as a curated site with a page of its own. Research each field listed below on its "
    "own and decide it from a source you quote. A value is written only with the quote you give "
    "for it, and every quote is checked by machine against its page."
)

STORED_NOTE = (
    'Each field\'s rules speak of a "stored" value. For this new site that is the seed this lane '
    "read from Wikidata, shown with each field - not a value anybody checked. keep confirms the "
    "seed with a quote; replace gives another value with a quote; a field without a seed has no "
    "keep."
)

RETRY_NOTE = (
    "An earlier answer to this field did not count: {why}. Answer it again from a source the "
    "checker can read - or answer unresolved when none can be quoted."
)

RESEARCH_TEXT = (
    "## How to research\n"
    "\n"
    "Start from the site's Wikidata item and its English Wikipedia article (above), then the same "
    "article in other languages and the item's statements, then reputable sources: heritage "
    "agencies and national monument registers, UNESCO, museums, universities, journals and "
    "excavation reports, Pleiades, established encyclopedias.\n"
    "\n"
    "- Never use ancientnerds.com, AI-written content farms, travel blogs that restate Wikipedia, "
    "or Wikipedia mirrors (Wikiwand, DBpedia and the like): a quote from one of them is refused.\n"
    "- Before any answer, make sure the source is about this very site: its name AND its place - "
    "not the modern town, the national park or the museum of the same name.\n"
    "- One source suffices. One Wikipedia article (in any language), its Wikidata item and "
    "Wikimedia Commons are ONE source; so are all pages of one website. One verbatim quote from "
    "one page is enough when it states the value itself.\n"
    "- A field no source supports: answer unresolved (the field's rules say what that does). That "
    "is an answer, not a failure - do not stretch a source to fill a field.\n"
    "\n"
) + RESEARCH[RESEARCH.index("## Quotes are checked by machine") :]

ANSWER_FORMAT = (
    "## Your answer\n"
    "\n"
    'One JSON object and nothing else: {{"fields": {{...}}{sources_key}}}. "fields" has exactly '
    "these keys: {keys}. Each is\n"
    '{{"decision": "...", "value": "..." or null, "period_name": "..." (period_start only), '
    '"quotes": [{{"url": "https://...", "quote": "verbatim text"}}], "reasoning": "..."}}\n'
    "keep and replace carry the value and at least one quote; unresolved carries value null and "
    "quotes []. The reasoning says, in a sentence or two, what the source says and why that "
    "decides it. A period_start that rests on a period word carries period_name instead of a value "
    '(period_name: "iron age", value: null) - the year is read from the vocabulary, so a value '
    "beside it is refused.\n"
    "{sources_line}"
)


def accepted_spellings(vocabulary: Mapping[str, int]) -> dict[str, int]:
    """The curated spellings a new row may take: those `_check_country` accepts. A spelling the
    census flags (`USA`, a hand-listed split of `United States`) is not offered."""
    return {
        name: count
        for name, count in vocabulary.items()
        if name != UNITED_KINGDOM and _country_is_canonical(name)
    }


def _vocabulary_line(vocabulary: Mapping[str, int]) -> str:
    return "The spellings this database uses (the number of curated sites each): " + ", ".join(
        f"{name} ({count})" for name, count in sorted(accepted_spellings(vocabulary).items())
    )


def render_prompt(
    candidate: Mapping[str, Any],
    asked: Sequence[str],
    vocabulary: Mapping[str, int],
    notes: Mapping[str, str] | None = None,
) -> str:
    """The exact question for one candidate - a pure function of the candidate line, the fields
    and sources asked, the run's country vocabulary and, in a re-ask, why each field's last answer
    did not count. Import renders it again and refuses an answer to any other text."""
    notes = notes or {}
    fields = [f for f in FIELDS if f in asked]
    sources = SOURCES in asked
    if not fields and not sources:
        raise ResearchError(f"{candidate['qid']}: a question needs at least one field")
    line = question_line(candidate)
    point = candidate["p625"]
    out = [
        INTRO,
        "",
        "## The site",
        "",
        f"- Wikidata item: https://www.wikidata.org/wiki/{candidate['qid']}"
        + (
            f" (the list named {candidate['qid_asked']}, which Wikidata merged into it)"
            if candidate.get("qid_asked")
            else ""
        ),
        f"- English Wikipedia article: {candidate['enwiki_title']} - {candidate['enwiki_url']}",
        f"- the item's English label: {candidate['label_en']}",
        f"- the item's point (P625): {point['lat']}, {point['lon']}",
    ]
    if candidate.get("note"):
        out.append(
            f"- the hand review of 2026-10-08 noted (German, a lead to check, not a source): "
            f"{candidate['note']}"
        )
    if candidate.get("parent"):
        out.append(
            f"- it will be a component of the curated site {candidate['parent']['name']} "
            "(its parent): research THIS site, not its parent"
        )
    out += ["", STORED_NOTE, "", "## The fields you decide", ""]
    for field in fields:
        out.append(f"### {field}")
        out.append("")
        out.append(
            f"Stored value (the seed): {json.dumps(line['fields'][field]['stored'], ensure_ascii=False)}"
        )
        if field in notes:
            out.append(RETRY_NOTE.format(why=notes[field]))
        out.append("")
        out.append(FIELD_RULES[field])
        vocabulary_text = _vocabulary_line(vocabulary) if field == "country" else definitions(field)
        if vocabulary_text:
            out.append("")
            out.append(vocabulary_text)
        out.append("")
    if sources:
        out += [f"### {SOURCES}", ""]
        if SOURCES in notes:
            out.append(RETRY_NOTE.format(why=notes[SOURCES]))
        out += [SOURCES_RULE, ""]
    out.append(RESEARCH_TEXT)
    out.append(HO.KNOWN_FETCH_TROUBLE)
    # the politeness and the marker note of the shared web rules; the researcher's cache-first
    # sentence is not this lane's (a new site has no article in `wiki_cache/`)
    out.append(WR.POLITENESS + " " + WR.MARKER_NOTE)
    out.append("")
    out.append(
        ANSWER_FORMAT.format(
            keys=", ".join(f'"{f}"' for f in fields) or "none",
            sources_key=f', "{SOURCES}": [...]' if sources else "",
            sources_line=(
                f'"{SOURCES}" is a list of {MIN_SOURCES} to {MAX_SOURCES} '
                '{"url": "https://...", "quote": "verbatim text"} objects.\n'
                if sources
                else ""
            ),
        )
    )
    return "\n".join(out)


# ------------------------------------------------------------------------------------ the answers
def _names(quote: str, phrase: str) -> bool:
    """Whether the folded quote holds the folded phrase as whole words."""
    hay = fold(quote, keep_parentheses=True)
    needle = fold(phrase, keep_parentheses=True)
    return bool(needle) and re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", hay) is not None


def _check_name(answer: A.FieldAnswer, line: Mapping[str, Any]) -> None:
    value = str(answer.value)
    stored = line["fields"]["name"]["stored"]
    if answer.decision == A.KEEP and value != stored:
        raise AnswerError(f"name: keep, but {value!r} is not the stored {stored!r}")
    if answer.decision == A.REPLACE and value == stored:
        raise AnswerError("name: replace, but the value is the stored name - that is keep")
    defects = [d for d in defects_of(value) if d not in ALLOWED_DEFECTS]
    if defects:
        raise AnswerError(f"name: {value!r} carries the name defect(s) {defects} (D23)")
    if not any(_names(q, value) for _, q in answer.quotes):
        raise AnswerError(f"name: no quote holds {value!r}")


@functools.cache
def _country_vocabulary() -> tuple[dict[str, str], Any]:
    """The frontend's flag map and `normalize_country`, read from their sources once (T05)."""
    return T05._vocabulary()


def _country_is_canonical(value: str) -> bool:
    codes, normalize = _country_vocabulary()
    return T05._is_canonical(value, codes, normalize)


def _check_country(answer: A.FieldAnswer, _line: Mapping[str, Any]) -> None:
    value = str(answer.value)
    if answer.decision == A.KEEP:
        raise AnswerError("country: there is no stored country, so keep is no answer - replace")
    if value == UNITED_KINGDOM:
        raise AnswerError(
            "country: a site in the United Kingdom is spelled by its part (B9): "
            + ", ".join(UK_PARTS.allowed_new_values)
        )
    if not _country_is_canonical(value):
        raise AnswerError(
            f"country: {value!r} is not a spelling the country census accepts (T05: a key of the "
            "frontend's flag map or of NAME_TO_ISO, not a hand-listed split such as USA)"
        )
    forms = {value, *country_name_variants(value)}
    if not any(_names(q, form) for _, q in answer.quotes for form in forms):
        raise AnswerError(f"country: no quote names {value} ({', '.join(sorted(forms))})")


OWN_CHECKS = {"name": _check_name, "country": _check_country}


def _sources(value: Any) -> tuple[tuple[str, str], ...] | str:
    """The description's sources, or the problem that makes them none."""
    try:
        quotes = _quotes(value, A.QUOTE_KEYS)
    except AnswerError as exc:
        return f"{SOURCES}: {exc}"
    if not MIN_SOURCES <= len(quotes) <= MAX_SOURCES:
        return f"{SOURCES}: {len(quotes)} quote(s), not {MIN_SOURCES} to {MAX_SOURCES}"
    families = {A.family_of(q.url, RULE) for q in quotes}
    if families & RULE.forbidden_families:
        return (
            f"{SOURCES}: a quote from {sorted(families & RULE.forbidden_families)} is no source - "
            "never the project's own site or a Wikipedia mirror"
        )
    return tuple((q.url, q.quote) for q in quotes)


def check_shape(text: str, asked: Sequence[str], line: Mapping[str, Any]) -> dict[str, Any]:
    """Every asked field's answer after every page-free check: `{field: FieldAnswer | problem}`,
    and `description_sources` as a tuple of `(url, quote)` or its problem. A text that is not the
    answer object raises `AnswerError`."""
    fields = [f for f in FIELDS if f in asked]
    keys = frozenset({"fields", SOURCES} if SOURCES in asked else {"fields"})
    data = load_object(text, keys)
    block = data["fields"]
    if not isinstance(block, dict) or set(block) != set(fields):
        shown = sorted(block) if isinstance(block, dict) else type(block).__name__
        raise AnswerError(f"`fields` carries {shown}, not the asked {sorted(fields)}")
    out: dict[str, Any] = {}
    shared = [f for f in SHARED_FIELDS if f in fields]
    if shared:
        payload = json.dumps({"fields": {f: block[f] for f in shared}}, ensure_ascii=False)
        out.update(A.check_shape(payload, shared, line, RULE))
    for field in (f for f in OWN_FIELDS if f in fields):
        try:
            parsed = A._block(field, block[field], RULE)
            if parsed.decision != A.UNRESOLVED:
                OWN_CHECKS[field](parsed, line)
        except AnswerError as exc:
            out[field] = str(exc)
        else:
            out[field] = parsed
    if SOURCES in asked:
        out[SOURCES] = _sources(data[SOURCES])
    return out


# ------------------------------------------------------------------------------------ the rounds
def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x.strip()]


def read_rounds(run: Path) -> list[dict[str, Any]]:
    return sorted(_read_jsonl(run / ROUNDS_FILE), key=lambda r: r["round"])


def _by_qid(run: Path) -> dict[str, dict[str, Any]]:
    return {str(c["qid"]): c for c in C.chosen(C.read_candidates(run))}


def batches(labels: Sequence[str], candidates: Mapping[str, Any], round_no: int, size: int):
    """Candidates by name, cut into batches of `size`."""
    if isinstance(size, bool) or size < 1:
        raise ResearchError(f"batch size {size!r} is not a count of 1 or more")
    ordered = sorted(labels, key=lambda q: (str(candidates[q]["label_en"]).casefold(), q))
    return [
        (f"ins-r{round_no}-b{number + 1:03d}", ordered[i : i + size])
        for number, i in enumerate(range(0, len(ordered), size))
    ]


def _export_round(
    run: Path,
    handoff: Path,
    round_no: int,
    asked_of: Mapping[str, Sequence[str]],
    notes: Mapping[str, Mapping[str, str]],
    batch_size: int,
) -> dict[str, Any]:
    rounds = read_rounds(run)
    if any(r["round"] == round_no for r in rounds):
        raise ResearchError(f"round {round_no} is already exported")
    if handoff.exists() and any(handoff.iterdir()):
        raise ResearchError(f"{handoff} is not empty: a round gets a directory of its own")
    candidates = _by_qid(run)
    vocabulary = C.read_vocabulary(run)
    groups = batches(list(asked_of), candidates, round_no, batch_size)
    for batch_id, labels in groups:
        for qid in labels:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=STAGE,
                label=qid,
                field="+".join(asked_of[qid]),
                prompt=render_prompt(candidates[qid], asked_of[qid], vocabulary, notes.get(qid)),
            )
    record = {
        "round": round_no,
        "handoff": handoff.resolve().as_posix(),
        "model": MODEL,
        "role": ROLE,
        "batch_size": batch_size,
        "batches": dict(groups),
        "asked": {qid: list(asked_of[qid]) for qid in sorted(asked_of)},
        "notes": {qid: dict(notes[qid]) for qid in sorted(notes)},
        "exported_at": FH.now(),
    }
    C.write_jsonl(run / ROUNDS_FILE, [*rounds, record])
    return {
        "round": round_no,
        "handoff": record["handoff"],
        "questions": len(asked_of),
        "batches": len(groups),
    }


def export(run: Path, handoff: Path, batch_size: int = BATCH_SIZE) -> dict[str, Any]:
    """Round 0: every candidate, every field and the description's sources."""
    if read_rounds(run):
        raise ResearchError("round 0 is exported already - re-ask with export-reask")
    candidates = _by_qid(run)
    if not candidates:
        raise ResearchError("the candidate list holds no candidate to research")
    return _export_round(run, handoff, 0, dict.fromkeys(candidates, list(ASKABLE)), {}, batch_size)


def export_reask(run: Path, handoff: Path) -> dict[str, Any]:
    """The next round: every field the last import left without a counted answer."""
    rounds = read_rounds(run)
    if not rounds:
        raise ResearchError("nothing was exported")
    reask = json.loads((run / REASK_FILE).read_text(encoding="utf-8"))
    last = rounds[-1]["round"]
    if reask["after_round"] != last:
        raise ResearchError(
            f"{REASK_FILE} is from round {reask['after_round']}: import round {last}"
        )
    if last >= MAX_ROUND:
        raise ResearchError(f"round {last} was the last re-ask (MAX_ROUND {MAX_ROUND})")
    waiting = reask["fields"]
    if not waiting:
        raise ResearchError("every field has a counted answer or is exhausted: nothing to ask")
    asked = {qid: [f for f in ASKABLE if f in waiting[qid]] for qid in waiting}
    notes = {qid: dict(waiting[qid]) for qid in waiting}
    return _export_round(run, handoff, last + 1, asked, notes, rounds[0]["batch_size"])


def _round_of(run: Path, handoff: Path) -> dict[str, Any]:
    shown = handoff.resolve().as_posix()
    for record in read_rounds(run):
        if record["handoff"] == shown:
            return record
    raise ResearchError(f"{handoff} is the directory of no exported round of {run}")


def check_answer(run: Path, handoff: Path, batch_id: str, label: str, text: str) -> dict[str, Any]:
    """The page-free checks of one answer: what `import` would count, short of the pages."""
    record = _round_of(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise ResearchError(f"{label} is not a question of {batch_id}")
    candidate = _by_qid(run)[label]
    try:
        checked = check_shape(text, record["asked"][label], question_line(candidate))
    except AnswerError as exc:
        return {"ok": False, "problems": {"answer": str(exc)}}
    problems = {f: v for f, v in checked.items() if isinstance(v, str)}
    return {"ok": not problems, "problems": problems}


BRIEF = """You are researcher {batch} of the D57 insert lane (new curated sites). You answer {count} \
question(s), each about another site. Answer each one on its own, as if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the repository - \
no other batch, nothing else under output/ or docs/, no database, no git history. Your evidence is \
your own web research, as each prompt says.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide each field, exactly as the prompt asks. Copy every quote from the \
page itself, character for character.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it (nothing is fetched; the quotes are checked against their pages at import):
   ./.venv/Scripts/python.exe scripts/remediation/insert_site/run.py research check-answer \
--run {run} --handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problems per field, if any: fix the answer, never the finding - a field you cannot \
source is "unresolved".
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} --model {model} \
--role {role} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    record = _round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise ResearchError(f"{batch_id} is no batch of {handoff}")
    shown = record["handoff"]
    return BRIEF.format(
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=run.resolve().as_posix(),
        stage=STAGE,
        model=record["model"],
        role=record["role"],
    )


# ------------------------------------------------------------------------------------ the import
def _answer_dict(parsed: Any) -> dict[str, Any] | None:
    if isinstance(parsed, A.FieldAnswer):
        return parsed.to_dict()
    if isinstance(parsed, tuple):
        return {"decision": "sources", "value": None, "quotes": [list(q) for q in parsed]}
    return None


def _read_attempts(run: Path) -> list[dict[str, Any]]:
    """Every answer of every round, as parsed (no page read yet)."""
    candidates = _by_qid(run)
    vocabulary = C.read_vocabulary(run)
    attempts: list[dict[str, Any]] = []
    for record in read_rounds(run):
        handoff = Path(record["handoff"])
        check = OH.validate(handoff)
        if not check.ok:
            raise ResearchError(
                f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
                f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
                "answer is validated before anything is imported"
            )
        for batch_id, labels in sorted(record["batches"].items()):
            for qid in labels:
                asked = record["asked"][qid]
                prompt = render_prompt(candidates[qid], asked, vocabulary, record["notes"].get(qid))
                answer = OH.read_answer(
                    handoff, batch_id=batch_id, stage=STAGE, label=qid, prompt=prompt
                )
                problem = HO.role_problem(RULE, answer)
                if problem is not None:
                    raise ResearchError(f"{batch_id}/{qid}: {problem}")
                try:
                    checked = check_shape(answer.text, asked, question_line(candidates[qid]))
                except AnswerError as exc:
                    checked = dict.fromkeys(asked, f"malformed answer: {exc}")
                for field in asked:
                    parsed = checked[field]
                    attempts.append(
                        {
                            "round": record["round"],
                            "batch_id": batch_id,
                            "qid": qid,
                            "field": field,
                            "answered_by": answer.answered_by,
                            "model": answer.model,
                            "answered_at": answer.answered_at,
                            "answer": _answer_dict(parsed),
                            "problem": parsed if isinstance(parsed, str) else None,
                        }
                    )
    return attempts


def _quotes_of(attempt: Mapping[str, Any]) -> list[tuple[str, str]]:
    answer = attempt["answer"]
    return [] if answer is None else [(u, q) for u, q in answer["quotes"]]


def _value_page_needed(attempt: Mapping[str, Any]) -> bool:
    answer = attempt["answer"]
    return (
        answer is not None
        and attempt["field"] == "source_url"
        and answer["decision"] in (A.KEEP, A.REPLACE)
    )


def check_pages(
    attempts: list[dict[str, Any]],
    run: Path,
    *,
    client: httpx.Client | None,
    net: Fetcher | None,
    pace: float,
) -> dict[str, int]:
    """Fetch every quoted page (and every source_url value) once, then decide each attempt:
    `counted`, `reason`, `unreadable`, `quotes`, `value_page`."""
    pages = run / PAGES_DIR
    urls = sorted(
        {u for a in attempts for u, _ in _quotes_of(a)}
        | {str(a["answer"]["value"]) for a in attempts if _value_page_needed(a)}
    )
    refetched = HO.forget_transient(urls, pages)
    if urls:
        if client is None:
            with FH.open_client() as own:
                Q.collect(urls, pages, own, now=FH.now, pace=pace)
        else:
            Q.collect(urls, pages, client, now=FH.now, pace=pace)
    library = Q.Library(REPO, pages)
    own_net = net is None and any(
        _value_page_needed(a) and wikipedia_title(str(a["answer"]["value"])) for a in attempts
    )
    api = FH.open_fetcher(run) if own_net else net
    try:
        for attempt in attempts:
            if attempt["answer"] is None:
                attempt.update(
                    counted=False,
                    reason=attempt["problem"],
                    unreadable=False,
                    quotes=[],
                    value_page=None,
                )
                continue
            results = [
                asdict(
                    Q.check_quote(
                        {"source": u, "quote": q},
                        {"change_key": attempt["qid"], "evidence_files": []},
                        library,
                    )
                )
                for u, q in _quotes_of(attempt)
            ]
            failed = [r for r in results if r["outcome"] != Q.FOUND]
            reason, blind, page = None, False, None
            if failed:
                first = failed[0]
                detail = f" ({first['detail']})" if first["detail"] else ""
                reason = f"quote {first['outcome']}: {first['source']}{detail}"
                blind = all(HO._unreadable_quote(r, pages) for r in failed)
            elif _value_page_needed(attempt):
                page = HO.value_page(str(attempt["answer"]["value"]), pages, api)
                reason, blind = page["problem"], page["unreadable"]
            attempt.update(
                counted=reason is None,
                reason=reason,
                unreadable=blind,
                quotes=results,
                value_page=page,
            )
    finally:
        if own_net and api is not None:
            api.close()
    if urls:
        C.write_jsonl(run / PAGES_INDEX, Q.page_index(urls, pages))
    return {"urls": len(urls), "refetched": refetched}


def decide(
    attempts: Sequence[Mapping[str, Any]], last_round: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """One decision per asked (candidate, field): its latest counted answer, else - after the last
    re-ask - exhausted (or held, when the last answer failed only on unreadable pages). The fields
    still open are the next re-ask's, each with why its last answer did not count."""
    latest: dict[tuple[str, str], Mapping[str, Any]] = {}
    counted: dict[tuple[str, str], Mapping[str, Any]] = {}
    for attempt in sorted(attempts, key=lambda a: a["round"]):
        key = (str(attempt["qid"]), str(attempt["field"]))
        latest[key] = attempt
        if attempt["counted"]:
            counted[key] = attempt
    decisions: list[dict[str, Any]] = []
    waiting: dict[str, dict[str, str]] = {}
    for key in sorted(latest):
        qid, field = key
        if key in counted:
            chosen = counted[key]
            decisions.append(_decision(chosen, COUNTED))
            continue
        last = latest[key]
        if last_round >= MAX_ROUND:
            decisions.append(_decision(last, HELD if last["unreadable"] else EXHAUSTED))
        else:
            waiting.setdefault(qid, {})[field] = str(last["reason"])
    return decisions, waiting


def _decision(attempt: Mapping[str, Any], status: str) -> dict[str, Any]:
    answer = attempt["answer"] if status == COUNTED else None
    return {
        "qid": attempt["qid"],
        "field": attempt["field"],
        "status": status,
        "decision": answer["decision"] if answer else None,
        "value": answer["value"] if answer else None,
        "period_name": (answer or {}).get("period_name"),
        "quotes": [list(q) for q in answer["quotes"]] if answer else [],
        "reasoning": (answer or {}).get("reasoning"),
        "reason": None if status == COUNTED else attempt["reason"],
        "round": attempt["round"],
        "batch_id": attempt["batch_id"],
        "answered_by": attempt["answered_by"],
        "model": attempt["model"],
        "answered_at": attempt["answered_at"],
        "value_page": attempt.get("value_page"),
    }


def import_rounds(
    run: Path,
    *,
    client: httpx.Client | None = None,
    net: Fetcher | None = None,
    pace: float = Q.PACE_SECONDS,
) -> dict[str, Any]:
    """Every round's answers: validated, parsed, quote-checked, decided."""
    rounds = read_rounds(run)
    if not rounds:
        raise ResearchError("nothing was exported")
    attempts = _read_attempts(run)
    pages = check_pages(attempts, run, client=client, net=net, pace=pace)
    decisions, waiting = decide(attempts, rounds[-1]["round"])
    C.write_jsonl(run / ATTEMPTS_FILE, attempts)
    C.write_jsonl(run / DECISIONS_FILE, decisions)
    C.write_json(run / REASK_FILE, {"after_round": rounds[-1]["round"], "fields": waiting})
    return {
        "rounds": len(rounds),
        "attempts": len(attempts),
        "counted": sum(1 for a in attempts if a["counted"]),
        "not_counted": dict(
            sorted(
                Counter(
                    str(a["reason"]).split(":")[0] for a in attempts if not a["counted"]
                ).items()
            )
        ),
        "decisions": dict(
            sorted(Counter(f"{d['field']}:{d['status']}" for d in decisions).items())
        ),
        "waiting_questions": len(waiting),
        **pages,
    }


def read_decisions(run: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """DECISIONS.jsonl by candidate and field; refused when the import has not run."""
    rows = _read_jsonl(run / DECISIONS_FILE)
    if not rows:
        raise ResearchError(f"{run / DECISIONS_FILE} is missing or empty - import first")
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["qid"]), {})[str(row["field"])] = row
    return out


def waiting(run: Path) -> dict[str, dict[str, str]]:
    """The fields the last import left for a re-ask (`REASK.json`): the plan runs only on none."""
    path = run / REASK_FILE
    if not path.is_file():
        raise ResearchError(f"{path} is missing - import first")
    return dict(json.loads(path.read_text(encoding="utf-8"))["fields"])
