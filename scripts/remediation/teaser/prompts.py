"""Lane WB's questions: the writer's, the rewriter's, the checker's, the web judge's (every card's
verifier and the pilot's judge) and the rewrite after a failed verification.

Every prompt is a pure function of the site's fact basis (`contract.Basis`) and, for a rewrite or a
check, of the card and findings before it - so an import can rebuild the exact prompt an answer was
given and refuse an answer to any other (`run.py import`, as `acceptance/judge.py` does).

The four examples in `EXAMPLES` were written for this lane from the live descriptions of four sites
(read-only SELECT, 2026-09-26 01:13 UTC; all four lane-W Phase-4 texts), each checked by
`contract.problems` and claim by claim against the sentences it names. Each example shows the
sentences it rests on with the ids the full description gives them (`contract.description_sentences`;
`tests/remediation/teaser_cases.py` holds the four full texts and a test pins every id and text).
They show the tone and the faithfulness - they are not templates to copy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from teaser import contract as C

#: What the card is for, and the tone the owner asked for (O2, 2026-09-26: "sie sollten die site
#: teasern und mystisch sein ... aber natuerlich muessen sie inhaltlich stimmen").
PURPOSE = (
    "Ancient Nerds is a globe of ancient sites with a card game and short videos. Every site has a "
    "card: a teaser of 160-190 characters, shown on the site's card and narrated as the voice-over "
    "of its short video. It should make the reader want to see the site - evocative, a little "
    "mysterious - and every fact in it must be true to the site's own published description."
)

RULES: tuple[str, ...] = (
    "English. 160-190 characters exactly as counted by the check (letters, spaces and punctuation "
    "all count). One or two sentences, one line.",
    "Evocative and a little mysterious: invite the reader in with a concrete image of what is there "
    "or what was found. Mystery is TONE (a vivid image, an open invitation, one short question), "
    "never a claim.",
    "Every fact comes from the numbered sentences of the description, the site's name or its "
    "country - nothing else: not your own knowledge, not what 'everybody knows' about the site.",
    "These are CLAIMS and need a sentence that says them: that something is unknown, unexplained, "
    "unsolved, disputed, secret or mysterious ('no one knows', 'a riddle', 'a lost civilization'); "
    "superlatives and rankings ('oldest', 'largest', 'first', 'only', 'unique'); numbers, dates, "
    "periods and centuries; names of people, peoples, cultures and places; materials, sizes, "
    "functions and uses. A hedge in the description ('possibly', 'believed', 'about', "
    "'roughly') stays a hedge in the card.",
    "Numbers: write each number with digits, exactly as the description writes it. Never compute a "
    "new one ('5,000 years ago' from '3000 BC'), never round, never convert units. A number in words "
    "is a claim too.",
    "Name the site: the card must contain one of its NAME FORMS, exactly as listed.",
    "At most one question, at most 60 characters, and it must not imply a claim: 'Who built it?' "
    "says the builders are unknown - only ask it if a sentence says so.",
    "No brackets, no citation markers, no emojis, no symbols (+, =, arrows), no hashtags, no "
    "asterisks, no abbreviation 'c.' "
    "(write 'circa'); no exclamation marks, no marketing phrases ('hidden gem', 'must-see', 'step "
    "back in time').",
    "The card already shows the site's country and flag: name the country only if it adds to the "
    "image.",
)

#: What the checker holds a card to, besides the claims.
TONE_RULES: tuple[str, ...] = (
    "English, one or two sentences, evocative and a little mysterious, not marketing copy.",
    "Mystery only as tone: no statement or implication that something is unknown, unexplained or "
    "unsolved unless a sentence says so (this is also a claim - list it).",
    "At most one short question, and the question implies nothing the sentences do not say.",
    "A hedge of the description stays a hedge ('possible offerings' may not become 'offerings').",
)


@dataclass(frozen=True)
class Example:
    """A card written from one site's live description, with the sentences it rests on."""

    site: str
    country: str
    sentences: tuple[tuple[str, str], ...]
    card: str
    claims: tuple[tuple[str, tuple[str, ...]], ...]


