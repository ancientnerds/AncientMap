"""WD1 step 3: every site with a field in CONFLICT, MISSING or flagged, asked of Opus, imported.

No model is called here. The orchestrator's cycle (run from the repository root;
`F=scripts/remediation/fields/handoff.py`, `R=output/remediation/fields/wd1`,
`H=output/remediation/handoff/fields-wd1`):

    $F export --run $R --handoff $H-r0          one question per site, its flagged fields only,
                                                batches of `BATCH_SIZE` sites (country, name order)
    $F brief --run $R --handoff $H-r0 --batch-id B      the instruction of batch B's Opus agent;
        the agent answers each question and records it with `opus_handoff.py answer`
    $F check-answer --run $R --handoff $H-r0 --batch-id B --label L --text-file F
                                                the answer's shape and page-free checks
    opus_handoff.py validate --dir $H-r0        every answer in, in shape, by Opus
    $F import --run $R                          parse, fetch every quoted page once, quote-check,
                                                decide: ATTEMPTS.jsonl, DECISIONS.jsonl, REASK.json
    $F export-reask --run $R --handoff $H-r1    the fields without a counted answer, to new agents
                                                (at most `MAX_ROUND` times; answer, validate, import)
    $F pilot-report --run $R                    a finished pilot's clears on exhaustion: PASS/STOP
    $F status --run $R

**A question** is one site (`label` = its id) and exactly its flagged fields, rendered from
CLASSIFIED.jsonl (`classify.py`): the site, what the machine found per field and why it is asked,
the field's rules, how to research and quote (the acceptance's research text, `acceptance.questions.
RESEARCH`), and the answer format (`answers.py`). Import renders every prompt again and refuses one
that is not the prompt the manifest names - a question is answered as it was asked.

**A field counts** when its answer passes `answers.check_shape` and every quote is found verbatim in
its page as fetched once by this run (`opus_audit/quotes.py`: NFC and whitespace only), and - for a
source_url value - the value's page was served (2xx) at that URL, not redirected to another page,
and, on Wikipedia, is an article of its own (not missing, not a redirect, not a disambiguation page:
the wiki's API, `harvest.resolve_wiki_titles`). A field without a counted answer is asked again, of
a new agent, at most `MAX_ROUND` times - the re-ask shows why the last answer did not count; then it
is **exhausted**: a clearable field is cleared (owner decision O6: "replace only with a sourced
value, else empty the field"), the coordinates stay and are held for the owner - a point cannot be
cleared - and a field whose last answer failed only on pages the checker could not read (no answer,
401/403/406/429, a server error, content it cannot read) is **held** too: "the checker could not
read the page" is not "no source exists" (the English registers refuse the checker).

**A fetch that failed transiently is asked again.** Every import first forgets the kept fetch of
each cited URL that failed for a reason that may pass (no answer, 429, a server error;
`transient`), so one dropped connection does not fail every later quote from that page. An earlier
round's answer can therefore count only at a later import; the latest counted answer decides. A
refusal (401/403/406) is kept: it is the host's answer to the checker, not a moment's failure.

**The pilot.** `pilot-report` measures a finished run's fields cleared on exhaustion, overall and
per country, against `PILOT_MAX_RATE` / `PILOT_MAX_COUNTRY_RATE` (a chosen line): the runbook runs a
pilot of about ten batches (`classify.py ... --pilot`) through all its rounds before a part's bulk.

Files in `--run` (beside CLASSIFIED.jsonl): ROUNDS.jsonl (every exported round, its directory, its
batches, each question's fields and the notes its prompt showed), ATTEMPTS.jsonl (every answer of
every round as parsed, each field's quotes and their outcomes, whether it counted, whether it failed
only on unreadable pages), DECISIONS.jsonl (one line per decided site and field - what `plan.py`
writes from), REASK.json, PAGES.jsonl, `pages/` and PILOT.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
from acceptance.answers import AnswerError  # noqa: E402
from acceptance.questions import RESEARCH, definitions  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from phase4.route_stage import wikipedia_title  # noqa: E402

from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import rule as R  # noqa: E402
from pipeline import periods as P  # noqa: E402

#: WD1's handoff stage (`Rule.stage`); a run's own stage is its rule's.
STAGE = R.TWO_FAMILIES.stage
BATCH_SIZE = 8
#: Round 0 and two re-asks, as the acceptance does.
MAX_ROUND = 2
ROUNDS_FILE = "ROUNDS.jsonl"
ATTEMPTS_FILE = "ATTEMPTS.jsonl"
DECISIONS_FILE = "DECISIONS.jsonl"
REASK_FILE = "REASK.json"
PAGES_DIR = "pages"
PAGES_INDEX = "PAGES.jsonl"
COUNTED, EXHAUSTED = "counted", "exhausted"
#: The exhausted field whose last answer failed only on pages the checker could not read: neither
#: written nor cleared, listed for the owner (the wave's HELD.jsonl, WF's report).
HELD = "held"
#: The statuses by which a host refuses the checker itself (a bot challenge, a login, a refused
#: agent, a rate limit): the page may hold the quote, the checker cannot tell.
REFUSED_STATUS = frozenset({401, 403, 406, 429})
#: The pilot's gate - a chosen line, not a measured one: the share of a finished pilot's asked
#: fields cleared on exhaustion, overall and in each country with at least `PILOT_MIN_FIELDS`.
PILOT_MAX_RATE = 0.10
PILOT_MAX_COUNTRY_RATE = 0.20
PILOT_MIN_FIELDS = 10
#: WD3 clears nothing, so its pilot guards the other way a run can go wrong - a checker that cannot
#: read what the agents cite (every such field ends `held`): a chosen line, not a measured one. An
#: unsourced field (`unresolved`) is a finding, not a defect: the population is what WD1 could not
#: source, and its rate (every `unresolved` decision, answered outright or on exhaustion) is
#: reported. The other way a run goes wrong is an agent that answers `unresolved` without
#: researching: a field of a site whose question showed a Wikidata item or an English Wikipedia
#: article usually has a source, so the share of those fields answered `unresolved` outright is
#: gated, overall and when at least `PILOT_MIN_FIELDS` of them were asked (a chosen line).
PILOT_MAX_HELD_RATE = 0.20
PILOT_MAX_COUNTRY_HELD_RATE = 0.30
PILOT_MAX_HINTED_UNRESOLVED_RATE = 0.60
PILOT_FILE = "PILOT.json"


class HandoffStepError(ValueError):
    """The step must not run on this state. Nothing was written by it."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO / path


def _shown(path: Path) -> str:
    try:
        return _resolve(path).resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        # the resolved path, never the path as spelled: a run reached through a junction or a
        # `..` component is the same run, and a wave's `run` is compared against this (2026-10-04)
        return path.resolve().as_posix()


def read_classified(run: Path) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(run / C.CLASSIFIED_FILE)
    if not rows:
        raise HandoffStepError(f"{run / C.CLASSIFIED_FILE} is missing or empty - classify first")
    return {row["site_id"]: row for row in rows}


def read_rounds(run: Path) -> list[dict[str, Any]]:
    return _read_jsonl(run / ROUNDS_FILE)


#: The claim the site's own article carried when the dataset was imported (2025-12-18), per site:
#: the run's own copy of the measured rows in `output/remediation/period_wave/
#: original_periods.jsonl` (`Year`, `Period` and the join that put the row on this site). A run
#: without the file asks the same question without it.
HINTS_FILE = "ORIGINAL_PERIODS.jsonl"
HINT_KEYS = frozenset(
    {"site_id", "name", "source_url", "match", "title", "year", "period", "category"}
)


def read_hints(run: Path) -> dict[str, dict[str, Any]]:
    """`{site_id: hint}` of the run's own `ORIGINAL_PERIODS.jsonl`, or `{}` when it has no such
    file. A row that is not a hint row is refused: the join behind it was measured once, and a row
    of another shape is a file the owner has to look at."""
    path = run / HINTS_FILE
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        if not isinstance(row, dict) or set(row) != HINT_KEYS:
            shown = sorted(row) if isinstance(row, dict) else type(row).__name__
            raise HandoffStepError(f"{HINTS_FILE}: a row carries {shown}, not {sorted(HINT_KEYS)}")
        if not all(isinstance(row[key], str) for key in HINT_KEYS - {"match"}) or not (
            row["match"] is None or isinstance(row["match"], str)
        ):
            raise HandoffStepError(
                f"{HINTS_FILE}: the row of {row['site_id']!r} carries a value that is not a string"
            )
        out[row["site_id"]] = row
    return out


