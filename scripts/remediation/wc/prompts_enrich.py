"""The frozen texts of lane E, the enrichment (owner decisions D3, D4 and D21 of 2026-10-08;
orchestrator decision X1; runbook `docs/procedures/SENTENCE_CHECK.md` section 14): the write question
that appends sentences to a description a site already has, the verifier's and the judge's question
about them, and the briefs of the three agents.

Like `prompts_sonnet.py` this module touches no earlier text: the questions of the runs in flight
(`mass-2026-09-27-01..05`, the WN and WB runs) rebuild byte for byte. Every text is pinned by a byte
hash in `tests/remediation/test_enrich.py`. The verifier's and the judge's rules of evidence are the
WC ones, derived by exact replacement from `prompts.py` where the sentence is the same, so a change
of the old template is an `ImportError`, never a silent drift.

The briefs record each answer with `--role` and the role's registered model (`roles.ROLES`, owner
decision D6): the writer runs as `field_researcher` (Sonnet 5.5, high), the verifier as `web_verifier`
(Sonnet 5.5, high) and the pilot's judge as `pilot_judge` (Opus 5.5, xhigh); the import refuses an
answer that names another role (`enrich.require_role`).
"""

from __future__ import annotations

from wc import prompts as P
from wc import prompts_sonnet as P2

WRITER_ROLE = "field_researcher"
VERIFIER_ROLE = "web_verifier"
JUDGE_ROLE = "pilot_judge"

# ------------------------------------------------------------------ the write question
#: One class line of the question per class a site may take (`enrich.classes_block`).
CLASS_FACT_THIN = (
    "- fact: up to {max_facts} sentences, each adding one sourced fact the description lacks - what "
    "the site is, where it lies, when it dates from, who built, found or excavated it, what was "
    "found there. This description is thin, so it may take them."
)
CLASS_FACT_NONE = "- fact: none. This description is long enough; add no fact."
CLASS_HOOK = (
    "- open_question: at most one sentence, the last of your answer, at most {max_hook} characters. "
    "It says what reputable sources call still open about THIS site - a dating, function, "
    "authorship or identification that scholars cannot settle, or something not yet excavated or "
    "explained. Write it as a question or as a plain statement that the matter is unresolved "
    '("Whether the chambers served a calendar remains unknown."). It rests on a quote in which a '
    "source itself says the matter is open, disputed or unknown. Never invent a mystery: if no "
    "reputable page frames anything about this site as open, write no open_question at all - that "
    "is the right answer for most sites."
)
#: Added when the site has a dispute brief (`enrich.dispute_block`); `{a_*}` and `{b_*}` are the two
#: positions of the adjudicated record.
DISPUTE_BLOCK = """
THIS SITE IS DISPUTED (an earlier research found two positions and an adjudicator confirmed that \
reputable sources hold both; neither is yours to settle)
POSITION A: {a_claim}
  held by: {a_holders}
  source: {a_url} - "{a_quote}"
POSITION B: {b_claim}
  held by: {b_holders}
  source: {b_url} - "{b_quote}"
Write exactly two sentences about it, one of class dispute_a (position A) and then one of class \
dispute_b (position B), after any facts: each names who holds the position ("Excavators led by X \
date it to ...", "Geologists argue that ...") and states it as THEIR position, never as established \
fact - the page must not take a side. Each rests on its own verbatim quote from a reputable page. \
The pages above are a start: open them, check that they say it, and prefer a page that states the \
position in its holder's own words. If you cannot support both positions with reputable quotes, \
answer with no sentence at all.
"""

