"""The command line of the Opus re-verification (`scripts/remediation/opus_audit/`).

    run.py sample   KEEP_SAMPLE.json: RULES.md rule 4's sample, stated before anyone judges it
    run.py fetch    every URL a verdict cites, fetched once into pages/ (read-only GETs)
    run.py decide   the quote check and the decision rule, offline: DECISIONS.jsonl, COUNTS.json,
                    REJUDGE.json and REVERSAL_3_INPUT.jsonl (a URL fetch has not kept is refused)

Every command refuses a RULES.md or INPUT.jsonl that is not the sealed one. Nothing here calls a
model or writes to production.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from opus_audit import decide as D  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

AUDIT = REPO / "output" / "remediation" / "opus_audit"


def cited_urls(*rounds: dict) -> list[str]:
    """Every URL a verdict of any round cites, in any of its passes or sections."""
    return sorted(
        {
            q["source"]
            for verdicts in rounds
            for section in verdicts.values()
            for v in section.values()
            for q in v["quotes"]
            if Q.is_url(q["source"])
        }
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def fetch(audit: Path) -> dict[str, object]:
    _rows, raw, round2, _inputs = D.load_rounds(audit, D.RULES_SHA256, D.INPUT_SHA256)
    urls = cited_urls(raw, round2)
    pages = audit / "pages"
    with Q.http_client() as client:
        counts = Q.collect(urls, pages, client, now=_now)
    index = Q.page_index(urls, pages)
    (audit / "PAGES.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in index),
        encoding="utf-8",
        newline="\n",
    )
    statuses = Counter(
        "not fetched" if "not_fetched" in x else str(x["status"] or x["error"].split(":")[0])
        for x in index
    )
    return {"urls": len(index), **counts, "status": dict(sorted(statuses.items()))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The Opus re-verification: sample, fetch, decide")
    ap.add_argument("command", choices=["sample", "fetch", "decide"])
    ap.add_argument("--dir", type=Path, default=AUDIT, help="the opus_audit directory")
    args = ap.parse_args(argv)
    try:
        if args.command == "sample":
            sample = D.write_keep_sample(args.dir)
            out: object = {k: v for k, v in sample.items() if k != "keys"}
        elif args.command == "fetch":
            out = fetch(args.dir)
        else:
            summary = D.run(args.dir)
            out = {
                "round_2": {s: summary["round_2"][s]["failed"] for s in D.ROUND_2_SECTIONS},
                "overlay": summary["overlay"],
                "rule_4": {
                    k: summary["rule_4"][k]
                    for k in ("sample", "counted", "not_keep", "threshold", "fired")
                },
                **{
                    k: summary[k]
                    for k in (
                        "decisions",
                        "rejudge_by_pass",
                        "pending_by_pass",
                        "second_judge",
                        "tie_round_2",
                        "reversal_rows",
                    )
                },
            }
    except Q.AuditError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