# ------------------------------------------------------------------------------ the question
FIELD_RULES = {
    "coordinates": (
        "The site's point: the place of the site itself - its centre or its main monument - not "
        "the nearest village, a namesake, the museum that keeps its finds, the hill or island it "
        "stands on, or the region.\n"
        f"- keep: two independent sources give a point within {A.KEEP_KM:g} km of the stored point. "
        'value = "lat, lon" of the point they give, in decimal degrees.\n'
        f"- replace: the stored point is more than {A.KEEP_KM:g} km from the site; two independent "
        'sources give the site\'s point. value = "lat, lon" in decimal degrees (at most 6 '
        "decimals).\n"
        "- unresolved: no two independent sources can be quoted for the site's point. The point "
        "cannot be emptied: every site stays on the map, and an unresolved point is held for the "
        "owner.\n"
        "Each quote must hold exactly the two coordinates as the page prints them - signed decimal "
        'degrees, latitude first ("51.1789, -1.8262"), or degrees with a hemisphere letter each '
        '("51°10′44″N 1°49′34″W", "51.1789°N 1.8262°W") - with nothing around them but labels such '
        f'as "Coordinates:". They must lie within {A.KEEP_KM:g} km of your value. A grid reference '
        "(OSGB, UTM) is not read."
    ),
    "period_start": (
        "period_start is the year the site's securely attested history as a site begins - its "
        "construction, foundation or first occupation - negative for BC. The map shows only its "
        "bucket.\n"
        "- keep: two independent sources date the start into the stored value's bucket. value = "
        "the attested start year.\n"
        "- replace: the attested start lies in another bucket (or the field is empty). value = "
        'that year, e.g. "-2500" for c. 2500 BC; a century as its first year ("the 8th century BC" '
        '-> "-800", "the 2nd century AD" -> "101").\n'
        "- clear: no two independent sources date the start. The field is emptied - an empty "
        "field beats a wrong one.\n"
        "Each quote must carry the date as the page states it (a year, a century, a millennium), "
        'and at least one must state your value itself: its year ("c. 2500 BC" for -2500), or its '
        'century or millennium with that word ("the 26th century BC", "the 3rd millennium BC"). A '
        'year worked out from "4,500 years ago" or a BP date is not read.'
    ),
    "site_type": (
        "site_type is one canonical type: the most specific one that holds what the sources say "
        "the site is. A generic type (Ruin, Archaeological site, Site, Heritage site, Scheduled "
        "monument) only when nothing more specific fits.\n"
        "- keep: two independent sources describe the site as the stored type. value = the stored "
        "type.\n"
        "- replace: the sources describe it as another type. value = one canonical type.\n"
        "- clear: no two independent sources say what kind of site it is. The field is emptied.\n"
        'At least one quote must hold a word of the chosen type ("temple" for Temple, '
        '"tumulus" or "mound" for Mound/tumulus).'
    ),
    "source_url": (
        "source_url is the page the site's entry names as its source. It must load without a "
        "login or a script and be about this very site - not the island, town, region or hill it "
        "lies in, not a namesake, not a list. Prefer the site's own Wikipedia article in English, "
        "else in another language, else a heritage register entry or a scholarly page.\n"
        "- keep: the stored page is about this site. value = the stored URL, unchanged.\n"
        "- replace: another page is about this site. value = its URL - the article's own URL, not "
        "a redirect, a section link (no #...), a search or a translation proxy - written "
        "percent-encoded, as a browser's address bar copies it (\"https://de.wikipedia.org/wiki/"
        'G%C3%B6bekli_Tepe", not "Göbekli_Tepe"); check-answer prints the form it wants.\n'
        "- clear: no page about this site can be found. The field is emptied.\n"
        "For keep and replace, at least one quote is from the value's page itself and names the "
        "site; a second quote, from an independent source family, names it too."
    ),
}

KNOWN_FETCH_TROUBLE = (
    "## Pages the quote check cannot read\n"
    "\n"
    "The checker fetches each page with a plain GET and no browser. On 2026-09-26 it was refused "
    "(403, most of them a bot challenge) by Historic England's list, the Heritage Gateway, the "
    "UNESCO World Heritage Centre (whc.unesco.org), Atlas Obscura and Britannica, and it cannot "
    "read scanned PDFs or pages that build their text with scripts. Wikipedia (every language), "
    "Wikidata, Pleiades, the Megalithic Portal and most national registers and museum pages "
    "work. Prefer pages that show their text as plain HTML; a quote from a page the checker "
    "cannot read does not count. A field whose last answer failed only because the checker "
    "could not read its pages is held for the owner, not cleared - but a readable source is "
    "always better.\n"
)

ANSWER_FORMAT = (
    "## Your answer\n"
    "\n"
    'One JSON object and nothing else: {{"fields": {{...}}}} with exactly these keys: {keys}. Each '
    "is\n"
    '{{"decision": "...", "value": "..." or null, "quotes": [{{"url": "https://...", "quote": '
    '"verbatim text"}}], "reasoning": "..."}}\n'
    "keep and replace carry the value and at least two quotes from at least two independent "
    "source families; clear and unresolved carry value null and quotes []. The reasoning says, in "
    "a sentence or two, what the sources say and why that decides it.\n"
)


# ---------------------------------------------------------------------------- lane WD3's texts
#: WD3's rules per field: the same checks as WD1's, but one source suffices and an answer that
#: cannot be sourced is `unresolved` - never `clear`: the field stays as it is.
FIELD_RULES_WD3 = {
    "coordinates": (
        "The site's point: the place of the site itself - its centre or its main monument - not "
        "the nearest village, a namesake, the museum that keeps its finds, the hill or island it "
        "stands on, or the region.\n"
        f"- keep: a source gives a point within {A.KEEP_KM:g} km of the stored point. The stored "
        'point then counts as sourced. value = "lat, lon" of the point the source gives, in '
        "decimal degrees.\n"
        f"- replace: the stored point is more than {A.KEEP_KM:g} km from the site and a source "
        'gives the site\'s point. value = "lat, lon" in decimal degrees (at most 6 decimals).\n'
        "- unresolved: no source can be quoted for the site's point. The stored point stays - "
        "it cannot be emptied, every site stays on the map - and the site goes to the owner's "
        "list.\n"
        "Each quote must hold exactly the two coordinates as the page prints them - signed decimal "
        'degrees, latitude first ("51.1789, -1.8262"), or degrees with a hemisphere letter each '
        '("51°10′44″N 1°49′34″W", "51.1789°N 1.8262°W") - with nothing around them but labels such '
        f'as "Coordinates:". They must lie within {A.KEEP_KM:g} km of your value, and be written '
        "at least to whole arcminutes. A grid reference (OSGB, UTM) is not read."
    ),
    "period_start": (
        "period_start is the year a source gives for the start of the site's history as a site - "
        "its construction, foundation or first occupation - negative for BC. The map shows only "
        "its bucket.\n"
        "- keep: only when the field holds a value: a source dates the start into the stored "
        "value's bucket. value = the attested start year.\n"
        "- replace: a source dates the start (the field is empty, or the start lies in another "
        'bucket). value = that year, e.g. "-2500" for c. 2500 BC; a century as its first year '
        '("the 8th century BC" -> "-800", "the 2nd century AD" -> "101").\n'
        "- unresolved: no source dates the start. The field stays as it is - an empty one stays "
        "empty - and the site goes to the owner's list.\n"
        "Each quote must carry the date as the page states it (a year, a century, a millennium), "
        'and at least one must state your value itself: its year ("c. 2500 BC" for -2500), or its '
        'century or millennium with that word ("the 26th century BC", "the 3rd millennium BC"). A '
        'year worked out from "4,500 years ago" or a BP date is not read.\n'
        "What dates this site (owner rule of 2026-10-01: one source suffices): a year, century or "
        "millennium a source gives for the start of THIS site counts also when the source hedges "
        'it ("c.", "around", "probably", "is thought to", "vers", "vraisemblablement") - give that '
        'year - unless the same source rejects it ("its date cannot be traced"). What does not '
        'date it: a period word alone ("Iron Age hillfort", "an Inca site", "Neolithic"), or a '
        'range a source gives for a whole class of monuments ("slight univallate hillforts were '
        'built from the 8th to the 5th century BC"): then answer unresolved.'
    ),
    "site_type": (
        "site_type is one canonical type: the most specific one that holds what the sources say "
        "the site is. A generic type (Ruin, Archaeological site, Site, Heritage site, Scheduled "
        "monument) only when nothing more specific fits.\n"
        "- keep: only when the field holds a value: a source describes the site as the stored "
        "type. value = the stored type.\n"
        "- replace: a source describes the site as a type (the field is empty, or it is another "
        "type). value = one canonical type.\n"
        "- unresolved: no source says what kind of site it is. The field stays as it is and the "
        "site goes to the owner's list.\n"
        'A quote must hold a word of the chosen type ("temple" for Temple, "tumulus" or "mound" '
        "for Mound/tumulus)."
    ),
    "source_url": (
        "source_url is the page the site's entry names as its source. It must load without a "
        "login or a script and be about this very site - not the island, town, region or hill it "
        "lies in, not a namesake, not a list. Prefer the site's own Wikipedia article in English, "
        "else in another language, else a heritage register entry or a scholarly page.\n"
        "- keep: only when the field holds a URL: the stored page is about this site. value = the "
        "stored URL, unchanged.\n"
        "- replace: a page is about this site (the field is empty, or another page is the "
        "better one). value = its URL - the article's own URL, not a redirect, a section link "
        "(no #...), a search or a translation proxy - written percent-encoded, as a browser's "
        'address bar copies it ("https://de.wikipedia.org/wiki/G%C3%B6bekli_Tepe", not '
        '"Göbekli_Tepe"); check-answer prints the form it wants.\n'
        "- unresolved: no page about this site can be found. The field stays as it is and the "
        "site goes to the owner's list.\n"
        "For keep and replace, one quote is from the value's page itself and names the site."
    ),
}