EXAMPLES: tuple[Example, ...] = (
    Example(
        site="Skara Brae",
        country="Scotland",
        sentences=(
            (
                "S1",
                "Skara Brae is a stone-built Neolithic settlement located along the Bay of Skaill "
                "on the west coast of Mainland, Orkney.",
            ),
            (
                "S2",
                "The site was discovered following a storm exposing the presence of stone "
                "structures within the coastal sand dunes.",
            ),
            (
                "S3",
                "The site was occupied from roughly 3180 BC to around 2500 BC and is Europe's most "
                "complete Neolithic village.",
            ),
            (
                "S6",
                "The buildings follow a similar layout with a central hearth, beds on either side "
                "of the hearth, and a dresser opposite the entrance.",
            ),
        ),
        card=(
            "A storm on Orkney laid bare stone structures in the sand dunes: Skara Brae, a "
            "Neolithic village of hearths, beds and dressers, lived in from roughly 3180 BC to "
            "around 2500 BC."
        ),
        claims=(
            ("a storm exposed stone structures in the sand dunes", ("S2",)),
            ("on Orkney", ("S1",)),
            ("a Neolithic village", ("S1", "S3")),
            ("its houses have hearths, beds and dressers", ("S6",)),
            ("lived in from roughly 3180 BC to around 2500 BC", ("S3",)),
        ),
    ),
    Example(
        site="Newgrange",
        country="Ireland",
        sentences=(
            (
                "S1",
                "Newgrange is a prehistoric monument in County Meath in Ireland, placed on a rise "
                "overlooking the River Boyne.",
            ),
            (
                "S3",
                "Newgrange consists of a large circular mound with an inner stone passageway and "
                "cruciform chamber.",
            ),
            (
                "S4",
                "Burnt and unburnt human bones and possible grave goods or votive offerings were "
                "found in this chamber.",
            ),
            (
                "S5",
                "The monument has a striking façade made mostly of white quartz cobblestones and "
                "ringed by engraved kerbstones.",
            ),
        ),
        card=(
            "Above the River Boyne rises Newgrange, its façade made mostly of white quartz. Inside, "
            "a stone passage leads to a cruciform chamber where burnt bones and possible offerings "
            "were found."
        ),
        claims=(
            ("it stands above the River Boyne", ("S1",)),
            ("its façade is made mostly of white quartz", ("S5",)),
            ("inside, a stone passage leads to a cruciform chamber", ("S3",)),
            ("burnt bones and possible offerings were found in the chamber", ("S4",)),
        ),
    ),
    Example(
        site="Stonehenge",
        country="England",
        sentences=(
            (
                "S1",
                "Stonehenge is a prehistoric megalithic structure on Salisbury Plain in Wiltshire, "
                "England, two miles west of Amesbury.",
            ),
            (
                "S2",
                "It consists of an outer ring of vertical sarsen standing stones, each around 13 "
                "feet high, seven feet wide, and weighing around 25 tons, topped by connecting "
                "horizontal lintel stones which are held in place with mortise and tenon joints—a "
                "feature unique among contemporary monuments.",
            ),
            (
                "S5",
                "The whole monument, now in ruins, is aligned towards the sunrise on the summer "
                "solstice and sunset on the winter solstice.",
            ),
            (
                "S7",
                "Stonehenge was constructed in several phases, beginning about 3100 BC and "
                "continuing until about 1600 BC.",
            ),
        ),
        card=(
            "On Salisbury Plain, Stonehenge's outer sarsens weigh around 25 tons each, the whole "
            "monument aligned to the midsummer sunrise and the midwinter sunset. Building began "
            "about 3100 BC."
        ),
        claims=(
            ("on Salisbury Plain", ("S1",)),
            ("the outer ring's sarsen stones each weigh around 25 tons", ("S2",)),
            (
                "the whole monument is aligned to the midsummer sunrise and midwinter sunset",
                ("S5",),
            ),
            ("construction began about 3100 BC", ("S7",)),
        ),
    ),
    Example(
        site="Sacsayhuamán",
        country="Peru",
        sentences=(
            (
                "S1",
                "Sacsayhuamán or Saksaywaman is a citadel on the northern outskirts of the city of "
                "Cusco, Peru, the historic capital of the Inca Empire.",
            ),
            (
                "S2",
                "The site is an important example of Inca architecture and sits at an altitude of "
                "3,701 metres.",
            ),
            (
                "S4",
                "Dry stone walls constructed of huge stones were built on the site, with the "
                "workers carefully cutting the boulders to fit them together tightly without "
                "mortar.",
            ),
            (
                "S5",
                "Archeological studies of surface collections of pottery at Sacsayhuamán indicate "
                "that the earliest occupation of the hilltop dates to about 900 CE.",
            ),
            (
                "S6",
                "During the 15th century, the Imperial Inca expanded on this settlement, building "
                "dry stone walls constructed of huge stones.",
            ),
        ),
        card=(
            "On a hilltop outside Cusco, 3,701 metres up, the Inca walls of Sacsayhuamán lock "
            "huge boulders together without mortar, each one carefully cut to fit its neighbours "
            "tightly."
        ),
        claims=(
            ("on a hilltop", ("S5",)),
            ("outside Cusco", ("S1",)),
            ("at 3,701 metres", ("S2",)),
            ("the walls are Inca work", ("S2", "S6")),
            ("huge boulders fitted together without mortar", ("S4",)),
            ("each boulder carefully cut to fit tightly", ("S4",)),
        ),
    ),
)

