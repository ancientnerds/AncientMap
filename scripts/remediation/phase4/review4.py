"""S6 REVIEW: an independent, drop-only LLM review of every assembled site, then S4 and S5 again.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, verification
"INDEPENDENT LLM REVIEW" (ledger stage REVIEWER; answers under `reviews/`, never bought twice).
Work item WB-B3.

For every site in `assembly.jsonl` that no stage has held (the verifier's pre-review holds
included), one call shows, per published sentence, the published text, the untrimmed source
sentence, the two source sentences before it and the section heading, plus the card and the site's
name, aliases, type, country and coordinates. The answer is one line per sentence, `R<i>: KEEP` or
`R<i>: DROP <why>`, and one `CARD: KEEP`/`CARD: DROP <why>` when a card is shown.

The verdict can only remove, and it fails closed:

* `DROP`, a missing line, or a second line for the same sentence removes that sentence;
* a line in no contract shape (`KEEP` takes nothing after it), an `R<i>` that names no shown
  sentence, or a `CARD` line where no card was shown makes the whole answer unparseable:
  `review-unparseable` holds the site;
* after removal the site is assembled again (the assembler's own code) and verified again (the
  `reverify` seam, which the driver builds from `verify4.verify_site`); fewer than 2 sentences left
  is `review-too-few-sentences`;
* a removed card sentence rebuilds the card from the remaining CARD items when they still reach 80
  characters; otherwise, and after `CARD: DROP` or a missing CARD line, the card alone is held
  (`card-too-short-after-review`) and the description goes on without it. A verifier hold on the
  card alone takes the card off the same way, and the card-less site is verified once more.

The stage rewrites `assembly.jsonl` with exactly the sites that passed, and writes `review4.json`
with every site's lines, what was kept and the sha256 of the `assembly.jsonl` it wrote: that is how
the driver (and the writer) tell a reviewed assembly from an unreviewed one.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3.model import Stage  # noqa: E402

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import prompts4 as P  # noqa: E402
from phase4 import sentences as S  # noqa: E402
from pipeline.lyra.text_sentences import sentence_span  # noqa: E402

#: The card rebuilt from the CARD items a review left must still reach this (card_texts, V10).
MIN_CARD_CHARS = 80
MIN_SENTENCES = 2

_LINE = re.compile(r"(?:R(?P<number>[1-9][0-9]*)|(?P<card>CARD)): (?:(?P<keep>KEEP)|DROP(?: .+)?)")

#: `reverify(site, assembly)`: the verifier's holds for a re-assembled site (empty: V1-V15 pass).
Reverify = Callable[[M.PlanSite, M.Assembly], tuple[M.Hold, ...]]


class ReviewUnparseable(ValueError):
    """The answer holds a line in no contract shape, or names a sentence or card never shown."""


@dataclass(frozen=True)
class Verdict:
    """What survives: the 1-based sentence numbers kept, and the card's fate (`None`: no card)."""

    kept: tuple[int, ...]
    card_kept: bool | None
    lines: tuple[str, ...]


def parse_review(answer: str, *, sentences: int, card: bool) -> Verdict:
    """Read the reviewer's lines. Fail-closed: anything but exactly one `KEEP` line removes."""
    seen: dict[int, list[bool]] = {}
    card_lines: list[bool] = []
    lines: list[str] = []
    for raw in answer.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ReviewUnparseable(f"a line in no contract shape: {line[:120]!r}")
        lines.append(line)
        keep = match["keep"] is not None
        if match["card"] is not None:
            if not card:
                raise ReviewUnparseable("a CARD line, but no card was shown")
            card_lines.append(keep)
            continue
        number = int(match["number"])
        if number > sentences:
            raise ReviewUnparseable(f"R{number} names no shown sentence (1-{sentences})")
        seen.setdefault(number, []).append(keep)
    kept = tuple(n for n in range(1, sentences + 1) if seen.get(n) == [True])
    return Verdict(
        kept=kept, card_kept=(card_lines == [True]) if card else None, lines=tuple(lines)
    )


# -------------------------------------------------------------------------------- the prompt


def _before(text: str, start: int) -> str:
    """The two sentences of a page that come before `start` (a lane-R quote has no numbering)."""
    before: list[str] = []
    cursor = sentence_span(text, start)[0]
    while len(before) < 2 and cursor > 0:
        low, high = sentence_span(text, cursor - 1)
        if low >= cursor:
            break
        before.insert(0, text[low:high].strip())
        cursor = low
    return " ".join(before)