#: Where lane WD3's agents start, and what they must not use. The machine-checked half of the
#: quotes' rules is `RESEARCH`'s second section, kept word for word.
RESEARCH_WD3 = (
    "## How to research\n"
    "\n"
    "Start from what the database already holds about this site, in this order:\n"
    "1. the site's Wikidata item and its English Wikipedia article (above), then the same "
    "article in other languages (its language links) and the item's other statements;\n"
    "2. the stored source_url and the pages the site's own page links to (listed above, with "
    "their kind) - each was found for this site, but read it before you trust it;\n"
    "3. then reputable sources: heritage agencies and national monument registers, UNESCO, "
    "museums, universities, journals and excavation reports, Pleiades, established "
    "encyclopedias.\n"
    "\n"
    "- A national register's own record is often readable by a plain GET where a portal, a "
    "search page or a site restating it is not: find the record itself (e.g. Peru's tourism "
    "inventory at consultasenlinea.mincetur.gob.pe/fichaInventario/index.aspx?cod_Ficha=<n>, "
    "France's Merimee at pop.culture.gouv.fr/notice/merimee/<id>) and quote it, not a mirror.\n"
    "- Never use ancientnerds.com (it is this database), AI-written content farms, travel "
    "blogs that restate Wikipedia, or Wikipedia mirrors (Wikiwand, DBpedia and the like): a "
    "quote from one of them is refused.\n"
    "- Before any answer, make sure the source is about this very site: its name AND its place.\n"
    "- One source suffices. One Wikipedia article (in any language), its Wikidata item and "
    "Wikimedia Commons are ONE source; so are all pages of one website. One verbatim quote from "
    "one page is enough when it states the value itself.\n"
    "- A field no source supports stays as it is: answer unresolved. That is an answer, not a "
    "failure - do not stretch a source to fill a field.\n"
    "\n"
) + RESEARCH[RESEARCH.index("## Quotes are checked by machine") :]


def _period_list() -> str:
    """The period names the question accepts, as lines for the prompt. The whole vocabulary is in
    the question on purpose: a name it does not hold is refused by name, so the agent reads the
    refusal against this list instead of guessing a spelling."""
    names = sorted(P.PERIODS)
    return "\n".join(", ".join(names[start : start + 8]) for start in range(0, len(names), 8))


#: WD4's rules per field: WD3's, with one change to `period_start` (the period word is an answer).
#: Every other field's text is WD3's own string, not a copy of it.
FIELD_RULES_WD4 = {
    **FIELD_RULES_WD3,
    "period_start": (
        "period_start is the year a source gives for the start of the site's history as a site - "
        "its construction, foundation or first occupation - negative for BC. The map shows only "
        "its bucket.\n"
        "- keep: only when the field holds a value: a source dates the start into the stored "
        "value's bucket. value = the attested start year.\n"
        "- replace: a source dates the start (the field is empty, or the start lies in another "
        'bucket). value = that year, e.g. "-2500" for c. 2500 BC; a century as its first year '
        '("the 8th century BC" -> "-800", "the 2nd century AD" -> "101").\n'
        "- unresolved: no source dates the start. The field stays as it is - an empty one stays "
        "empty - and the site goes to the owner's list.\n"
        "Each quote must carry the date as the page states it (a year, a century, a millennium), "
        'and at least one must state your value itself: its year ("c. 2500 BC" for -2500), or its '
        'century or millennium with that word ("the 26th century BC", "the 3rd millennium BC"). A '
        'year worked out from "4,500 years ago" or a BP date is not read.\n'
        "What dates this site (owner rule of 2026-10-01: one source suffices): a year, century or "
        "millennium a source gives for the start of THIS site counts also when the source hedges "
        'it ("c.", "around", "probably", "is thought to", "vers", "vraisemblablement") - give that '
        'year - unless the same source rejects it ("its date cannot be traced").\n'
        'A period word is a date too, and this lane takes it (owner decision of 2026-10-04, "a '
        'named period is a value"). When a source calls the site a period of its own ("an Iron '
        'Age hillfort", "a Neolithic causeway enclosure", "Romano-British", "Maya"), answer:\n'
        '- "decision": "replace" (or "keep"), "value": null, "period_name": the period as the '
        "source names it, and the quote that names it.\n"
        "The year is then read from a fixed table, not from you: the one start the vocabulary "
        'holds for that name ("iron age" -> -800, "neolithic" -> -4000, "victorian" -> 1837). '
        "Never write a year next to a period_name. A name the table does not know is refused, so "
        "use one of these spellings: "
        f"{_period_list()}\n"
        "What still dates nothing: a period a source gives for a whole class of monuments rather "
        'than for this site ("slight univallate hillforts were built from the 8th to the 5th '
        'century BC"), a period a source rejects, or a site a source dates no way: then answer '
        "unresolved."
    ),
}


ANSWER_FORMAT_WD3 = (
    "## Your answer\n"
    "\n"
    'One JSON object and nothing else: {{"fields": {{...}}}} with exactly these keys: {keys}. Each '
    "is\n"
    '{{"decision": "...", "value": "..." or null, "quotes": [{{"url": "https://...", "quote": '
    '"verbatim text"}}], "reasoning": "..."}}\n'
    "keep and replace carry the value and at least one quote; unresolved carries value null and "
    "quotes []. The reasoning says, in a sentence or two, what the source says and why that "
    "decides it.\n"
)

ANSWER_FORMAT_WD4 = (
    "## Your answer\n"
    "\n"
    'One JSON object and nothing else: {{"fields": {{...}}}} with exactly these keys: {keys}. Each '
    "is\n"
    '{{"decision": "...", "value": "..." or null, "period_name": "..." (period_start only), '
    '{{"url": "https://...", "quote": "verbatim text"}} quotes, "reasoning": "..."}}\n'
    "keep and replace carry the value and at least one quote; unresolved carries value null and "
    "quotes []. The reasoning says, in a sentence or two, what the source says and why that "
    "decides it. A period_start that rests on a period word carries period_name instead of a value "
    '(period_name: "iron age", value: null) - the year is read from the vocabulary, so a value '
    "beside it is refused.\n"
)


# ---------------------------------------------------------------------------- lane wd5's texts
def _swap(text: str, old: str, new: str) -> str:
    """`text` with the one sentence `old` replaced by `new` - refused when `old` is not in it, so a
    later edit of the text this one is derived from fails here instead of shipping unchanged."""
    if text.count(old) != 1:
        raise ValueError(f"the text to derive wd5's rule from no longer holds {old!r} once")
    return text.replace(old, new)


#: How the plan treats `unresolved` per field under the recheck rule (`plan.site_cells`): what the
#: agent is told, so that an answer is never given for the sake of its consequence.
_WD5_UNRESOLVED = {
    "coordinates": (
        "What unresolved does in this lane: a point a MiniMax agent moved is moved back to the "
        "point it had before; any other stored point stays - it cannot be emptied - and the site "
        "goes to the owner's list (such a site gets no Short). Answer unresolved only when no "
        "source can be quoted; a page you could not open is not a finding, say so in the "
        "reasoning."
    ),
    "site_type": (
        "What unresolved does in this lane: a type a MiniMax agent wrote is withdrawn; any other "
        "stored type stays and the site goes to the owner's list."
    ),
    "source_url": (
        "What unresolved does in this lane: a page a MiniMax agent wrote is withdrawn; any other "
        "stored page stays and the site goes to the owner's list."
    ),
}

_WD5_BP = (
    ' A date in years before the present is read too - "40,000 years ago", "12,000 BP", '
    '"12,000 cal BP", "45 ka", "1.2 Ma" (also "between 12,000 and 10,000 years ago"): the '
    'year is 1950 minus that number ("12,000 BP" is -10050), and a quote states your year when '
    "it is within one unit of that number's last significant digit (at least 76 years). A "
    "site a source dates older than 6,450 years before the present (4500 BC) is in the band "
    '"< 4500 BC", the only thing the map shows of it: give the year the number works out to, '
    "or -4501, the band's own year."
)
_WD5_UNRESOLVED_PERIOD = (
    "- unresolved: no source dates the start. What follows is this lane's own rule: a start that a "
    'rule made (the stored value says so above) becomes "Undated" with no year, and a start a '
    "MiniMax agent wrote is withdrawn. Answer unresolved only when no source can be quoted - a "
    "page you could not open is not a finding, say so in the reasoning - and never keep or "
    "replace a start to avoid that: the stored start has no source behind it.\n"
)

