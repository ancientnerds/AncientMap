"""Lane WC's frozen texts: the check question, its re-ask, the verifier's question, the judge's
question and their briefs.

Every text is pinned by a byte hash in `tests/remediation/test_wc.py`: a changed question makes
every exported answer stale (`opus_handoff.validate`), so a change is a new pin and a new export,
never an edit under a running round. The prompts are built only from these templates and the site's
own values (`cli.check_prompt`, `cli.verify_prompt`, `cli.judge_prompt`), so the import can rebuild
each exported prompt byte for byte and refuse an answer to anything else.
"""

from __future__ import annotations

import web_rules as WR

#: The one question per site. `{site}` is the site block, `{sentences}` the numbered sentences,
#: `{asked}` the sentence numbers to answer, `{reask}` empty in round 1 and the re-ask block after.
CHECK_QUESTION = """\
You check one site description of the Ancient Nerds archaeology database sentence by sentence. \
The description was written in March 2026 by an AI enrichment chain and is shown on the public \
page of the site. A sentence stays only when a reputable, independent source supports every claim \
in it; a sentence a source contradicts, or that no such source supports, is removed. You research \
on the web yourself.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

THE SENTENCES (as served, citation markers removed)
{sentences}
{reask}
DECIDE, for each of the sentences {asked}, exactly one of:
- KEEP: the whole sentence is true of this site. Give 1 to 4 quotes that together support every \
claim in it.
- KEEP_TRIMMED: one piece of the sentence is contradicted or unsupported and the rest is a \
grammatical sentence that is supported. Give the piece to remove in "remove" and 1 to 4 quotes \
that support everything that stays.
- DROP: give the reason "contradicted" (with at least one quote that contradicts a claim) or \
"unsupported" (no reputable, independent source you found supports every claim; no quote).

RULES
1. A claim is every name, number, date, measurement, attribution ("built by", "dedicated to"), \
relation ("near", "part of", "the largest", "the oldest") and every stated fact. A number or date \
that no source gives is unsupported. An approximate figure is supported only by a source that \
gives the same figure or range. A sentence that states as fact what the sources call uncertain is \
not supported; a hedge the sources share ("probably", "is thought to") is fine. A \
superlative or uniqueness claim ("the only", "the first", "the largest", "unique") and a \
style or cultural attribution ("passage tomb-style", "Roman-style", "Phoenician") stays only \
when a source states exactly that; search for a source that disputes or qualifies it too, and \
if you find one, remove that piece (KEEP_TRIMMED) or DROP the sentence as contradicted.
2. A source is reputable and independent: Wikipedia (the article itself, any language), \
UNESCO, national heritage registers, museums, universities, excavation reports, scholarly \
publications, established reference works. Never: ancientnerds.com; AI-generated aggregators \
(grokipedia, aroundus, mindtrip, evendo, wanderlog); Wikipedia mirrors (wikiwand, kiddle, \
dbpedia, alchetron, wiki2, everybodywiki, infogalactic, wikishire); any page that repeats this \
description's own wording - a copy of our text proves nothing, and code refuses it.
3. A quote is copied verbatim from the page at its URL - character for character; only whitespace \
may differ. Code fetches every URL with a plain HTTP request (no JavaScript, no cookies, no login) \
and searches the page text for the quote; a quote it does not find does not count. Prefer pages \
that serve their text directly: Wikipedia, UNESCO (whc.unesco.org), museum, university and \
government pages. These refused our fetcher when it was tested (HTTP 403 or a timeout): \
historicengland.org.uk, heritagegateway.org.uk, canmore.org.uk, britishmuseum.org, \
smarthistory.org, megalithic.co.uk - do not quote them. Avoid PDFs of scanned books, Google Books, \
JSTOR, paywalled journals and pages behind a cookie wall. Give the page's URL without tracking \
parameters, and its title: the page's main heading exactly as it stands on the page (for a \
Wikipedia article its name, e.g. "Tarxien Temples", not "Tarxien Temples - Wikipedia"). The title \
is published in the site's list of sources, so code checks that the page's text carries it.
4. Quote the words that carry the claim, 20 to 500 characters each; a quote may be a sentence or a \
passage of one page. Several quotes may come from one page.
5. "remove" (KEEP_TRIMMED only) is one exact piece of the sentence, copied character for \
character, including the comma or space that must go with it (", built by Khufu," or " in 1200 \
BC"), so that what stays reads as a complete sentence. The piece begins and ends between words - \
never inside a word or a number (" c. 3000 BCE", not " c. 3000 BC"; never "5" out of "3500") - \
and never takes the sentence's final . ! or ?. Code removes it only if it occurs exactly once, \
cuts no word or number, and what stays is a clean sentence (no double space, no dangling comma, at \
least 25 characters, a capital or digit first and . ! or ? last); code capitalises the first letter \
when the piece opened the sentence. A trim never takes a qualifier off what stays; code refuses \
such a piece, and the sentence is a DROP instead:
   - never just a word that negates, hedges or restricts (not, no, never, possibly, probably, \
about, c., only, partly, ...), nor a frame that hedges or reports what stays ("According to \
legend, ", "It is believed that ", "It is likely that ", ", it is said,");
   - never a piece with a word that puts the sentence under a telling or into doubt (according \
to, legend, tradition, myth, folklore, disputed, uncertain, unknown, attributed, ...);
   - a reporting word (believed, thought, said, claimed, reportedly, considered, ...) only inside \
the sentence, as the inner clause of the number or date it reports (", believed to date to about \
3000 BC,");
   - a negation only together with the whole rest of its clause (", not a tomb,"), and never a \
piece inside the clause of a negation that stays (" by Evans" out of "never excavated by Evans" \
widens the "never").
   A hedge or restriction word may go together with the whole claim it belongs to (" (c. 3000 \
BC)", ", probably a tomb,"). A piece must not leave the rest saying more than the sources support.
6. A sentence that opens with a pronoun (It, Its, This, These, They, ...) is removed by code when \
the sentence before it is removed; judge each sentence on its own claims.
7. Answer from what the sources say, never from memory alone, and never keep a sentence because it \
sounds plausible. The stored source and the Wikipedia article, where the site has them, are a good \
start - once you made sure they are about this site, not a namesake, the region or a later building \
on the spot.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "sentences": [
  {{"n": 1, "verdict": "KEEP", "remove": null, "reason": null, "quotes": [{{"url": "https://...", \
"title": "...", "quote": "..."}}], "note": "which claim each quote supports"}},
  {{"n": 2, "verdict": "KEEP_TRIMMED", "remove": ", built in 1200 BC", "reason": null, "quotes": \
[...], "note": "why the piece goes, what the quotes support"}},
  {{"n": 3, "verdict": "DROP", "remove": null, "reason": "contradicted", "quotes": [...], "note": \
"what the source says instead"}},
  {{"n": 4, "verdict": "DROP", "remove": null, "reason": "unsupported", "quotes": [], "note": \
"what you searched and did not find"}}
]}}
One object per sentence of {asked}, in that order; "note" is a short plain sentence, at most 600 \
characters.
"""

