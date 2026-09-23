"""S4 ASSEMBLE: code builds every byte of the description, its citations, the card and provenance.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, writer
"ASSEMBLY" and "SENTENCE-TO-QUOTE MAP", card_texts "HOW A CARD IS BUILT", production_write
"_description_provenance v1". Work item WB-B3. Deterministic: no network, no model, no clock. The
verifier (`phase4/verify4.py`, WB-C2) re-derives all of it with its own code and never imports this
module.

The closed edit list, applied to the source slice `text[start:end]` of every chosen sentence:

1. remove every dropped range (a range is exactly an offered span, which carries its delimiter -
   `sentences.py` says which);
2. collapse runs of spaces into one;
3. repair `' ,'` into `','`;
4. restore the capital letter when a dropped range opened the sentence;
5. insert `' [n]'` before the final punctuation (the majority production form, `' [1].'`).

Sentences stay in source order, each carries exactly one marker, and the citation numbers are
assigned here by the first appearance of each source - the model never sees or writes a number.
Lanes T and R publish generated text (a translation, a restatement), so edit 5 is the only edit
their published sentence gets; their provenance still pins the quote's range in the source.

A card (lanes W and S) is 1-2 of the published sentences, each cut by its DESC drops plus its CARD
drops, with edits 1-4, no marker, and the one spoken edit `'c.'`/`'ca.'` -> `'circa'` in front of
a number. Lanes T and R build no card (their text is not the source's, so no offered span applies):
their `card` is `None` and the old card stays unwritten.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3.run import InputError  # noqa: E402

from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import prompts4 as P  # noqa: E402

TERMINAL = ".!?"
_SPACES = re.compile(r" {2,}")


# ---------------------------------------------------------------------------- the edit list


def maximal(ranges: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """The ranges not nested in another, sorted. Partial overlaps were refused before this."""
    ordered = sorted(set(ranges), key=lambda r: (r[0], -r[1]))
    kept: list[tuple[int, int]] = []
    for low, high in ordered:
        if kept and low >= kept[-1][0] and high <= kept[-1][1]:
            continue
        if kept and low < kept[-1][1]:
            raise ValueError(f"({low}, {high}) overlaps {kept[-1]} without being inside it")
        kept.append((low, high))
    return tuple(kept)


def trim(text: str, start: int, end: int, drops: Sequence[tuple[int, int]]) -> str:
    """Edits 1-4 on `text[start:end]`: remove the ranges, collapse, repair `' ,'`, recapitalise."""
    pieces: list[str] = []
    cursor = start
    for low, high in drops:
        if not start <= cursor <= low < high <= end:
            raise ValueError(f"drop ({low}, {high}) is not inside [{cursor}, {end})")
        pieces.append(text[cursor:low])
        cursor = high
    pieces.append(text[cursor:end])
    kept = _SPACES.sub(" ", "".join(pieces)).replace(" ,", ",")
    if drops and drops[0][0] == start:
        kept = kept[:1].upper() + kept[1:]
    return kept


def with_marker(sentence: str, n: int) -> str:
    """Edit 5: `' [n]'` in front of the final punctuation."""
    if not sentence or sentence[-1] not in TERMINAL:
        raise ValueError(f"no final punctuation to put [{n}] in front of: {sentence[-40:]!r}")
    return f"{sentence[:-1]} [{n}]{sentence[-1]}"


def spoken(card_sentence: str) -> str:
    """The card's one non-source edit: every `model4.CIRCA_PATTERN` match becomes `circa ` (`Circa `
    for a capital `C`)."""
    return M.CIRCA_PATTERN.sub(lambda m: "Circa " if m["c"] == "C" else "circa ", card_sentence)


def domain_of(url: str) -> str:
    """The citation's `domain`: the host without a leading `www.` (the existing production form)."""
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"{url!r} has no host")
    return host.removeprefix("www.")


def _title(meta: M.SourceDoc) -> str:
    if meta.title is None:
        raise ValueError(f"source {meta.id} carries no title to cite")
    return meta.title


def citation_title(meta: M.SourceDoc) -> str:
    """`'Wikipedia: <title>'` for a Wikipedia source; a non-free page's own title."""
    if meta.kind in (M.SourceKind.W, M.SourceKind.T):
        return f"Wikipedia: {_title(meta)}"
    return _title(meta)


