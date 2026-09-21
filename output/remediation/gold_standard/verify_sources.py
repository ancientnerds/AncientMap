"""Does a correction's source hold? Measured against the bytes the run itself fetched.

The discover pass asks for a `WRONG` verdict, a `PROPOSED` value and a `SOURCE` line, and the answer
claims that a sentence occurs on a page. That claim is checkable here, and this script is the check:
every cited page must be a URL **this run fetched**, and the quoted sentence must occur in the bytes
we stored for it. A citation that fails either test is a fabricated citation, and the writer refuses
the finding.

Why the comparison decodes escapes: the evidence files for `enwiki` and `wikidata_entity` are the
APIs' **JSON responses**, and `model_stage.evidence_block` puts that text into the prompt verbatim. So
the page carries `\\u00c1vila` and `\\n` where the model reads `Ávila` and a line break. Comparing raw
bytes would report every honest quote as missing and the metric would be about JSON, not about
citations. Both sides are therefore unescaped and whitespace-folded before they are compared, and
that fold is the only relaxation: the words and their order are still required.

Usage: ./.venv/Scripts/python.exe output/remediation/gold_standard/verify_sources.py [RUN_DIR]
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass, field

REPO = pathlib.Path(__file__).resolve().parents[3]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402

DEFAULT_RUN = REPO / "output" / "remediation" / "phase3_runner" / "runs" / "gold5"


@dataclass
class SourceScore:
    """What one run's corrections are worth. `problems` names every citation that failed."""

    run: str
    seen: Counter[str] = field(default_factory=Counter)
    problems: list[str] = field(default_factory=list)


def fetched_pages(batch: pathlib.Path) -> dict[str, str]:
    """url -> the bytes this run stored for it, for every target of this batch."""
    report = json.loads((batch / "fetch.json").read_text(encoding="utf-8"))
    pages: dict[str, str] = {}
    for site in report["sites"]:
        for outcome in site["outcomes"]:
            path = batch / "evidence" / f"{site['site_id']}%2F{outcome['feature']}.txt"
            if path.exists():
                pages[outcome["url"]] = path.read_text(encoding="utf-8")
    return pages


def score(run_dir: pathlib.Path) -> SourceScore:
    result = SourceScore(run=run_dir.name)
    seen = result.seen
    for batch in sorted(run_dir.glob("batch-*")):
        if not (batch / "fetch.json").exists():
            continue
        pages = fetched_pages(batch)
        for answer_file in sorted((batch / "answers").glob("*.txt")):
            answer = DS.parse_answer(answer_file.read_text(encoding="utf-8"))
            seen["answered"] += 1
            if answer.verdict is not None:
                seen[f"verdict_{answer.verdict}"] += 1
            if answer.verdict != "WRONG":
                continue
            seen["wrong"] += 1
            if answer.proposed is not None:
                seen["wrong_with_proposed"] += 1
            if answer.sources:
                seen["wrong_with_source"] += 1
            seen["quotes"] += len(answer.sources)
            bad = DS.source_problems(answer, pages)
            seen["citation_problems"] += len(bad)
            result.problems.extend(f"{answer_file.name}: {problem}" for problem in bad)
            if answer.complete and not bad:
                seen["writable"] += 1
    return result


def main(argv: list[str]) -> int:
    run_dir = pathlib.Path(argv[0]) if argv else DEFAULT_RUN
    if not run_dir.is_absolute():
        run_dir = REPO / run_dir
    result = score(run_dir)
    print(f"run: {result.run}")
    for key, value in result.seen.items():
        print(f"  {key:>22}: {value}")
    for line in result.problems[:20]:
        print(f"  ! {line}")
    out = REPO / "output" / "remediation" / "gold_standard" / (f"source_result_{run_dir.name}.json")
    out.write_text(
        json.dumps(
            {
                "run": result.run,
                "seen": dict(sorted(result.seen.items())),
                "problems": result.problems,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
