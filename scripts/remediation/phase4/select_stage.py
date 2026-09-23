"""S3 SELECT: one Pi call per site, whose answer names sentence ids and span ids, and nothing else.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, pipeline "S3
SELECT" and writer "PROMPT CONTRACT"/"OUTPUT". Work item WB-B2.

For every site of lane W, S or T that no earlier stage has held, the stage reads the pinned text of
the lane's one source, splits it (`sentences.split_source`), bounds the pool
(`sentences.candidate_pool`) and asks the frozen selector question (`prompts4.SELECTOR_QUESTION`)
through `model_stage.judge_site`: the ledger line goes down first, the answer is stored write-once
under `answers/`, and an answer already on disk is read instead of bought again. There is no retry
and no second call inside the stage: an unreadable stream holds the site
(`model-stream-unreadable`), and so does an answer the parser refuses (`selection-refused`, the
detail naming the `SelectionProblem`) or an `ABSTAIN` (`abstained`). A rerun is a new ledgered
call, made by deleting the answer file.

`parse_selection` refuses an unknown line, an unknown sid and a span the sid does not offer itself,
and so a pick whose spans partially overlap (the union would be no offered span, so V4 could never
pass it); `model4.Selection` refuses the rest. The call could not be made at all (a timeout, a
non-zero exit, a process that would not start: `ModelCallFailed`) stops the batch: the stage returns
non-zero and names the error in `select.json`.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3.model import Stage  # noqa: E402

from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import prompts4 as P  # noqa: E402
from phase4 import sentences as S  # noqa: E402

#: The lanes whose text is selected from a Wikipedia source (T selects in its own language).
SELECTING_LANES = frozenset({M.Lane.W, M.Lane.S, M.Lane.T})

_LINE = re.compile(r"(?P<kind>DESC|CARD|ABSTAIN):(?P<rest>.*)")
_PICK = re.compile(r"[ \t]*(?P<sid>\S+)(?P<drops>(?:[ \t]+-\S+)*)[ \t]*")


def _refuse(problem: M.SelectionProblem, detail: str) -> M.SelectionRefused:
    return M.SelectionRefused(problem, detail)


def _overlap(ranges: Sequence[tuple[str, int, int]]) -> str | None:
    """The first pair of ranges that overlap without one holding the other, named, or `None`."""
    ordered = sorted(ranges, key=lambda r: (r[1], -r[2]))
    for i, (first, _, high) in enumerate(ordered):
        for second, other_low, other_high in ordered[i + 1 :]:
            if other_low >= high:
                break
            if other_high > high:
                return f"{first} and {second} overlap"
    return None


def parse_selection(site_id: str, answer: str, pool: Sequence[M.Sentence]) -> M.Selection:
    """The selector's answer as a `Selection`, or `SelectionRefused` naming the problem.

    Raised here: `unknown-line` (a line that is not `DESC:`, `CARD:` or `ABSTAIN:` in the contract's
    shape), `unknown-sid` (a sid the pool did not show), `span-not-offered` (a span the sid did not
    offer, or two chosen spans that overlap without one holding the other). A second `ABSTAIN` line
    is a `duplicate`. `model4.Selection` (and `Pick`) raise the other seven problems.
    """
    by_sid = {sentence.sid: sentence for sentence in pool}
    desc: list[M.Pick] = []
    card: list[M.Pick] = []
    abstain: str | None = None
    for raw in answer.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise _refuse(M.SelectionProblem.UNKNOWN_LINE, f"{site_id}: {line[:120]!r}")
        if match["kind"] == "ABSTAIN":
            if abstain is not None:
                raise _refuse(M.SelectionProblem.DUPLICATE, f"{site_id}: two ABSTAIN lines")
            abstain = match["rest"].strip()
            continue
        pick = _PICK.fullmatch(match["rest"])
        if pick is None:
            raise _refuse(M.SelectionProblem.UNKNOWN_LINE, f"{site_id}: {line[:120]!r}")
        sid = pick["sid"]
        sentence = by_sid.get(sid)
        if sentence is None:
            raise _refuse(M.SelectionProblem.UNKNOWN_SID, f"{site_id}: {sid} is not in the pool")
        offered = {span.id for span in sentence.spans}
        drops = tuple(token[1:] for token in pick["drops"].split())
        for span_id in drops:
            if span_id not in offered:
                raise _refuse(
                    M.SelectionProblem.SPAN_NOT_OFFERED,
                    f"{site_id}: {sid} offers {sorted(offered)}, not {span_id!r}",
                )
        (desc if match["kind"] == "DESC" else card).append(M.Pick(sid=sid, drop=drops))
    selection = M.Selection(site_id=site_id, desc=tuple(desc), card=tuple(card), abstain=abstain)
    desc_drops = {pick.sid: pick.drop for pick in selection.desc}
    for label, picks in (("DESC", selection.desc), ("CARD", selection.card)):
        for pick in picks:
            spans = {span.id: span for span in by_sid[pick.sid].spans}
            chosen = set(pick.drop) | (set(desc_drops[pick.sid]) if label == "CARD" else set())
            clash = _overlap([(i, spans[i].start, spans[i].end) for i in sorted(chosen)])
            if clash is not None:
                raise _refuse(
                    M.SelectionProblem.SPAN_NOT_OFFERED,
                    f"{site_id}: {label} {pick.sid}: {clash}; no offered span is their union",
                )
    return selection


# ------------------------------------------------------------------------------------ the stage


def site_pool(
    batch_dir: Path, site: M.PlanSite, lane: M.LaneAssignment
) -> tuple[str, M.SourceDoc, str, tuple[M.Sentence, ...]]:
    """The lane's one source, its pinned text and the candidate pool the selector is shown."""
    (source_id,) = lane.sources
    meta, text = B.read_source(batch_dir, site.site_id, source_id)
    pool = S.candidate_pool(
        S.split_source(source_id, text),
        lane=lane.lane,
        names=(site.name, *site.aliases),
        text=text,
    )
    return source_id, meta, text, pool