#: The re-ask block (round 2): the sentences of round 1 whose quotes code did not find, and why.
REASK_BLOCK = """
RE-ASK: in the earlier answer about this site, code could not use the following sentences - their \
quotes were not found on the pages as fetched, a page was refused, or the answer was not in shape. \
Answer ONLY these sentences again. A page that failed to fetch stays failed: use another page.
{failures}
"""

#: What every brief says of the shared Wikipedia cache (`{wiki_cache}`: the repo-relative directory
#: of `output/remediation/final-2026-10-08/wiki_cache`, filled once by one serial fetcher). The
#: agents read the site's Wikipedia text from disk and fetch every other source live, one request at
#: a time: four or more parallel fetchers got the office IP throttled (403/429) on 2026-10-07, and
#: a throttled fetch is no finding. The cache is a reading aid only: code checks every quote against
#: the live page it fetches itself. A brief is printed for the agent and is no part of an exported
#: prompt, so a change here makes no answer stale.
#:
#: What the agent may take from the cache depends on its role (`web_rules`, diagnosis of calibration
#: teaser-2026-10-09): the text it checks was written from that very article, so a CHECKER, verifier
#: or judge (`WIKI_CACHE_NOTE`) never counts the article as confirmation and searches outside it,
#: without a cap on requests; a WRITER (`WIKI_CACHE_NOTE_WRITER`, lane WN and the enrichment) reads
#: it first and needs a page from outside it for a fact the question asks it to establish.
_WIKI_CACHE_LOOKUP = """\
The Wikipedia article of each site is in a shared cache on disk: {wiki_cache}/INDEX.jsonl holds one \
JSON line per site and page ({{"site_id", "lang", "title", "file"}}); the page is the JSON file \
{wiki_cache}/<file> ({{"resolved_title", "revid", "text"}}; <file> is written with \\ or /). Read the \
site's Wikipedia text from there - this cache is the only other place you may read. """
WIKI_CACHE_NOTE = (
    _WIKI_CACHE_LOOKUP
    + WR.VERIFIER_RULE
    + " "
    + WR.MARKER_NOTE
    + " Code still checks each quote against the live page it fetches itself."
)
WIKI_CACHE_NOTE_WRITER = (
    _WIKI_CACHE_LOOKUP
    + WR.RESEARCHER_RULE
    + " "
    + WR.MARKER_NOTE
    + " Code still checks each quote against the live page it fetches itself."
)

