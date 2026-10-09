"""Contract shorts-v1's questions: the writer's (three variants), the rewriter's, the hook rater's,
the checker's, the web judge's and the rewrite after a failed verification - and, for the
Claude re-check of the 167 MiniMax cards, the adversarial reviewer's.

Every prompt is a pure function of the site's basis (`shorts_v1.ShortsBasis`) and, for a rewrite or
a check, of the cards and findings before it - so an import can rebuild the exact prompt an answer
was given and refuse an answer to any other (`run.import_stage`). The v1 prompts (`prompts.py`) stay
byte-frozen; this module imports their pieces (`Finding`, `REPUTABLE`) and replaces the rest.

The four examples in `EXAMPLES` are samples of the card design (2026-10-08) for four pilot sites,
each passing `shorts_v1.problems_shorts` and mapped claim by claim to the sentences it rests on
(`tests/remediation/shorts_cases.py` pins their descriptions; a test holds every example to the code
and to the fixture). They show the tone and the faithfulness - they are not templates to copy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from teaser import answers_shorts as AS
from teaser import contract as C
from teaser import prompts as P
from teaser import shorts_v1 as SV

#: What the card is for (owner request of 2026-10-08, decisions D1-D5).
PURPOSE = (
    "Ancient Nerds is a globe of ancient sites with a card game and short videos. Every site has a "
    "card: a teaser of 160-190 characters that is the voice-over of the site's YouTube Short, "
    "shown on the site's card too. The Short opens with a flight over the globe - the site's "
    "country is already tinted on the screen - while the card is read aloud, and it reveals the "
    "site's name only at the very end, so the viewer must want to know which site this is. The "
    "card therefore never says the name. It must make a stranger stay for the next words and "
    "want to learn more about the site afterwards - and every fact in it must be true to the "
    "site's own published description."
)

RULES: tuple[str, ...] = (
    "English. Exactly two sentences, each ending with a full stop, on one line, 160-190 characters "
    "in all (letters, spaces and punctuation count). Sentence 1 is 40-85 characters: it is read "
    "during the flight, before any picture of the site.",
    "NO NAME. The card never holds the site's name, any alias of it, any distinctive word of the "
    "name, its country or the adjective for its people. The AVOID list names them. The Short "
    "names the site only after the card.",
    "The first five words are the hook: the most surprising concrete detail the description "
    "gives - an object, an act, a person, a number, what the name means, or something stated to "
    "be missing. Never an address and never a bare type label ('A Neolithic dolmen ...'). Sentence "
    "1 does not open with a place word (On, At, In, Near, Above, Between, Along ...) unless a "
    "number follows, nor with Located, Situated, Set, This, It, Its, Here or They.",
    "Landscape yes, address no. Say what the camera sees (a ridge, a hilltop, a valley, 'about "
    "3,800 metres up'), never where on the map: no province, district, region, county, parish or "
    "'near the village of ...'.",
    "Every fact comes from the numbered sentences of the description - nothing else: not your "
    "own knowledge, not what 'everybody knows' about the site. A hedge in the description "
    "('possibly', 'believed', 'by one estimate', 'about') stays a hedge in the card.",
    "These are CLAIMS and need a sentence that says them: that something is unknown, unexplained, "
    "secret, lost, hidden or mysterious; superlatives ('oldest', 'largest', 'first', 'only', "
    "'unique', 'rare', 'most'); numbers, dates and periods; names of people, peoples and places; "
    "materials, sizes, functions. A mystery or superlative word is allowed only where the "
    "description itself uses the same word.",
    "Mystery is TONE: order the facts so that one true thread stays open - the viewer learns what "
    "is there and wants to know which site it is and what the rest of the story is. Never imply "
    "that something is unknown unless a sentence says so.",
    "Numbers: digits exactly as the description writes them, at most 2 numerals, at most 8 digits "
    "in all and at most 4 in sentence 1 (a digit costs about a third of a second of narration). "
    "Never compute a new number or convert one. Write a regnal number out ('Ramesses the Third'), "
    "no Roman numerals. The whole card is read in at most 14 seconds: 6.04 + 0.0334 x characters + "
    "0.318 x digits.",
    "Short, common words, for all ages and vivid active verbs. Each word is shown alone on the "
    "screen: avoid words of twelve letters or more and long hyphenated compounds. No marketing "
    "phrases ('hidden gem', 'step back in time').",
    "No question mark, no exclamation mark, no ellipsis, no 'you' or 'your', and no word that "
    "talks about the video or sends the viewer anywhere: link, description, comment, subscribe, "
    "guess, find out, discover, learn more, watch, click, video.",
    "Sentence 1 must also read naturally straight after the spoken 'Name, Country.' - the Short "
    "loops - and the card must fit this site only, not ten sites of the same kind.",
    "The card's open thread must be answered on the site's page: name in RESERVE the ids of "
    "description sentences you did NOT use that answer or extend it, or 'reveal' when the spoken "
    "name itself answers it (a name that means something). If nothing answers it, the reserve is "
    "null.",
)

ANCHOR_RULE = (
    "PHOTO ANCHORS (this site can be a Short). The Short cuts its pictures on the words you name. "
    "Copy 1-3 phrases from your card, exactly as written, each a concrete thing a photograph can "
    "show (the IMAGE TITLES hint at what exists, they are no fact). Anchor 1 ends in the last 25 "
    "characters of sentence 1; every later anchor starts at character 95 or later; two anchors "
    "start at least 28 characters apart."
)
NO_ANCHORS = "PHOTO ANCHORS: this site cannot be a Short; the anchors are []."

DONT: tuple[str, ...] = (
    "'In the Cusco Region, the Inca citadel of ...' - an address, and a name.",
    "'A Neolithic dolmen on a hillside near the village of ...' - a type label and an address.",
    "'Built by a lost civilization no one can name' - unless a sentence says the builders are "
    "unknown.",
    "'5,000 years ago' from '3000 BC' - a computed number.",
    "'Discover the secrets of this ancient site - link below!' - a call to action.",
)


@dataclass(frozen=True)
class Example:
    """A card written from one site's description, with what a writer answers beside it."""

    site: str
    country: str
    eligible: bool
    sentences: tuple[tuple[str, str], ...]
    card: str
    anchors: tuple[str, ...]
    reserve: tuple[str, ...]
    hook_type: str
    claims: tuple[tuple[str, tuple[str, ...]], ...]


