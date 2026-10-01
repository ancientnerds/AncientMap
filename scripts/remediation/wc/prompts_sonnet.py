"""The frozen texts added on 2026-10-01 (owner decisions "Wikipedia/Wikidata reicht", "Neu aus
Webquellen" and the model decision: the orchestrator is Opus 5.5, every answering agent Sonnet 5.5):
the check question of a site-list run, the write question of lane WN, the verifier's and the judge's
question of a WN run, and the briefs of every run that is not a plain WC run.

`prompts.py` is not touched: its question texts are pinned by `prompt_sha256` in the exported rounds
of the runs in flight (`mass-2026-09-27-01..05`, the WB and P4 runs), and their briefs are pinned by a
byte hash too. Every text here is **derived** from the old one by exact replacements, each of which
must match - so the rules of the check, the verification and the judge stay one text, and a change of
the old template that this one rests on is an `ImportError`, never a silent drift. The WN write
question is its own text. Every text is pinned by a byte hash in `tests/remediation/test_wn.py`.

The briefs tell the agent to record its answer with `--model claude-sonnet-5-5` (the model id every
answering agent runs as) and name the agents `sonnet-...`.
"""

from __future__ import annotations

from wc import prompts as P


def _derive(template: str, *edits: tuple[str, str]) -> str:
    """`template` with each (old, new) applied; every `old` must occur, or the old text changed."""
    out = template
    for old, new in edits:
        if old not in out:
            raise ImportError(f"the old template no longer holds {old[:70]!r}: re-derive it")
        out = out.replace(old, new)
    return out


# ------------------------------------------------------------------ a site-list run's check
#: Where the asked text comes from, by its marking (`wc4.Marking`): one sentence in the question.
ORIGINS = {
    "L": "The description was written in March 2026 by an AI enrichment chain.",
    "march-unmarked": "The description was written in March 2026 by an AI enrichment chain.",
    "unclaimed": "The description is an older text of the database whose origin is not recorded.",
    "phase4": (
        "The description was assembled in 2026 by an AI system from sentences of a Wikipedia "
        "article, and a later web check found a claim in it contradicted."
    ),
    "web": "The description was written in 2026 by an AI agent from web pages.",
}

#: A Phase-4 text keeps its sentences or loses them: the old provenance can only be filtered.
NO_TRIM = (
    "THIS TEXT IS NOT TRIMMED. Its sentences are kept whole or dropped: answer KEEP or DROP for "
    "every sentence. A KEEP_TRIMMED answer is refused by code, so a sentence with one piece that "
    "no reputable source supports is a DROP.\n\n"
)

#: The check question of a site-list run (`wc/cli.py export --sites`): `CHECK_QUESTION` with the
#: origin of the text said as it is (`{origin}`, `ORIGINS`) and, for a Phase-4 text, the no-trim
#: rule (`{trims}`, `NO_TRIM`; empty otherwise).
CHECK_QUESTION_LISTED = _derive(
    P.CHECK_QUESTION,
    (
        "The description was written in March 2026 by an AI enrichment chain and is shown on the "
        "public page of the site.",
        "{origin} It is shown on the public page of the site.",
    ),
    (
        "DECIDE, for each of the sentences {asked}, exactly one of:",
        "{trims}DECIDE, for each of the sentences {asked}, exactly one of:",
    ),
)

# ------------------------------------------------------------------ lane WN's write question
#: The one question per site of lane WN: write 2 to 6 sentences, each on verbatim quotes. The
#: numbers are the parser's (`answers.MIN_SENTENCES` ...); `cli.write_prompt` fills them in.
WRITE_QUESTION = """\
You write the description of one site of the Ancient Nerds archaeology database. The site has no \
description yet. You write it only from what reputable pages on the web say: every sentence you \
write is a faithful statement of a verbatim quote you give from a page, and a second agent verifies \
every sentence afterwards against the web. The description is shown on the public page of the site. \
You research on the web yourself.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

WRITE {min_sentences} to {max_sentences} sentences about this site: what it is, where it lies, when \
it dates from, what was built, found or done there - whatever reputable sources state. A site you \
cannot identify on the web, a namesake, or one for which no reputable page supports \
{min_sentences} sentences gets NO sentences (see ANSWER): it then stays without a description. \
Never pad, never guess, never write from memory alone.

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
is published in the site's list of sources, so code checks that the page's text carries it.
4. Write in your own words, in plain, neutral English: state the quoted fact, do not paste the \
quoted sentence. A sentence that shares a run of {max_run} words or more with one of its own quotes \
is refused by code.
5. Every sentence is one sentence of {min_chars} to {max_chars} characters that opens with a capital \
letter or a digit and ends with . ! or ?. It stands on its own: it never opens with a pronoun that \
points back to the sentence before it (It, Its, This, These, They, Their, He, She, His, Her, There, \
Here, ...) and has no "it" or "they" as its subject right after its first comma - name the \
subject. The first sentence says what the site is and where. No citation marker like [1]: code adds the \
citations from your quotes. No sentence is written twice.
6. Every sentence is about THIS site. The stored values identify it - above all its coordinates; \
they are no evidence for a sentence and may themselves be wrong.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "sentences": [
  {{"text": "...", "quotes": [{{"url": "https://...", "title": "...", "quote": "..."}}], "note": \
"which claim each quote supports"}},
  {{"text": "...", "quotes": [...], "note": "..."}}
], "note": "what you searched, in one sentence"}}
{min_sentences} to {max_sentences} sentence objects, in the order they are read. If no reputable \
page supports {min_sentences} sentences, answer {{"site_id": "{site_id}", "sentences": [], "note": \
"what you searched and why nothing is supported"}}. Every "note" is a short plain sentence, at most \
600 characters.
"""

