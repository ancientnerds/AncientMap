"""S3R: lane R - facts restated from non-free pages, each tied to a quote code locates in its page.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, writer "LANES
WITH GENERATED TEXT", lane R, and source_store (lane-R pages are `restricted`: the facts may be
restated, the wording is never published). Work item WB-B3.

One call per lane-R site shows every stored page of the site (`src.R<k>`, their pinned text) and
asks the frozen `RESTRICTED_QUESTION` for 2-4 pairs

    S<i>: <sentence>
    Q<i>: <url> - "<verbatim quote>"

The url must be one the prompt showed. The quote is then **located by code** in that page's pinned
text (`locate_quote`, the fold of `discover_stage.normalise_quote` - case, whitespace, quote marks and
dashes - and nothing else), and the published provenance pins the exact range, so the journal quote
is `text[start:end]` and V2 holds by construction; a quote the fold cannot find holds the site. The
restatement text is the model's; V11 (the verifier) owns `discover_stage.claim_problems` against
the stored page, the 8-word no-copy rule and the anchor closure. A page with no title or no final
url cannot be cited, and a site whose pages are over `model_stage.MAX_EVIDENCE_CHARS` cannot be
asked in one bounded prompt: both hold before any call is bought.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import discover_stage as DS  # noqa: E402  - the quote fold
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3.model import Stage  # noqa: E402

from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import prompts4 as P  # noqa: E402

MIN_PAIRS = 2
MAX_PAIRS = 4
TERMINAL = ".!?"

_S_LINE = re.compile(r"S(?P<number>[1-9][0-9]*):[ \t]*(?P<text>\S.*?)[ \t]*")
_Q_LINE = re.compile(
    r"Q(?P<number>[1-9][0-9]*):[ \t]*(?P<url>https?://\S+)[ \t]+[-–—][ \t]*"
    r"[\"“](?P<quote>.+?)[\"”][ \t]*"
)


class RestatementRefused(ValueError):
    """The answer is not 2-4 well-formed S/Q pairs whose quotes occur in the named pages."""


def locate_quote(quote: str, text: str) -> tuple[int, int] | None:
    """The first `[start, end)` of `text` whose fold equals the quote's fold, or `None`.

    The fold is `discover_stage.normalise_quote`, applied one character at a time so every folded
    character keeps the index it came from; a whitespace run folds to one space.
    """
    needle = DS.normalise_quote(quote)
    if not needle:
        return None
    folded: list[str] = []
    origin: list[int] = []
    in_space = True
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space:
                folded.append(" ")
                origin.append(index)
                in_space = True
            continue
        for piece in DS.normalise_quote(char):
            folded.append(piece)
            origin.append(index)
        in_space = False
    haystack = "".join(folded)
    at = haystack.find(needle)
    if at < 0:
        return None
    return origin[at], origin[at + len(needle) - 1] + 1


def parse_restatement(
    answer: str, pages: Mapping[str, tuple[str, str]]
) -> tuple[B.Restatement, ...]:
    """The pairs as restatements, each with its located quote range, or `RestatementRefused`.

    `pages` maps the url the prompt showed to `(source id, pinned text)`.
    """
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if len(lines) % 2 or not MIN_PAIRS <= len(lines) // 2 <= MAX_PAIRS:
        raise RestatementRefused(f"{len(lines)} lines; the contract is 2-4 S/Q pairs")
    out: list[B.Restatement] = []
    for number, (s_line, q_line) in enumerate(zip(lines[::2], lines[1::2], strict=True), 1):
        said = _S_LINE.fullmatch(s_line)
        cited = _Q_LINE.fullmatch(q_line)
        if said is None or cited is None:
            raise RestatementRefused(f"pair {number} is not `S{number}:` then `Q{number}:`")
        if int(said["number"]) != number or int(cited["number"]) != number:
            raise RestatementRefused(
                f"pair {number} is numbered S{said['number']}/Q{cited['number']}"
            )
        sentence = said["text"]
        if sentence[-1] not in TERMINAL:
            raise RestatementRefused(f"S{number} does not end in . ! or ?: {sentence[-40:]!r}")
        url = cited["url"]
        if url not in pages:
            raise RestatementRefused(f"Q{number} cites {url}, which the prompt did not show")
        source_id, text = pages[url]
        located = locate_quote(cited["quote"], text)
        if located is None:
            raise RestatementRefused(f"Q{number}: the quote does not occur in {source_id} ({url})")
        out.append(B.Restatement(text=sentence, src=source_id, start=located[0], end=located[1]))
    for source_id in {r.src for r in out}:
        mine = sorted((r.start, r.end) for r in out if r.src == source_id)
        for (_, high), (low, _) in zip(mine, mine[1:], strict=False):
            if low < high:
                raise RestatementRefused(f"two quotes of {source_id} overlap")
    return tuple(out)


def _hold(site_id: str, reason: M.HoldReason, detail: str) -> M.Hold:
    return M.Hold(site_id=site_id, scope=M.HoldScope.SITE, reason=reason, detail=detail)


def _unusable(pages: Sequence[tuple[str, M.SourceDoc, str]], site_id: str) -> str | None:
    """Why the pages cannot be asked about in one call, or `None`."""
    for source_id, meta, _ in pages:
        if meta.title is None or meta.final_url is None:
            return f"{source_id} carries no title or no final url; it cannot be cited"
    excerpts = [
        MS.EvidenceExcerpt(
            feature=source_id, url=P.cited_url(meta), path=Path(source_id), text=text
        )
        for source_id, meta, text in pages
    ]
    try:
        MS.check_evidence_bound(site_id, excerpts)
    except MS.EvidenceOverBound as exc:
        return f"no bounded prompt exists: {exc}"
    return None


def restricted_batch(batch_dir: Path, *, ledger: Path, runner: MS.ModelRunner) -> int:
    """S3R over one batch: one call per lane-R site that no stage has held."""
    batch_id, sites = B.read_batch(batch_dir)
    lanes = B.read_lanes(batch_dir, sites)
    held = B.site_held(B.read_holds(batch_dir))
    answers = F.EvidenceStore(batch_dir / B.ANSWERS_DIR)
    book = L.Ledger(ledger)
    records: list[dict[str, Any]] = []
    holds: list[M.Hold] = []
    rows: list[dict[str, Any]] = []
    error: str | None = None
    for site in sites:
        lane = lanes[site.site_id]
        if lane.lane is not M.Lane.R or site.site_id in held:
            continue
        pages = [(sid, *B.read_source(batch_dir, site.site_id, sid)) for sid in lane.sources]
        row: dict[str, Any] = {"site_id": site.site_id, "pages": len(pages)}
        rows.append(row)
        why = _unusable(pages, site.site_id)
        if why is not None:
            holds.append(_hold(site.site_id, M.HoldReason.RESTATEMENT_REFUSED, why))
            row["outcome"] = "held"
            continue
        prompt = MS.Prompt(
            stage=Stage.FINDER,
            system=P.RESTRICTED_QUESTION,
            user=P.restricted_block(site, pages),
        )
        try:
            bought = B.buy(
                batch_dir=batch_dir,
                batch_id=batch_id,
                site_id=site.site_id,
                field=B.RESTRICTED_FIELD,
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
        shown = {P.cited_url(meta): (sid, text) for sid, meta, text in pages}
        try:
            restated = parse_restatement(bought.text, shown)
        except RestatementRefused as exc:
            holds.append(_hold(site.site_id, M.HoldReason.RESTATEMENT_REFUSED, str(exc)))
            row["outcome"] = "held"
            continue
        records.append(
            {"site_id": site.site_id, "sentences": [item.to_dict() for item in restated]}
        )
        row["outcome"] = "restated"
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, records)
    B.append_holds(batch_dir, holds)
    B.write_report(
        batch_dir / B.RESTRICTED_REPORT,
        {"batch_id": batch_id, "stage": "restricted", "sites": rows, "error": error},
    )
    return 0 if error is None else 2