EXAMPLES: tuple[Example, ...] = (
    Example(
        site="Glaphyrae",
        country="Greece",
        eligible=False,
        sentences=(
            (
                "S1",
                "Glaphyrae was a settlement in Magnesia, ancient Thessaly, Greece, mentioned by "
                "Homer in the Catalogue of Ships alongside Boebe and Iolcus.",
            ),
            (
                "S2",
                "After this reference, the town does not appear in subsequent historical records.",
            ),
            (
                "S3",
                "In the 19th century, William Martin Leake identified the site with Hellenic "
                "ruins on a hill above modern Glafira, between Boebe and Iolcus, an "
                "identification accepted by modern scholars.",
            ),
            (
                "S4",
                "At the time of Leake's visit, the entire circuit of the citadel on the hill "
                "summit remained visible.",
            ),
        ),
        card=(
            "Homer names this town in his Catalogue of Ships, and then the records fall silent. In "
            "the 19th century, the whole circuit of its citadel was still visible on a hill "
            "between Boebe and Iolcus."
        ),
        anchors=(),
        reserve=("reveal",),
        hook_type="person",
        claims=(
            ("Homer names the town in the Catalogue of Ships", ("S1",)),
            ("after that the town does not appear in the records", ("S2",)),
            ("in the 19th century the site was identified on a hill", ("S3",)),
            ("the hill lies between Boebe and Iolcus", ("S3",)),
            ("the whole circuit of the citadel was still visible then", ("S4",)),
        ),
    ),
    Example(
        site="Huaca del Sol",
        country="Peru",
        eligible=True,
        sentences=(
            (
                "S1",
                "The Huaca del Sol is an adobe brick pyramid built by the Moche civilization "
                "(100 AD to 800 AD) on the northern coast of what is now Peru.",
            ),
            (
                "S2",
                "By 450 AD, eight different stages of construction had been completed on the Huaca del Sol.",
            ),
            (
                "S3",
                "Archeologists have estimated that the Huaca del Sol was composed of over 130 "
                "million adobe bricks and was the largest pre-Columbian adobe structure built in "
                "the Americas.",
            ),
            (
                "S5",
                "During the Spanish occupation of Peru in the early 17th century, colonists "
                "redirected the waters of the Moche River to run past the base of the Huaca del "
                "Sol in order to facilitate the looting of gold artifacts from the temple.",
            ),
        ),
        card=(
            "To help loot its gold, colonists made a river run past this Moche pyramid. By one "
            "estimate it took over 130 million adobe bricks: the largest adobe structure of the "
            "Americas before Columbus."
        ),
        anchors=("Moche pyramid", "130 million adobe bricks"),
        reserve=("S2",),
        hook_type="act",
        claims=(
            ("colonists redirected a river past the pyramid", ("S5",)),
            ("they did it to help loot gold", ("S5",)),
            ("it is a Moche pyramid", ("S1",)),
            ("an estimate says it took over 130 million adobe bricks", ("S3",)),
            ("it was the largest adobe structure of the Americas before Columbus", ("S3",)),
        ),
    ),
    Example(
        site="Machu Picchu",
        country="Peru",
        eligible=True,
        sentences=(
            (
                "S1",
                "Machu Picchu is a 15th-century Inca citadel located in the Eastern Cordillera of "
                "southern Peru on a mountain ridge at 2,430 meters.",
            ),
            (
                "S2",
                "Studies of skeletal remains found at Machu Picchu show that most people who "
                "lived there were immigrants from diverse backgrounds.",
            ),
            (
                "S3",
                "Excavations documented approximately 104 caves and rock shelters used as burial "
                "chambers around Machu Picchu, containing the remains of about 174 individuals, "
                "interpreted as largely belonging to yanaconas of diverse ethnic origins rather "
                "than the Inca elite.",
            ),
            (
                "S5",
                "The central buildings of Machu Picchu are built in classical Inca dry masonry, "
                "with large blocks precisely shaped through quarrying, stone-cutting, and "
                "stone-dressing, then fitted together without mortar.",
            ),
        ),
        card=(
            "Bones found here show that most people living in this Inca citadel were immigrants. "
            "Its central buildings are made of precisely shaped stone blocks, fitted together "
            "without mortar."
        ),
        anchors=("Inca citadel", "precisely shaped stone blocks"),
        reserve=("S3",),
        hook_type="object",
        claims=(
            ("skeletal remains were found at the site", ("S2",)),
            ("they show that most people who lived there were immigrants", ("S2",)),
            ("it is an Inca citadel", ("S1",)),
            ("its central buildings are made of precisely shaped stone blocks", ("S5",)),
            ("the blocks are fitted together without mortar", ("S5",)),
        ),
    ),
    Example(
        site="Intiyuq K'uchu",
        country="Peru",
        eligible=False,
        sentences=(
            (
                "S1",
                "Intiyuq K'uchu (or Pintasqa Wayq'u) is an archaeological site in Peru with rock paintings.",
            ),
            ("S3", "Intiyuq K'uchu is situated at a height of about 3,800 metres."),
            (
                "S4",
                'Inti means sun; -yuq is a suffix that denotes ownership; k\'uchu means "corner".',
            ),
        ),
        card=(
            "About 3,800 metres up, rock paintings mark a place with a name to decode. It starts "
            "with the word for sun, adds a suffix that means ownership, and ends with the word "
            "for corner."
        ),
        anchors=(),
        reserve=("reveal",),
        hook_type="number",
        claims=(
            ("the site is at about 3,800 metres", ("S3",)),
            ("it has rock paintings", ("S1",)),
            ("its name starts with the word for sun", ("S4",)),
            ("the name adds a suffix that means ownership", ("S4",)),
            ("the name ends with the word for corner", ("S4",)),
        ),
    ),
)