ENRICH_QUESTION = """\
You extend the description of one site of the Ancient Nerds archaeology database. The site has a \
description already, shown below; it stays exactly as it is, and the sentences you write are \
appended to the end of it. You write them only from what reputable pages on the web say: every \
sentence you write is a faithful statement of a verbatim quote you give from a page, and a second \
agent verifies every sentence afterwards against the web. The text is shown on the public page of \
the site. You research on the web yourself.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

THE DESCRIPTION AS IT STANDS (context only: its sentences are no evidence for yours, they may be \
wrong, and you never repeat them)
{sentences}

WHAT YOU MAY APPEND (a class per sentence; write the sentences in this order of classes)
{classes}
{dispute}
RULES
1. Every sentence states only what the quotes you give for it say, and every claim in it - every \
name, number, date, measurement, attribution ("built by", "dedicated to"), relation ("near", "part \
of") and every stated fact - rests on one of them. A number or date that no quote gives is not \
written. An approximate figure is written as approximate as the quote has it; a hedge the source \
shares ("probably", "is thought to") stays in the sentence; what a source calls uncertain is never \
turned into a fact. No superlative or uniqueness claim ("the oldest", "the only", "the largest") \
unless a quote states exactly that, and no style or cultural attribution that a source does not \
state.
2. A source is reputable and independent: Wikipedia (the article itself, any language), Wikidata, \
UNESCO, national heritage registers, museums, universities, excavation reports, scholarly \
publications, established reference works. Prefer Wikipedia and Wikidata where they say what you \
need; use another reputable page where they are silent. Never: ancientnerds.com; AI-generated \
aggregators (grokipedia, aroundus, mindtrip, evendo, wanderlog); Wikipedia mirrors (wikiwand, \
kiddle, dbpedia, alchetron, wiki2, everybodywiki, infogalactic, wikishire); code refuses them. The \
stored source and the Wikipedia title of the site, where it has them, are a good start - once you \
made sure they are about this site, not a namesake, the region or a later building on the spot.
3. A quote is copied verbatim from the page at its URL - character for character; only whitespace \
may differ - 20 to 500 characters, 1 to 4 quotes per sentence. Code fetches every URL with a plain \
HTTP request (no JavaScript, no cookies, no login) and searches the page text for the quote; a \
quote it does not find does not count, and a sentence with a quote that does not count is dropped. \
Prefer pages that serve their text directly: Wikipedia, Wikidata, UNESCO (whc.unesco.org), museum, \
university and government pages. These refused our fetcher when it was tested (HTTP 403 or a \
timeout): historicengland.org.uk, heritagegateway.org.uk, canmore.org.uk, britishmuseum.org, \
smarthistory.org, megalithic.co.uk - do not quote them. Avoid PDFs of scanned books, Google Books, \
JSTOR, paywalled journals and pages behind a cookie wall. Give the page's URL without tracking \
parameters, and its title: the page's main heading exactly as it stands on the page (for a \
Wikipedia article its name, e.g. "Tarxien Temples", not "Tarxien Temples - Wikipedia"). The title \
is published in the site's list of sources, so code checks that the page's text carries it. A page \
the description already cites keeps its number; give it as you would any other.
4. Write in your own words, in plain, neutral English: state the quoted fact, do not paste the \
quoted sentence. A sentence that shares a run of {max_run} words or more with one of its own quotes \
- or with a sentence the description has - is refused by code, and so is one that says again what \
the description already says.
5. Every sentence is one sentence of {min_chars} to {max_chars} characters that opens with a capital \
letter or a digit and ends with . ! or ?. It stands on its own: it never opens with a pronoun that \
points back to the sentence before it (It, Its, This, These, They, Their, He, She, His, Her, There, \
Here, ...) and has no "it" or "they" as its subject right after its first comma - name the \
subject. No citation marker like [1]: code adds the citations from your quotes. No sentence is \
written twice. All the sentences together add at most {max_added} characters.
6. Every sentence is about THIS site. The stored values identify it - above all its coordinates; \
they are no evidence for a sentence and may themselves be wrong.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "sentences": [
  {{"class": "fact", "text": "...", "quotes": [{{"url": "https://...", "title": "...", "quote": \
"..."}}], "note": "which claim each quote supports"}},
  {{"class": "open_question", "text": "...", "quotes": [...], "note": "..."}}
], "note": "what you searched, in one sentence"}}
The sentences in the order of the classes above. If you have nothing to append that reputable pages \
support, answer {{"site_id": "{site_id}", "sentences": [], "note": "what you searched and why \
nothing is supported"}}: the site is then left as it is - an honest empty answer beats a padded \
one. Every "note" is a short plain sentence, at most 600 characters.
"""