# ------------------------------------------------------------------------------ the builders


@dataclass(frozen=True)
class Built:
    """An assembly and the published sentences it was joined from (the reviewer shows them)."""

    assembly: M.Assembly
    sentences: tuple[str, ...]


def _numbers(order: Sequence[str]) -> dict[str, int]:
    """Citation numbers by first appearance of each source id."""
    numbers: dict[str, int] = {}
    for source_id in order:
        numbers.setdefault(source_id, len(numbers) + 1)
    return numbers


def _finish(
    *,
    site: M.PlanSite,
    lane: M.Lane,
    run: str,
    sources: Mapping[str, M.SourceDoc],
    published: Sequence[tuple[str, str, int, int, tuple[tuple[int, int], ...]]],
    card: tuple[str, M.Card] | None,
) -> Built:
    """Number, mark, join and record. `published` is (body, src, start, end, drops) in order."""
    numbers = _numbers([src for _, src, _, _, _ in published])
    sentences = tuple(with_marker(body, numbers[src]) for body, src, _, _, _ in published)
    description = " ".join(sentences)
    cited = sorted(numbers, key=numbers.__getitem__)
    first = sources[cited[0]]
    provenance = M.Provenance(
        run=run,
        lane=lane,
        ai=M.LANE_AI[lane],
        ai_system=M.AI_SYSTEM,
        licence=M.PUBLISHED_LICENCE,
        attribution=M.Attribution(
            title=_title(first),
            url=P.cited_url(first),
            licence_url=M.PUBLISHED_LICENCE_URL,
            changes=M.LANE_CHANGES[lane],
        ),
        sources=tuple(
            M.SourceRef(
                id=source_id,
                url=P.cited_url(sources[source_id]),
                revid=sources[source_id].revid,
                rev_timestamp=sources[source_id].rev_timestamp,
                text_sha256=_text_sha(sources[source_id]),
                licence=sources[source_id].licence,
            )
            for source_id in cited
        ),
        sentences=tuple(
            M.PublishedSentence(n=numbers[src], src=src, start=start, end=end, drop=drops)
            for _, src, start, end, drops in published
        ),
        card=None if card is None else card[1],
        desc_sha256=M.text_sha256(description),
    )
    citations = tuple(
        M.Citation(
            n=numbers[source_id],
            url=P.cited_url(sources[source_id]),
            title=citation_title(sources[source_id]),
            domain=domain_of(P.cited_url(sources[source_id])),
            license=sources[source_id].licence,
        )
        for source_id in cited
    )
    return Built(
        assembly=M.Assembly(
            site_id=site.site_id,
            description=description,
            citations=citations,
            card=None if card is None else card[0],
            provenance=provenance,
        ),
        sentences=sentences,
    )


def _text_sha(meta: M.SourceDoc) -> str:
    if meta.sha256_text is None:
        raise ValueError(f"source {meta.id} carries no sha256_text; a cited source has a text")
    return meta.sha256_text