#: What a card may not do, each with the reason - shown to the writer.
DONT: tuple[str, ...] = (
    "'Built by a lost civilization no one can name' - unless a sentence says the builders are "
    "unknown.",
    "'The oldest temple on Earth' - a superlative no sentence makes.",
    "'5,000 years ago' from '3000 BC' - a computed number.",
    "'Who built it, and why?' - implies both are unknown.",
    "'Legend says the giants raised it' - unless the description reports that legend.",
)


#: The sources a web fact may come from to count as a fact - lane WC's source rule
#: (`wc/prompts.CHECK_QUESTION`, rule 2; its refusals by code: `wc.answers.url_problem`).
REPUTABLE = (
    "Wikipedia (the article itself, any language), UNESCO, a national heritage register, a museum, "
    "a university, an excavation report, a scholarly publication or an established reference work"
)


def _sentences(site: C.Basis) -> str:
    return "\n".join(f"{sentence.id} {sentence.text}" for sentence in site.sentences)


def _web_block(site: C.Basis) -> str:
    """The web facts of a rewrite after a failed verification; nothing for any other question."""
    if not site.web:
        return ""
    facts = "\n".join(f'{fact.id} "{fact.quote}" - {fact.url}' for fact in site.web)
    return (
        "\n\nWEB FACTS - quotes an independent web check found on the pages named, each "
        "contradicting a claim of an earlier card of this site. A web fact counts as a fact only "
        f"where its page is a reputable source: {REPUTABLE}.\n{facts}"
    )


def _site_block(site: C.Basis) -> str:
    forms = " | ".join(site.forms)
    return (
        f"Name: {site.name}\nCountry: {site.country}\n"
        f"NAME FORMS (the card must contain one of these, exactly): {forms}\n\n"
        "THE FACT BASIS - the site's published description, sentence by sentence:\n"
        f"{_sentences(site)}{_web_block(site)}"
    )


def _numbered(items: Sequence[str]) -> str:
    return "\n".join(f"{n}. {item}" for n, item in enumerate(items, start=1))


def _examples() -> str:
    blocks = []
    for example in EXAMPLES:
        used = "\n".join(f"  {sid} {text}" for sid, text in example.sentences)
        claims = "\n".join(f"  - {claim}: {', '.join(ids)}" for claim, ids in example.claims)
        blocks.append(
            f"{example.site} ({example.country}) - the sentences it rests on:\n{used}\n"
            f"Card ({len(example.card)} characters): {example.card}\n"
            f"Its claims and their sentences:\n{claims}"
        )
    return "\n\n".join(blocks)


WRITER_FORMAT = (
    'Answer with ONLY this JSON object, nothing before or after it:\n{"card": "<the card>", '
    '"basis": ["S1", "S3"]}\n"basis" lists the ids of the sentences your card\'s facts come from.'
)