#: wd5's rules per field: WD4's, with the BP reader named in `period_start` and what `unresolved`
#: does said per field. Every other sentence is WD3's/WD4's own string, not a copy of it.
FIELD_RULES_WD5 = {
    **{field: FIELD_RULES_WD4[field] + "\n" + note for field, note in _WD5_UNRESOLVED.items()},
    "period_start": _swap(
        _swap(
            FIELD_RULES_WD4["period_start"],
            ' A year worked out from "4,500 years ago" or a BP date is not read.',
            _WD5_BP,
        ),
        "- unresolved: no source dates the start. The field stays as it is - an empty one stays "
        "empty - and the site goes to the owner's list.\n",
        _WD5_UNRESOLVED_PERIOD,
    ),
}

RESEARCH_WD5 = _swap(
    RESEARCH_WD3,
    "- A field no source supports stays as it is: answer unresolved. That is an answer, not a "
    "failure - do not stretch a source to fill a field.\n",
    "- A field no source supports: answer unresolved (the field's rules say what that does). That "
    "is an answer, not a failure - do not stretch a source to fill a field, and do not keep a "
    "stored value because it is stored: every field of this question has no source behind it yet.\n",
)

ANSWER_FORMAT_WD5 = ANSWER_FORMAT_WD4

#: A field of a WD3 question is open for one of these reasons (`population.py`).
OPEN_TEXT = {
    "empty": "the field is empty",
    "unresolved": "the stored point has no sourced witness: an earlier pass found none",
    "held": "the stored value has no source: an earlier pass could not read the pages it cited. "
    "A source that confirms it is a keep; a source for another value is a replace, which is "
    "listed for the owner and not written - only an empty field is filled",
    "unsourced": "the stored value has no source: an earlier pass found none (its clear was "
    "refused). A source that confirms it is a keep; a source for another value is a replace, "
    "which is listed for the owner and not written - only an empty field is filled",
    # lane wd5: a stored value is replaced, when it is one of these three
    "rule-made": "the stored start was made by a rule and found in no source: the beginning of "
    "the epoch a rule gives the site's type, the edge of the band the 2025 import filed the site "
    "under, or the inception date of the site's Wikidata item. No source stands behind it",
    "minimax-answered": "an earlier pass answered this field with a MiniMax model, whose answers "
    "failed their calibration (64.71 % agreement, the bar was 90 %). Whatever it decided - a "
    "value it wrote, a value it kept, or no value - no reliable pass has checked a source for it",
    "unsourced-point": "the stored point has no source: earlier passes found none for it, or "
    "found a better point that a guard refused",
}
WD1_SHOWN_CHARS = 600
#: How many of a site's own links a WD3 question lists (best first).
LINKS_SHOWN = 10

#: What the site's own article carried when the dataset was imported, told to the agent as a claim
#: to check. Measured 2026-10-04 against the 2,775 curated sites that have a period: the file's
#: nine-band `Period` agrees with the stored `period_start` in 70.6 % of the cases and its `Year` in
#: 20.9 %, and none of 1,544 Years lands inside the stored [period_start, period_end] span. No code
#: path reads a value because it equals the claim: an answer needs a page it quotes either way.
ORIGINAL_CLAIM = (
    "The original import of this database (2025-12-18) kept what the site's own article carried "
    'then ("{title}", matched on its {match}): Year "{year}", Period "{period}".\n'
    "A claim to confirm or contradict, not a source. The band spans up to a thousand years, the "
    "file disagrees with what this database holds for about a third of the sites that have both, "
    "and no answer is read because it agrees with it: confirm or contradict it with a page you "
    "quote.\n"
)


#: The stages that show the original import's claim: WD4's and the recheck's.
HINT_STAGES = (R.ONE_FAMILY_PERIOD.stage, R.RECHECK.stage)


def _original_claim(hint: Mapping[str, Any] | None, rule: R.Rule) -> list[str]:
    """The lines of the original import's own period claim, or none. WD4 and wd5 only: the two
    older lanes asked their question without it, and their prompts are pinned by hash."""
    if hint is None or rule.stage not in HINT_STAGES:
        return []
    year, period = str(hint.get("year") or "").strip(), str(hint.get("period") or "").strip()
    if not year and not period:
        return []
    return [
        ORIGINAL_CLAIM.format(
            title=hint.get("title") or "the article",
            match=hint.get("match") or "stored URL",
            year=year or "empty",
            period=period or "empty",
        )
    ]


def _evidence_lines(field: str, status: Mapping[str, Any]) -> list[str]:
    ev = status["evidence"]
    lines: list[str] = []
    if field == "coordinates":
        for w in ev.get("witnesses", []):
            lines.append(
                f"  - {w['source']}: {w['point'][0]}, {w['point'][1]} "
                f"({w['km_from_stored']} km from the stored point)"
            )
        if ev.get("stacked"):
            lines.append(
                f"  - {ev['stacked']} other site(s) of the database hold exactly the stored point"
            )
    elif field == "period_start":
        for d in ev.get("dates", []):
            lines.append(f"  - wikidata {d['property']}: {d['time']}")
        for d in ev.get("modern", []):
            lines.append(
                f"  - wikidata {d['property']}: {d['time']} - not read: a date from "
                f"{C.MODERN} AD on is a designation, park or museum date, not the site's start"
            )
        if status["stored"] is not None:
            lines.append(f"  - the stored value's bucket: {C.bucket(int(status['stored']))}")
    elif field == "site_type":
        for c in ev.get("classes", []):
            lines.append(f"  - the item is an instance of: {c['label']} ({c['qid']})")
    else:
        kind = ev.get("kind")
        if kind == H.URL_WIKIPEDIA:
            lines.append(
                f"  - {ev['lang']}.wikipedia: resolves to {ev['resolved_title']!r}"
                + (f"#{ev['fragment']}" if ev.get("fragment") else "")
                + (" (a redirect)" if ev.get("redirected") else "")
                + (" - missing" if ev.get("missing") else "")
            )
        elif kind == H.URL_WEB:
            lines.append(
                f"  - HTTP {ev.get('status')}, served at {ev.get('final_url')}, title "
                f"{ev.get('page_title')!r}" + (f", error {ev['error']}" if ev.get("error") else "")
            )
    return lines


@dataclass(frozen=True)
class Texts:
    """What a rule's question says in its own words: the opening, each field's rules, what an empty
    field and a re-ask are told, how to research and the answer's format."""

    intro: str
    field_rules: Mapping[str, str]
    empty_note: str
    retry_note: str
    research: str
    answer_format: str


TEXTS = {
    R.TWO_FAMILIES.name: Texts(
        intro=(
            "You are an Opus researcher in the structured-field repair (lane WD1) of a curated "
            "database of ancient sites. This question is about ONE site and the fields listed "
            "below. Research each field on its own and decide it from sources you quote."
        ),
        field_rules=FIELD_RULES,
        empty_note=(
            "The field is empty, so keep is no answer: replace with a sourced value, or clear "
            "to leave it empty."
        ),
        retry_note=(
            "An earlier answer to this field did not count: {why}. Answer it again "
            "from sources the checker can read - or clear it (unresolved for coordinates) "
            "when none can be quoted."
        ),
        research=RESEARCH + "\n" + KNOWN_FETCH_TROUBLE,
        answer_format=ANSWER_FORMAT,
    ),
    R.ONE_FAMILY.name: Texts(
        intro=(
            "You are a researcher in the structured-field fill (lane WD3) of a curated database "
            "of ancient sites. This question is about ONE site and the open fields listed below: "
            "each is empty, or holds a value no source stands behind yet. Research each field on "
            "its own and decide it from a source you quote."
        ),
        field_rules=FIELD_RULES_WD3,
        empty_note=(
            "The field is empty, so keep is no answer: replace with a sourced value, or answer "
            "unresolved to leave it empty."
        ),
        retry_note=(
            "An earlier answer to this field did not count: {why}. Answer it again "
            "from a source the checker can read - or answer unresolved when none can be quoted."
        ),
        research=RESEARCH_WD3 + "\n" + KNOWN_FETCH_TROUBLE,
        answer_format=ANSWER_FORMAT_WD3,
    ),
    R.ONE_FAMILY_PERIOD.name: Texts(
        intro=(
            "You are a researcher in the structured-field fill (lane WD4) of a curated database "
            "of ancient sites. This question is about ONE site and the open fields listed below: "
            "each is empty, or holds a value no source stands behind yet. Research each field on "
            "its own and decide it from a source you quote."
        ),
        field_rules=FIELD_RULES_WD4,
        empty_note=(
            "The field is empty, so keep is no answer: replace with a sourced value or a sourced "
            "period name, or answer unresolved to leave it empty."
        ),
        retry_note=(
            "An earlier answer to this field did not count: {why}. Answer it again "
            "from a source the checker can read - or answer unresolved when none can be quoted."
        ),
        research=RESEARCH_WD3 + "\n" + KNOWN_FETCH_TROUBLE,
        answer_format=ANSWER_FORMAT_WD4,
    ),
    R.RECHECK.name: Texts(
        intro=(
            "You are a researcher in the structured-field re-check (lane wd5) of a curated "
            "database of ancient sites. This question is about ONE site and the fields listed "
            "below: each holds a value, or nothing, that no reliable pass has found a source "
            "for. Research each field on its own and decide it from a source you quote."
        ),
        field_rules=FIELD_RULES_WD5,
        empty_note=(
            "The field is empty, so keep is no answer: replace with a sourced value or a sourced "
            "period name, or answer unresolved."
        ),
        retry_note=(
            "An earlier answer to this field did not count: {why}. Answer it again "
            "from a source the checker can read - or answer unresolved when none can be quoted."
        ),
        research=RESEARCH_WD5 + "\n" + KNOWN_FETCH_TROUBLE,
        answer_format=ANSWER_FORMAT_WD5,
    ),
}


