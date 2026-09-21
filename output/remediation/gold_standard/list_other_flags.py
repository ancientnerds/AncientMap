"""Every flag a recall run raised that the truth fixture does not list, one block per (site, field).

The fixture is *"the 24 errors the census did not flag"*, not the complete error set, so a `WRONG`
verdict on a pair outside it is undecided evidence: it is either a real error the fixture does not
contain (precision the recall number cannot see) or a false alarm. This script exists to put those
verdicts in front of a reader with the stored value and the answer's own sentence, instead of
letting the recall percentage absorb them. It reads a run directory and prints; it writes nothing
into the run.

Usage: ./.venv/Scripts/python.exe output/remediation/gold_standard/list_other_flags.py <run-dir> [...]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
GOLD = REPO / "output" / "remediation" / "gold_standard"
TRUTH_FIELDS = GOLD / "truth_fields.json"

#: The scorer's own rule (`score_recall.py:38`), deliberately shared rather than re-derived: two
#: instruments that read the same answers must agree on how a verdict is found, or their difference
#: is a measurement artefact. Answers put the verdict on its own line *or* inline ("2. VERDICT: ...").
VERDICT = re.compile(r"VERDICT:\s*(CORRECT|WRONG|UNVERIFIABLE)")


def truth_keys() -> set[tuple[str, str]]:
    payload = json.loads(TRUTH_FIELDS.read_text(encoding="utf-8"))
    return {(entry["site_id"], entry["field"]) for entry in payload["entries"]}


def answers(run_dir: pathlib.Path) -> list[tuple[str, str, str, list[str]]]:
    """(site_id, field, verdict, body) for every answer file of every batch, in batch order."""
    out: list[tuple[str, str, str, list[str]]] = []
    for batch in sorted(run_dir.glob("batch-*")):
        for path in sorted((batch / "answers").glob("*.txt")):
            lines = path.read_text(encoding="utf-8").splitlines()
            match = VERDICT.search("\n".join(lines))
            verdict = match.group(1) if match else "MISSING"
            site_id, _, field = path.stem.partition("%2F")
            out.append((site_id, field, verdict, lines))
    return out


def stored_values(run_dir: pathlib.Path) -> dict[tuple[str, str], object]:
    """The plan's own stored value per (site, field), read from the prepared batch inputs."""
    values: dict[tuple[str, str], object] = {}
    for batch in sorted(run_dir.glob("batch-*")):
        payload = json.loads((batch / "input.json").read_text(encoding="utf-8"))
        for site in payload["sites"]:
            for row in site["findings"]:
                values[(site["site_id"], row["field"])] = row["current_value"]
    return values


def main(argv: list[str]) -> int:
    in_fixture = truth_keys()
    for name in argv:
        run_dir = pathlib.Path(name)
        values = stored_values(run_dir)
        rows = answers(run_dir)
        counts: dict[str, int] = {}
        for _, _, verdict, _ in rows:
            counts[verdict] = counts.get(verdict, 0) + 1
        other = [(s, f, v, b) for s, f, v, b in rows if v == "WRONG" and (s, f) not in in_fixture]
        print(f"=== {run_dir.name}: {len(rows)} answers {counts} ===")
        print(f"--- WRONG outside the fixture: {len(other)} ---")
        for site_id, field, _verdict, body in other:
            print(f"\n[{site_id[:8]}] {field}: stored={values.get((site_id, field))!r}")
            for line in body:
                if line.strip() and not line.startswith(("VERDICT:", "Answer", "1.")):
                    print(f"    {line.strip()[:300]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