def writer_prompt(site: C.Basis) -> str:
    """The writer's question for one site."""
    return (
        f"{PURPOSE}\n\nWrite the card of this site.\n\nTHE SITE\n{_site_block(site)}\n\n"
        f"THE RULES\n{_numbered(RULES)}\n\nNEVER, for example:\n{_numbered(DONT)}\n\n"
        f"GOOD CARDS (other sites, each true to its own description):\n\n{_examples()}\n\n"
        f"{WRITER_FORMAT}\n"
    )


@dataclass(frozen=True)
class Finding:
    """Why an earlier card of the site was not accepted: its text and the reasons."""

    card: str
    reasons: tuple[str, ...]


def rewrite_prompt(site: C.Basis, findings: Sequence[Finding]) -> str:
    """The rewriter's question: the writer's, plus every earlier card and why it failed."""
    earlier = "\n\n".join(
        f"Card {n} ({len(f.card)} characters): {f.card}\nWhy it was not accepted:\n"
        + "\n".join(f"- {reason}" for reason in f.reasons)
        for n, f in enumerate(findings, start=1)
    )
    return (
        f"{PURPOSE}\n\nThe card of this site has to be written again: the earlier card(s) below "
        "were not accepted. Write a new card that fixes every finding - it is checked again, by "
        f"another checker.\n\nTHE SITE\n{_site_block(site)}\n\nEARLIER CARDS\n{earlier}\n\n"
        f"THE RULES\n{_numbered(RULES)}\n\nNEVER, for example:\n{_numbered(DONT)}\n\n"
        f"GOOD CARDS (other sites, each true to its own description):\n\n{_examples()}\n\n"
        f"{WRITER_FORMAT}\n"
    )


VERIFY_WRITER_FORMAT = (
    'Answer with ONLY this JSON object, nothing before or after it:\n{"card": "<the card>", '
    '"basis": ["S1", "W1"], "repeats": ["S3"]}\n"basis" lists the ids of the sentences and web '
    'facts your card\'s facts come from. "repeats" has one entry per CONTRADICTED claim above, in '
    "its order: the id of the sentence of the description that states that claim, or null when no "
    "sentence does ([] when none is listed)."
)


def _contradicted(claims: Sequence[Mapping[str, Any]]) -> str:
    if not claims:
        return "(none)"
    blocks = []
    for n, claim in enumerate(claims, start=1):
        found = (
            "the machine found this quote on the page"
            if claim["proven"]
            else f"the machine could not confirm this quote on the page: {claim['quote_outcome']}"
        )
        blocks.append(
            f'{n}. {claim["claim"]}\n   page: {claim["url"]}\n   quote: "{claim["quote"]}" '
            f"({found})"
        )
    return "\n".join(blocks)