def _site_lines(line: Mapping[str, Any], rule: R.Rule) -> list[str]:
    item = line["qid"]
    out = [
        f"- name: {line['name']}",
        f"- country: {line['country']}",
        f"- stored point: {line['fields']['coordinates']['stored']} (latitude, longitude)",
        f"- Wikidata item: {'https://www.wikidata.org/wiki/' + item if item else 'none'}"
        + (
            f" - possibly not the site: it is a {', '.join(line['identity']['containers'])}"
            if line["identity"]["doubt"]
            else ""
        ),
        f"- English Wikipedia article of the item: {line['enwiki'] or 'none'}",
    ]
    if rule.asks_open_fields:
        out.append(f"- stored source_url: {line['fields']['source_url']['stored'] or 'none'}")
        links = line["links"]
        if links:
            out.append("- pages the site's own page links to (best first):")
            out.extend(
                f"  - [{link['type']}] {link['title']} - {link['url']}"
                for link in links[:LINKS_SHOWN]
            )
        else:
            out.append("- pages the site's own page links to: none")
    return out


def _open_lines(line: Mapping[str, Any], field: str) -> list[str]:
    """WD3: why the field is open, and what the earlier pass (WD1, which asked for two source
    families) made of it - a lead to check, not evidence."""
    opened = line["open"][field]
    out = [f"Open because: {OPEN_TEXT[opened['why']]}."]
    made = opened.get("made")
    if made is not None:
        out.append(f"What stands: {made} (a lead to check, not evidence).")
    earlier = opened["wd1"]
    if earlier is not None:
        out.append(
            f"The earlier pass (lane WD1, two independent source families required) decided "
            f"{earlier['decision']}: {earlier['reasoning'][:WD1_SHOWN_CHARS]} "
            "(a lead to check, not evidence)."
        )
    return out


def render_prompt(
    line: Mapping[str, Any],
    fields: Sequence[str],
    notes: Mapping[str, str] | None = None,
    rule: R.Rule = R.DEFAULT,
    hint: Mapping[str, Any] | None = None,
) -> str:
    """The exact question for one site and `fields` - a pure function of the classified line, of
    the rule the run decides under, of the site's original-import claim (`hint`, `read_hints`, WD4
    only) and, in a re-ask, of why each field's last answer did not count (`notes`, kept in the
    round's record)."""
    notes = notes or {}
    fields = [f for f in C.FIELDS if f in fields]
    if not fields:
        raise HandoffStepError(f"{line['site_id']}: a question needs at least one field")
    texts = TEXTS[rule.name]
    out = [
        texts.intro,
        "",
        "## The site",
        "",
        *_site_lines(line, rule),
        "",
        "## The fields you decide",
        "",
    ]
    for field in fields:
        status = line["fields"][field]
        out.append(f"### {field}")
        out.append("")
        out.append(f"Stored value: {json.dumps(status['stored'], ensure_ascii=False)}")
        if rule.asks_open_fields:
            out.extend(_open_lines(line, field))
        out.append(f"Why you are asked: {status['status']} - {status['reason']}")
        evidence = _evidence_lines(field, status)
        if evidence:
            out.append("What the machine read:")
            out.extend(evidence)
        if field == "period_start":
            claim = _original_claim(hint, rule)
            if claim:
                out.extend(claim)
        if status["flags"]:
            out.append(
                "An earlier reading found this field wrong (a lead to check, not evidence - "
                "decide from the sources you quote):"
            )
            out.extend(f"  - {flag}" for flag in status["flags"])
        if status["stored"] is None:
            out.append(texts.empty_note)
        if field in notes:
            out.append(texts.retry_note.format(why=notes[field]))
        out.append("")
        out.append(texts.field_rules[field])
        vocabulary = definitions(field)
        if vocabulary:
            out.append("")
            out.append(vocabulary)
        out.append("")
    out.append(texts.research)
    out.append(texts.answer_format.format(keys=", ".join(f'"{f}"' for f in fields)))
    return "\n".join(out)


# ------------------------------------------------------------------------------ export
def batches(
    labels: Sequence[str], classified: Mapping[str, Any], round_no: int, stage: str = STAGE
) -> list[tuple[str, list[str]]]:
    """Sites by country, then name, cut into batches of `BATCH_SIZE` - one agent reads one
    country's registers for a whole batch."""
    ordered = sorted(
        labels,
        key=lambda s: (classified[s]["country"] or "", classified[s]["name"].casefold(), s),
    )
    return [
        (f"{stage}-r{round_no}-b{number + 1:04d}", ordered[i : i + BATCH_SIZE])
        for number, i in enumerate(range(0, len(ordered), BATCH_SIZE))
    ]


def _answering_model(run: Path, model: str | None) -> str | None:
    """The model id this round's answers are recorded under, or `None` when the rule's own brief
    asks each agent to name what it runs as (WD1). It must be one `opus_handoff.ANSWER_MODELS`
    knows, because the brief writes it into the recording command and the journal keeps it - a
    typo here would be a stamp no model ever earned (2026-10-04: WD3's round 1 lost eight answers
    to an invented stamp, "wrong model", 0 of 91 counted)."""
    rule = R.read_rule(run)
    if model is None:
        named = BRIEF_PARTS[rule.name]["model"]
        return None if named.startswith("<") else named
    if model not in set(OH.ANSWER_MODELS):
        raise HandoffStepError(
            f"{model!r} is not one of the model ids an answer may carry: {sorted(OH.ANSWER_MODELS)}"
        )
    return model


def _export_round(
    run: Path,
    handoff: Path,
    round_no: int,
    fields_of: Mapping[str, Sequence[str]],
    notes: Mapping[str, Mapping[str, str]],
    model: str | None = None,
) -> dict[str, Any]:
    rule = R.read_rule(run)
    answering = _answering_model(run, model)
    rounds = read_rounds(run)
    if any(r["round"] == round_no for r in rounds):
        raise HandoffStepError(f"round {round_no} is already exported")
    target = _resolve(handoff)
    if target.exists() and any(target.iterdir()):
        raise HandoffStepError(f"{handoff} is not empty: a round gets a directory of its own")
    classified = read_classified(run)
    hints = read_hints(run)
    groups = batches(list(fields_of), classified, round_no, rule.stage)
    for batch_id, labels in groups:
        for label in labels:
            OH.export(
                target,
                batch_id=batch_id,
                stage=rule.stage,
                label=label,
                field="+".join(fields_of[label]),
                prompt=render_prompt(
                    classified[label], fields_of[label], notes.get(label), rule, hints.get(label)
                ),
            )
    record = {
        "round": round_no,
        "handoff": _shown(handoff),
        "model": answering,
        "batches": dict(groups),
        "fields": {label: list(fields_of[label]) for label in sorted(fields_of)},
        "notes": {label: dict(notes[label]) for label in sorted(notes)},
        "exported_at": H.now(),
    }
    _write_jsonl(run / ROUNDS_FILE, [*rounds, record])
    return {
        "round": round_no,
        "handoff": record["handoff"],
        "sites": len(fields_of),
        "fields": sum(len(f) for f in fields_of.values()),
        "batches": len(groups),
    }


def _cut(
    classified: dict[str, Any], fields_of: dict[str, list[str]], sites: frozenset[str]
) -> dict[str, list[str]]:
    """The named sites' questions, or a refusal naming what cannot be asked. A cut file that drifted
    from the run would otherwise export fewer batches than it claims, silently."""
    if not sites:
        raise HandoffStepError("a cut that names no site asks nothing - name at least one")
    unknown = sorted(set(sites) - set(classified))
    if unknown:
        raise HandoffStepError(
            f"the cut names {len(unknown)} site(s) the run does not hold, e.g. {unknown[0]!r}"
        )
    silent = sorted(set(sites) - set(fields_of))
    if silent:
        raise HandoffStepError(
            f"the cut names {len(silent)} site(s) with nothing open, e.g. {silent[0]!r}"
        )
    return {sid: fields_of[sid] for sid in sorted(sites)}


