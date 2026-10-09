"""How the lanes' agents use the shared Wikipedia cache and the web: one statement for every brief.

Diagnosis of the calibration teaser-2026-10-09 (Opus, 2026-10-09): the web verifiers read the site's
cached English Wikipedia article and nothing else - 17 of 20 known contradictions stand only on other
pages (an excavation report, a heritage register, a museum, a paper, another Wikipedia) - because the
brief told them to read the cache first and to fetch "at most a few requests per site". The cached
article is where a description or a card came from, so for a role that is meant to catch what is wrong
in it, it is never independent confirmation. The briefs of every lane that points an agent at
`wiki_cache/` take their rule from here, by role:

* `VERIFIER_RULE`: a verifier, a judge, an adversarial reviewer - any role that confirms or rejects a
  decision or a text. No cap on requests; the politeness stays.
* `RESEARCHER_RULE`: a researcher or a writer - the cache stays the first reading, its text is not a
  second witness for the description that was written from it.
* `QUOTE_RULE`: what an agent that quotes a page does before it records the answer (a lane with a
  `check-answer` of its own that fetches the quoted pages says only `MARKER_NOTE`).
"""

from __future__ import annotations

#: Politeness (Wikimedia throttles this office IP from four parallel readers, memory 2026-10-07):
#: kept in every role. It limits how a page is requested, never how many pages are read.
POLITENESS = (
    "Request pages one at a time, with the project's User-Agent "
    "(curl -A 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'). "
    "An HTTP 403 or 429 is a throttle and NEVER a finding: fetch the page again yourself with curl, "
    "or quote another page, before you call a source unreachable or a claim unverifiable."
)

#: For a role that confirms or rejects (verifier, judge, adversarial reviewer).
VERIFIER_RULE = (
    "The cached Wikipedia article is where the description or the card under test came from, so "
    "for you it is NEVER independent confirmation: a claim it repeats is not thereby checked. Read "
    "the WHOLE article for contradictions inside it (a number, date or name that the infobox, the "
    "lead and a later section state differently; a section that qualifies the lead). Before you "
    "decide SUPPORTED, or confirm, a number, date, count, size, superlative, name, a 'never', 'only', "
    "'still' or 'first', or a present-tense state, look for a page OUTSIDE that article that could "
    "contradict it: an excavation report or heritage register, a museum or university page, a "
    "scholarly paper, the other-language Wikipedias, the WebSearch tool. There is no cap on "
    "requests for this: read as many pages as the claim needs. " + POLITENESS
)

#: For a role that researches or writes (the cache is the first reading).
RESEARCHER_RULE = (
    "Read the site's cached Wikipedia text first, then go to the web for everything the question "
    "asks beyond it. The cached article is a reading aid and one witness: a description or card "
    "written from it is not confirmed by it, so a fact you rely on that stands only in that article "
    "has one source, and a fact the question asks you to establish needs a page from outside it. "
    + POLITENESS
)

#: The one fact about quoting that the cache hides (`opus_audit/quotes.normalise`).
MARKER_NOTE = (
    "A quote is checked by a machine against the LIVE page, which carries footnote markers such as "
    "[22] that the cached text drops; the check ignores such markers on both sides, so a quote copied "
    "from the cache or from the page as it stands is found."
)

#: For an agent that quotes a page and has no check of its own (`quote_check.py` is the lanes' check
#: on one page).
QUOTE_RULE = (
    MARKER_NOTE
    + " Before you record the answer, check each quote yourself with the lanes' own check: "
    "./.venv/Scripts/python.exe scripts/remediation/quote_check.py --url <url> --quote-file <file> "
    "(prints found / not found and, if not found, where the page differs); correct the quote from "
    "the page it names, never the finding."
)


#: Which rule a registered role (`roles.ROLES`) reads. A role is in exactly one set: a role that
#: confirms or rejects (the fact checker, the web verifier, the adversarial reviewer, the pilot
#: judge) or one that researches or writes. A role added to the registry is classified here before
#: a brief for it can be built - there is no default.
VERIFIER_ROLES = frozenset({"fact_checker", "web_verifier", "adversarial", "pilot_judge"})
RESEARCHER_ROLES = frozenset({"field_researcher", "card_writer", "enrich_writer"})


class WebRuleError(ValueError):
    """A role that is in neither set of web rules: the rule it reads is not decided."""


def rule_for_role(role: str) -> str:
    """The cache and web rule of an agent that answers as `role`."""
    if role in VERIFIER_ROLES:
        return VERIFIER_RULE
    if role in RESEARCHER_ROLES:
        return RESEARCHER_RULE
    raise WebRuleError(
        f"role {role!r} has no web rule: add it to VERIFIER_ROLES or RESEARCHER_ROLES in web_rules.py"
    )
