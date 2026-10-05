#!/usr/bin/env python3
"""paper24_claimsync: which source sentence carries a research claim.

The brief filter (`paper24_seed` -> `pull._carried`) withholds a marker when
`claim_support.locate_support` finds no window of at most two sentences that
carries every one of the claim's specifics. Writing the claim in the source's
own wording - its numbers, its units, its symbols - is what makes it locatable,
and a research file written any other way loses a third of its markers.

This is the report for that: for every claim of a research file, the sentences
of each cited source that come closest, so the claim can be reworded against
real text instead of against memory. It never edits a claim and never invents
one; it prints.

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/paper24_claimsync.py research.json
    ... research.json --only-uncarried --words 240

Scoring is the gate's own vocabulary: every number of the claim must be in the
candidate window (via `claim_support.claim_numbers`), and the remaining
specifics are counted as word-boundary hits (`claim_support._carried`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pipeline.lyra.claim_support import _carried, _claim_specifics, _sentence_spans
from pipeline.lyra.text_sentences import split_sentences

WINDOW = 2
_WORD_RE = re.compile(r"[a-z0-9]+")


def _windows(text: str) -> list[str]:
    """Every contiguous run of at most WINDOW sentences, verbatim."""
    sentences = split_sentences(text)
    out: list[str] = []
    for index in range(len(sentences)):
        for size in range(1, WINDOW + 1):
            chunk = "".join(sentences[index : index + size])
            if chunk.strip():
                out.append(chunk)
    return out


def _score(specifics: tuple[tuple[str, str], ...], candidate: str, numbers: frozenset[str]) -> int:
    """How many of the claim's specifics the candidate carries."""
    return sum(1 for kind, text in specifics if _carried(kind, text, candidate.lower(), numbers))


def suggestions(claim: str, source_text: str, *, limit: int, words: int) -> list[tuple[int, str]]:
    """(score, verbatim window) for the best-scoring windows, best first."""
    from pipeline.lyra.claim_support import claim_numbers

    specifics = _claim_specifics(claim)
    if not specifics:
        return []
    numbers = frozenset(claim_numbers(source_text))
    scored: list[tuple[int, int, str]] = []
    for position, candidate in enumerate(_windows(source_text)):
        score = _score(specifics, candidate, numbers)
        if score:
            scored.append((score, -position, candidate))
    scored.sort(reverse=True)
    seen: set[str] = set()
    out: list[tuple[int, str]] = []
    for score, _position, candidate in scored:
        key = " ".join(candidate.split())[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append((score, " ".join(candidate.split())[:words]))
        if len(out) >= limit:
            break
    return out


def _carried_already(claim: str, source_text: str) -> bool:
    from pipeline.lyra.claim_support import locate_support

    return locate_support(claim, source_text, window=WINDOW) is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/paper24_claimsync.py",
        description="Report the source sentences that come closest to each research claim.",
    )
    parser.add_argument("research", type=Path)
    parser.add_argument(
        "--only-uncarried",
        action="store_true",
        help="only claims no cited source carries (the ones that lost their marker)",
    )
    parser.add_argument("--limit", type=int, default=2, help="suggestions per source")
    parser.add_argument("--words", type=int, default=240, help="characters per suggestion")
    args = parser.parse_args(argv)

    research: dict[str, Any] = json.loads(args.research.read_text(encoding="utf-8"))
    by_id = {source["id"]: source for source in research["sources"]}
    uncarried = 0
    reported = 0
    for claim in research["claims"]:
        text = claim["claim"]
        sources = [by_id[sid] for sid in claim["source_ids"] if sid in by_id]
        carried = [source for source in sources if _carried_already(text, source["text"])]
        if carried:
            if args.only_uncarried:
                continue
            continue
        uncarried += 1
        if not args.only_uncarried:
            continue
        reported += 1
        print(f"\n--- NOT CARRIED: {text}")
        for source in sources:
            for score, candidate in suggestions(
                text, source["text"], limit=args.limit, words=args.words
            ):
                print(f"    [{source['title'][:60]} | score {score}] {candidate}")
    print(f"\n{uncarried} of {len(research['claims'])} claims are carried by no cited source")
    return 0 if reported or not args.only_uncarried else 1


if __name__ == "__main__":
    raise SystemExit(main())