def _read_site_ids(path: Path) -> frozenset[str]:
    """The ids of a cut file, one per line. An unreadable file is refused by name."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HandoffStepError(f"the cut file {path} cannot be read: {exc}") from exc
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


def export(
    run: Path, handoff: Path, model: str | None = None, *, sites: frozenset[str] | None = None
) -> dict[str, Any]:
    """Round 0: every site with a field in CONFLICT or MISSING or flagged, with exactly those fields.

    `model` is the stamp the round's answers may carry, stored in the round's record and named by
    every brief of it; the default is what the run's rule names. It is the only place a model id
    reaches an answer, so a lane answered by another model says so here (2026-10-04).

    `sites` cuts the round down to the named sites of this run, and the run keeps every site it
    classified: a round's own record lists the questions it asked, so a cut shows up as the
    questions that are not in it. A site the run does not hold, or holds with nothing open, is
    refused by name instead of being dropped. The owner's cut of 2026-10-04: 18 batches for the 144
    live sites whose period cell is empty, out of a run that holds 2,636."""
    if read_rounds(run):
        raise HandoffStepError("round 0 is exported already - re-asks go through export-reask")
    classified = read_classified(run)
    fields_of = {sid: line["asked"] for sid, line in classified.items() if line["asked"]}
    if sites is not None:
        fields_of = _cut(classified, fields_of, sites)
    return _export_round(run, handoff, 0, fields_of, {}, model)


def export_reask(run: Path, handoff: Path) -> dict[str, Any]:
    rounds = read_rounds(run)
    if not rounds:
        raise HandoffStepError("nothing was exported")
    last = max(r["round"] for r in rounds)
    reask_path = run / REASK_FILE
    if not reask_path.exists():
        raise HandoffStepError(f"import round {last} before a re-ask")
    reask = json.loads(reask_path.read_text(encoding="utf-8"))
    if reask["after_round"] != last:
        raise HandoffStepError(f"import round {last} before a re-ask")
    if not reask["fields"]:
        raise HandoffStepError("nothing to ask again")
    if last >= MAX_ROUND:
        raise HandoffStepError(
            f"round {last} was the last: a field is asked at most {MAX_ROUND + 1} times"
        )
    attempts = _read_jsonl(run / ATTEMPTS_FILE)
    counted = {(a["site_id"], a["field"]) for a in attempts if a["counted"]}
    named = [(site, field) for site, fields in reask["fields"].items() for field in fields]
    stale = sorted(f"{site}/{field}" for site, field in named if (site, field) in counted)
    if stale:
        raise HandoffStepError(
            f"REASK.json names {len(stale)} field(s) with a counted answer ({stale[:3]}): import "
            "again - a counted field is never asked again"
        )
    reasons = {(a["site_id"], a["field"]): a["reason"] for a in attempts if a["round"] == last}
    notes = {
        site: {field: str(reasons[(site, field)]) for field in fields}
        for site, fields in reask["fields"].items()
    }
    # a re-ask goes to a new agent of the same lane, so it carries the round's stamp forward
    carried = next((r.get("model") for r in rounds if r["round"] == last), None)
    return _export_round(run, handoff, last + 1, reask["fields"], notes, carried)


# ------------------------------------------------------------------------------ the agent's aids
def _round_of(run: Path, handoff: Path) -> dict[str, Any]:
    wanted = _resolve(handoff).resolve()
    for record in read_rounds(run):
        if _resolve(Path(record["handoff"])).resolve() == wanted:
            return record
    raise HandoffStepError(f"{handoff} is not the directory of an exported round of {run}")


def check_answer(run: Path, handoff: Path, batch_id: str, label: str, text: str) -> dict[str, Any]:
    """The shape and page-free problems of one answer, per field - nothing is fetched."""
    record = _round_of(run, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise HandoffStepError(f"{batch_id}/{label} is no question of {handoff}")
    line = read_classified(run)[label]
    try:
        checked = A.check_shape(text, record["fields"][label], line, R.read_rule(run))
    except AnswerError as exc:
        return {"ok": False, "problems": {"answer": str(exc)}}
    problems = {f: a for f, a in checked.items() if isinstance(a, str)}
    return {"ok": not problems, "problems": problems}


BRIEF = """You are {role} {batch} of the {lane} structured-field {work}. You answer {count} \
question(s), each about another site. Answer each one on its own, as if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" and its "prompt_path" (relative to {handoff}). Open no other file of the repository - \
no other batch, nothing else under output/ or docs/, no database, no git history. {evidence}

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide each field, exactly as the prompt asks. Copy every quote from the \
page itself, character for character.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it (nothing is fetched; the quotes are checked against their pages at import):
   ./.venv/Scripts/python.exe scripts/remediation/fields/handoff.py check-answer --run {run} \