def _numbered(items: Sequence[str]) -> str:
    return "\n".join(f"{n}. {item}" for n, item in enumerate(items, start=1))


def avoid_words(site: SV.ShortsBasis) -> list[str]:
    """Everything the card must not say (C7, C8): the name's forms, every stored alias, the
    distinctive words of the name, the country and the words naming its people."""
    found = [*site.forms, *site.aliases, *SV.distinctive_tokens(site.name)]
    found += SV.country_terms(site.country)
    return list(dict.fromkeys(found))


def _sentences(site: C.Basis) -> str:
    return "\n".join(f"{sentence.id} {sentence.text}" for sentence in site.sentences)


def _web_block(site: C.Basis) -> str:
    """The web facts of a rewrite after a failed verification (v1's block); nothing otherwise."""
    return P._web_block(site)


def _site_block(site: SV.ShortsBasis) -> str:
    titles = "; ".join(site.image_titles) if site.image_titles else "(none)"
    return (
        f"Name: {site.name} (NEVER in the card)\nCountry: {site.country} (NEVER in the card)\n"
        f"AVOID (the card holds none of these words): {' | '.join(avoid_words(site))}\n"
        f"SHORTS-ELIGIBLE: {'yes' if site.shorts_eligible else 'no'}\n"
        f"IMAGE TITLES (hints for the photo anchors, no fact): {titles}\n\n"
        "THE FACT BASIS - the site's published description, sentence by sentence:\n"
        f"{_sentences(site)}{_web_block(site)}"
    )