# ------------------------------------------------------------------ the verifier's question
VERIFY_QUESTION_ENRICH = """\
You verify, independently, sentences that another agent appended to one site description of the \
Ancient Nerds archaeology database before it is published. The description below is what the site \
page will show: its old sentences (marked S) stood there before and are not under judgement; the NEW \
sentences (marked K) were written from web pages, each on verbatim quotes the writer gave. A new \
sentence you do not confirm is removed; nothing is ever added or rewritten, and an old sentence is \
never removed. You decide, from your own research on the web, whether each new sentence is true of \
this site, and whether the whole text still reads as a coherent description.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

THE OLD SENTENCES (context; not under judgement)
{old}

THE NEW SENTENCES (appended after the old ones, in this order; below each, its class and the \
writer's quotes)
{kept}

NEW SENTENCES ALREADY REMOVED (shown only so that you see what a kept sentence may have referred \
to - do not judge them)
{dropped}

DECIDE
- For each new sentence K<k>: SUPPORTED (a reputable, independent source supports every claim in \
it - the writer's quotes or your own), UNSUPPORTED (some claim is supported by no such source you \
found) or WRONG (a source contradicts a claim; give that quote). A claim is every name, number, \
date, measurement, attribution, relation and stated fact - also a single word that says how, by \
whom or from what something was made. A superlative or uniqueness claim ("the only", "the first", \
"the largest") is SUPPORTED only when a source states exactly that; search for a source that \
disputes or qualifies it too, and if you find one, it is WRONG. Read what the writer's pages say \
around its quotes: a quote torn from its context supports nothing.
- A sentence of class open_question is SUPPORTED only if a reputable source itself calls the matter \
open, disputed or unknown, and every other claim in it is supported. If you find only that the \
writer saw a gap, or the sources treat the matter as settled, it is UNSUPPORTED (WRONG, with the \
quote, if a source settles it).
- A sentence of class dispute_a or dispute_b is SUPPORTED only if the position exists in reputable \
sources, is attributed to those who hold it and is stated as their position, not as fact. A \
position stated as fact is UNSUPPORTED.
- coherent: false when the whole text, old and new, does not read as one description of this site - \
a new sentence repeats or contradicts an old one, points at something the text never introduced, or \
does not fit; else true.
- broken: when coherent is false, the numbers k of the NEW sentences that make it incoherent (they \
are removed; what remains is published only if a verifier confirms it, else every new sentence is \
removed); when coherent is true, an empty list. If you cannot name them, give an empty list with \
coherent false: every new sentence is removed.
Sources follow the same rules as the writer's: Wikipedia, Wikidata, UNESCO, registers, museums, \
universities, scholarly publications; never ancientnerds.com, AI aggregators, Wikipedia mirrors or a \
copy of this description. A quote is verbatim from the page at its URL (code fetches it and searches \
for it) and 20 to 500 characters long.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "kept": [{{"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": \
"..."}}], "coherent": true, "broken": [], "note": "..."}}
One object per new sentence, in order ({kept_count} new); each quote is {{"url": "...", \
"quote": "..."}}; WRONG needs at least one quote; "broken" lists k numbers in ascending order; \
every "note" is a short plain sentence, at most 600 characters.
"""