#: The instruction of the agent that answers one batch of check questions.
#:
#: CHECK_BRIEF and VERIFY_BRIEF sharpened 2026-11-05 (owner decision D80, orchestrator decision O6):
#: the Opus calibrations wc-fc-2o and wc-wv-2o failed at the top tier, and the adjudication of their
#: disagreements (`calibration/wc-adjudication-2026-10-25/REPORT.md`) names the failure modes - the
#: checker kept a sentence whose word of how something was made differed from its own quote, kept a
#: text whose definite phrase lost its referent with a cut, kept as fact what the sources hedge, and
#: dropped sentences a legal trim repairs after reading too few pages; the verifier answered
#: UNSUPPORTED where support exists (too few pages, a throttled fetch taken for a finding, another
#: sentence's dispute counted twice, the stored article treated as one side of a disagreement). The
#: briefs carry the checks against them; the QUESTION texts stay as exported (open rounds rebuild
#: their prompts byte for byte), and no example is drawn from a unit of the recalibrated pools
#: (`test_wc.POOL_EXAMPLES`). A seal binds the new bytes; the re-seals are wc-fc-1o2/2o2/3o2 and
#: wc-wv-1o2/2o2.
CHECK_BRIEF = """You are {family} checker {batch} of the Ancient Nerds sentence check (lane WC, round \
{round}). You answer {count} question(s), each about another site. Answer each one on its own, as \
if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository (the Wikipedia cache named below is the one exception) - no other batch, nothing else under output/ or docs/, no database, \
no git history. Your evidence is your own web research (WebSearch, WebFetch), as each prompt says. \
Run every command below from the repository root, {repo}.

{wiki_cache_note}

For each question:
1. Read {handoff}/<prompt_path>.
2. Research each sentence on the web and decide, exactly as the prompt asks. Then go through \
every sentence once more with the four checks below; each names an error earlier checkers of this \
lane made.
   a. Word against quote. Set every word of the sentence that says how, by whom, from what or of \
what something was made or done beside the words of your own quotes. A sentence that uses another \
such word than its sources use is not supported as worded, even where your quote is about the \
same thing: remove that piece (KEEP_TRIMMED) or DROP. Never keep a sentence that your quote fits \
only once it is reworded.
   b. Settled against hedged. Where the reputable sources call a claim probable, uncertain or \
disputed and the sentence states it as settled fact, the claim is not supported; one page that \
states it as fact does not outweigh the others' hedge.
   c. Search before you drop, and trim before you drop. Before you call any claim unsupported, \
search beyond the first pages you read: the sources the Wikipedia article itself cites, \
other-language Wikipedias, national and regional heritage registers and culture-ministry portals, \
scholarly encyclopedias and excavation reports, and an archived copy (web.archive.org) of a page \
that refuses the fetcher. A short official page that leaves something out is no evidence against \
it. When one piece of a sentence fails and the rest holds, the answer is KEEP_TRIMMED with a legal \
rule-5 piece, not DROP.
   d. What stays must still read. Read the sentences you keep alone, in order, as the page will \
show them after your cuts. A kept sentence whose pronoun or definite phrase ("it", "this", "the \
later phase") pointed at a sentence you drop or at a piece you remove - also when a reader would \
now take it to mean something that is still in the text - was written about what is gone: keep \
the piece it points at if that piece holds, else DROP the sentence ("unsupported", the note naming \
the lost referent). A text of supported sentences can still be broken this way.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it. The check fetches every page you quote (as the import will) and searches it for your \
quotes; it prints each sentence's outcome and the description your answer would leave:
   {python} scripts/remediation/wc/cli.py check-answer --run-dir {run} --handoff {handoff} \
--batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   Fix what it names - a quote copied inexactly, a page that refuses the fetcher, a title the page \
does not carry, a piece to remove that is not exact - and check again. If no page you can quote supports a sentence, it is a DROP \
("unsupported"). Never change a finding to make the check pass.
5. Record it (you run as {model}; the command refuses any other model) - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --model {model} --role {role} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded and how many \
sentences you kept, trimmed and dropped.
"""