def selector_prompt(
    site: M.PlanSite, source_id: str, meta: M.SourceDoc, pool: Sequence[M.Sentence], text: str
) -> MS.Prompt:
    return MS.Prompt(
        stage=Stage.FINDER,
        system=P.SELECTOR_QUESTION,
        user=P.selector_block(site, source_id, meta, pool, text),
    )


def _hold(site_id: str, reason: M.HoldReason, detail: str) -> M.Hold:
    return M.Hold(site_id=site_id, scope=M.HoldScope.SITE, reason=reason, detail=detail)


def select_batch(batch_dir: Path, *, ledger: Path, runner: MS.ModelRunner) -> int:
    """S3 over one batch. 0 when every selecting site reached an outcome (a hold is one)."""
    batch_id, sites = B.read_batch(batch_dir)
    lanes = B.read_lanes(batch_dir, sites)
    held = B.site_held(B.read_holds(batch_dir))
    answers = F.EvidenceStore(batch_dir / B.ANSWERS_DIR)
    book = L.Ledger(ledger)
    pools: list[dict[str, Any]] = []
    selections: list[M.Selection] = []
    holds: list[M.Hold] = []
    rows: list[dict[str, Any]] = []
    error: str | None = None
    for site in sites:
        lane = lanes[site.site_id]
        if lane.lane not in SELECTING_LANES or site.site_id in held:
            continue
        source_id, meta, text, pool = site_pool(batch_dir, site, lane)
        row: dict[str, Any] = {
            "site_id": site.site_id,
            "lane": lane.lane.value,
            "source": source_id,
            "pool_sentences": len(pool),
            "pool_chars": sum(s.end - s.start for s in pool),
        }
        rows.append(row)
        if not pool:
            holds.append(
                _hold(
                    site.site_id,
                    M.HoldReason.NO_SOURCE,
                    f"lane {lane.lane.value}: no sentence of {source_id} can be offered "
                    "(none publishable, or in lane S none names the site); no call was bought",
                )
            )
            row["outcome"] = "held"
            continue
        pools.append(B.pool_record(site.site_id, source_id, pool))
        try:
            bought = B.buy(
                batch_dir=batch_dir,
                batch_id=batch_id,
                site_id=site.site_id,
                field=B.SELECT_FIELD,
                stage=Stage.FINDER,
                prompt=selector_prompt(site, source_id, meta, pool, text),
                runner=runner,
                ledger=book,
                answers=answers,
            )
        except MS.UnreadableStream as exc:
            holds.append(_hold(site.site_id, M.HoldReason.MODEL_STREAM_UNREADABLE, str(exc)))
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
            selection = parse_selection(site.site_id, bought.text, pool)
        except M.SelectionRefused as exc:
            holds.append(_hold(site.site_id, M.HoldReason.SELECTION_REFUSED, str(exc)))
            row["outcome"] = "held"
            continue
        if selection.abstain is not None:
            holds.append(_hold(site.site_id, M.HoldReason.ABSTAINED, selection.abstain))
            row["outcome"] = "held"
            continue
        selections.append(selection)
        row["outcome"] = "selected"
    B.write_records(batch_dir / B.POOLS_FILE, pools)
    B.write_text_atomic(batch_dir / B.SELECTIONS_FILE, M.dump_jsonl(selections))
    B.append_holds(batch_dir, holds)
    B.write_report(
        batch_dir / B.SELECT_REPORT,
        {"batch_id": batch_id, "stage": "select", "sites": rows, "error": error},
    )
    return 0 if error is None else 2