--handoff {handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problems per field, if any: fix the answer, never the finding - a field you cannot \
source {unsourced}.
5. Record it - an answer is written once:
   ./.venv/Scripts/python.exe scripts/remediation/opus_handoff.py answer --dir {handoff} \
--batch-id {batch} --stage {stage} --label <label> --answered-by {batch} \
--model {model} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


#: What differs between the rules' briefs: who answers, where the evidence comes from, what a field
#: nobody can source is, and the model id the answer is recorded with (owner decision 2026-10-01:
#: every answering agent of WD3 is Sonnet 5.5; WD1's agents named what they ran as).
BRIEF_PARTS = {
    R.TWO_FAMILIES.name: {
        "role": "Opus researcher",
        "lane": "WD1",
        "work": "repair",
        "evidence": (
            "Your evidence is your own web research, as each prompt says: heritage registers, "
            "Wikidata, Wikipedia in any language, Pleiades, excavation reports, museum and "
            "university pages."
        ),
        "unsourced": 'is "clear" (or "unresolved" for coordinates)',
        "model": "<the model id you run as: claude-sonnet-5-5 or claude-opus-5-5>",
    },
    R.ONE_FAMILY.name: {
        "role": "Sonnet researcher",
        "lane": "WD3",
        "work": "fill",
        "evidence": (
            "Your evidence is your own web research, as each prompt says: start from the site's "
            "Wikidata item, its Wikipedia article in any language, its stored source_url and the "
            "pages listed in the prompt, then reputable sources - heritage registers, museums, "
            "universities, journals, Pleiades, excavation reports. Never ancientnerds.com, AI "
            "content farms or Wikipedia mirrors."
        ),
        "unsourced": 'is "unresolved"',
        "model": "claude-sonnet-5-5",
    },
    R.ONE_FAMILY_PERIOD.name: {
        "role": "Sonnet researcher",
        "lane": "WD4",
        "work": "fill",
        "evidence": (
            "Your evidence is your own web research, as each prompt says: start from the site's "
            "Wikidata item, its Wikipedia article in any language, its stored source_url and the "
            "pages listed in the prompt, then reputable sources - heritage registers, museums, "
            "universities, journals, Pleiades, excavation reports. Never ancientnerds.com, AI "
            "content farms or Wikipedia mirrors."
        ),
        "unsourced": 'is "unresolved"',
        "model": "claude-sonnet-5-5",
    },
    R.RECHECK.name: {
        "role": "Sonnet researcher",
        "lane": "WD5",
        "work": "re-check",
        "evidence": (
            "Your evidence is your own web research, as each prompt says: start from the site's "
            "Wikidata item, its Wikipedia article in any language, its stored source_url and the "
            "pages listed in the prompt, then reputable sources - heritage registers, museums, "
            "universities, journals, Pleiades, excavation reports. Never ancientnerds.com, AI "
            "content farms or Wikipedia mirrors."
        ),
        "unsourced": 'is "unresolved"',
        "model": "claude-sonnet-5-5",
    },
}


def brief(run: Path, handoff: Path, batch_id: str) -> str:
    record = _round_of(run, handoff)
    if batch_id not in record["batches"]:
        raise HandoffStepError(f"{batch_id} is no batch of {handoff}")
    rule = R.read_rule(run)
    shown = _shown(handoff)
    # the stamp the round was exported with; a round exported before this was recorded keeps the
    # rule's own, which is what its answers were counted under
    parts = {
        **BRIEF_PARTS[rule.name],
        "model": record.get("model") or BRIEF_PARTS[rule.name]["model"],
    }
    if record.get("model"):
        # the round names the model, so the role must not claim to be another one
        parts["role"] = "researcher"
    return BRIEF.format(
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=_shown(run),
        stage=rule.stage,
        **parts,
    )


# ------------------------------------------------------------------------------ import
def transient(meta: Mapping[str, Any]) -> bool:
    """Whether a kept fetch failed for a reason that may pass: no answer, 429, a server error."""
    status = meta["status"]
    return status is None or int(status) == 429 or int(status) >= 500


def unreadable(meta: Mapping[str, Any]) -> bool:
    """Whether a kept fetch says nothing about the page: no answer, a refusal of the checker
    (`REFUSED_STATUS`), a server error - as against a 404, which says the page is not there."""
    status = meta["status"]
    return status is None or int(status) in REFUSED_STATUS or int(status) >= 500


def _page_meta(url: str, pages: Path) -> dict[str, Any]:
    return json.loads((pages / f"{Q.url_key(url)}.json").read_text(encoding="utf-8"))


def forget_transient(urls: Iterable[str], pages: Path) -> int:
    """Remove the kept fetch of each URL whose fetch failed transiently, so `Q.collect` asks it
    again; how many were removed. The record goes first, then its body (`Q.store_page` writes them
    the other way round: a record always names a body)."""
    forgotten = 0
    for url in sorted({Q.canonical_url(u)[0] for u in urls}):
        meta_path = pages / f"{Q.url_key(url)}.json"
        if meta_path.exists() and transient(json.loads(meta_path.read_text(encoding="utf-8"))):
            meta_path.unlink()
            (pages / f"{Q.url_key(url)}.body").unlink()
            forgotten += 1
    return forgotten


def _unreadable_quote(result: Mapping[str, Any], pages: Path) -> bool:
    """Whether a failed quote failed only because the checker could not read its page."""
    if result["outcome"] == Q.UNREADABLE:
        return True
    return result["outcome"] == Q.FETCH_FAILED and unreadable(_page_meta(result["source"], pages))


def value_page(value: str, pages: Path, net: Fetcher | None) -> dict[str, Any]:
    """Whether a source_url value is a served page of its own (`problem` is None, else why not,
    and whether only the checker's reading failed) and, for a Wikipedia article, the item it names -
    what a site_external_ids pass re-derives the site's ids from (`plan.py handoff`)."""
    meta = _page_meta(value, pages)
    out: dict[str, Any] = {
        "problem": None,
        "unreadable": False,
        "lang": None,
        "resolved_title": None,
        "wikibase_item": None,
    }
    if meta["status"] is None or not 200 <= int(meta["status"]) < 300:
        shown = meta["error"] or f"HTTP {meta['status']}"
        return {
            **out,
            "problem": f"the value's page was not served: {shown}",
            "unreadable": unreadable(meta),
        }
    if not C.same_page(value, str(meta["final_url"])):
        return {**out, "problem": f"the value's page redirects to {meta['final_url']}"}
    titled = wikipedia_title(value)
    if titled is None:
        return out
    if net is None:
        raise HandoffStepError("a Wikipedia value needs the API client to be resolved")
    lang, title = titled
    record = H.resolve_wiki_titles(net, lang, [title])[title]
    out.update(
        lang=lang, resolved_title=record["resolved_title"], wikibase_item=record["wikibase_item"]
    )
    if record["missing"] or record["invalid"]:
        return {**out, "problem": "the value's article does not exist"}
    if record["redirected"]:
        return {
            **out,
            "problem": f"the value is a redirect to {record['resolved_title']!r}: give the "
            "article's own URL",
        }
    if record["disambiguation"]:
        return {**out, "problem": "the value is a disambiguation page"}
    return out


def import_rounds(
    run: Path,
    *,
    client: httpx.Client | None = None,
    net: Fetcher | None = None,
    pace: float = Q.PACE_SECONDS,
) -> dict[str, Any]:
    """Every round's answers: validated, parsed, quote-checked, decided."""
    rule = R.read_rule(run)
    classified = read_classified(run)
    hints = read_hints(run)
    rounds = sorted(read_rounds(run), key=lambda r: r["round"])
    if not rounds:
        raise HandoffStepError("nothing was exported")
    attempts: list[dict[str, Any]] = []
    for record in rounds:
        handoff = _resolve(Path(record["handoff"]))
        check = OH.validate(handoff)
        if not check.ok:
            raise HandoffStepError(
                f"{record['handoff']}: {len(check.missing)} missing, {len(check.stale)} stale, "
                f"{len(check.malformed)} malformed, {len(check.orphans)} orphan answer(s) - every "
                "answer is validated before anything is imported"
            )
        manifest = {(line["batch_id"], line["label"]): line for line in OH.manifest(handoff)}
        asked = {(b, label) for b, labels in record["batches"].items() for label in labels}
        if set(manifest) != asked:
            raise HandoffStepError(f"{record['handoff']}: the manifest is not the round's record")
        for (batch_id, label), line in sorted(manifest.items()):
            fields = record["fields"][label]
            prompt = render_prompt(
                classified[label], fields, record["notes"].get(label), rule, hints.get(label)
            )
            if OH.prompt_sha256(prompt) != line["prompt_sha256"]:
                raise HandoffStepError(
                    f"{batch_id}/{label}: the exported prompt is not this question's"
                )
            answer = OH.read_answer(
                handoff, batch_id=batch_id, stage=rule.stage, label=label, prompt=prompt
            )
            try:
                checked = A.check_shape(answer.text, fields, classified[label], rule)
            except AnswerError as exc:
                checked = dict.fromkeys(fields, f"malformed answer: {exc}")
            for field in fields:
                parsed = checked[field]
                attempts.append(
                    {
                        "round": record["round"],
                        "batch_id": batch_id,
                        "site_id": label,
                        "field": field,
                        "answered_by": answer.answered_by,
                        "model": answer.model,
                        "answered_at": answer.answered_at,
                        "answer": None if isinstance(parsed, str) else parsed.to_dict(),
                        "problem": parsed if isinstance(parsed, str) else None,
                    }
                )

    counted_before = {
        (a["round"], a["site_id"], a["field"])
        for a in _read_jsonl(run / ATTEMPTS_FILE)
        if a["counted"]
    }
    pages = run / PAGES_DIR
    # every quoted page, and every source_url value itself: a quote may spell the value's page
    # unencoded, the value is written percent-encoded - two keys of the page cache
    urls = sorted(
        {q[0] for a in attempts if a["answer"] for q in a["answer"]["quotes"]}
        | {
            str(a["answer"]["value"])
            for a in attempts
            if a["answer"]
            and a["field"] == "source_url"
            and a["answer"]["decision"] in (A.KEEP, A.REPLACE)
        }
    )
    refetched = forget_transient(urls, pages)
    if urls:
        if client is None:
            with H.open_client() as own:
                Q.collect(urls, pages, own, now=H.now, pace=pace)
        else:
            Q.collect(urls, pages, client, now=H.now, pace=pace)
    library = Q.Library(REPO, pages)
    own_net = net is None and any(
        a["answer"] and a["field"] == "source_url" and wikipedia_title(str(a["answer"]["value"]))
        for a in attempts
    )
    api = H.open_fetcher(run) if own_net else net
    try:
        for attempt in attempts:
            answer = attempt["answer"]
            if answer is None:
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
                        {"change_key": attempt["site_id"], "evidence_files": []},
                        library,
                    )
                )
                for u, q in answer["quotes"]
            ]
            failed = [r for r in results if r["outcome"] != Q.FOUND]
            reason, blind, page = None, False, None
            if failed:
                first = failed[0]
                detail = f" ({first['detail']})" if first["detail"] else ""
                reason = f"quote {first['outcome']}: {first['source']}{detail}"
                blind = all(_unreadable_quote(r, pages) for r in failed)
            elif attempt["field"] == "source_url" and answer["decision"] in (A.KEEP, A.REPLACE):
                page = value_page(str(answer["value"]), pages, api)
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

    decisions, waiting = _decide(attempts, classified, counted_before, rule)
    _write_jsonl(run / ATTEMPTS_FILE, attempts)
    _write_jsonl(run / DECISIONS_FILE, decisions)
    _write_json(run / REASK_FILE, {"after_round": rounds[-1]["round"], "fields": waiting})
    _write_jsonl(run / PAGES_INDEX, Q.page_index(urls, pages) if urls else [])
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
            sorted(Counter(f"{d['field']}:{d['decision']}" for d in decisions).items())
        ),
        "waiting_sites": len(waiting),
        "waiting_fields": sum(len(v) for v in waiting.values()),
        "urls": len(urls),
        "refetched": refetched,
    }


