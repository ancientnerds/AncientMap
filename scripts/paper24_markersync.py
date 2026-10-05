#!/usr/bin/env python3
"""paper24_markersync: for every marker in a draft, why is it (not) carried.

`paper check` reports a wrong marker as `[N] is not supported`, which names the
reference number and the specifics the reference is missing - but not the marker
itself, and not the paragraph's other sources, which is the expensive part to
recover by hand. The brief's own measurement says that re-running the gate over
a paragraph's other sources named a replacement for 47 of 82 markers without a
single model call; this is that re-run, as a command.

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/paper24_markersync.py REQUEST_ID

Per marker it prints the sentence the marker closes, the specifics the gate wants
(`claim_support.locate_support`'s vocabulary: every number of the sentence with
its unit, plus dates, persons, titles, quotes, institutions), the keys the cited
source is missing, and - when a sibling source of the same paragraph carries the
sentence - that source's id. It never edits the draft.

The rule it makes visible, and the reason a paper keeps failing this gate: a
sentence's numbers must be in *every* source that sentence cites, with the unit
spelled the way the source spells it. `20 y` in the source and `20 years` in the
paper are different keys.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from pipeline.lyra import paper_claim_gate
from pipeline.lyra.claim_support import (
    _claim_specifics,
    claim_numbers,
    locate_support,
)
from pipeline.lyra.text_sentences import split_sentences
from pipeline.studio import config
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import PaperWorkspace, load_dossier, workspace

MARKER_RE = re.compile(r"\[S:([0-9a-f]{12})\]")
WINDOW = 2


def paragraph_sentence(paragraph: str, at: int) -> str:
    """The sentence a marker closes, with the gate's own sentence splitter."""
    offset = 0
    for sentence in split_sentences(paragraph):
        if offset + len(sentence) >= at:
            return sentence.strip()
        offset += len(sentence)
    return paragraph.strip()


def wanted_keys(sentence: str) -> set[str]:
    """The gate's vocabulary for a sentence: its numbers with units, plus specifics."""
    keys = set(claim_numbers(sentence))
    for _kind, text in _claim_specifics(sentence):
        keys.add(f"~{text}")
    return keys


def source_keys(text: str) -> set[str]:
    keys = set(claim_numbers(text))
    for _kind, specific in _claim_specifics(text):
        keys.add(f"~{specific}")
    return keys


def reference_numbers(blocks: list[str]) -> dict[str, int]:
    """The audit's reference numbering: distinct source ids, in order of first appearance.

    `paper check` reports a wrong marker as `[N]`, where N is the index in the
    reference list the artifact audit builds from the draft. Reproducing that
    order is what makes a gate message actionable.
    """
    numbers: dict[str, int] = {}
    for block in blocks:
        for source_id in MARKER_RE.findall(block):
            numbers.setdefault(source_id, len(numbers) + 1)
    return numbers


def report(ws: PaperWorkspace) -> dict[str, Any]:
    """Re-run the gate's own marker rules over a `[S:...]` draft.

    `paper check` numbers a copy of the draft and calls
    `paper_claim_gate._check_markers` on it; this does the same and maps every issue
    back to the `[S:...]` marker, so the report is the gate's verdict on this draft
    rather than a re-implementation of it.
    """
    draft = ws.draft.read_text(encoding="utf-8")
    dossier = load_dossier(ws)
    texts = dict(dossier.texts)
    blocks = re.split(r"\n\s*\n", draft)
    numbers = reference_numbers(blocks)
    by_number = {str(number): source_id for source_id, number in numbers.items()}
    numbered_texts = {
        str(number): texts.get(source_id, "") for source_id, number in numbers.items()
    }
    lines: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        if not MARKER_RE.search(block):
            continue
        numbered = MARKER_RE.sub(lambda match: f"[{numbers[match.group(1)]}]", block)
        for issue in paper_claim_gate._check_markers(numbered, index, numbered_texts):
            source_id = by_number.get(issue.marker.strip("[]"), "?")
            position = numbered.find(issue.marker)
            lines.append(
                {
                    "paragraph": issue.paragraph,
                    "marker": issue.marker,
                    "source_id": source_id,
                    "rule": issue.rule,
                    "detail": issue.detail,
                    "sentence": paragraph_sentence(numbered, max(position, 0))[:300],
                }
            )
    return {
        "request_id": ws.request_id,
        "references": len(numbers),
        "issues": len(lines),
        "lines": lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/paper24_markersync.py",
        description="Report why each citation marker of a draft is or is not carried.",
    )
    parser.add_argument("request_id")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--only-failing", action="store_true", help="only uncarried markers")
    args = parser.parse_args(argv)
    try:
        result = report(workspace(config.check_request_id(args.request_id)))
    except (OSError, KeyError) as exc:  # unreadable workspace or dossier
        print(f"error: cannot read the workspace: {exc}", file=sys.stderr)
        return 2
    except StudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(
        f"{result['issues']} marker issue(s) over {result['references']} references "
        f"({result['request_id']})"
    )
    for line in result["lines"]:
        print(f"\np{line['paragraph']} {line['marker']} {line['source_id']} {line['rule']}")
        print(f"    {line['detail'][-200:]}")
        print(f"    sentence: {line['sentence'][:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