#: The independent verifier's question about one checked site, before its text is published (the
#: stages `verify` and `verify2`, every site whose check kept a sentence): the judge's question
#: below applied to the kept text - its kept sentences, verdicts, quote shape and coherence - with
#: the dropped sentences as context only, and `broken`, the sentences whose reference or meaning
#: broke (`cli.verify_prompt`, `answers.parse_verify`).
VERIFY_QUESTION = """\
You verify, independently, one site description of the Ancient Nerds archaeology database before \
it is published. Another agent checked the old description sentence by sentence against sources; \
the sentences below marked KEPT are what the site page will show, in this order, each with the \
quotes that agent gave. A sentence you do not confirm is removed; nothing is ever added or \
rewritten. You decide, from your own research on the web, whether each kept sentence is true of \
this site, and whether the kept text reads as a coherent description.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

KEPT SENTENCES (the text to publish, in order; below each, the old sentence a piece was cut from, \
and the checker's quotes)
{kept}

DROPPED SENTENCES (removed from the old description; shown only so that you see what a kept \
sentence may have referred to - do not judge them)
{dropped}

DECIDE
- For each kept sentence K<k>: SUPPORTED (a reputable, independent source supports every claim in \
it - the checker's quotes or your own), UNSUPPORTED (some claim is supported by no such source you \
found) or WRONG (a source contradicts a claim; give that quote). A claim is every name, number, \
date, measurement, attribution, relation and stated fact - also a single word that says how, by \
whom or from what something was made ("carved" where the sources say "built"). A superlative or \
uniqueness claim ("the only", "the first", "the largest") and a style or cultural attribution \
("passage tomb-style", "Roman-style") is SUPPORTED only when a source states exactly that; search \
for a source that disputes or qualifies it too, and if you find one, it is WRONG. Read what the \
checker's pages say around its quotes: a quote torn from its context supports nothing.
- coherent: false when the kept text does not read as a description of this site - a pronoun or \
a phrase ("it", "the complex", "the ancient name") whose referent was dropped or cut, or that now \
points at something else; a trimmed sentence that is no longer grammatical; a sentence that now \
says something else than it did; else true.
- broken: when coherent is false, the numbers k of every kept sentence whose reference or meaning \
broke (they are removed; what remains is published only if a verifier confirms it, else the whole \
description is cleared); when coherent is true, an empty list. If you cannot name them, give an \
empty list with coherent false: the whole description is cleared.
Sources follow the same rules as the check: Wikipedia, UNESCO, registers, museums, universities, \
scholarly publications; never ancientnerds.com, AI aggregators, Wikipedia mirrors or a copy of this \
description. A quote is verbatim from the page at its URL (code fetches it and searches for it) and \
20 to 500 characters long.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "kept": [{{"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": \
"..."}}], "coherent": true, "broken": [], "note": "..."}}
One object per kept sentence, in order ({kept_count} kept); each quote is {{"url": "...", \
"quote": "..."}}; WRONG needs at least one quote; "broken" lists k numbers in ascending order; \
every "note" is a short plain sentence, at most 600 characters.
"""

