#!/usr/bin/env python3
"""paper24_evidence: build evidence.json from a numbered paper.

Every entry is real, not a placeholder: the quote is the source's own window that
`claim_support.locate_support` located for the paragraph's sentence, so the quote
provably carries the sentence that cites it, and `anchor_text` is the paragraph's
opening copied verbatim and checked to open exactly one paragraph.

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/paper24_evidence.py REQUEST_ID

It writes `evidence.json` only when every marked paragraph produced a located
quote, and names the paragraphs that did not - a paragraph whose marker is not
located has a citation defect to fix in the draft, and an evidence entry for it
would be a claim the sources do not carry. `--allow-partial` writes what it has
and reports the rest, for the case where a paragraph's second marker still needs
work: the first marker's quote is the paragraph's evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pipeline.lyra import paper_claim_gate
from pipeline.lyra.claim_support import locate_support
from pipeline.lyra.paper_claim_gate import _carrying_sentence, _prose_only
from pipeline.lyra.text_sentences import sentence_span
from pipeline.studio import config
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import load_dossier, workspace

CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")
ANCHOR_CHARS = 72
MIN_ANCHOR = 20


def paragraphs(markdown: str) -> list[str]:
    """Body paragraphs of the built paper, without the References section."""
    prose = re.sub(r"(?ms)^## References\s*$.*", "", markdown)
    return [block for block in re.split(r"\n\s*\n", prose) if block.strip()]


def anchor_for(paragraph: str, taken: dict[str, int]) -> str:
    """A verbatim opening that opens this paragraph and no other one already anchored."""
    text = " ".join(paragraph.split())
    for length in (ANCHOR_CHARS, 52, 40, 32, MIN_ANCHOR):
        anchor = text[:length].rstrip()
        if len(anchor) >= MIN_ANCHOR and taken.get(anchor, 0) == 0:
            taken[anchor] = 1
            return anchor
        taken[anchor] = taken.get(anchor, 0) + 1
    raise StudioError(f"cannot anchor a paragraph: {text[:60]!r}")


def entries(
    ws: Any, *, allow_partial: bool = False
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dossier = load_dossier(ws)
    rows = json.loads(ws.sources_json.read_text(encoding="utf-8"))
    by_number = {str(row["n"]): row["source_id"] for row in rows}
    texts = {str(row["n"]): dossier.texts.get(row["source_id"], "") for row in rows}
    out: list[dict[str, Any]] = []
    unlocated: list[dict[str, Any]] = []
    taken: dict[str, int] = {}
    for index, paragraph in enumerate(paragraphs(ws.paper.read_text(encoding="utf-8")), start=1):
        markers = CITATION_MARKER_RE.findall(paragraph)
        if not markers:
            continue
        located: list[tuple[str, str, str]] = []
        for match in CITATION_MARKER_RE.finditer(paragraph):
            number = match.group(1)
            start, end = sentence_span(paragraph, match.start())
            claim = _prose_only(_carrying_sentence(paragraph, match.start()))
            support = locate_support(claim, texts.get(number, ""))
            if support is None:
                # The same condition the gate uses: a sentence that asserts nothing
                # checkable is not a citation defect, and this tool must not report
                # one where `paper check` reports none.
                if not paper_claim_gate._verifiable_content(claim):
                    continue
                unlocated.append(
                    {
                        "paragraph": index,
                        "marker": f"[{number}]",
                        "sentence": claim[:200],
                        "source_id": by_number.get(number, ""),
                    }
                )
                continue
            located.append((number, claim, " ".join(support.quote.split())))
        if not located:
            continue
        number, claim, quote = located[0]
        out.append(
            {
                "id": f"ev-{len(out) + 1:02d}",
                "anchor_text": anchor_for(paragraph, taken),
                "claim": " ".join(claim.split()),
                "source_ids": [by_number[number]],
                "quote": quote,
                "quote_source_id": by_number[number],
                "verdict": "supported",
            }
        )
    if unlocated and not allow_partial:
        return [], unlocated
    return out, unlocated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/paper24_evidence.py",
        description="Write evidence.json from the located quotes of a numbered paper.",
    )
    parser.add_argument("request_id")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="write the located entries and report the rest instead of refusing",
    )
    args = parser.parse_args(argv)
    try:
        ws = workspace(config.check_request_id(args.request_id))
        out, unlocated = entries(ws, allow_partial=args.allow_partial)
        if unlocated and not args.allow_partial:
            print(
                f"error: {len(unlocated)} marker(s) are not located; fix the draft first "
                f"(first: p{unlocated[0]['paragraph']} {unlocated[0]['marker']})",
                file=sys.stderr,
            )
            return 1
        if not out:
            print("error: no paragraph produced a located quote", file=sys.stderr)
            return 1
        ws.evidence.write_text(
            json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except StudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"evidence": len(out), "unlocated": len(unlocated), "path": str(ws.evidence)},
            ensure_ascii=False,
        )
    )
    for entry in unlocated:
        print(f"unlocated p{entry['paragraph']} {entry['marker']}: {entry['sentence'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