def _examples() -> str:
    blocks = []
    for example in EXAMPLES:
        used = "\n".join(f"  {sid} {text}" for sid, text in example.sentences)
        claims = "\n".join(f"  - {claim}: {', '.join(ids)}" for claim, ids in example.claims)
        answer = json.dumps(
            {
                "card": example.card,
                "basis": sorted({s for _, ids in example.claims for s in ids}),
                "anchors": list(example.anchors),
                "reserve": list(example.reserve),
                "hook_type": example.hook_type,
            },
            ensure_ascii=False,
        )
        blocks.append(
            f"{example.site} ({example.country}; the card does not say either) - the sentences "
            f"it rests on:\n{used}\nCard ({len(example.card)} characters): {example.card}\n"
            f"Its claims and their sentences:\n{claims}\nOne variant of the answer: {answer}"
        )
    return "\n\n".join(blocks)


WRITER_FORMAT = (
    "Answer with ONLY this JSON object, nothing before or after it:\n"
    '{"variants": [{"card": "<card 1>", "basis": ["S1", "S3"], "anchors": ["<phrase>"], '
    '"reserve": ["S5"], "hook_type": "object"}, <variant 2>, <variant 3>]}\n'
    "Exactly three variants. They differ in their cards and in their first three words - three "
    'different hooks drawn from the description. "basis" lists the ids of the sentences the '
    f'card\'s facts come from. "hook_type" is one of {", ".join(SV.HOOK_TYPES)}. "anchors" and '
    '"reserve" are as described above; "reserve" may be null.'
)
THIN_OPTION = (
    "THIN DESCRIPTION. This description is under 300 characters. If a card of 160-190 characters "
    "cannot be written from it without padding, repeating a sentence or inferring anything, do "
    'not write one - answer with exactly {"card": null, "thin": true, "reason": "<why>"} '
    "instead. The site is then enriched from sourced pages first."
)


def _tail(site: SV.ShortsBasis, format_text: str, *, may_decline: bool = True) -> str:
    """The rules, the anchor rule, the thin decline (offered only to a writer that may decline: not
    to the rewrite after a failed verification, whose answer is one card), the examples, the format."""
    thin = f"{THIN_OPTION}\n\n" if site.thin and may_decline else ""
    anchors = ANCHOR_RULE if site.shorts_eligible else NO_ANCHORS
    return (
        f"THE RULES\n{_numbered(RULES)}\n\n{anchors}\n\n{thin}NEVER, for example:\n"
        f"{_numbered(DONT)}\n\nGOOD CARDS (other sites, each true to its own description; they "
        f"are not templates):\n\n{_examples()}\n\n{format_text}\n"
    )


def writer_prompt(site: SV.ShortsBasis) -> str:
    """The writer's question for one site: three variants of the nameless card."""
    return (
        f"{PURPOSE}\n\nWrite three variants of the card of this site.\n\nTHE SITE\n"
        f"{_site_block(site)}\n\n{_tail(site, WRITER_FORMAT)}"
    )