#: The instruction of the agent that verifies one batch (stage `verify` or `verify2`).
VERIFY_BRIEF = """You are {family} verifier {batch} of the Ancient Nerds sentence check (lane WC, \
verification round {round}, stage {stage}). You verify {count} site(s), each on its own, before \
its text is published. You are an agent of your own: you answered no other batch of lane WC - no \
check, no other verification, no judge question. If you did, stop here and report it; the import \
refuses a verifier whose name checked or verified the site before.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository (the Wikipedia cache named below is the one exception) - no other batch, nothing else under output/ or docs/, no database, \
no git history. Your evidence is your own web research (WebSearch, WebFetch). Run every command \
below from the repository root, {repo}.

{wiki_cache_note}

For each question:
1. Read {handoff}/<prompt_path>.
2. Research every kept sentence on the web and decide, exactly as the prompt asks. Then go \
through every kept sentence once more with the five checks below; each names an error earlier \
verifiers of this lane made, in one direction or the other.
   a. UNSUPPORTED is the verdict of a search, not of the first pages. Before you give it, search \
beyond them: the sources the Wikipedia article itself cites (they are independent of it; only the \
article is not) and their sub-pages, other-language Wikipedias, national and regional heritage \
registers and culture-ministry portals, museum and university pages, scholarly encyclopedias and \
excavation reports. A page that refuses the fetcher (403, 418, 429, a timeout) is a throttle and \
never a finding: fetch it again, read an archived copy (web.archive.org), or quote another page. A \
short official page that leaves something out is no evidence against it.
   b. The stored article is no witness on either side. Where only it, or a page that repeats it, \
supports a claim and a reputable source states something incompatible with it, the verdict is \
WRONG with that source's quote - not UNSUPPORTED, and not a disagreement between the two.
   c. Each sentence on its own claims. The dispute or missing support of a claim in another kept \
sentence is no reason against this one; that a sentence leans on another for its referent is the \
coherence question ("coherent", "broken"), not this sentence's verdict.
   d. Every word is a claim. A single word that says how, by whom or from what something was made \
or done, a credit to one person where the sources name several, and a fact stated as settled that \
the sources hedge are claims too: set them beside the words of your quotes before you support \
the sentence.
   e. A real disagreement. Before you count two sources as disagreeing, make sure both state the \
same fact: a hedged or compatible statement ("probably", a range that overlaps, a rounding) is \
no disagreement. Where reputable sources do disagree, a sentence that carries the hedge they share \
can be SUPPORTED; one that states one side as settled is not (UNSUPPORTED, or WRONG where a \
reputable source contradicts it as worded).
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched and your verdict is not judged):
   {python} scripts/remediation/wc/cli.py verify-check-answer --run-dir {run} --handoff \
{handoff} --batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it (you run as {model}; the command refuses any other model) - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --model {model} --role {role} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded, how many kept \
sentences you found SUPPORTED, UNSUPPORTED and WRONG, and how many texts incoherent.
"""