# ------------------------------------------------------------------ the judge's question
JUDGE_QUESTION_ENRICH = """\
You judge, independently, sentences that another agent appended to one site description of the \
Ancient Nerds archaeology database. The agent wrote them from web pages, every sentence on verbatim \
quotes it gave, and a second agent verified them; the description below is what the site page will \
show. Its old sentences (marked S) stood there before and are not under judgement. You decide, from \
your own research on the web, whether each new sentence is true of this site, whether each removed \
one was rightly removed, whether the whole text reads as a coherent description, and - for the \
sentence of class open_question - whether the matter is really open.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

THE OLD SENTENCES (context; not under judgement)
{old}

THE NEW SENTENCES (kept, appended after the old ones, in this order; below each, its class and the \
writer's quotes)
{kept}

NEW SENTENCES REMOVED
{dropped}

DECIDE
- For each kept new sentence K<k>: SUPPORTED (a reputable, independent source supports every claim in \
it - the writer's quotes or your own), UNSUPPORTED (some claim is supported by no such source you \
found) or WRONG (a source contradicts a claim; give that quote).
- For a kept sentence of class open_question you may also answer INVENTED: the sentence may be \
true, yet no reputable source calls the matter open - the writer made the mystery up. A hook that \
only reads well is INVENTED.
- For each removed sentence D<d>: DROP_OK (it is contradicted or unsupported) or DROP_WRONG (a \
reputable, independent source supports every claim in it; give the quote).
- coherent: false when the whole text, old and new, does not read as one description of this site - \
a new sentence repeats or contradicts an old one, points at something the text never introduced, or \
does not fit; else true.
Sources follow the same rules as the writer's: Wikipedia, Wikidata, UNESCO, registers, museums, \
universities, scholarly publications; never ancientnerds.com, AI aggregators, Wikipedia mirrors or a \
copy of this description. A quote is verbatim from the page at its URL (code fetches it and searches \
for it) and 20 to 500 characters long.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "kept": [{{"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": \
"..."}}], "dropped": [{{"d": 1, "verdict": "DROP_OK", "quotes": [], "note": "..."}}], \
"coherent": true, "note": "..."}}
One object per kept and per removed new sentence, in order ({kept_count} kept, \
{dropped_count} removed); each quote is {{"url": "...", "quote": "..."}}; WRONG and DROP_WRONG \
need at least one quote; every "note" is a short plain sentence, at most 600 characters.
"""

# ------------------------------------------------------------------ the briefs
_OLD_MODEL = P2._OLD_MODEL
_WRITER_MODEL = f"--role {WRITER_ROLE} --model claude-sonnet-5-5"
_VERIFIER_MODEL = f"--role {VERIFIER_ROLE} --model claude-sonnet-5-5"
_JUDGE_MODEL = f"--role {JUDGE_ROLE} --model claude-opus-5-5"

#: The instruction of the Sonnet agent that answers one batch of enrich questions: `WRITE_BRIEF`
#: with the enrichment's task and the role the answer is recorded in.
ENRICH_BRIEF = P2._derive(
    P2.WRITE_BRIEF,
    (
        "You are Sonnet writer {batch} of the Ancient Nerds web-sourced descriptions (lane WN). ",
        "You are Sonnet writer {batch} of the Ancient Nerds description enrichment (lane E). ",
    ),
    (
        "2. Research the site on the web and write the description, exactly as the prompt asks.",
        "2. Research the site on the web and write the sentences to append, exactly as the prompt asks.",
    ),
    (
        "If no page you can quote supports {min_sentences} sentences, answer with no sentences.",
        "If no page you can quote supports a sentence, answer with no sentence.",
    ),
    ("--model claude-sonnet-5-5 --text-file", f"{_WRITER_MODEL} --text-file"),
    (
        "report how many answers you recorded and how many sentences you wrote and how many sites you left without any.",
        "report how many answers you recorded, how many sentences you appended and for how many sites you appended none.",
    ),
)
#: The Sonnet verifier's and the Opus judge's brief: the WC briefs with the role their answers are
#: recorded in.
VERIFY_BRIEF_ENRICH = P2._derive(
    P.VERIFY_BRIEF,
    ("You are Opus verifier", "You are Sonnet verifier"),
    (_OLD_MODEL, _VERIFIER_MODEL),
)
JUDGE_BRIEF_ENRICH = P2._derive(P.JUDGE_BRIEF, (_OLD_MODEL, _JUDGE_MODEL))
