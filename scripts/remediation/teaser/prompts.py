"""Lane WB's questions: the writer's, the rewriter's, the checker's and the pilot judge's prompts.

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
    "No brackets, no citation markers, no emojis, no hashtags, no asterisks, no abbreviation 'c.' "
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
            "huge, carefully cut boulders together without mortar. How do you make stone fit like "
            "that?"
        ),
        claims=(
            ("on a hilltop", ("S5",)),
            ("outside Cusco", ("S1",)),
            ("at 3,701 metres", ("S2",)),
            ("the walls are Inca work", ("S2", "S6")),
            ("huge boulders, carefully cut, fitted together without mortar", ("S4",)),
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


def _sentences(site: C.Basis) -> str:
    return "\n".join(f"{sentence.id} {sentence.text}" for sentence in site.sentences)


def _site_block(site: C.Basis) -> str:
    forms = " | ".join(site.forms)
    return (
        f"Name: {site.name}\nCountry: {site.country}\n"
        f"NAME FORMS (the card must contain one of these, exactly): {forms}\n\n"
        "THE FACT BASIS - the site's published description, sentence by sentence:\n"
        f"{_sentences(site)}"
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


def checker_prompt(site: C.Basis, card: str) -> str:
    """The checker's question: every claim of `card` against the site's sentences."""
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
    """The pilot judge's question: every claim of a card against sources on the web."""
    return (
        "You are an independent fact checker. Below is a short teaser text about an archaeological "
        "site, written for a website and its narrated short videos. Check it against sources on "
        "the web. You do not see what it was written from, and you must not rely on memory: every "
        "verdict rests on a page you open and quote.\n\n"
        f"Site: {name}\nCountry: {country}\nText: {card}\n\n"
        "YOUR TASK\n"
        "1. List every claim of the text: each fact, number, date, name, place, material, size, "
        "function, superlative, and every statement or implication that something is unknown or "
        "mysterious.\n"
        "2. For each, search the web and decide SUPPORTED, CONTRADICTED or UNVERIFIABLE.\n"
        "3. Prefer pages that can be quoted: Wikipedia, national heritage registers, museum and "
        "university pages, published papers. Some sites refuse automated readers (Historic "
        "England and the Heritage Gateway answer 403, UNESCO often refuses, PDFs may be "
        "unreadable): quote another page when you can. Never cite ancientnerds.com - it is the "
        "text under test.\n\n"
        f"{JUDGE_FORMAT}\n"
    )


def findings_of(record: Mapping[str, Any]) -> tuple[str, ...]:
    """The reasons an attempt failed, as the rewrite prompt shows them: the mechanical problems of
    a writer's record, or the checker's unsupported claims, tone, site and reasons."""
    if record["kind"] == "write":
        return tuple(record["problems"])
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
