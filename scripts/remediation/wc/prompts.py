"""Lane WC's frozen texts: the check question, its re-ask, the judge's question and both briefs.

Every text is pinned by a byte hash in `tests/remediation/test_wc.py`: a changed question makes
every exported answer stale (`opus_handoff.validate`), so a change is a new pin and a new export,
never an edit under a running round. The prompts are built only from these templates and the site's
own values (`cli.check_prompt`, `cli.judge_prompt`), so the import can rebuild each exported prompt
byte for byte and refuse an answer to anything else.
"""

from __future__ import annotations

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
not supported; a hedge the sources share ("probably", "is thought to") is fine.
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

#: The instruction of the Opus agent that answers one batch of check questions.
CHECK_BRIEF = """You are Opus checker {batch} of the Ancient Nerds sentence check (lane WC, round \
{round}). You answer {count} question(s), each about another site. Answer each one on its own, as \
if it were the only one.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository - no other batch, nothing else under output/ or docs/, no database, \
no git history. Your evidence is your own web research (WebSearch, WebFetch), as each prompt says. \
Run every command below from the repository root, {repo}.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research each sentence on the web and decide, exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check it. The check fetches every page you quote (as the import will) and searches it for your \
quotes; it prints each sentence's outcome and the description your answer would leave:
   {python} scripts/remediation/wc/cli.py check-answer --run-dir {run} --handoff {handoff} \
--batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   Fix what it names - a quote copied inexactly, a page that refuses the fetcher, a title the page \
does not carry, a piece to remove that is not exact - and check again. If no page you can quote supports a sentence, it is a DROP \
("unsupported"). Never change a finding to make the check pass.
5. Record it - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded and how many \
sentences you kept, trimmed and dropped.
"""

#: The independent judge's question about one checked site (the pilot's measurement).
JUDGE_QUESTION = """\
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

DECIDE
- For each kept sentence K<k>: SUPPORTED (a reputable, independent source supports every claim in \
it - the checker's quotes or your own), UNSUPPORTED (some claim is supported by no such source you \
found) or WRONG (a source contradicts a claim; give that quote).
- For each dropped sentence D<d>: DROP_OK (it is contradicted or unsupported) or DROP_WRONG (a \
reputable, independent source supports every claim in it; give the quote).
- coherent: false when the kept text does not read as a description of this site - a pronoun \
whose referent was dropped, a trimmed sentence that is no longer grammatical, a sentence that now \
says something else than it did; else true.
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

#: The instruction of the Opus agent that judges one batch of the pilot.
JUDGE_BRIEF = """You are Opus judge {batch} of the pilot of the Ancient Nerds sentence check (lane \
WC). You judge {count} site(s), each on its own. You are not the agent that checked them: judge \
from your own research.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the site id) and its "prompt_path" (relative to {handoff}). Open no \
other file of the repository - no other batch, nothing else under output/ or docs/, no database, \
no git history. Run every command below from the repository root, {repo}.

For each question:
1. Read {handoff}/<prompt_path>.
2. Research on the web and decide, exactly as the prompt asks.
3. Write your answer - only the JSON object the prompt specifies - to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched and your verdict is not judged):
   {python} scripts/remediation/wc/cli.py judge-check-answer --run-dir {run} --handoff {handoff} \
--batch-id {batch} --label <label> --text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   {python} scripts/remediation/opus_handoff.py answer --dir {handoff} --batch-id {batch} \
--stage {stage} --label <label> --answered-by {batch_agent} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""