def build_picks(
    site: M.PlanSite,
    desc: Sequence[M.Pick],
    card: Sequence[M.Pick],
    pool: Sequence[M.Sentence],
    lane: M.Lane,
    sources: Mapping[str, M.SourceDoc],
    texts: Mapping[str, str],
    *,
    run: str,
    translations: Mapping[str, str] | None = None,
) -> Built:
    """Lanes W, S and T from DESC picks and 0-2 CARD picks (0: no card, as after a review drop).

    `translations` (sid -> English sentence) is required in lane T and refused elsewhere.
    """
    if lane not in (M.Lane.W, M.Lane.S, M.Lane.T):
        raise ValueError(f"lane {lane.value} is not assembled from picks")
    if (lane is M.Lane.T) != (translations is not None):
        raise ValueError(f"lane {lane.value}: translations are for lane T and only for it")
    if not desc:
        raise ValueError(f"{site.site_id}: no DESC pick to assemble")
    by_sid = {sentence.sid: sentence for sentence in pool}
    ordered = sorted(desc, key=lambda pick: by_sid[pick.sid].index)
    published: list[tuple[str, str, int, int, tuple[tuple[int, int], ...]]] = []
    drops_of: dict[str, tuple[tuple[int, int], ...]] = {}
    for pick in ordered:
        sentence = by_sid[pick.sid]
        spans = {span.id: span for span in sentence.spans}
        drops = maximal([(spans[i].start, spans[i].end) for i in pick.drop])
        drops_of[pick.sid] = drops
        if translations is not None:
            body = translations[pick.sid]
        else:
            body = trim(texts[sentence.src], sentence.start, sentence.end, drops)
        published.append((body, sentence.src, sentence.start, sentence.end, drops))
    built_card: tuple[str, M.Card] | None = None
    if card and lane is not M.Lane.T:
        position = {pick.sid: i for i, pick in enumerate(ordered)}
        items: list[M.CardItem] = []
        texts_of_card: list[str] = []
        for pick in sorted(card, key=lambda p: position[p.sid]):
            sentence = by_sid[pick.sid]
            spans = {span.id: span for span in sentence.spans}
            union = maximal(
                [*drops_of[pick.sid], *((spans[i].start, spans[i].end) for i in pick.drop)]
            )
            items.append(M.CardItem(sentence=position[pick.sid], drop=union))
            texts_of_card.append(
                spoken(trim(texts[sentence.src], sentence.start, sentence.end, union))
            )
        card_text = " ".join(texts_of_card)
        built_card = (card_text, M.Card(items=tuple(items), text_sha256=M.text_sha256(card_text)))
    return _finish(
        site=site, lane=lane, run=run, sources=sources, published=published, card=built_card
    )


def assemble(
    site: M.PlanSite,
    selection: M.Selection,
    pool: Sequence[M.Sentence],
    lane: M.Lane,
    sources: Mapping[str, M.SourceDoc],
    texts: Mapping[str, str],
    *,
    run: str,
    translations: Mapping[str, str] | None = None,
) -> M.Assembly:
    """The contract's entry for lanes W, S (and T, with its `translations`)."""
    if selection.abstain is not None:
        raise ValueError(f"{site.site_id}: an abstaining selection is held, never assembled")
    return build_picks(
        site,
        selection.desc,
        selection.card,
        pool,
        lane,
        sources,
        texts,
        run=run,
        translations=translations,
    ).assembly


def restated_order(restatements: Sequence[B.Restatement]) -> tuple[B.Restatement, ...]:
    """Lane R's published order: by page, in the order the pages first appear, then by offset."""
    first_seen = _numbers([r.src for r in restatements])
    return tuple(sorted(restatements, key=lambda r: (first_seen[r.src], r.start)))


def build_restated(
    site: M.PlanSite,
    restatements: Sequence[B.Restatement],
    sources: Mapping[str, M.SourceDoc],
    *,
    run: str,
) -> Built:
    """Lane R: each restated sentence cites the page its quote was located in; no card.

    The sentences keep the model's order within each page and are grouped by page in the order
    the pages first appear, so every page's quotes stay in source order (`Provenance` refuses a page
    whose quotes go backwards or overlap).
    """
    if not restatements:
        raise ValueError(f"{site.site_id}: no restated sentence to assemble")
    published = [(r.text, r.src, r.start, r.end, ()) for r in restated_order(restatements)]
    return _finish(
        site=site, lane=M.Lane.R, run=run, sources=sources, published=published, card=None
    )


_MARKER_END = re.compile(r"\[[1-9][0-9]*\][.!?](?= )")


def published_sentences(assembly: M.Assembly) -> tuple[str, ...]:
    """The description cut back into its published sentences, at the space after each marker.

    The cut is at the one space after `[n].`, so the parts join back byte for byte; it raises when
    it does not give exactly one sentence per provenance sentence (a source sentence carrying
    `[n].` itself, or a description that is not this assembly's).
    """
    cuts = [match.end() for match in _MARKER_END.finditer(assembly.description)]
    bounds = zip([0, *(cut + 1 for cut in cuts)], [*cuts, len(assembly.description)], strict=True)
    parts = tuple(assembly.description[low:high] for low, high in bounds)
    if len(parts) != len(assembly.provenance.sentences):
        raise ValueError(f"{assembly.site_id}: the description does not cut into its sentences")
    return parts