#: The independent judge's question about one checked site (the pilot's measurement).
#:
#: Sharpened 2026-10-25 (orchestrator decision X15, precedent D52: the checker is sharpened and
#: recalibrated, never the gate lowered). The pilot judge failed its calibrations wc-pj-1/2 in the
#: direction the gate cannot see: it called a kept sentence UNSUPPORTED that a scholarly source
#: contradicts as worded, and a kept text coherent whose definite phrase had lost its referent with a
#: trimmed piece. `cli.judge_result` counts a WRONG with a found quote and an incoherent text as hard
#: failures (`J_THRESHOLDS`) but an UNSUPPORTED only toward a 5 % share, so a WRONG called UNSUPPORTED
#: turns a failure into an allowance. The question therefore decides in three steps: each kept
#: sentence under the lanes' contradiction rule (`web_rules.CONTRADICTION_RULE`, verbatim) with
#: WRONG, UNSUPPORTED and SUPPORTED told apart - a contradiction as worded is WRONG, UNSUPPORTED only
#: when no reputable source states the claim either way, a rounding, a compatible estimate or a
#: variance the claim's own hedge covers is SUPPORTED, and a claim's tense and present state are part
#: of it (D52); each dropped sentence; then coherence as a step of its own, with what makes a text
#: incoherent named. `prompts_sonnet.JUDGE_QUESTION_WN` is derived from this text, so lane WN's judge
#: decides the same way. A calibration seal binds these bytes (`wc/calibration.py`, `templates`).
#: The rules are general and their examples are drawn from no unit of the pools the recalibration
#: wc-pj-1o/2o re-runs (wc-pilot-2026-09-27 judge-0002, wc-pilot-2026-09-27b judge-0001/0004): a judge
#: graded on those pools must not be pointed at their known errors (`test_wc.POOL_EXAMPLES`). The
#: contradiction rule's DISPUTED is mapped onto this answer format, which has none: a disputed claim
#: stated without the sources' shared hedge is WRONG. The tense words "still", "today", "now" are the
#: card lane's D52 rule verbatim, the one example kept although such words occur in the pools.
JUDGE_QUESTION = (
    """\
You judge, independently, the result of a sentence check of one site description of the Ancient \
Nerds archaeology database. Another agent checked the old description sentence by sentence \
against sources; the sentences below marked KEPT are what the site page will show, each with the \
quotes the checker gave. You decide, from your own research on the web, whether each kept sentence \
is true of this site, whether each dropped sentence was rightly dropped, and whether the kept text \
reads as a coherent description.

THE SITE (identify it by these values; a namesake elsewhere is another site)
{site}

KEPT SENTENCES (the new description, in order; below each, the old sentence a piece was cut from, \
and the checker's quotes)
{kept}

DROPPED SENTENCES (removed from the old description)
{dropped}

DECIDE in three steps, in this order.

STEP 1 - each kept sentence K<k>. A claim is every name, number, date, measurement, attribution, \
relation and stated fact - also a single word that says how, by whom or from what something was \
made ("moulded" where the sources say "engraved"). Take each claim as the sentence words it: its \
tense, its "still", "today" or "now", and every qualifier and hedge are part of the claim. Never \
restate a claim in the present as one in the past, nor the reverse: a state the sentence gives in \
the present that held only in the past - a casing since robbed, a building since collapsed - is \
contradicted, even where a page uses the same present tense. For every claim search for what \
supports it AND for what contradicts it; a superlative or uniqueness claim ("the tallest", "one \
of a kind") and a style or cultural attribution ("Etruscan-style", "Mycenaean in style") needs a \
source that states exactly that and a search for a source that disputes or qualifies it. Read \
what the checker's pages say around its quotes: a quote torn from its context supports nothing. \
Then give exactly one verdict:
- WRONG: a reputable source contradicts a claim as the sentence words it; give that quote. This \
answer has no DISPUTED verdict: a sentence that states as settled fact a claim that reputable \
sources dispute, qualify or call uncertain is WRONG - quote the source that disputes it - unless \
the sentence carries the hedge the sources share. Support from pages that are no reputable source \
does not outweigh a reputable source that contradicts the claim: such a claim is WRONG, not \
UNSUPPORTED.
- UNSUPPORTED: no reputable, independent source you found states the claim either way - none \
supports it and none contradicts it. It is the verdict of a search for both that found neither: \
when you find no support, keep searching for a contradiction before you decide.
- SUPPORTED: reputable, independent sources support every claim in it - the checker's quotes or \
your own - and none contradicts it as worded.
"""
    + WR.CONTRADICTION_RULE
    + """ This answer format has no DISPUTED: a claim on which reputable sources disagree, stated \
without the hedge they share, is WRONG, with the quote of the source that disputes it; stated with \
that hedge, it can be SUPPORTED. A rounding, a range that overlaps the claim's, an estimate or \
variance that the claim's own hedge covers, another spelling and the same fact in other words \
leave a claim SUPPORTED. Before you count two sources as disagreeing, make sure they state the \
same fact: two measures of one thing taken differently (a height with or without its plinth) or \
two different events (a ruler's accession and his coronation) are no disagreement.

STEP 2 - each dropped sentence D<d>: DROP_OK (it is contradicted or unsupported) or DROP_WRONG (a \
reputable, independent source supports every claim in it; give the quote).

STEP 3 - coherence, a step of its own, after the sentences. Read the kept sentences alone, in \
order, as the site page will show them, and compare each with the old sentence it was cut from \
(where one is shown) and with the dropped sentences. "coherent" is false when any of these holds:
(a) a pronoun or a definite phrase ("it", "this", "the later phase") whose \
referent stood in a dropped sentence or in a piece cut from a sentence - also when a reader could \
now take it to mean something that is still in the text: it was written about what was removed;
(b) a sentence that now says something else than it said in the old text;
(c) a sentence that is no longer grammatical, or that ends mid-sentence;
(d) the text contradicts itself: a kept sentence states something that another kept sentence \
denies (two dates, two places, two functions of one thing);
(e) the kept sentences describe two different sites - this site and a namesake elsewhere, or a \
later building on the same spot.
Otherwise "coherent" is true. Coherence is decided apart from the verdicts of step 1: a text of \
SUPPORTED sentences can be incoherent, and a WRONG sentence does not by itself make a text \
incoherent. The closing "note" names which of (a) to (e) fails, or says that none does.

Sources follow the same rules as the check: Wikipedia, UNESCO, registers, museums, universities, \
scholarly publications; never ancientnerds.com, AI aggregators, Wikipedia mirrors or a copy of this \
description. A quote is verbatim from the page at its URL (code fetches it and searches for it) and \
20 to 500 characters long.

ANSWER with exactly one JSON object and nothing around it (no code fence):
{{"site_id": "{site_id}", "kept": [{{"k": 1, "verdict": "SUPPORTED", "quotes": [], "note": \
"..."}}], "dropped": [{{"d": 1, "verdict": "DROP_OK", "quotes": [], "note": "..."}}], \
"coherent": true, "note": "..."}}
One object per kept sentence and per dropped sentence, in order ({kept_count} kept, \
{dropped_count} dropped); each quote is {{"url": "...", "quote": "..."}}; WRONG and DROP_WRONG \
need at least one quote; every "note" is a short plain sentence, at most 600 characters.
"""
)

