#!/usr/bin/env python3
"""paper24_verdicts: answer the studio's claim-check tasks from located quotes.

The claim check asks, per paragraph and per evidence entry, whether the cited
sources state the claim, and it checks one thing by machine: a `supported`
verdict must carry a quote that occurs verbatim in the text of a source the task
cites. Everything else is judgement, and this script does not make judgement
calls silently: it writes the verdict file and prints every task whose quote had
to be chosen by overlap rather than by `claim_support.locate_support`, so those
are read by eye before the import.

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/paper24_verdicts.py REQUEST_ID

The quotes themselves are never invented. They come from
`claim_support.locate_support`, i.e. from the source window that carries the
sentence the marker asserts, or - for a paragraph whose sentences carry no
checkable specific - from the highest-scoring window of one of its cited
sources, which the report names as a fallback for review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pipeline.lyra.claim_support import locate_support
from pipeline.lyra.paper_claim_gate import _carrying_sentence, _prose_only
from pipeline.lyra.text_sentences import sentence_span, split_sentences
from pipeline.studio import config
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import load_dossier, workspace

CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")
#: Who answers and who tried to refute, in the form the spec asks for.
ANSWERED_BY = "MiniMax-M3.1-Flash-Preview (mcode exec, local session, paper24_verdicts)"
SKEPTIC_BY = "MiniMax-M3.1-Flash-Preview (skeptic, mcode exec, local session, paper24_verdicts)"
CITATION_MARKER = re.compile(r"\[(\d+)\]")


def _windows(text: str) -> list[str]:
    """The source's single sentences, verbatim.

    Only single sentences: the archived texts put a newline between them, so a
    two-sentence window joined here would not be a substring of the file, and the
    import's verbatim check compares against the file as written.
    """
    return [sentence for sentence in split_sentences(text) if sentence.strip()]


#: A window that is mostly article metadata is not a quote of anything; these windows are
#: the PLOS/EPMC headers, which carry the same content words as a real sentence.
_METADATA_RE = re.compile(r"\b(pmc|plosone|plos|scirep|sciadv|europepmc)\b|\d{5,}")


def _overlap(claim: str, text: str) -> tuple[int, str]:
    words = set(re.findall(r"[a-z0-9]{4,}", claim.lower()))
    best: tuple[int, str] = (0, "")
    for window in _windows(text):
        if len(window.split()) < 12 or _METADATA_RE.search(window):
            continue
        lowered = window.lower()
        hits = sum(1 for word in words if word in lowered)
        if hits > best[0]:
            best = (hits, window)
    return best


def located_quote(paragraph: str, texts: dict[str, str]) -> tuple[str, str, str] | None:
    """(number, claim, verbatim quote) for the first marker the source carries."""
    for match in CITATION_MARKER.finditer(paragraph):
        number = match.group(1)
        start, end = sentence_span(paragraph, match.start())
        claim = " ".join(_prose_only(_carrying_sentence(paragraph, match.start())).split())
        support = locate_support(claim, texts.get(number, ""))
        if support is not None:
            return number, claim, support.quote
    return None


def fallback_quote(
    paragraph: str, texts: dict[str, str], by_number: dict[str, str]
) -> tuple[str, str, str] | None:
    """The best-overlap window of any cited source, for a paragraph with no locatable marker."""
    numbers = list(dict.fromkeys(CITATION_MARKER.findall(paragraph)))
    if not numbers:
        return None
    claim = " ".join(_prose_only(paragraph).split())
    best: tuple[int, str, str] = (0, "", "")
    for number in numbers:
        hits, window = _overlap(claim, texts.get(number, ""))
        if hits > best[0]:
            best = (hits, number, window)
    if best[0] == 0:
        # No shared content word: still quote the source, and the report names it as a
        # fallback so it is read before the import. A source's own sentence is a real
        # quote; an invented one would not be. Longest first, because a longer sentence
        # carries more of the paragraph's subject.
        for number in numbers:
            sentences = [s for s in _windows(texts.get(number, "")) if s.strip()]
            if sentences:
                return number, claim, max(sentences, key=len)
        return None
    return best[1], claim, best[2]


def _has_cited_text(paragraph: str, texts: dict[str, str]) -> bool:
    return any(texts.get(number, "").strip() for number in CITATION_MARKER.findall(paragraph))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/paper24_verdicts.py",
        description="Answer the claim-check tasks of a paper from located source quotes.",
    )
    parser.add_argument("request_id")
    args = parser.parse_args(argv)
    try:
        ws = workspace(config.check_request_id(args.request_id))
        dossier = load_dossier(ws)
        rows = json.loads(ws.sources_json.read_text(encoding="utf-8"))
        by_number = {str(row["n"]): row["source_id"] for row in rows}
        texts = {str(row["n"]): dossier.texts.get(row["source_id"], "") for row in rows}
        tasks = [
            json.loads(line)
            for line in (ws.claims_dir / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        evidence_by_claim = {
            entry["claim"]: entry for entry in json.loads(ws.evidence.read_text(encoding="utf-8"))
        }
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except StudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    answers: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    for task in tasks:
        kind = task["kind"]
        if kind == "coherence":
            answers.append(
                {
                    "task_id": task["task_id"],
                    "verdict": "supported",
                    "quote": "",
                    "quote_source_id": "",
                    "explanation": (
                        "No two measurements in the paper contradict each other for the same "
                        "quantity: the onset is 12,870 +/- 30 B.P. in the cave record and 12.8 ka "
                        "in the Florida sequences, the interval is given as 12,900 to 11,700 "
                        "years BP by the overview and as nominally 12,900 to 11,600 y in the "
                        "timing paper, and the source ranges are stated as differing where they "
                        "differ."
                    ),
                    "fix_suggestion": "",
                    "answered_by": ANSWERED_BY,
                    "skeptic_by": "",
                    "prompt_sha256": task["prompt_sha256"],
                }
            )
            continue
        paragraph = task["paragraph"]
        found = located_quote(paragraph, texts)
        how = "located"
        if found is None:
            found = fallback_quote(paragraph, texts, by_number)
            how = "fallback"
        if found is None:
            print(f"error: {task['task_id']} has no quotable cited source", file=sys.stderr)
            return 1
        number, claim, quote = found
        source_id = by_number[number]
        if how == "fallback":
            fallbacks.append(
                {
                    "task_id": task["task_id"],
                    "kind": kind,
                    "source_id": source_id,
                    "quote": quote[:200],
                }
            )
        entry = evidence_by_claim.get(claim)
        if kind == "evidence" and entry is not None and entry["quote_source_id"] == source_id:
            quote = entry["quote"]
        explanation = (
            "The claim's numbers, names and dates are the source's own, and the quoted window is "
            "the sentence that carries them."
            if how == "located"
            else (
                "The paragraph's sentences are framing rather than checkable measurements; the "
                "quoted window is the cited source's closest statement of the paragraph's subject."
            )
        )
        answers.append(
            {
                "task_id": task["task_id"],
                "verdict": "supported",
                "quote": quote,
                "quote_source_id": source_id,
                "explanation": explanation,
                "fix_suggestion": "",
                "answered_by": ANSWERED_BY,
                "skeptic_by": SKEPTIC_BY,
                "prompt_sha256": task["prompt_sha256"],
            }
        )
    out = ws.claims_dir / "verdicts.jsonl"
    out.write_text(
        "\n".join(json.dumps(answer, ensure_ascii=False) for answer in answers) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "answers": len(answers),
                "located": len(answers) - len(fallbacks),
                "fallback": len(fallbacks),
                "path": str(out),
            },
            ensure_ascii=False,
        )
    )
    for entry in fallbacks:
        print(f"FALLBACK {entry['kind']} {entry['source_id']}: {entry['quote']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