def rewrite_prompt(site: SV.ShortsBasis, findings: Sequence[P.Finding]) -> str:
    """The rewriter's question: the writer's, plus every earlier card and why it failed."""
    earlier = "\n\n".join(
        f"Card {n} ({len(f.card)} characters): {f.card}\nWhy it was not accepted:\n"
        + "\n".join(f"- {reason}" for reason in f.reasons)
        for n, f in enumerate(findings, start=1)
    )
    return (
        f"{PURPOSE}\n\nThe card of this site has to be written again: the earlier card(s) below "
        "were not accepted. Write three new variants that fix every finding - the best one is "
        f"checked again, by another checker.\n\nTHE SITE\n{_site_block(site)}\n\nEARLIER "
        f"CARDS\n{earlier}\n\n{_tail(site, WRITER_FORMAT)}"
    )


VERIFY_WRITER_FORMAT = (
    "Answer with ONLY this JSON object, nothing before or after it:\n"
    '{"card": "<the card>", "basis": ["S1", "W1"], "repeats": ["S3"], "anchors": ["<phrase>"], '
    '"reserve": ["S5"], "hook_type": "object"}\n"basis" lists the ids of the sentences and web '
    'facts your card\'s facts come from. "repeats" has one entry per CONTRADICTED claim above, in '
    "its order: the id of the sentence of the description that states that claim, or null when no "
    'sentence does ([] when none is listed). "anchors", "reserve" and "hook_type" are as in '
    "the rules."
)


def verify_rewrite_prompt(
    site: SV.ShortsBasis,
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
        "it. A card read aloud must not repeat a claim the web contradicts. Write ONE new card: "
        "it is checked again, by another checker, and verified again on the web, by another "
        "verifier. There is no further round: if the new card fails, the site keeps the card it "
        f"has.\n\nTHE SITE\n{_site_block(site)}\n\n"
        f"THE CARD THE WEB CHECK DID NOT VERIFY ({len(card)} characters)\n{card}\n\n"
        f"CONTRADICTED - a page says otherwise:\n{P._contradicted(contradicted)}\n\n"
        f"NOT PROVEN - the web check found no page that proves these:\n{not_proven}\n\n"
        "WHAT THE NEW CARD MUST DO\n"
        "1. Drop every contradicted claim, or correct it. Correct a claim only with a fact that a "
        "sentence of the description or a WEB FACT states, its numbers written as that sentence "
        "or web fact writes them - nothing else, not your own knowledge. A web fact may be used "
        f"only if its page is a reputable source: {P.REPUTABLE}. When in doubt, drop the claim. "
        "(Rule 5 below extends to the web facts in this round only.)\n"
        "2. What the site is is never corrected from a web fact: a page that says the site is "
        "something else, or somewhere else, may be about a namesake. If that claim is "
        "contradicted, say it only as the description says it - the new verifier decides - or "
        "drop it.\n"
        "3. At most one claim of the new card may be one the web check could not prove, and "
        "never its identity-bearing claim (the detail that makes the card this site and no "
        "other). Prefer the facts the web check proved.\n"
        "4. For each contradicted claim above, in its order, name the sentence of the description "
        "that states it, or null if no sentence does: this lists the description's own errors for "
        "their repair.\n\n"
        f"{_tail(site, VERIFY_WRITER_FORMAT, may_decline=False)}"
    )


# ------------------------------------------------------------------------------ the hook rater
HOOK_SCALE: tuple[str, ...] = (
    "5 - the first five words are a concrete, surprising detail (an object, an act, a person, a "
    "number, a stated absence) that makes a stranger want the next words; it could open a video "
    "on its own.",
    "4 - concrete and interesting, but not surprising, or a little generic.",
    "3 - acceptable: concrete and no address; a viewer might stay.",
    "2 - weak: abstract, a general statement or a bare type label.",
    "1 - an address or boilerplate ('Located in ...', 'A Neolithic site ...').",
)
RATER_FORMAT = (
    "Answer with ONLY this JSON object, nothing before or after it:\n"
    '{"ratings": [{"variant": 1, "first5": "<its first five words, copied exactly>", "hook": 4}], '
    '"best": 1}\n- one rating for every variant shown, in any order; "hook" is a whole number 1-5; '
    '"best" is the number of a variant with the highest hook - on a tie, the one whose sentence 1 '
    "reads best straight after the spoken name."
)