#: The instruction of the agent that judges one batch of the pilot.
#:
#: JUDGE_BRIEF sharpened 2026-11-06 (owner decision D80, orchestrator decision O6): the six
#: disagreements of the Opus calibrations wc-pj-1o/2o were adjudicated
#: (`calibration/wc-pj-adjudication-2026-11-05/REPORT.md`). The recorded judge supported a present
#: state the excavators record as long destroyed, an unhedged figure peer-reviewed sources measure
#: otherwise, and a text whose definite phrase had lost its antecedent; the fresh judge supported a
#: style attribution the scholarly literature qualifies (the seeded known error) and answered
#: UNSUPPORTED twice after too narrow a search. The brief carries the checks against them; the
#: QUESTION stays as exported, and no example is drawn from a unit of the pools (`test_wc.POOL_EXAMPLES`).
#: A seal binds the new bytes; the re-seals are wc-pj-1o2/2o2.
JUDGE_BRIEF = """You are {family} judge {batch} of the pilot of the Ancient Nerds sentence check (lane \
WC). You judge {count} site(s), each on its own. You are a fresh agent: you checked and verified \
none of this run's sites and answered no other batch of lane WC - if you did, stop here and report \
it. Judge from your own research.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository (the Wikipedia cache named below is the one exception) - no other batch, nothing else under output/ or docs/, no database, \
no git history. Run every command below from the repository root, {repo}.

{wiki_cache_note}

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide, exactly as the prompt asks, every point in the order the \
prompt gives, the coherence of the text included: for each kept sentence search for what \
contradicts it as well as for what supports it. Then go through every kept sentence and the \
coherence once more with the five checks below; each names an error earlier judges of this lane \
made, in one direction or the other.
   a. A present state is a claim that it still holds. Where a sentence says in the present that a \
structure is there, survives, can be seen or is preserved, search excavation reports, heritage \
registers and protection decisions for its destruction, removal or collapse before you support it. \
A page that uses the same present tense does not settle it.
   b. A figure against other measures. For every number, length, area, height, count and date, look \
for another measurement of the same quantity in a scholarly or official source. Where a reputable \
source gives an incompatible value and the sentence states its figure without the hedge the \
sources share, the sentence is WRONG, even when an official page and the stored article agree \
with it.
   c. An attribution against the literature. For a style, cultural, functional or chronological \
attribution, search the scholarly literature for a qualification. An enthusiast, travel or \
photography page does not outweigh a scholarly source that calls it something else, and an \
attribution the sources dispute, stated without their hedge, is WRONG.
   d. UNSUPPORTED is the verdict of a search, not of the first pages. Before you give it, search \
other-language Wikipedias on the site and on its parts, national registers and gazetteers (for a \
place name, the national directory of populated places under every spelling), the bodies that own \
or manage the site, and archived copies (web.archive.org). A page that refuses the fetcher (403, \
418, 429, 503, a timeout) is a throttle and never a finding, and pages that are silent about a \
claim are no evidence against it.
   e. Trace every referent. For coherence condition (a), take each pronoun and definite phrase of \
each kept sentence and find what it referred to in the old text. If that stood in a dropped \
sentence or in a cut piece, "coherent" is false, however naturally the phrase still reads.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched and your verdict is not judged):
   {python} scripts/remediation/wc/cli.py judge-check-answer --run-dir {run} --handoff {handoff} \
--batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it (you run as {model}; the command refuses any other model) - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --model {model} --role {role} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""