def verify_rewrite_prompt(
    site: C.Basis,
    card: str,
    contradicted: Sequence[Mapping[str, Any]],
    unproven: Sequence[Mapping[str, Any]],
) -> str:
    """The one rewrite after a failed web verification: the writer's rules, the card, every claim
    the verifier found contradicted (page, quote, whether the machine found the quote) or could not
    prove, and the web facts (`site.web`) a contradicted claim may be corrected with."""
    not_proven = "\n".join(f"- {claim['claim']}" for claim in unproven) or "(none)"
    return (
        f"{PURPOSE}\n\nThe card below was accepted by a checker - every claim of it is in the "
        "site's description - but an independent check against pages on the web did not verify "
        "it. A card read aloud must not repeat a claim the web contradicts. Write a new card: it is "
        "checked again, by another checker, and verified again on the web, by another verifier. "
        "There is no further round: if the new card fails, the site gets no card.\n\n"
        f"THE SITE\n{_site_block(site)}\n\n"
        f"THE CARD THE WEB CHECK DID NOT VERIFY ({len(card)} characters)\n{card}\n\n"
        f"CONTRADICTED - a page says otherwise:\n{_contradicted(contradicted)}\n\n"
        f"NOT PROVEN - the web check found no page that proves these:\n{not_proven}\n\n"
        "WHAT THE NEW CARD MUST DO\n"
        "1. Drop every contradicted claim, or correct it. Correct a claim only with a fact that a "
        "sentence of the description or a WEB FACT states, its numbers written as that sentence "
        "or web fact writes them - nothing else, not your own knowledge. A web fact may be used "
        f"only if its page is a reputable source: {REPUTABLE}. When in doubt, drop the claim. "
        "(Rule 3 below extends to the web facts in this round only.)\n"
        "2. What the site is, and where, is never corrected from a web fact: a page that says the "
        "site is something else, or somewhere else, may be about a namesake. If that claim is "
        "contradicted, say it only as the description says it - the new verifier decides, and if "
        "the web contradicts it again the site gets no card - or drop it.\n"
        "3. At most one claim of the new card may be one the web check could not prove, and never "
        "the claim that says what the site is. Prefer the facts the web check proved.\n"
        "4. For each contradicted claim above, in its order, name the sentence of the description "
        "that states it, or null if no sentence does: this lists the description's own errors for "
        "their repair.\n\n"
        f"THE RULES\n{_numbered(RULES)}\n\nNEVER, for example:\n{_numbered(DONT)}\n\n"
        f"GOOD CARDS (other sites, each true to its own description):\n\n{_examples()}\n\n"
        f"{VERIFY_WRITER_FORMAT}\n"
    )


CHECKER_FORMAT = (
    "Answer with ONLY this JSON object, nothing before or after it:\n"
    '{"claims": [{"claim": "<one claim, in your words>", "support": ["S2"]}], '
    '"tone_ok": true, "this_site": true, "verdict": "PASS", "reasons": []}\n'
    '- "support": the ids of the sentences that say the claim; [] when none does.\n'
    '- "verdict" is "PASS" only when every claim has support, tone_ok and this_site are true and '
    'you have no other finding; then "reasons" is []. Otherwise "verdict" is "FAIL" and "reasons" '
    "lists every finding as one concrete sentence the writer can act on."
)


def _worked_check() -> str:
    example = EXAMPLES[2]
    claims = [{"claim": claim, "support": list(ids)} for claim, ids in example.claims]
    answer = {
        "claims": claims,
        "tone_ok": True,
        "this_site": True,
        "verdict": "PASS",
        "reasons": [],
    }
    return (
        f"Example - {example.site}, card: {example.card}\n"
        f"Answer: {json.dumps(answer, ensure_ascii=False)}\n"
        "Had the card said 'the oldest stone circle in Britain', the claim would have had support "
        '[], and the verdict would be FAIL with the reason "No sentence says it is the oldest '
        'stone circle in Britain."'
    )


def _web_rule(site: C.Basis) -> str:
    """How a checker counts a web fact - only in the check of a rewrite that has some."""
    if not site.web:
        return ""
    return (
        "   A claim may also rest on a WEB FACT (its id, W1, ...) - but only if that fact's page is "
        f"a reputable source ({REPUTABLE}); a claim that rests only on a web fact from any other "
        "page has support []. A card that follows a web fact saying the site is something else, "
        "or somewhere else, than the sentences say makes this_site false: that page may be about "
        "a namesake.\n"
    )


def checker_prompt(site: C.Basis, card: str) -> str:
    """The checker's question: every claim of `card` against the site's sentences (and, checking a
    rewrite after a failed web verification, its web facts)."""
    return (
        "You are the independent checker of a teaser card for Ancient Nerds, a globe of ancient "
        "sites with a card game and narrated short videos. The card was written by someone else "
        "from the site's published description; it may claim nothing the description does not "
        "say.\n\n"
        f"THE SITE\n{_site_block(site)}\n\nTHE CARD\n{card}\n\n"
        "YOUR TASK\n"
        "1. List EVERY claim the card makes: each fact, number, date, period, name, place, "
        "material, size, function and use; every superlative or ranking; and every statement or "
        "implication that something is unknown, unexplained, unsolved or mysterious (a question "
        "can imply one). Split compound statements into single claims.\n"
        "2. For each claim, give the ids of the sentences that say it. A faithful paraphrase is "
        "supported; an embellishment, a sharpened hedge, a computed number or an inference the "
        "sentences do not make is not. Use only the sentences above - not your own knowledge, "
        "even where you know the claim is true.\n"
        f"{_web_rule(site)}"
        f"3. tone_ok: the card follows these rules:\n{_numbered(TONE_RULES)}\n"
        "4. this_site: the card is about this site - not a namesake, a neighbouring town, the "
        "region, a museum or an object kept elsewhere.\n\n"
        f"{_worked_check()}\n\n{CHECKER_FORMAT}\n"
    )