def quotes_of(assembly: M.Assembly, texts: Mapping[str, str]) -> tuple[str, ...]:
    """The quote of every published sentence: `text[start:end]` of its source (`verify_site`'s
    `quotes` in a batch; the journal's evidence at acceptance)."""
    return tuple(
        texts[sentence.src][sentence.start : sentence.end]
        for sentence in assembly.provenance.sentences
    )


# ------------------------------------------------------------------------------------ the batch


@dataclass(frozen=True)
class SiteInputs:
    """Everything one site's assembly is built from, read from its batch directory."""

    site: M.PlanSite
    lane: M.Lane
    sources: dict[str, M.SourceDoc]
    texts: dict[str, str]
    pool: tuple[M.Sentence, ...]
    selection: M.Selection | None
    translations: dict[str, str] | None
    restatements: tuple[B.Restatement, ...] | None


def batch_inputs(batch_dir: Path) -> tuple[str, list[SiteInputs]]:
    """Every site of the batch that no stage has held and that reached a text: its inputs.

    A site of lane W/S/T without a selection, of lane T without its translation, or of lane R
    without its restatement, and without a hold either, means an earlier stage did not finish:
    that raises rather than assembling a smaller batch.
    """
    batch_id, sites = B.read_batch(batch_dir)
    lanes = B.read_lanes(batch_dir, sites)
    held = B.site_held(B.read_holds(batch_dir))
    # `run4 select` runs S3, S3T and S3R and each writes its file, empty or not: a file that is
    # absent means its stage never ran, and that raises in the reader.
    selections = B.read_selections(batch_dir)
    pools = B.read_pools(batch_dir)
    translations = B.read_translations(batch_dir)
    restatements = B.read_restatements(batch_dir)
    out: list[SiteInputs] = []
    for site in sites:
        lane = lanes[site.site_id]
        if site.site_id in held:
            continue
        if lane.lane is M.Lane.ZERO:
            raise InputError(f"{batch_id}: {site.site_id} is lane 0 and carries no hold")
        docs: dict[str, M.SourceDoc] = {}
        texts: dict[str, str] = {}
        for source_id in lane.sources:
            docs[source_id], texts[source_id] = B.read_source(batch_dir, site.site_id, source_id)
        if lane.lane is M.Lane.R:
            if site.site_id not in restatements:
                raise InputError(f"{batch_id}: {site.site_id} (lane R) has no restatement")
            out.append(
                SiteInputs(site, lane.lane, docs, texts, (), None, None, restatements[site.site_id])
            )
            continue
        if site.site_id not in selections:
            raise InputError(f"{batch_id}: {site.site_id} has neither a selection nor a hold")
        if lane.lane is M.Lane.T and site.site_id not in translations:
            raise InputError(f"{batch_id}: {site.site_id} (lane T) has no translation")
        out.append(
            SiteInputs(
                site=site,
                lane=lane.lane,
                sources=docs,
                texts=texts,
                pool=pools[site.site_id][1],
                selection=selections[site.site_id],
                translations=translations.get(site.site_id) if lane.lane is M.Lane.T else None,
                restatements=None,
            )
        )
    return batch_id, out


def build_site(inputs: SiteInputs, *, run: str) -> Built:
    if inputs.lane is M.Lane.R:
        if inputs.restatements is None:
            raise ValueError(f"{inputs.site.site_id}: lane R without restatements")
        return build_restated(inputs.site, inputs.restatements, inputs.sources, run=run)
    if inputs.selection is None:
        raise ValueError(f"{inputs.site.site_id}: lane {inputs.lane.value} without a selection")
    return build_picks(
        inputs.site,
        inputs.selection.desc,
        inputs.selection.card,
        inputs.pool,
        inputs.lane,
        inputs.sources,
        inputs.texts,
        run=run,
        translations=inputs.translations,
    )


def assemble_batch(batch_dir: Path) -> int:
    """S4 over one batch: `assembly.jsonl`, one `Assembly` per site that reached a text."""
    _, inputs = batch_inputs(batch_dir)
    run = B.run_name(batch_dir)
    assemblies = [build_site(site_inputs, run=run).assembly for site_inputs in inputs]
    B.write_text_atomic(batch_dir / M.ASSEMBLY_FILE, M.dump_jsonl(assemblies))
    return 0