def passages(
    assembly: M.Assembly, published: Sequence[str], texts: Mapping[str, str]
) -> list[tuple[str, str, str, str | None]]:
    """Per published sentence: published text, untrimmed source sentence (a lane-R quote), the two
    source sentences before it, and its section. Shared with the independent audit (`audit4`)."""
    rows: list[tuple[str, str, str, str | None]] = []
    numbered: dict[str, tuple[M.Sentence, ...]] = {}
    for shown, cut in zip(published, assembly.provenance.sentences, strict=True):
        text = texts[cut.src]
        if M.source_kind(cut.src) not in M.SELECTABLE_KINDS:
            rows.append((shown, text[cut.start : cut.end], _before(text, cut.start), None))
            continue
        split = numbered.setdefault(cut.src, S.split_source(cut.src, text))
        at = next(i for i, source in enumerate(split) if source.start == cut.start)
        before = " ".join(S.sentence_text(text, s) for s in split[max(0, at - 2) : at])
        rows.append((shown, S.sentence_text(text, split[at]), before, split[at].section))
    return rows


def reviewer_prompt(inputs: A.SiteInputs, built: A.Built) -> MS.Prompt:
    rows = passages(built.assembly, built.sentences, inputs.texts)
    return MS.Prompt(
        stage=Stage.REVIEWER,
        system=P.REVIEWER_QUESTION,
        user=P.reviewer_block(inputs.site, rows, built.assembly.card),
    )


# -------------------------------------------------------------------------------- the verdict


@dataclass(frozen=True)
class Kept:
    """What a verdict leaves to publish: DESC and CARD picks (W, S, T) or restatements (R)."""

    desc: tuple[M.Pick, ...] = ()
    card: tuple[M.Pick, ...] = ()
    restated: tuple[B.Restatement, ...] = ()


def build(inputs: A.SiteInputs, kept: Kept, *, run: str) -> A.Built:
    """S4 again, through the assembler's own builders."""
    if inputs.lane is M.Lane.R:
        return A.build_restated(inputs.site, kept.restated, inputs.sources, run=run)
    return A.build_picks(
        inputs.site,
        kept.desc,
        kept.card,
        inputs.pool,
        inputs.lane,
        inputs.sources,
        inputs.texts,
        run=run,
        translations=inputs.translations,
    )


def _site_hold(site_id: str, reason: M.HoldReason, detail: str) -> M.Hold:
    return M.Hold(site_id=site_id, scope=M.HoldScope.SITE, reason=reason, detail=detail)


def _card_hold(site_id: str, detail: str) -> M.Hold:
    return M.Hold(
        site_id=site_id,
        scope=M.HoldScope.CARD,
        reason=M.HoldReason.CARD_TOO_SHORT_AFTER_REVIEW,
        detail=detail,
    )


def keep(
    inputs: A.SiteInputs, built: A.Built, verdict: Verdict
) -> tuple[Kept | None, tuple[M.Hold, ...], str]:
    """The verdict applied: what is left, the holds, and the card's fate (`kept`, `rebuilt`,
    `held` or `none`). `None` when fewer than two sentences are left."""
    site_id = inputs.site.site_id
    if len(verdict.kept) < MIN_SENTENCES:
        detail = f"the review kept {len(verdict.kept)} of {len(built.sentences)} sentences"
        return None, (_site_hold(site_id, M.HoldReason.REVIEW_TOO_FEW_SENTENCES, detail),), "held"
    if inputs.lane is M.Lane.R:
        if inputs.restatements is None:
            raise ValueError(f"{site_id}: lane R without restatements")
        order = A.restated_order(inputs.restatements)
        return Kept(restated=tuple(order[n - 1] for n in verdict.kept)), (), "none"
    if inputs.selection is None:
        raise ValueError(f"{site_id}: lane {inputs.lane.value} without a selection")
    by_sid = {sentence.sid: sentence for sentence in inputs.pool}
    ordered = sorted(inputs.selection.desc, key=lambda pick: by_sid[pick.sid].index)
    desc = tuple(ordered[n - 1] for n in verdict.kept)
    if built.assembly.card is None:
        return Kept(desc=desc), (), "none"
    if verdict.card_kept is not True:
        return Kept(desc=desc), (_card_hold(site_id, "the reviewer did not keep the card"),), "held"
    left = {pick.sid for pick in desc}
    card = tuple(pick for pick in inputs.selection.card if pick.sid in left)
    if len(card) == len(inputs.selection.card):
        return Kept(desc=desc, card=card), (), "kept"
    if not card:
        detail = "every card sentence was dropped by the review"
        return Kept(desc=desc), (_card_hold(site_id, detail),), "held"
    return Kept(desc=desc, card=card), (), "rebuilt"


@dataclass(frozen=True)
class Outcome:
    """A reviewed site: the assembly to write (or `None`), the holds it leaves, the card's fate."""

    assembly: M.Assembly | None
    holds: tuple[M.Hold, ...]
    card: str