JUDGE_FORMAT = (
    "Answer with ONLY this JSON object, nothing before or after it:\n"
    '{"claims": [{"claim": "<one claim>", "verdict": "SUPPORTED", "url": "https://...", '
    '"quote": "<the exact words of the page>"}]}\n'
    '- "verdict": SUPPORTED (a page says it), CONTRADICTED (a page says otherwise) or '
    "UNVERIFIABLE (you found no page that settles it).\n"
    '- SUPPORTED and CONTRADICTED need "url" and "quote": the quote is copied character for '
    "character from that page's visible text, at least 20 characters, and it is checked by a "
    'machine against the page. UNVERIFIABLE has "url": null and "quote": null.'
)


def judge_prompt(name: str, country: str, card: str) -> str:
    """A web judge's question - the verifier of every card (stages `verify`, `verify2`) and the
    pilot's judge: every claim of a card against sources on the web, the central claim first (the
    VERIFIED rule never lets it go unproven: `run.card_verification`)."""
    return (
        "You are an independent fact checker. Below is a short teaser text about an archaeological "
        "site, written for a website and its narrated short videos. Check it against sources on "
        "the web. You do not see what it was written from, and you must not rely on memory: every "
        "verdict rests on a page you open and quote.\n\n"
        f"Site: {name}\nCountry: {country}\nText: {card}\n\n"
        "YOUR TASK\n"
        "1. List every claim of the text, the central claim first: what kind of place the site is "
        "(a fort, a tomb, a settlement, a temple, ...), with where it is if the text says so - the "
        "claim without which the text would be about another place. Then each fact, number, date, "
        "name, place, material, size, function, superlative, and every statement or implication "
        "that something is unknown or mysterious.\n"
        "2. For each, search the web and decide SUPPORTED, CONTRADICTED or UNVERIFIABLE.\n"
        "3. Prefer pages that can be quoted: Wikipedia, national heritage registers, museum and "
        "university pages, published papers. Some sites refuse automated readers (Historic "
        "England and the Heritage Gateway answer 403, UNESCO often refuses, PDFs may be "
        "unreadable): quote another page when you can. Never cite ancientnerds.com - it is the "
        "text under test - nor an AI aggregator or a copy of Wikipedia (wikiwand, dbpedia, ...): "
        "the machine refuses such a page as a source, and its quote proves nothing.\n\n"
        f"{JUDGE_FORMAT}\n"
    )


def findings_of(record: Mapping[str, Any]) -> tuple[str, ...]:
    """The reasons an attempt failed, as the rewrite prompt and the outcomes show them: the
    mechanical problems of a writer's record, the checker's unsupported claims, tone, site and
    reasons, or the web verifier's contradicted and unproven claims."""
    if record["kind"] == "write":
        return tuple(record["problems"])
    if record["kind"] == "verify":
        return tuple(
            f'The web check contradicts: {claim["claim"]} ({claim["url"]}: "{claim["quote"]}")'
            if claim["verdict"] == "CONTRADICTED"
            else f"The web check could not prove: {claim['claim']}"
            for claim in record["claims"]
            if not claim["proven"] or claim["verdict"] != "SUPPORTED"
        )
    reasons = [
        f"No sentence of the description supports the claim: {claim['claim']}"
        for claim in record["claims"]
        if not claim["support"]
    ]
    if not record["tone_ok"]:
        reasons.append("The tone rules are broken (see the checker's reasons).")
    if not record["this_site"]:
        reasons.append("The card is not about this site.")
    reasons.extend(record["reasons"])
    return tuple(reasons)