def rate_prompt(name: str, country: str, shown: Sequence[tuple[int, str]]) -> str:
    """The hook rater's question: only the variants and the site's name and country (the Short
    speaks them right after the card, which is how the loop is judged). No description: the rater
    judges how the opening works, never whether it is true."""
    variants = "\n".join(f"Variant {number}: {card}" for number, card in shown)
    return (
        "You rate the opening of a teaser for a YouTube Short about an ancient site. The Short is "
        "a flight over the globe while the card is read aloud; the viewer decides within the "
        "first words whether to stay. The site's name is spoken only after the card: "
        f"'{name}, {country}.' - then the Short loops and the card starts again.\n\n"
        f"{variants}\n\nYOUR TASK\n"
        "Rate each variant's hook - its first five words, as a stranger hears them with no other "
        f"context - on this scale:\n{_numbered(HOOK_SCALE)}\n"
        "You do not know whether the facts are true and you must not try to find out: rate only "
        "how the opening works.\n\n"
        f"{RATER_FORMAT}\n"
    )


# ------------------------------------------------------------------------------ the checker
CHECKER_TONE: tuple[str, ...] = (
    "Plain words for all ages and vivid active verbs, not marketing copy ('hidden gem', 'step "
    "back in time').",
    "Mystery only as tone: no statement or implication that something is unknown, unexplained "
    "or unsolved unless a sentence says so ('no one can say why', 'how did they ...' are claims).",
    "No question, no 'you', no call to action; a hedge of the description stays a hedge.",
    "The closing beat is a concrete image or a true fact that widens the picture; a date may "
    "close the card only when it is the site's strongest fact.",
)
CHECKER_FORMAT = (
    "Answer with ONLY this JSON object, nothing before or after it:\n"
    '{"claims": [{"claim": "<one claim, in your words>", "support": ["S2"]}], "name_leak": false, '
    '"this_site": true, "hook_ok": true, "s1_no_place": true, "payoff_ok": true, "generic_ok": '
    'true, "loop_ok": true, "tone_ok": true, "anchors_ok": true, "verdict": "PASS", "reasons": []}\n'
    '- "support": the ids of the sentences that say the claim; [] when none does.\n'
    '- "verdict" is "PASS" only when every claim has support, name_leak is false, every other '
    'field is true and you have no other finding; then "reasons" is []. Otherwise "verdict" is '
    '"FAIL" and "reasons" lists every finding as one concrete sentence the writer can act on.'
)


def _worked_check() -> str:
    example = EXAMPLES[2]
    answer = {
        "claims": [{"claim": claim, "support": list(ids)} for claim, ids in example.claims],
        "name_leak": False,
        "this_site": True,
        "hook_ok": True,
        "s1_no_place": True,
        "payoff_ok": True,
        "generic_ok": True,
        "loop_ok": True,
        "tone_ok": True,
        "anchors_ok": True,
        "verdict": "PASS",
        "reasons": [],
    }
    return (
        f"Example - {example.site}, card: {example.card}\n"
        f"Answer: {json.dumps(answer, ensure_ascii=False)}\n"
        "Had the card said 'the oldest citadel in the Andes', the claim would have had support "
        '[], and the verdict would be FAIL with the reason "No sentence says it is the oldest '
        'citadel in the Andes."'
    )


def _web_rule(site: C.Basis) -> str:
    return P._web_rule(site)


