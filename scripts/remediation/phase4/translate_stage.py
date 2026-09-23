"""S3T: lane T's second call - the chosen source-language sentences into English.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, writer "LANES
WITH GENERATED TEXT", lane T. Work item WB-B3.

The selector has already chosen sentences of the other-language article (`select_stage`, the same
contract as lane W). A `T.<lang>` sentence offers no span (`sentences.split_source`: the protected
tokens are English), so every DESC pick is a whole sentence and `assemble.trim` applies only edits
2-3 to it. This stage shows those sentences, numbered `T1..Tk` in source order, and asks the frozen
`TRANSLATE_QUESTION`. The answer must be exactly one line `T<i>: <English sentence>` per shown
sentence, each ending in its own final punctuation, and nothing else; anything else holds the site
as `translation-refused`. An unreadable stream holds it as `model-stream-unreadable`. There is no
retry, and a call that could not be made stops the batch.

The published text is generated (`ai: generated`), so it gets only edit 5 (the marker), and the
citation numbers are assigned by the assembler. Lane T builds no card.
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

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import prompts4 as P  # noqa: E402

_LINE = re.compile(r"T(?P<number>[1-9][0-9]*):[ \t]*(?P<text>\S.*?)[ \t]*")


class TranslationRefused(ValueError):
    """The translation answer is not one terminated English line per shown sentence."""


def trimmed_sentences(
    selection: M.Selection, pool: Sequence[M.Sentence], text: str
) -> list[tuple[str, str]]:
    """`(sid, trimmed source sentence)` for every DESC pick, in source order."""
    by_sid = {sentence.sid: sentence for sentence in pool}
    rows: list[tuple[str, str]] = []
    for pick in sorted(selection.desc, key=lambda p: by_sid[p.sid].index):
        sentence = by_sid[pick.sid]
        spans = {span.id: span for span in sentence.spans}
        drops = A.maximal([(spans[i].start, spans[i].end) for i in pick.drop])
        rows.append((pick.sid, A.trim(text, sentence.start, sentence.end, drops)))
    return rows


def parse_translation(answer: str, sids: Sequence[str]) -> dict[str, str]:
    """`sid -> English sentence`, or `TranslationRefused` naming what is wrong."""
    found: dict[int, str] = {}
    for raw in answer.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise TranslationRefused(f"a line that is not `T<i>: <sentence>`: {line[:120]!r}")
        number = int(match["number"])
        if not 1 <= number <= len(sids):
            raise TranslationRefused(f"T{number} names no shown sentence (1-{len(sids)})")
        if number in found:
            raise TranslationRefused(f"T{number} is answered twice")
        sentence = match["text"]
        if sentence[-1] not in A.TERMINAL:
            raise TranslationRefused(f"T{number} does not end in . ! or ?: {sentence[-40:]!r}")
        found[number] = sentence
    missing = [f"T{i}" for i in range(1, len(sids) + 1) if i not in found]
    if missing:
        raise TranslationRefused(f"no translation for {missing}")
    return {sid: found[i] for i, sid in enumerate(sids, start=1)}


def _hold(site_id: str, reason: M.HoldReason, detail: str) -> M.Hold:
    return M.Hold(site_id=site_id, scope=M.HoldScope.SITE, reason=reason, detail=detail)


def translate_batch(batch_dir: Path, *, ledger: Path, runner: MS.ModelRunner) -> int:
    """S3T over one batch: every lane-T site with a selection and no hold gets one call."""
    batch_id, sites = B.read_batch(batch_dir)
    lanes = B.read_lanes(batch_dir, sites)
    held = B.site_held(B.read_holds(batch_dir))
    selections = B.read_selections(batch_dir)
    pools = B.read_pools(batch_dir)
    answers = F.EvidenceStore(batch_dir / B.ANSWERS_DIR)
    book = L.Ledger(ledger)
    records: list[dict[str, Any]] = []
    holds: list[M.Hold] = []
    rows: list[dict[str, Any]] = []
    error: str | None = None
    for site in sites:
        lane = lanes[site.site_id]
        if lane.lane is not M.Lane.T or site.site_id in held:
            continue
        selection = selections[site.site_id]
        source_id, pool = pools[site.site_id]
        meta, text = B.read_source(batch_dir, site.site_id, source_id)
        shown = trimmed_sentences(selection, pool, text)
        row: dict[str, Any] = {"site_id": site.site_id, "source": source_id, "shown": len(shown)}
        rows.append(row)
        prompt = MS.Prompt(
            stage=Stage.FINDER,
            system=P.TRANSLATE_QUESTION,
            user=P.translate_block(site, source_id, meta, [body for _, body in shown]),
        )
        try:
            bought = B.buy(
                batch_dir=batch_dir,
                batch_id=batch_id,
                site_id=site.site_id,
                field=B.TRANSLATE_FIELD,
                stage=Stage.FINDER,
                prompt=prompt,
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
            english = parse_translation(bought.text, [sid for sid, _ in shown])
        except TranslationRefused as exc:
            holds.append(_hold(site.site_id, M.HoldReason.TRANSLATION_REFUSED, str(exc)))
            row["outcome"] = "held"
            continue
        records.append(
            {
                "site_id": site.site_id,
                "sentences": [{"sid": sid, "text": english[sid]} for sid, _ in shown],
            }
        )
        row["outcome"] = "translated"
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, records)
    B.append_holds(batch_dir, holds)
    B.write_report(
        batch_dir / B.TRANSLATE_REPORT,
        {"batch_id": batch_id, "stage": "translate", "sites": rows, "error": error},
    )
    return 0 if error is None else 2