#: The instruction of the Sonnet agent that answers one batch of write questions.
WRITE_BRIEF = """You are Sonnet writer {batch} of the Ancient Nerds web-sourced descriptions (lane WN). \
You answer {count} question(s), each about another site. Answer each one on its own, as if it were \
the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository - no other batch, nothing else under output/ or docs/, no database, \
no git history. Your evidence is your own web research (WebSearch, WebFetch), as each prompt says. \
Run every command below from the repository root, {repo}.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research the site on the web and write the description, exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it. The check fetches every page you quote (as the import will) and searches it for your \
quotes; it prints each sentence's outcome and the description your answer would leave:
   {python} scripts/remediation/wc/cli.py check-answer --run-dir {run} --handoff {handoff} \
--batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   Fix what it names - a quote copied inexactly, a page that refuses the fetcher, a title the page \
does not carry, a sentence too close to its quote, a sentence that opens with a pronoun - and check \
again. If no page you can quote supports {min_sentences} sentences, answer with no sentences. Never \
change a finding to make the check pass.
5. Record it - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --model claude-sonnet-5-5 \
--text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded and how many \
sentences you wrote and how many sites you left without any.
"""

# ------------------------------------------------------------------ lane WN's verification and judge
#: The verifier's question about a text lane WN wrote: `VERIFY_QUESTION`, told that the sentences
#: were written, not checked.
VERIFY_QUESTION_WN = _derive(
    P.VERIFY_QUESTION,
    (
        "Another agent checked the old description sentence by sentence against sources; the "
        "sentences below marked KEPT are what the site page will show, in this order, each with the "
        "quotes that agent gave.",
        "Another agent wrote this new description from web pages, every sentence on verbatim quotes "
        "it gave; the sentences below marked KEPT are what the site page will show, in this order, "
        "each with the quotes that agent gave.",
    ),
    (
        "below each, the old sentence a piece was cut from, and the checker's quotes",
        "below each, the writer's quotes",
    ),
    ("removed from the old description;", "written, then removed;"),
    ("the checker's quotes or your own", "the writer's quotes or your own"),
    ("Read what the checker's pages say", "Read what the writer's pages say"),
    (
        "Sources follow the same rules as the check:",
        "Sources follow the same rules as the writer's:",
    ),
)

#: The judge's question about a text lane WN wrote (the pilot's measurement).
JUDGE_QUESTION_WN = _derive(
    P.JUDGE_QUESTION,
    (
        "You judge, independently, the result of a sentence check of one site description of the "
        "Ancient Nerds archaeology database. Another agent checked the old description sentence by "
        "sentence against sources; the sentences below marked KEPT are what the site page will show, "
        "each with the quotes the checker gave.",
        "You judge, independently, a new description of one site of the Ancient Nerds archaeology "
        "database. Another agent wrote it from web pages, every sentence on verbatim quotes it gave, "
        "and a second agent verified it; the sentences below marked KEPT are what the site page will "
        "show, each with the quotes the writer gave.",
    ),
    (
        "below each, the old sentence a piece was cut from, and the checker's quotes",
        "below each, the writer's quotes",
    ),
    ("removed from the old description)", "written, then removed)"),
    ("the checker's quotes or your own", "the writer's quotes or your own"),
    (
        "Sources follow the same rules as the check:",
        "Sources follow the same rules as the writer's:",
    ),
)

# ------------------------------------------------------------------ the briefs of every non-plain run
_OLD_MODEL = "--model <the model id you run as: claude-sonnet-5-5 or claude-opus-5-5>"
_NEW_MODEL = "--model claude-sonnet-5-5"

#: The check brief of a site-list run, the verifier's and the judge's brief of a site-list or WN
#: run: the old briefs, a Sonnet agent, recording with `--model claude-sonnet-5-5`.
CHECK_BRIEF_SONNET = _derive(
    P.CHECK_BRIEF, ("You are Opus checker", "You are Sonnet checker"), (_OLD_MODEL, _NEW_MODEL)
)
VERIFY_BRIEF_SONNET = _derive(
    P.VERIFY_BRIEF, ("You are Opus verifier", "You are Sonnet verifier"), (_OLD_MODEL, _NEW_MODEL)
)
JUDGE_BRIEF_SONNET = _derive(
    P.JUDGE_BRIEF, ("You are Opus judge", "You are Sonnet judge"), (_OLD_MODEL, _NEW_MODEL)
)