def settle(
    inputs: A.SiteInputs, built: A.Built, verdict: Verdict, reverify: Reverify, *, run: str
) -> Outcome:
    """Apply the verdict, assemble again, verify again (twice when only the card is held)."""
    site_id = inputs.site.site_id
    kept, holds, fate = keep(inputs, built, verdict)
    if kept is None:
        return Outcome(None, holds, "held")
    rebuilt = build(inputs, kept, run=run)
    card = rebuilt.assembly.card
    if fate == "rebuilt" and (card is None or len(card) < MIN_CARD_CHARS):
        detail = (
            f"a card sentence was dropped and the rest is {len(card or '')} characters, "
            f"under {MIN_CARD_CHARS}"
        )
        holds = (*holds, _card_hold(site_id, detail))
        fate = "held"
        kept = dataclasses.replace(kept, card=())
        rebuilt = build(inputs, kept, run=run)
    found = reverify(inputs.site, rebuilt.assembly)
    if any(hold.scope is M.HoldScope.SITE for hold in found):
        return Outcome(None, (*holds, *found), "held")
    if not found:
        return Outcome(rebuilt.assembly, holds, fate)
    if rebuilt.assembly.card is None:
        raise ValueError(f"{site_id}: the verifier held a card on an assembly without one")
    bare = build(inputs, dataclasses.replace(kept, card=()), run=run)
    again = reverify(inputs.site, bare.assembly)
    if again:
        return Outcome(None, (*holds, *found, *again), "held")
    return Outcome(bare.assembly, (*holds, *found), "held")


# ------------------------------------------------------------------------------------- the stage


def review_batch(
    batch_dir: Path, *, ledger: Path, runner: MS.ModelRunner, reverify: Reverify
) -> int:
    """S6 over one batch. `reverify` is the driver's `verify4.verify_site` wiring (`run4`).

    `assemble.batch_inputs` leaves out every site a site-scope hold keeps (the verifier's
    pre-review holds included), so a held site is never reviewed and buys no call.
    """
    batch_id, inputs = A.batch_inputs(batch_dir)
    assembled = {a.site_id for a in M.load_jsonl(batch_dir / M.ASSEMBLY_FILE, M.Assembly)}
    run = B.run_name(batch_dir)
    reviews = F.EvidenceStore(batch_dir / B.REVIEWS_DIR)
    book = L.Ledger(ledger)
    written: list[M.Assembly] = []
    holds: list[M.Hold] = []
    rows: list[dict[str, Any]] = []
    error: str | None = None
    for site_inputs in inputs:
        site_id = site_inputs.site.site_id
        if site_id not in assembled:
            continue
        built = A.build_site(site_inputs, run=run)
        row: dict[str, Any] = {"site_id": site_id, "sentences": len(built.sentences)}
        rows.append(row)
        try:
            bought = B.buy(
                batch_dir=batch_dir,
                batch_id=batch_id,
                site_id=site_id,
                field=B.REVIEW_FIELD,
                stage=Stage.REVIEWER,
                prompt=reviewer_prompt(site_inputs, built),
                runner=runner,
                ledger=book,
                answers=reviews,
            )
        except MS.UnreadableStream as exc:
            holds.append(_site_hold(site_id, M.HoldReason.MODEL_STREAM_UNREADABLE, str(exc)))
            row["outcome"] = "held"
            continue
        except MS.ModelCallFailed as exc:
            error = str(exc)
            row["outcome"] = "not-asked"
            break
        row.update(
            label=bought.label,
            prompt_sha256=bought.prompt_sha256,
            answer_sha256=bought.answer_sha256,
            cost_usd=bought.cost_usd,
            bought=bought.wrote,
        )
        try:
            verdict = parse_review(
                bought.text, sentences=len(built.sentences), card=built.assembly.card is not None
            )
        except ReviewUnparseable as exc:
            holds.append(_site_hold(site_id, M.HoldReason.REVIEW_UNPARSEABLE, str(exc)))
            row["outcome"] = "held"
            continue
        outcome = settle(site_inputs, built, verdict, reverify, run=run)
        holds.extend(outcome.holds)
        row.update(lines=list(verdict.lines), kept=list(verdict.kept), card=outcome.card)
        if outcome.assembly is None:
            row["outcome"] = "held"
            continue
        written.append(outcome.assembly)
        row["outcome"] = "reviewed"
    report: dict[str, Any] = {"batch_id": batch_id, "stage": "review", "sites": rows}
    if error is None:
        B.write_text_atomic(batch_dir / M.ASSEMBLY_FILE, M.dump_jsonl(written))
        report["assembly_sha256"] = B.sha256_file(batch_dir / M.ASSEMBLY_FILE)
    B.append_holds(batch_dir, holds)
    B.write_report(batch_dir / B.REVIEW_REPORT, {**report, "error": error})
    return 0 if error is None else 2
