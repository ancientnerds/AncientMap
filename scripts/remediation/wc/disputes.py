"""Lane E's dispute screen (owner decision D21 of 2026-10-08, orchestrator decision X2).

D21: a disputed site's description names both positions with sources, and the card asserts neither.
X2: it applies to shown sites (the retired ones - the Baltic Sea Anomaly, Yonaguni, the Bosnian
pyramids, Richat - stay retired). The screen is four steps, each a command; the model makes every
judgement, code screens, validates, fetches and checks:

    candidates        a shown site is a candidate when its description, its English Wikipedia text
                      (the shared cache), its Wikipedia categories (`fetch-categories`) or its site
                      type carry a dispute signal. A screen, not a verdict: it is meant to be broad.
    export / import   RESEARCH: per candidate, one `field_researcher` (Sonnet, high) answers whether
                      reputable sources hold two positions about the site, gives both with verbatim
                      quotes, and names the description sentences that state one side as fact. The
                      import fetches every page itself and checks every quote (`answers.quote_outcomes`):
                      a position that no checked quote supports ends the candidate (`unverified`).
    adjudicate-*      an independent `adversarial` (Opus, high) looks for the reasons it is NOT a
                      dispute, and confirms the sentences that assert a side. Only a `dispute`
                      verdict reaches the outputs.
    outputs           `DISPUTES.jsonl`, the briefs `export --enrich --disputes` appends both positions
                      from (`enrich.DISPUTE_KEYS`), and `DISPUTE_DEFECTS.jsonl`, one
                      `DESCRIPTION_DEFECTS.jsonl`-shaped line per sentence that states a side as
                      fact - the input of `cli.py defect-sites`, so a `wc-list` pass reads the dispute
                      as a reported claim (`prompts_sonnet.DEFECTS_HEAD`) and drops that sentence.

    PY=.venv/Scripts/python.exe ; D="$PY scripts/remediation/wc/disputes.py" ; C="$PY scripts/remediation/wc/cli.py"
    $C read --run-dir R                                   # the run's one read (ROWS.jsonl)
    $D fetch-categories --run-dir R                       # CATEGORIES.json (the MediaWiki API, a few dozen GETs)
    $D candidates --run-dir R [--wiki-cache DIR]          # CANDIDATES.jsonl
    $D export --run-dir R --handoff H                     # research questions
    $D brief --run-dir R --handoff H --batch-id B         # per batch: one Sonnet agent
    $D check-answer --run-dir R --handoff H --batch-id B --label SITE --text-file F
    $D import --run-dir R --handoff H                     # RESEARCH.jsonl
    $D adjudicate-export --run-dir R --handoff H2         # new agents
    $D adjudicate-brief ... ; $D adjudicate-import --run-dir R --handoff H2
    $D outputs --run-dir R                                # DISPUTES.jsonl, DISPUTE_DEFECTS.jsonl, SUMMARY.json

The screen is calibrated before its first answer (`recall`): it must flag at least 90 % of the known
positives of `KNOWN_POSITIVES` (the shown ones of the descriptions map plus the retired E3 sites,
by name) and the candidate count is reported with the share of random negatives it flags.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
import run_files as RF  # noqa: E402
from acceptance.answers import AnswerError, load_object  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import plan4, wc4  # noqa: E402

from wc import answers as A  # noqa: E402
from wc import cli  # noqa: E402
from wc import enrich as E  # noqa: E402

#: The roles of the screen (owner decision D6): the researcher is the web researcher, the adjudicator
#: the adversarial re-check; the two answer in different names.
RESEARCH_ROLE = "field_researcher"
ADJUDICATE_ROLE = "adversarial"
RESEARCH_STAGE, ADJUDICATE_STAGE = "dispute", "adjudicate"
RESEARCH_PREFIX, ADJUDICATE_PREFIX = "ds", "da"
CANDIDATES_FILE = "CANDIDATES.jsonl"
CATEGORIES_FILE = "CATEGORIES.json"
RESEARCH_FILE = "RESEARCH.jsonl"
ADJUDICATED_FILE = "ADJUDICATED.jsonl"
DISPUTES_FILE = "DISPUTES.jsonl"
DEFECTS_FILE = "DISPUTE_DEFECTS.jsonl"
SUMMARY_FILE = "SUMMARY.json"
DISPUTE_DIR = "dispute"
PAGES_DIR = "pages"
BATCH_SIZE = 5
#: The defect line's `run`, `stage` and `owner_lane`: a dispute is lane E's (WE) business.
DEFECT_STAGE = "dispute"
DEFECT_OWNER_LANE = "WE"
MAX_CLAIM_CHARS = 300
MAX_SOURCES = 4
#: How many hits the English Wikipedia text needs to flag a site (a design number: one hit is any
#: article that says "alleged" once; measured on the cache of 2026-10-08: 373 articles with one hit, 104
#: with two).
WIKI_MIN_HITS = 2

#: The signals, in code (D21: "candidates in code"). Each is a screen, measured to be broad.
DESCRIPTION_PATTERNS: Mapping[str, str] = {
    "disputed": r"\b(?:disputed|contested|controvers\w+|debated|contentious|disputes?)\b",
    "hoax": r"\b(?:hoax\w*|forger(?:y|ies)|fraud\w*|forged|spurious|fabricat\w+)\b",
    "pseudo": (
        r"\b(?:pseudo-?(?:archaeolog\w+|scien\w+|histor\w+)|fringe|esoteric|ancient astronauts?|"
        r"alternative (?:archaeolog\w+|histor\w+))\b"
    ),
    "natural": (
        r"\b(?:natural(?:ly)? (?:formation|formed|origin|feature)|"
        r"(?:likely |probably )?natural origin|geological(?:ly)? (?:origin|feature|formation))\b"
    ),
    "claimed": (
        r"\b(?:alleged\w*|purported\w*|so-called|self-proclaimed|some (?:researchers|archaeologists|"
        r"scholars|geologists|authors|scientists|historians|experts)|according to some|"
        r"claimed to (?:be|have))\b"
    ),
    "doubt": (
        r"\b(?:unproven|unverified|unconfirmed|not (?:universally|widely|generally) accepted|"
        r"remains? (?:uncertain|unclear|unresolved)|authenticity|question(?:ed|able))\b"
    ),
}
#: What the English Wikipedia text is searched for (counted, `WIKI_MIN_HITS`).
WIKIPEDIA_PATTERN = (
    r"\b(?:pseudo-?archaeolog\w+|pseudoscien\w+|pseudohistor\w+|fringe (?:theor|claim|archaeolog|"
    r"histor)\w*|controvers\w+|hoax\w*|disputed|debated|contested|alleged\w*)\b"
)
#: The enwiki categories (D21: Pseudoarchaeology, Archaeological controversies, the runestone
#: hoaxes, Lost City of Z, the rock-formation categories, and the like), matched on the category title.
CATEGORY_PATTERNS: Mapping[str, str] = {
    "pseudoarchaeology": r"^Category:Pseudo(?:archaeology|history|science)",
    "controversies": r"^Category:(?:Archaeological controversies|.*controvers)",
    "hoaxes": r"^Category:.*(?:hoax|forger)",
    "lost-city": r"^Category:(?:Lost City of Z|Lost ancient populated places)",
    "rock-formations": r"^Category:Rock formations\b",
    "fringe": r"^Category:(?:Esoteric|Unexplained phenomena|Ufology|Paranormal|Ancient astronauts|"
    r"Pre-Columbian transoceanic contact theories)",
}
#: Site types that name an anomaly or a natural feature taken for a site.
SITE_TYPE_PATTERNS: Mapping[str, str] = {
    "anomaly": r"anomal",
    "natural": r"^Natural feature$",
}

#: The known positives of the descriptions map (2026-10-08), by name, for `recall`. The first nine
#: are shown sites; the retired E3 sites are never candidates and are listed for the record only.
KNOWN_POSITIVES = (
    "Pantelleria Vecchia Bank Megalith",
    "Te Pito O Te Henua",
    "America's Stonehenge",
    "Gunung Padang Megalithic Site",
    "Dighton Rock",
    "Sakdrisi",
    "Kuhikugu",
    "Vottovaara",
    "Sacsayhuamán",
    "Carn Menyn",
    "Beglik Tash",
)
KNOWN_RETIRED = ("Baltic Sea Anomaly", "Yonaguni Monument", "Richat Structure")
MIN_RECALL = 0.9


class DisputeError(ValueError):
    """The run, a round or an answer is not what the screen needs: the command stops."""


# ------------------------------------------------------------------------------ the screen
def candidate_reasons(
    row: Mapping[str, Any], *, wikipedia: str | None, categories: Sequence[str], wiki_min_hits: int
) -> dict[str, list[str]]:
    """The signals a shown site carries, by source (`description`, `wikipedia`, `category`,
    `site_type`), each the names of the patterns that hit. Empty: not a candidate."""
    reasons: dict[str, list[str]] = {}
    description = row["description"] or ""
    hits = [
        name
        for name, pattern in DESCRIPTION_PATTERNS.items()
        if re.search(pattern, description, re.I)
    ]
    if hits:
        reasons["description"] = hits
    if (
        wikipedia is not None
        and len(re.findall(WIKIPEDIA_PATTERN, wikipedia, re.I)) >= wiki_min_hits
    ):
        reasons["wikipedia"] = ["controversy-words"]
    cats = [
        name
        for name, pattern in CATEGORY_PATTERNS.items()
        if any(re.search(pattern, category) for category in categories)
    ]
    if cats:
        reasons["category"] = cats
    types = [
        name
        for name, pattern in SITE_TYPE_PATTERNS.items()
        if re.search(pattern, row["site_type"] or "", re.I)
    ]
    if types:
        reasons["site_type"] = types
    return reasons


def wikipedia_texts(cache: Path) -> dict[str, str]:
    """site id -> the English Wikipedia text of the shared cache (`wiki_cache/INDEX.jsonl`, one
    `{site_id, lang, title, file}` line per page; the page file holds `{resolved_title, revid, text}`)."""
    texts: dict[str, str] = {}
    for entry in read_jsonl(cache / "INDEX.jsonl"):
        if entry["lang"] != "en":
            continue
        page = json.loads((cache / entry["file"].replace("\\", "/")).read_text(encoding="utf-8"))
        texts[entry["site_id"]] = page["text"]
    return texts


def cmd_candidates(
    run: Path, *, wiki_cache: Path | None, wiki_min_hits: int = WIKI_MIN_HITS
) -> dict[str, Any]:
    """`CANDIDATES.jsonl`: every shown curated site of the read (not retired, with a description
    that splits into sentences) that carries a dispute signal. Reads `CATEGORIES.json` when
    `fetch-categories` made it."""
    rows = read_jsonl(run / cli.ROWS_FILE)
    categories_path = run / CATEGORIES_FILE
    categories: dict[str, list[str]] = (
        json.loads(categories_path.read_text(encoding="utf-8")) if categories_path.exists() else {}
    )
    texts = wikipedia_texts(wiki_cache) if wiki_cache is not None else {}
    candidates: list[dict[str, Any]] = []
    listed: Counter[str] = Counter()
    signals: Counter[str] = Counter()
    for row in sorted(rows, key=lambda r: r["id"]):
        if row["scope_status"] == "retired":
            listed["retired"] += 1
            continue
        if wc4.is_empty(row["description"]):
            listed["no-description"] += 1
            continue
        reasons = candidate_reasons(
            row,
            wikipedia=texts.get(row["id"]),
            categories=categories.get(row["id"], ()),
            wiki_min_hits=wiki_min_hits,
        )
        if not reasons:
            continue
        try:
            sentences = wc4.checked_sentences(row["description"])
        except wc4.WcError:
            listed["not-splittable"] += 1
            continue
        site = plan4.plan_site(
            {k: v for k, v in row.items() if k != "scope_status"}, flags=frozenset()
        )
        signals.update(reasons.keys())
        candidates.append(
            {
                "site_id": site.site_id,
                "name": site.name,
                "reasons": reasons,
                "sentences": list(sentences),
                "desc_sha256": row["description_sha256"],
                "plan_site": site.to_dict(),
            }
        )
    RF.write_jsonl(run / CANDIDATES_FILE, candidates)
    return {
        "candidates": len(candidates),
        "by_signal": dict(sorted(signals.items())),
        "listed": dict(sorted(listed.items())),
        "categories": len(categories),
        "wikipedia_texts": len(texts),
        "wiki_min_hits": wiki_min_hits,
    }


def cmd_recall(run: Path, *, known: Sequence[str] = KNOWN_POSITIVES) -> dict[str, Any]:
    """The screen's recall on the known positives (by site name) among the run's candidates, and the
    names it missed. The screen is calibrated before the research answers a question: below
    `MIN_RECALL` the signals are widened (a code change, then the calibration is run again)."""
    names = {entry["name"] for entry in read_jsonl(run / CANDIDATES_FILE)}
    found = [name for name in known if name in names]
    return {
        "known": len(known),
        "flagged": len(found),
        "recall": round(len(found) / len(known), 4),
        "missed": [name for name in known if name not in names],
        "passed": len(found) / len(known) >= MIN_RECALL,
    }


# ------------------------------------------------------------------------------ the categories
API_URL = "https://en.wikipedia.org/w/api.php"
CATEGORY_BATCH = 50


def fetch_categories(
    titles: Mapping[str, str], *, get: Callable[[dict[str, Any]], Mapping[str, Any]]
) -> dict[str, list[str]]:
    """site id -> the (visible) categories of its English article. `titles` is site id -> article
    title; `get` answers one MediaWiki API query (`action=query&prop=categories`) with its JSON, so a
    test serves the pages from a dict and the command from `requests`. Fifty titles to a query,
    redirects followed, `continue` answered until the query is complete; a title the API reports
    missing is an error (the cache says the article exists)."""
    by_title: dict[str, list[str]] = {}
    order = sorted(set(titles.values()))
    for start in range(0, len(order), CATEGORY_BATCH):
        chunk = order[start : start + CATEGORY_BATCH]
        params: dict[str, Any] = {
            "action": "query",
            "prop": "categories",
            "titles": "|".join(chunk),
            "cllimit": "max",
            "clshow": "!hidden",
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
        resolved = {title: title for title in chunk}
        while True:
            data = get(dict(params))
            query = data["query"]
            for step in ("normalized", "redirects"):
                for hop in query.get(step, ()):
                    for original, current in resolved.items():
                        if current == hop["from"]:
                            resolved[original] = hop["to"]
            for page in query["pages"]:
                if page.get("missing"):
                    raise DisputeError(f"the article {page['title']!r} does not exist")
                by_title.setdefault(page["title"], []).extend(
                    category["title"] for category in page.get("categories", ())
                )
            if "continue" not in data:
                break
            params.update(data["continue"])
        for original, current in resolved.items():
            by_title.setdefault(original, by_title.get(current, []))
    return {site_id: sorted(set(by_title[title])) for site_id, title in titles.items()}


def cmd_fetch_categories(
    run: Path, *, get: Callable[[dict[str, Any]], Mapping[str, Any]]
) -> dict[str, Any]:
    """`CATEGORIES.json`: the categories of every shown curated site that has an English Wikipedia
    title (the read's `enwiki_title`)."""
    rows = [
        r
        for r in read_jsonl(run / cli.ROWS_FILE)
        if r["scope_status"] != "retired" and r["enwiki_title"]
    ]
    found = fetch_categories({r["id"]: r["enwiki_title"] for r in rows}, get=get)
    RF.write_json(run / CATEGORIES_FILE, found)
    return {"sites": len(found), "with_categories": sum(bool(v) for v in found.values())}


def api_get(params: dict[str, Any], *, client: Any | None = None) -> Mapping[str, Any]:
    """One MediaWiki query over `requests` with the lanes' User-Agent."""
    own = client or A.Client()
    try:
        response = own.session.get(API_URL, params=params, timeout=Q.TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    finally:
        if client is None:
            own.close()


# ------------------------------------------------------------------------------ the research question
RESEARCH_QUESTION = """\
You research, for one site of the Ancient Nerds archaeology database, whether it is DISPUTED: whether \
reputable sources hold two incompatible positions about what the site is, how old it is, who made \
it, what it was for, whether it is a human work at all, or whether it is authentic. The page of the \
site must one day name both positions with their sources, so you give both, each on verbatim quotes. \
You research on the web yourself.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

THE DESCRIPTION AS IT STANDS
{sentences}

DECIDE
- disputed: true only if at least two positions about THIS site exist in reputable sources and a \
reputable source documents the disagreement itself (a scholarly dispute, a published controversy, an \
article that sets a claim against its scientific assessment). An old uncertainty ("c. 3000 BC") is \
no dispute, a single fringe website is none, and a position that no reputable page even reports is \
none. Otherwise false.
- position_a and position_b: the two positions as the sources state them, each with "claim" (one \
plain sentence of the position, at most {max_claim} characters), "holders" (who holds it: \
"excavation team led by X", "most geologists", at most {max_claim} characters) and "sources" - 1 to \
{max_sources} verbatim quotes {{"url", "title", "quote"}} from reputable pages that state the position \
or report that it is held. Which position is "a" does not matter.
- asserting: the sentences of the description above that state one of the positions as plain \
established fact: {{"sentence": <the number>, "asserts": "a" or "b"}}. A sentence that names both, \
or hedges, or states neither is not listed.

RULES
1. A source is reputable and independent: Wikipedia (the article itself, any language), Wikidata, \
UNESCO, national heritage registers, museums, universities, excavation reports, scholarly \
publications, established reference works. Never: ancientnerds.com; AI-generated aggregators \
(grokipedia, aroundus, mindtrip, evendo, wanderlog); Wikipedia mirrors (wikiwand, kiddle, dbpedia, \
alchetron, wiki2, everybodywiki, infogalactic, wikishire); code refuses them. The article of the site \
on Wikipedia, where it has one, is a start: read it - the cache of the pipeline holds it, and \
{wiki_hint}.
2. A quote is copied verbatim from the page at its URL - character for character; only whitespace \
may differ - 20 to 500 characters. Code fetches every URL with a plain HTTP request (no JavaScript, \
no cookies, no login) and searches the page text for the quote; a quote it does not find does not \
count, and a position with no quote that counts ends your answer as unverified. Give the page's URL \
without tracking parameters and its title: the page's main heading exactly as it stands on the page \
(for a Wikipedia article its name, not "... - Wikipedia"). These refused our fetcher when it was \
tested (HTTP 403 or a timeout): historicengland.org.uk, heritagegateway.org.uk, canmore.org.uk, \
britishmuseum.org, smarthistory.org, megalithic.co.uk - do not quote them.
3. Never decide the dispute: neither position is yours to prefer, and the description is no evidence \
for either.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "disputed": true, "position_a": {{"claim": "...", "holders": "...", \
"sources": [{{"url": "https://...", "title": "...", "quote": "..."}}]}}, "position_b": {{...}}, \
"asserting": [{{"sentence": 2, "asserts": "a"}}], "note": "what you searched, in one sentence"}}
If the site is not disputed: {{"site_id": "{site_id}", "disputed": false, "position_a": null, \
"position_b": null, "asserting": [], "note": "why not"}}. Every "note" is a short plain sentence, at \
most 600 characters.
"""

ADJUDICATE_QUESTION = """\
You adjudicate, independently, whether one site of the Ancient Nerds archaeology database is really \
DISPUTED. Another agent researched it and found two positions, each on quotes that code has found on \
their pages; you are the adversary: your task is to find the reasons it is NOT a dispute - a position \
that no reputable source holds, a claim reputable sources merely mention in order to dismiss it, two \
positions that are one position in different words, a quote torn from its context - and only when \
you cannot, you confirm it. You research on the web yourself.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

THE DESCRIPTION AS IT STANDS
{sentences}

THE TWO POSITIONS THE RESEARCHER FOUND (each quote was found on its page by code)
POSITION A: {a_claim}
  held by: {a_holders}
{a_sources}
POSITION B: {b_claim}
  held by: {b_holders}
{b_sources}

DECIDE
- verdict: "dispute" if reputable sources hold both positions about THIS site and a reputable source \
documents the disagreement (a claim set against its scientific assessment is a dispute when a \
reputable source reports it as a live controversy about this very site); "not-a-dispute" otherwise.
- asserting: the sentences of the description above that state one of the positions as plain \
established fact: {{"sentence": <the number>, "asserts": "a" or "b"}}. Empty for "not-a-dispute".
Open the pages, read around the quotes, look for the strongest source of each position. Sources \
follow the same rules as the researcher's (reputable, independent, never ancientnerds.com, AI \
aggregators or Wikipedia mirrors).

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "verdict": "dispute", "asserting": [{{"sentence": 2, "asserts": "a"}}], \
"note": "the strongest reason you found against it, and why it does not stand - or why it does"}}
"note" is a short plain sentence, at most 600 characters.
"""

_BRIEF_HEAD = """You are {agent_kind} {batch} of the Ancient Nerds dispute screen (lane E, {task}). \
You answer {count} question(s), each about another site. Answer each one on its own, as if it were \
the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository - no other batch, nothing else under output/ or docs/, no database, \
no git history. Your evidence is your own web research (WebSearch, WebFetch){wiki}. Run every \
command below from the repository root, {repo}.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research and answer, exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it{fetch}:
   {python} scripts/remediation/wc/disputes.py {check} --run-dir {run} --handoff {handoff} \
--batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   Fix what it names and check again. Never change a finding to make the check pass.
5. Record it - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --role {role} --model {model} \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


# ------------------------------------------------------------------------------ the answers
def _position(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != E.POSITION_KEYS:
        raise AnswerError(f"{where} is not {sorted(E.POSITION_KEYS)}")
    for key in ("claim", "holders"):
        text = value[key]
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CLAIM_CHARS:
            raise AnswerError(f"{where}.{key} is 1 to {MAX_CLAIM_CHARS} characters")
    sources = A._check_quotes(value["sources"], f"{where}.sources")
    if not 1 <= len(sources) <= MAX_SOURCES:
        raise AnswerError(f"{where} gives {len(sources)} quotes, 1 to {MAX_SOURCES}")
    return {"claim": value["claim"], "holders": value["holders"], "sources": sources}


def _asserting(value: Any, sentences: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AnswerError("asserting is a list")
    out: list[dict[str, Any]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"sentence", "asserts"}
            or isinstance(item["sentence"], bool)
            or not isinstance(item["sentence"], int)
            or not 1 <= item["sentence"] <= sentences
            or item["asserts"] not in ("a", "b")
        ):
            raise AnswerError(
                f"asserting names {{sentence: 1..{sentences}, asserts: 'a' or 'b'}}, not {item!r}"
            )
        out.append({"sentence": item["sentence"], "asserts": item["asserts"]})
    if len({item["sentence"] for item in out}) != len(out):
        raise AnswerError("a sentence is listed twice in asserting")
    return sorted(out, key=lambda item: item["sentence"])


def parse_research(text: str, *, site_id: str, sentences: int) -> dict[str, Any]:
    """A research answer: `disputed` false with no position, or true with both positions (each
    claim, holders and 1-4 quotes) and the asserting sentences."""
    data = load_object(
        text, frozenset({"site_id", "disputed", "position_a", "position_b", "asserting", "note"})
    )
    if data["site_id"] != site_id:
        raise AnswerError(f"the answer names site {data['site_id']!r}, the question {site_id}")
    if not isinstance(data["disputed"], bool):
        raise AnswerError("disputed is true or false")
    note = A._text(data["note"], "note", limit=A.MAX_NOTE_CHARS)
    if not data["disputed"]:
        if data["position_a"] is not None or data["position_b"] is not None or data["asserting"]:
            raise AnswerError("a site that is not disputed has no position and asserts nothing")
        return {"disputed": False, "note": note}
    return {
        "disputed": True,
        "position_a": _position(data["position_a"], "position_a"),
        "position_b": _position(data["position_b"], "position_b"),
        "asserting": _asserting(data["asserting"], sentences),
        "note": note,
    }


def parse_adjudication(text: str, *, site_id: str, sentences: int) -> dict[str, Any]:
    data = load_object(text, frozenset({"site_id", "verdict", "asserting", "note"}))
    if data["site_id"] != site_id:
        raise AnswerError(f"the answer names site {data['site_id']!r}, the question {site_id}")
    if data["verdict"] not in (E.DISPUTE_VERDICT, "not-a-dispute"):
        raise AnswerError(f"verdict {data['verdict']!r} is 'dispute' or 'not-a-dispute'")
    asserting = _asserting(data["asserting"], sentences)
    if data["verdict"] != E.DISPUTE_VERDICT and asserting:
        raise AnswerError("a site that is not a dispute asserts nothing")
    return {
        "verdict": data["verdict"],
        "asserting": asserting,
        "note": A._text(data["note"], "note", limit=A.MAX_NOTE_CHARS),
    }


# ------------------------------------------------------------------------------ the rounds
def _candidates(run: Path) -> dict[str, dict[str, Any]]:
    return {entry["site_id"]: entry for entry in read_jsonl(run / CANDIDATES_FILE)}


def _numbered(sentences: Sequence[str]) -> str:
    return "\n".join(f"S{n}: {text}" for n, text in enumerate(sentences, start=1))


def research_prompt(entry: Mapping[str, Any]) -> str:
    return RESEARCH_QUESTION.format(
        site=cli.site_block(M.PlanSite.from_dict(entry["plan_site"])),
        sentences=_numbered(entry["sentences"]),
        site_id=entry["site_id"],
        max_claim=MAX_CLAIM_CHARS,
        max_sources=MAX_SOURCES,
        wiki_hint="a few GETs of other pages are fine; a 403 or 429 is never a finding",
    )


def _sources_lines(sources: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(f'  source: {s["url"]} - "{s["quote"]}"' for s in sources)


def adjudicate_prompt(entry: Mapping[str, Any], research: Mapping[str, Any]) -> str:
    a, b = research["position_a"], research["position_b"]
    return ADJUDICATE_QUESTION.format(
        site=cli.site_block(M.PlanSite.from_dict(entry["plan_site"])),
        sentences=_numbered(entry["sentences"]),
        site_id=entry["site_id"],
        a_claim=a["claim"],
        a_holders=a["holders"],
        a_sources=_sources_lines(a["sources"]),
        b_claim=b["claim"],
        b_holders=b["holders"],
        b_sources=_sources_lines(b["sources"]),
    )


def _round_path(run: Path, stage: str) -> Path:
    return run / DISPUTE_DIR / stage / "ROUND.json"


def _export(
    run: Path,
    handoff: Path,
    *,
    stage: str,
    prefix: str,
    prompts: Mapping[str, str],
    batch_size: int,
) -> dict[str, Any]:
    if _round_path(run, stage).exists():
        raise DisputeError(f"{run}: the {stage} round was exported")
    if handoff.exists() and any(handoff.iterdir()):
        raise DisputeError(f"{handoff} is not empty: a round takes a new handoff directory")
    if not prompts:
        raise DisputeError(f"{run}: nothing to ask at {stage}")
    batches: dict[str, list[str]] = {}
    labels = sorted(prompts)
    for start in range(0, len(labels), batch_size):
        batch_id = f"{prefix}-{start // batch_size + 1:04d}"
        for label in labels[start : start + batch_size]:
            OH.export(
                handoff,
                batch_id=batch_id,
                stage=stage,
                label=label,
                field="description",
                prompt=prompts[label],
            )
            batches.setdefault(batch_id, []).append(label)
    RF.write_json(
        _round_path(run, stage),
        {"handoff": cli._shown(handoff), "exported_at": RF.now(), "batches": batches},
    )
    return {"questions": len(labels), "batches": len(batches)}


def cmd_export(run: Path, handoff: Path, *, batch_size: int = BATCH_SIZE) -> dict[str, Any]:
    """The research round: one question per candidate."""
    candidates = _candidates(run)
    return _export(
        run,
        handoff,
        stage=RESEARCH_STAGE,
        prefix=RESEARCH_PREFIX,
        prompts={site_id: research_prompt(entry) for site_id, entry in candidates.items()},
        batch_size=batch_size,
    )


def _round(run: Path, stage: str, handoff: Path) -> dict[str, Any]:
    path = _round_path(run, stage)
    if not path.exists():
        raise DisputeError(f"{run}: no {stage} round was exported")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (REPO / record["handoff"]).resolve() != handoff.resolve():
        raise DisputeError(f"{handoff} is not {run}'s {stage} round")
    return record


def brief(run: Path, handoff: Path, batch_id: str, *, stage: str = RESEARCH_STAGE) -> str:
    record = _round(run, stage, handoff)
    if batch_id not in record["batches"]:
        raise DisputeError(f"{batch_id} is no batch of {handoff}")
    shown = cli._shown(handoff)
    research = stage == RESEARCH_STAGE
    role = RESEARCH_ROLE if research else ADJUDICATE_ROLE
    return _BRIEF_HEAD.format(
        agent_kind="Sonnet researcher" if research else "Opus adjudicator",
        task="research" if research else "adjudication",
        batch=batch_id,
        count=len(record["batches"][batch_id]),
        handoff=shown,
        scratch=f"{shown}-scratch/{batch_id}",
        run=cli._shown(run),
        python=Path(sys.executable).as_posix(),
        repo=REPO.as_posix(),
        wiki=", and the Wikipedia cache is yours to read" if research else "",
        fetch=" (it fetches every page you quote, as the import will)" if research else "",
        check="check-answer" if research else "adjudicate-check-answer",
        stage=stage,
        batch_agent=f"{'sonnet' if research else 'opus'}-{stage}-{batch_id}",
        role=role,
        model=RO.role(role).model,
    )


def check_answer(
    run: Path,
    handoff: Path,
    batch_id: str,
    label: str,
    text: str,
    *,
    stage: str = RESEARCH_STAGE,
    client: A.Client | None = None,
    pace: float = Q.PACE_SECONDS,
) -> tuple[bool, str]:
    """The agent's aid: the answer's shape and, for a research answer, every quote against its page as
    the import will check it. (clean, report). Records nothing."""
    record = _round(run, stage, handoff)
    if label not in record["batches"].get(batch_id, []):
        raise DisputeError(f"{batch_id}/{label} is no question of {handoff}")
    entry = _candidates(run)[label]
    count = len(entry["sentences"])
    try:
        if stage == ADJUDICATE_STAGE:
            parse_adjudication(text, site_id=label, sentences=count)
            return True, "in shape"
        parsed = parse_research(text, site_id=label, sentences=count)
    except AnswerError as exc:
        return False, f"NOT IN SHAPE: {exc}"
    if not parsed["disputed"]:
        return True, f"not disputed ({parsed['note']})"
    pages = cli._agent_pages(handoff, batch_id)
    quotes = [q for side in ("position_a", "position_b") for q in parsed[side]["sources"]]
    cli.fetch([q.url for q in quotes], pages, client=client, pace=pace)
    library = Q.Library(REPO, pages)
    lines = []
    clean = True
    for side in ("position_a", "position_b"):
        outcomes = A.quote_outcomes(
            label, parsed[side]["sources"], library, checked=entry["plan_site"]["description"] or ""
        )
        good = sum(o.verified for o in outcomes)
        clean &= good > 0
        lines.append(f"{side}: {good} of {len(outcomes)} quote(s) found on their pages")
        lines.extend(f"  NOT FOUND {o.quote.url}: {o.outcome}" for o in outcomes if not o.verified)
    if not clean:
        lines.append("NOT CLEAN: a position needs at least one quote that code finds on its page")
    return clean, "\n".join(lines)


def _answers(
    run: Path, handoff: Path, stage: str, role: str
) -> dict[str, tuple[OH.Answer, str, str]]:
    """Every answer of the round, validated: label -> (answer, batch id, prompt). Each names its
    role and the role's model (`enrich.require_role`)."""
    record = _round(run, stage, handoff)
    check = OH.validate(handoff)
    if not check.ok:
        raise DisputeError(f"{handoff}: the round does not validate: {check.to_dict()}")
    candidates = _candidates(run)
    research = _research(run) if stage == ADJUDICATE_STAGE else {}
    out: dict[str, tuple[OH.Answer, str, str]] = {}
    for batch_id, labels in sorted(record["batches"].items()):
        for label in labels:
            prompt = (
                research_prompt(candidates[label])
                if stage == RESEARCH_STAGE
                else adjudicate_prompt(candidates[label], research[label])
            )
            answer = OH.read_answer(
                handoff, batch_id=batch_id, stage=stage, label=label, prompt=prompt
            )
            E.require_role(answer, role, f"{batch_id}/{label}")
            out[label] = (answer, batch_id, prompt)
    return out


def cmd_import(
    run: Path, handoff: Path, *, client: A.Client | None = None, pace: float = Q.PACE_SECONDS
) -> dict[str, Any]:
    """The research round, once: validated, every answer parsed, every quoted page fetched into the
    run's own store and every quote checked. A position none of whose quotes is found ends the site
    as `unverified`; `RESEARCH.jsonl` records every site."""
    if (run / RESEARCH_FILE).exists():
        raise DisputeError(f"{run}: the research round was imported")
    answers = _answers(run, handoff, RESEARCH_STAGE, RESEARCH_ROLE)
    candidates = _candidates(run)
    parsed: dict[str, dict[str, Any]] = {}
    for label, (answer, batch_id, _) in sorted(answers.items()):
        try:
            parsed[label] = parse_research(
                answer.text, site_id=label, sentences=len(candidates[label]["sentences"])
            )
        except AnswerError as exc:
            raise DisputeError(
                f"{batch_id}/{label}: malformed answer ({exc}) - check-answer refuses it; delete "
                "the answer file and have the batch agent answer it again"
            ) from exc
    urls = {
        q.url
        for result in parsed.values()
        if result["disputed"]
        for side in ("position_a", "position_b")
        for q in result[side]["sources"]
    }
    cli.fetch(urls, run / PAGES_DIR, client=client, pace=pace)
    library = Q.Library(REPO, run / PAGES_DIR)
    rows: list[dict[str, Any]] = []
    for label, result in sorted(parsed.items()):
        answer, batch_id, prompt = answers[label]
        row: dict[str, Any] = {
            "site_id": label,
            "batch_id": batch_id,
            "answered_by": answer.answered_by,
            "answer_sha256": M.text_sha256(answer.text),
            "prompt_sha256": OH.prompt_sha256(prompt),
            "note": result["note"],
        }
        if not result["disputed"]:
            rows.append({**row, "status": "not-disputed"})
            continue
        positions: dict[str, Any] = {}
        for side in ("position_a", "position_b"):
            outcomes = A.quote_outcomes(
                label,
                result[side]["sources"],
                library,
                checked=candidates[label]["plan_site"]["description"] or "",
            )
            positions[side] = {
                "claim": result[side]["claim"],
                "holders": result[side]["holders"],
                "sources": [
                    q.to_dict()
                    for q, o in zip(result[side]["sources"], outcomes, strict=True)
                    if o.verified
                ],
                "failed": [o.to_dict() for o in outcomes if not o.verified],
            }
        verified = all(position["sources"] for position in positions.values())
        rows.append(
            {
                **row,
                "status": "researched" if verified else "unverified",
                "asserting": result["asserting"],
                **positions,
            }
        )
    RF.write_jsonl(run / RESEARCH_FILE, rows)
    return dict(sorted(Counter(row["status"] for row in rows).items()))


def _research(run: Path) -> dict[str, dict[str, Any]]:
    path = run / RESEARCH_FILE
    if not path.exists():
        raise DisputeError(f"{run}: the research round was not imported")
    return {row["site_id"]: row for row in read_jsonl(path) if row["status"] == "researched"}


def cmd_adjudicate_export(
    run: Path, handoff: Path, *, batch_size: int = BATCH_SIZE
) -> dict[str, Any]:
    """The adjudication round: one question per researched site (both positions verified)."""
    candidates = _candidates(run)
    research = _research(run)
    return _export(
        run,
        handoff,
        stage=ADJUDICATE_STAGE,
        prefix=ADJUDICATE_PREFIX,
        prompts={
            site_id: adjudicate_prompt(candidates[site_id], row)
            for site_id, row in research.items()
        },
        batch_size=batch_size,
    )


def adjudicate_check_answer(
    run: Path, handoff: Path, batch_id: str, label: str, text: str
) -> str | None:
    clean, report = check_answer(run, handoff, batch_id, label, text, stage=ADJUDICATE_STAGE)
    return None if clean else report


def cmd_adjudicate_import(run: Path, handoff: Path) -> dict[str, Any]:
    """The adjudication round, once. The adjudicator is not the site's researcher (a name that
    researched it does not count): the dispute is confirmed by an independent agent."""
    if (run / ADJUDICATED_FILE).exists():
        raise DisputeError(f"{run}: the adjudication round was imported")
    research = _research(run)
    answers = _answers(run, handoff, ADJUDICATE_STAGE, ADJUDICATE_ROLE)
    candidates = _candidates(run)
    rows: list[dict[str, Any]] = []
    for label, (answer, batch_id, prompt) in sorted(answers.items()):
        if wc4.agent_name(answer.answered_by) == wc4.agent_name(research[label]["answered_by"]):
            raise DisputeError(
                f"{batch_id}/{label}: {answer.answered_by} researched this site - the dispute is "
                "confirmed by an independent agent; have the batch answered again by a new agent"
            )
        try:
            verdict = parse_adjudication(
                answer.text, site_id=label, sentences=len(candidates[label]["sentences"])
            )
        except AnswerError as exc:
            raise DisputeError(
                f"{batch_id}/{label}: malformed answer ({exc}) - delete the answer file and have "
                "the batch agent answer it again"
            ) from exc
        rows.append(
            {
                "site_id": label,
                "batch_id": batch_id,
                "answered_by": answer.answered_by,
                "answer_sha256": M.text_sha256(answer.text),
                "prompt_sha256": OH.prompt_sha256(prompt),
                **verdict,
            }
        )
    RF.write_jsonl(run / ADJUDICATED_FILE, rows)
    return dict(sorted(Counter(row["verdict"] for row in rows).items()))


# ------------------------------------------------------------------------------ the outputs
def _basis(raw: Mapping[str, Any] | None) -> str:
    """The basis the description is (`teaser/run.py:basis_of`): its Phase-4 lane, else the sentence
    check."""
    stored = (raw or {}).get(M.PROVENANCE_KEY)
    lane = stored.get("lane") if isinstance(stored, dict) else None
    return str(lane) if lane in ("W", "S", "T", "R", "E") else "WC"


def dispute_record(
    entry: Mapping[str, Any], research: Mapping[str, Any], verdict: Mapping[str, Any]
) -> dict[str, Any]:
    """The brief `export --enrich --disputes` appends both positions from (`enrich.DISPUTE_KEYS`)."""
    asserting = [
        {**item, "text": entry["sentences"][item["sentence"] - 1]} for item in verdict["asserting"]
    ]
    return {
        "site_id": entry["site_id"],
        "name": entry["name"],
        "desc_sha256": entry["desc_sha256"],
        "verdict": E.DISPUTE_VERDICT,
        "position_a": {k: research["position_a"][k] for k in sorted(E.POSITION_KEYS)},
        "position_b": {k: research["position_b"][k] for k in sorted(E.POSITION_KEYS)},
        "asserting": asserting,
        "note": verdict["note"],
        "researched_by": research["answered_by"],
        "adjudicated_by": verdict["answered_by"],
    }


def defect_lines(
    run_name: str, entry: Mapping[str, Any], record: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """One `DESCRIPTION_DEFECTS.jsonl` line (`cli.DEFECT_KEYS`) per sentence that states one position
    as fact: the claim is the dispute, the quote the page of the other position - checked by code at
    the research import, so `proven` and `found`."""
    lines = []
    for item in record["asserting"]:
        other = record["position_b" if item["asserts"] == "a" else "position_a"]
        mine = record["position_a" if item["asserts"] == "a" else "position_b"]
        source = other["sources"][0]
        lines.append(
            {
                "run": run_name,
                "site_id": entry["site_id"],
                "name": entry["name"],
                "basis": _basis(entry["plan_site"]["raw_data"]),
                "owner_lane": DEFECT_OWNER_LANE,
                "desc_sha256": entry["desc_sha256"],
                "stage": DEFECT_STAGE,
                "sentence": item["sentence"],
                "sentence_text": item["text"],
                "candidates": [f"S{item['sentence']}"],
                "claim": (
                    f"DISPUTED: the sentence states as settled fact that {mine['claim']} - but "
                    f"{other['holders']} hold that {other['claim']}"
                ),
                "url": source["url"],
                "quote": source["quote"],
                "quote_outcome": "found",
                "proven": True,
                "verifier": record["adjudicated_by"],
                "mapped_by": record["researched_by"],
            }
        )
    return lines


def cmd_outputs(run: Path) -> dict[str, Any]:
    """`DISPUTES.jsonl` (the confirmed disputes), `DISPUTE_DEFECTS.jsonl` (the repair feed) and
    `SUMMARY.json`."""
    path = run / ADJUDICATED_FILE
    if not path.exists():
        raise DisputeError(f"{run}: the adjudication round was not imported")
    candidates = _candidates(run)
    research = _research(run)
    disputes: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []
    for verdict in read_jsonl(path):
        if verdict["verdict"] != E.DISPUTE_VERDICT:
            continue
        site_id = verdict["site_id"]
        record = dispute_record(candidates[site_id], research[site_id], verdict)
        problems = E.dispute_record_problems(record)
        if problems:
            raise DisputeError(f"{site_id}: " + "; ".join(problems))
        disputes.append(record)
        defects.extend(defect_lines(run.name, candidates[site_id], record))
    RF.write_jsonl(run / DISPUTES_FILE, disputes)
    RF.write_jsonl(run / DEFECTS_FILE, defects)
    research_rows = read_jsonl(run / RESEARCH_FILE)
    summary = {
        "candidates": len(candidates),
        "research": dict(sorted(Counter(row["status"] for row in research_rows).items())),
        "adjudicated": dict(sorted(Counter(r["verdict"] for r in read_jsonl(path)).items())),
        "disputes": len(disputes),
        "sentences_to_repair": len(defects),
        "sites_to_repair": len({d["site_id"] for d in defects}),
    }
    RF.write_json(run / SUMMARY_FILE, summary)
    return summary


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="disputes", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "fetch-categories", "candidates", "recall", "export", "brief", "check-answer", "import",
        "adjudicate-export", "adjudicate-brief", "adjudicate-check-answer", "adjudicate-import",
        "outputs",
    ):  # fmt: skip
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True, type=Path)
        if name not in ("fetch-categories", "candidates", "recall", "outputs"):
            command.add_argument("--handoff", required=True, type=Path)
        if name in ("brief", "check-answer", "adjudicate-brief", "adjudicate-check-answer"):
            command.add_argument("--batch-id", required=True)
        if name in ("check-answer", "adjudicate-check-answer"):
            command.add_argument("--label", required=True)
            command.add_argument("--text-file", required=True, type=Path)
        if name in ("export", "adjudicate-export"):
            command.add_argument("--batch-size", type=int, default=BATCH_SIZE)
        if name == "candidates":
            command.add_argument("--wiki-cache", type=Path, default=None)
            command.add_argument("--wiki-min-hits", type=int, default=WIKI_MIN_HITS)
    return parser


def run_command(args: argparse.Namespace) -> int:
    run: Path = args.run_dir
    command = args.command
    if command == "fetch-categories":
        client = A.Client()
        try:
            _print(cmd_fetch_categories(run, get=lambda params: api_get(params, client=client)))
        finally:
            client.close()
    elif command == "candidates":
        _print(cmd_candidates(run, wiki_cache=args.wiki_cache, wiki_min_hits=args.wiki_min_hits))
    elif command == "recall":
        result = cmd_recall(run)
        _print(result)
        return 0 if result["passed"] else 1
    elif command == "export":
        _print(cmd_export(run, args.handoff, batch_size=args.batch_size))
    elif command == "brief":
        print(brief(run, args.handoff, args.batch_id))
    elif command == "adjudicate-brief":
        print(brief(run, args.handoff, args.batch_id, stage=ADJUDICATE_STAGE))
    elif command in ("check-answer", "adjudicate-check-answer"):
        text = args.text_file.read_bytes().decode("utf-8")
        stage = RESEARCH_STAGE if command == "check-answer" else ADJUDICATE_STAGE
        clean, report = check_answer(
            run, args.handoff, args.batch_id, args.label, text, stage=stage
        )
        print(report)
        return 0 if clean else 1
    elif command == "import":
        _print(cmd_import(run, args.handoff))
    elif command == "adjudicate-export":
        _print(cmd_adjudicate_export(run, args.handoff, batch_size=args.batch_size))
    elif command == "adjudicate-import":
        _print(cmd_adjudicate_import(run, args.handoff))
    elif command == "outputs":
        _print(cmd_outputs(run))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        code = run_command(args)
    except (DisputeError, E.EnrichError, cli.WcRunError, OH.HandoffError, AnswerError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        code = 1
    print(f"DISPUTE_EXIT={code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