def checker_prompt(site: SV.ShortsBasis, card: str, anchors: Sequence[str] = ()) -> str:
    """The checker's question: every claim of `card` against the site's sentences (and, checking a
    rewrite after a failed web verification, its web facts), and the judgement fields."""
    flagged = SV.present_state_words(card)
    present = (
        f"\nPRESENT-STATE WORDS in the card: {', '.join(flagged)}. A word that states how the "
        "site is today needs a sentence that states that state for that time; otherwise it is a "
        "claim without support.\n"
        if flagged
        else ""
    )
    shown_anchors = f"PHOTO ANCHORS the writer named: {' | '.join(anchors)}\n" if anchors else ""
    return (
        "You are the independent checker of a nameless teaser card for Ancient Nerds, a globe of "
        "ancient sites with a card game and narrated YouTube Shorts. The card is read aloud during "
        "a flight over the globe and the site's name is spoken only after it. The card was "
        "written by someone else from the site's published description; it may claim nothing the "
        f"description does not say.\n\nTHE SITE\n{_site_block(site)}\n\nTHE CARD\n{card}\n"
        f"{shown_anchors}{present}\nYOUR TASK\n"
        "1. List EVERY claim the card makes: each fact, number, date, period, name, place, "
        "material, size, function and use; every superlative or ranking; and every statement or "
        "implication that something is unknown, unexplained, unsolved or mysterious. Split "
        "compound statements into single claims.\n"
        "2. For each claim, give the ids of the sentences that say it. A faithful paraphrase is "
        "supported; an embellishment, a sharpened hedge, a computed number or an inference the "
        "sentences do not make is not. Use only the sentences above - not your own knowledge, "
        "even where you know the claim is true.\n"
        f"{_web_rule(site)}"
        "3. name_leak: true when the card gives the site away - its name or an alias, any "
        "distinctive word of the name (see AVOID), an English rendering used as a name ('Temple "
        "of the Sun'), or a modern settlement that shares the site's name.\n"
        "4. this_site: from its sentences the card could only be this site - not a namesake, a "
        "neighbouring place, the region, a museum or an object kept elsewhere.\n"
        "5. hook_ok: words 1-5 carry the most surprising concrete detail of the card (an object, "
        "an act, a person, a number, a name's meaning, a stated absence) - not an address, not a "
        "bare type label.\n"
        "6. s1_no_place: sentence 1 uses no settlement, region or river as an address; a "
        "landscape image (a ridge, a valley, 'about 3,800 metres up') is allowed.\n"
        "7. payoff_ok: every thread the card opens is answered by the description - by sentences "
        "the card does not use, or by the spoken name. The card must not close on a thread the "
        "description only names.\n"
        "8. generic_ok: the card would not fit ten other sites of the same kind.\n"
        "9. loop_ok: sentence 1 reads naturally straight after the spoken 'Name, Country.' and "
        "also as a free-standing line on the site's card.\n"
        f"10. tone_ok: the card follows these rules:\n{_numbered(CHECKER_TONE)}\n"
        "11. anchors_ok: each PHOTO ANCHOR is a concrete subject that one of the IMAGE TITLES "
        "could show (true when no anchor is named).\n\n"
        f"{_worked_check()}\n\n{CHECKER_FORMAT}\n"
    )


# ------------------------------------------------------------------------------ the web judge
def judge_prompt(name: str, country: str, card: str) -> str:
    """The web judge's question - the verifier of every card (stages `verify`, `verify2`) and the
    pilot's judge. The v1 question asks for the claim 'what kind of place the site is' first; a
    nameless card names no place, so the first claim is its identity-bearing claim (the verified
    rule never lets it go unproven: `run.card_verification`)."""
    return (
        "You are an independent fact checker. Below is a short teaser text about an archaeological "
        "site, written for a website and its narrated short videos. The text deliberately does "
        "not say the site's name; the name and country are given to you so that you can check "
        "every claim against the right site. Check the text against sources on the web. You do "
        "not see what it was written from, and you must not rely on memory: every verdict rests "
        "on a page you open and quote.\n\n"
        f"Site: {name}\nCountry: {country}\nText: {card}\n\n"
        "YOUR TASK\n"
        "1. List every claim of the text, the identity-bearing claim first: the claim that, with "
        "the country, picks this one site out - the object, person, event or detail that makes "
        "the text about this site and no other - understood as a claim about the site named "
        "above, not about a namesake or a neighbouring place. Then each other fact, number, "
        "date, name, place, material, size, function, superlative, and every statement or "
        "implication that something is unknown or mysterious.\n"
        "2. For each, search the web and decide SUPPORTED, CONTRADICTED or UNVERIFIABLE.\n"
        "3. Prefer pages that can be quoted: Wikipedia, national heritage registers, museum and "
        "university pages, published papers. Some sites refuse automated readers (Historic "
        "England and the Heritage Gateway answer 403, UNESCO often refuses, PDFs may be "
        "unreadable): quote another page when you can. Never cite ancientnerds.com - it is the "
        "text under test - nor an AI aggregator or a copy of Wikipedia (wikiwand, dbpedia, ...): "
        "the machine refuses such a page as a source, and its quote proves nothing.\n\n"
        f"{P.JUDGE_FORMAT}\n"
    )