def _decide(
    attempts: Sequence[Mapping[str, Any]],
    classified: Mapping[str, Mapping[str, Any]],
    counted_before: Iterable[tuple[int, str, str]],
    rule: R.Rule = R.DEFAULT,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Each asked (site, field): its latest counted answer, or - after the last round - exhausted.
    Under WD1's rule: held when the last answer failed only on unreadable pages (and always for
    coordinates, which cannot be cleared), else cleared. Under WD3's, which never clears: held when
    it failed only on unreadable pages, else unresolved - the field stays as it is, for the owner's
    list. `counted_before`: the (round, site, field) that counted at the last import - each must
    count still."""
    before = set(counted_before)
    by_cell: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for attempt in attempts:
        by_cell.setdefault((attempt["site_id"], attempt["field"]), []).append(attempt)
    decisions: list[dict[str, Any]] = []
    waiting: dict[str, list[str]] = {}
    for (site, field), tries in sorted(by_cell.items()):
        tries = sorted(tries, key=lambda a: a["round"])
        if [a["round"] for a in tries] != sorted({a["round"] for a in tries}):
            raise HandoffStepError(f"{site}/{field}: asked twice in one round")
        for attempt in tries:
            if (attempt["round"], site, field) in before and not attempt["counted"]:
                raise HandoffStepError(
                    f"{site}/{field}: round {attempt['round']}'s answer counted at the last import "
                    f"and no longer counts ({attempt['reason']}) - the kept pages or the answers "
                    "changed under the run"
                )
        counted = [a for a in tries if a["counted"]]
        line = classified[site]
        base = {
            "site_id": site,
            "name": line["name"],
            "field": field,
            "status": line["fields"][field]["status"],
            "stored": line["fields"][field]["stored"],
            "asked": len(tries),
        }
        if counted:
            chosen = counted[-1]
            answer = chosen["answer"]
            decisions.append(
                {
                    **base,
                    "decision": answer["decision"],
                    "value": answer["value"],
                    "via": COUNTED,
                    "round": chosen["round"],
                    "counted_rounds": [a["round"] for a in counted],
                    "answered_by": chosen["answered_by"],
                    "model": chosen["model"],
                    "quotes": chosen["quotes"],
                    "reasoning": answer["reasoning"],
                    "value_page": chosen["value_page"],
                }
            )
        elif tries[-1]["round"] >= MAX_ROUND:
            if tries[-1]["unreadable"] and (not rule.clearable or field != "coordinates"):
                outcome = HELD
            elif field == "coordinates" or not rule.clearable:
                outcome = A.UNRESOLVED
            else:
                outcome = A.CLEAR
            decisions.append(
                {
                    **base,
                    "decision": outcome,
                    "value": None,
                    "via": EXHAUSTED,
                    "round": tries[-1]["round"],
                    "counted_rounds": [],
                    "answered_by": None,
                    "model": None,
                    "quotes": [],
                    "reasoning": f"no counted answer in {len(tries)} rounds: "
                    + "; ".join(str(a["reason"]) for a in tries),
                    "value_page": None,
                }
            )
        else:
            waiting.setdefault(site, []).append(field)
    return decisions, {site: sorted(f, key=C.FIELDS.index) for site, f in sorted(waiting.items())}


def pilot_report(run: Path) -> dict[str, Any]:
    """A finished run's exhausted fields - overall and per country - against the pilot's gate:
    PILOT.json with the verdict PASS or STOP. Under WD1's rule the gate is the share cleared on
    exhaustion (`PILOT_MAX_RATE`, `PILOT_MAX_COUNTRY_RATE` for a country with at least
    `PILOT_MIN_FIELDS` fields); under WD3's, which clears nothing, the share held because the
    checker could not read the cited pages (`PILOT_MAX_HELD_RATE`, `PILOT_MAX_COUNTRY_HELD_RATE`),
    and the share of every `unresolved` decision, whatever its `via`, is reported beside it
    (`unresolved_rate`), and the share of the fields of sites with a Wikidata item or an English
    Wikipedia article that an agent answered `unresolved` outright (`hinted_unresolved_rate`) is
    gated (`PILOT_MAX_HINTED_UNRESOLVED_RATE`): a lazy pilot cannot pass as a thin population."""
    rule = R.read_rule(run)
    reask = json.loads((run / REASK_FILE).read_text(encoding="utf-8"))
    if reask["fields"]:
        waiting = sum(len(v) for v in reask["fields"].values())
        raise HandoffStepError(
            f"{waiting} field(s) still wait for a re-ask: a pilot is reported when every field is "
            "decided"
        )
    classified = read_classified(run)
    tallies: dict[str, Counter[str]] = {}
    for d in _read_jsonl(run / DECISIONS_FILE):
        tally = tallies.setdefault(str(classified[d["site_id"]]["country"]), Counter())
        tally["fields"] += 1
        hinted = bool(classified[d["site_id"]]["qid"] or classified[d["site_id"]]["enwiki"])
        tally["hinted"] += hinted
        if d["decision"] == A.UNRESOLVED:
            tally["unresolved"] += 1
            if d["via"] == COUNTED:
                tally["hinted_unresolved"] += hinted
        if d["via"] == EXHAUSTED:
            tally[
                "exhausted_"
                + {A.CLEAR: "clear", A.UNRESOLVED: "unresolved"}.get(d["decision"], "held")
            ] += 1

    def row(tally: Counter[str]) -> dict[str, Any]:
        figures = {
            "fields": tally["fields"],
            "exhausted_clear": tally["exhausted_clear"],
            "exhausted_held": tally["exhausted_held"],
        }
        if rule.clearable:
            return {**figures, "clear_rate": round(tally["exhausted_clear"] / tally["fields"], 3)}
        return {
            **figures,
            "exhausted_unresolved": tally["exhausted_unresolved"],
            "unresolved": tally["unresolved"],
            "hinted": tally["hinted"],
            "hinted_unresolved": tally["hinted_unresolved"],
            "held_rate": round(tally["exhausted_held"] / tally["fields"], 3),
            "unresolved_rate": round(tally["unresolved"] / tally["fields"], 3),
            "hinted_unresolved_rate": (
                round(tally["hinted_unresolved"] / tally["hinted"], 3) if tally["hinted"] else 0.0
            ),
        }

    # the gated share, what it is called in a message, and its two lines
    gated, said, max_rate, max_country = (
        ("clear_rate", "cleared", PILOT_MAX_RATE, PILOT_MAX_COUNTRY_RATE)
        if rule.clearable
        else ("held_rate", "held as unreadable", PILOT_MAX_HELD_RATE, PILOT_MAX_COUNTRY_HELD_RATE)
    )
    count_key = "exhausted_clear" if rule.clearable else "exhausted_held"
    overall = row(sum(tallies.values(), Counter()))
    stopped_by = []
    if overall[gated] > max_rate:
        stopped_by.append(
            f"overall: {overall[count_key]} of {overall['fields']} fields {said} on "
            f"exhaustion ({overall[gated]})"
        )
    if (
        not rule.clearable
        and overall["hinted"] >= PILOT_MIN_FIELDS
        and overall["hinted_unresolved_rate"] > PILOT_MAX_HINTED_UNRESOLVED_RATE
    ):
        stopped_by.append(
            f"overall: {overall['hinted_unresolved']} of {overall['hinted']} fields of sites with "
            "a Wikidata item or an English Wikipedia article answered `unresolved` outright "
            f"({overall['hinted_unresolved_rate']}) - spot-check the agents' research"
        )
    countries = {country: row(tally) for country, tally in sorted(tallies.items())}
    for country, figures in countries.items():
        if figures["fields"] >= PILOT_MIN_FIELDS and figures[gated] > max_country:
            stopped_by.append(
                f"{country}: {figures[count_key]} of {figures['fields']} fields {said} on "
                f"exhaustion ({figures[gated]})"
            )
    report = {
        "verdict": "STOP" if stopped_by else "PASS",
        "stopped_by": stopped_by,
        "overall": overall,
        "countries": countries,
        "gate": {
            "rule": rule.name,
            "measure": gated,
            "max_rate": max_rate,
            "max_country_rate": max_country,
            "max_hinted_unresolved_rate": None
            if rule.clearable
            else PILOT_MAX_HINTED_UNRESOLVED_RATE,
            "min_country_fields": PILOT_MIN_FIELDS,
        },
        "reported_at": H.now(),
    }
    _write_json(run / PILOT_FILE, report)
    return report


def status(run: Path) -> dict[str, Any]:
    rounds = read_rounds(run)
    decisions = _read_jsonl(run / DECISIONS_FILE)
    return {
        "rounds": [
            {
                "round": r["round"],
                "handoff": r["handoff"],
                "batches": len(r["batches"]),
                "sites": len(r["fields"]),
            }
            for r in rounds
        ],
        "decisions": dict(
            sorted(Counter(f"{d['field']}:{d['decision']}:{d['via']}" for d in decisions).items())
        ),
    }


# ------------------------------------------------------------------------------ the CLI
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {}
    for name in (
        "export",
        "export-reask",
        "brief",
        "check-answer",
        "import",
        "pilot-report",
        "status",
    ):
        commands[name] = sub.add_parser(name)
        commands[name].add_argument("--run", type=Path, default=C.DEFAULT_OUT)
    for name in ("export", "export-reask", "brief", "check-answer"):
        commands[name].add_argument("--handoff", type=Path, required=True)
    for name in ("brief", "check-answer"):
        commands[name].add_argument("--batch-id", required=True)
    commands["export"].add_argument(
        "--model",
        help="the stamp this round's answers may carry (one of opus_handoff.ANSWER_MODELS); "
        "default: what the run's rule names. The recording command in every brief names it, and it "
        "is what the journal keeps.",
    )
    commands["export"].add_argument(
        "--sites",
        type=Path,
        help="a file of site ids, one per line: this round asks only these sites of the run, and "
        "the run keeps the rest (the owner's cut of 2026-10-04: 18 of 330 batches)",
    )
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", type=Path, required=True)
    commands["import"].add_argument("--pace", type=float, default=Q.PACE_SECONDS)
    args = parser.parse_args(argv)
    run = _resolve(args.run)
    try:
        if args.command == "export":
            result: Any = export(
                run,
                args.handoff,
                args.model,
                sites=None if args.sites is None else _read_site_ids(_resolve(args.sites)),
            )
        elif args.command == "export-reask":
            result = export_reask(run, args.handoff)
        elif args.command == "brief":
            print(brief(run, args.handoff, args.batch_id))
            return 0
        elif args.command == "check-answer":
            text = _resolve(args.text_file).read_bytes().decode("utf-8")
            result = check_answer(run, args.handoff, args.batch_id, args.label, text)
            print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
            return 0 if result["ok"] else 1
        elif args.command == "import":
            result = import_rounds(run, pace=args.pace)
        elif args.command == "pilot-report":
            result = pilot_report(run)
            print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
            return 0 if result["verdict"] == "PASS" else 1
        else:
            result = status(run)
    except (HandoffStepError, OH.HandoffError, Q.AuditError, H.HarvestError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