# ------------------------------------------------------------------------------ the adversary
ADVERSARIAL_NOTE = (
    "You are the adversarial reviewer of a teaser card that is already public on the website. It "
    "was written by an AI model whose answers are not trusted, and a checker and a web verifier "
    "have both passed it. Your task is to find the reason it must NOT stay public. Read every "
    "claim as a sceptical editor: a sharpened hedge, a computed number, a superlative, an implied "
    "mystery, a namesake, a claim the cited pages do not carry. Pass the card only if you tried "
    "and found nothing."
)


def _evidence(verified: Mapping[str, Any]) -> str:
    lines = []
    for claim in verified["claims"]:
        found = (
            "quote found on the page"
            if claim["proven"]
            else (f"no proof: {claim['quote_outcome']}")
        )
        source = f" - {claim['url']}" if claim["url"] else ""
        lines.append(f"- [{claim['verdict']}, {found}] {claim['claim']}{source}")
    return "\n".join(lines)


def adversarial_prompt(
    site: C.Basis, card: str, checked: Mapping[str, Any], verified: Mapping[str, Any]
) -> str:
    """The Claude re-check's last question (owner decision D10): the card, the description's
    sentences, the checker's claim map and the verifier's evidence. The answer is v1's checker
    shape (`answers.parse_checker`)."""
    claims = "\n".join(
        f"- {claim['claim']}: {', '.join(claim['support']) or 'NO SUPPORT'}"
        for claim in checked["claims"]
    )
    return (
        f"{ADVERSARIAL_NOTE}\n\nTHE SITE\n{P._site_block(site)}\n\nTHE CARD\n{card}\n\n"
        f"THE CHECKER'S CLAIM MAP (another agent's, to be doubted):\n{claims}\n\n"
        f"THE WEB VERIFIER'S EVIDENCE (another agent's, to be doubted):\n{_evidence(verified)}\n\n"
        "YOUR TASK\n"
        "1. List EVERY claim of the card yourself, each fact on its own, including every "
        "superlative and every statement or implication that something is unknown.\n"
        "2. For each, give the ids of the sentences that say it - or [] where none does. A "
        "faithful paraphrase is supported; anything sharper than its sentence is not. Use only "
        "the sentences above and the evidence above.\n"
        "3. tone_ok: English, one or two sentences, no marketing copy, mystery only as tone.\n"
        "4. this_site: the card is about this site, not a namesake or a neighbour.\n"
        "5. The verifier above may have missed something. You may check any claim against pages on "
        "the web; a reason that rests on a page names the page and quotes it.\n"
        "PASS only when every claim has support, tone_ok and this_site are true and you have no "
        "other finding.\n\n"
        f"{P.CHECKER_FORMAT}\n"
    )


def findings_of(record: Mapping[str, Any]) -> tuple[str, ...]:
    """The reasons an attempt failed, as the rewrite prompt and the outcomes show them: the
    mechanical problems of a card (`write`), the rater's or the diversity finding (`rate`), the
    checker's findings (`check`) or the web verifier's contradicted and unproven claims
    (`verify`, v1's)."""
    kind = record["kind"]
    if kind == "write":
        return tuple(record["problems"])
    if kind == "rate":
        return tuple(record["findings"])
    if kind == "verify":
        return P.findings_of(record)
    reasons = [
        f"No sentence of the description supports the claim: {claim['claim']}"
        for claim in record["claims"]
        if not claim["support"]
    ]
    meanings = {
        "name_leak": True,
        "this_site": False,
        "hook_ok": False,
        "s1_no_place": False,
        "payoff_ok": False,
        "generic_ok": False,
        "loop_ok": False,
        "tone_ok": False,
        "anchors_ok": False,
    }
    labels = {
        "name_leak": "The card gives the site's name away.",
        "this_site": "The card is not about this site.",
        "hook_ok": "The first five words are not a concrete, surprising hook.",
        "s1_no_place": "Sentence 1 uses a place as an address.",
        "payoff_ok": "A thread the card opens is not answered by the description.",
        "generic_ok": "The card would fit ten other sites of the same kind.",
        "loop_ok": "Sentence 1 does not read naturally after the spoken name.",
        "tone_ok": "The tone rules are broken (see the checker's reasons).",
        "anchors_ok": "A photo anchor is no subject the site's images can show.",
    }
    reasons += [labels[key] for key, bad in meanings.items() if record.get(key) is bad]
    reasons.extend(record["reasons"])
    return tuple(reasons)
