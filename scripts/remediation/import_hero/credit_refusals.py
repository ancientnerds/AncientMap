"""The sites an INSERT wave refused for a credit column, and the re-seed that asks them again.

Owner decision D18 (2026-10-08) with orchestrator decision X4: a manifest entry demands an author
and a licence URL only of a licence that asks for attribution, never an author page (`fetch.
credit_columns`). The INSERT waves `insert-2026-10-06-001` to `insert-2026-10-07-011` refused every
file whose `imageinfo` answer lacked `author_url` or `license_url`; this module finds those sites in
the waves' own records (`FETCH_FAILURES.jsonl`, which `run_fetch` appends a line to for every
refusal) and names them, so that one new wave can ask for them again:

    credit_refusals.py --import-root output/remediation/import_hero \\
        --candidate-run output/remediation/candidate_search/candidates-2026-10-06 --out R

writes `R/CREDIT_SITES_CANDIDATE.txt`, `R/CREDIT_SITES_IMPORT.txt` and `R/CREDIT_SITES_CLAUDE.txt`
(one site id per line) and prints the commands of the new waves. The candidate run of 2026-10-06 was
judged by MiniMax alone (owner decisions D6, D10): a site whose target no Claude model judged and no
Claude re-check confirmed (`--recheck-run`) lands in `CREDIT_SITES_CLAUDE.txt` and is not released.

The INSERT waves of 2026-10-06/07 were built from two sources, and none of them still holds its `IMPORT_CLAIMS.json`: a site the candidate search confirmed gets
its claim written again from the candidate run (`judge_run.py insert-claims --sites`), a site the
2025 import linked gets it from a regenerated import run (`run.py plan`, `insert-seed`). A refusal
for anything else (size, upscale, a name the file system refuses, a file type) is not touched: it
stays refused by name. A site that any wave fetched is not asked again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Collection, Sequence
from pathlib import Path

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from candidate_search import judge as CJ  # noqa: E402

from import_hero.plan import NULLABLE_FETCH_COLUMNS, ImportHeroError  # noqa: E402

FAILURES = "FETCH_FAILURES.jsonl"
FETCHED = "FETCHED.json"
TARGETS = "TARGETS.jsonl"
#: `... names no author_url, license_url: the imageinfo answer ...` (the first wording) and
#: `... names no author, which the licence 'X' demands ...` (the current one).
_NAMES_NO = re.compile(r"names no ([a-z_]+(?:, [a-z_]+)*)(?:,? which|:)")


class CreditRefusalError(ImportHeroError):
    """A wave directory or a candidate run that does not hold what the re-seed reads."""


def named_columns(why: str) -> tuple[str, ...] | None:
    """The columns a refusal text says the manifest entry lacks, or None for another refusal."""
    found = _NAMES_NO.search(why)
    return tuple(found.group(1).split(", ")) if found else None


def is_credit_refusal(why: str) -> bool:
    """A refusal that names only credit columns, so the D18 rule may release it."""
    columns = named_columns(why)
    return columns is not None and set(columns) <= set(NULLABLE_FETCH_COLUMNS)


def _jsonl(path: Path) -> list[dict[str, str]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def credit_refusals(import_root: Path) -> list[str]:
    """The site ids whose latest refusal, over the `insert-*` waves in name order, is a credit one.

    A later line replaces an earlier one for the same site (a retried site is refused or fetched
    again), and a site that any wave's manifest carries is not asked again."""
    waves = sorted(p for p in import_root.glob("insert-*") if p.is_dir())
    if not waves:
        raise CreditRefusalError(f"{import_root} holds no insert-* wave")
    fetched: set[str] = set()
    latest: dict[str, str] = {}
    for wave in waves:
        manifest = wave / FETCHED
        if manifest.is_file():
            fetched.update(json.loads(manifest.read_text(encoding="utf-8")))
        failures = wave / FAILURES
        if failures.is_file():
            for row in _jsonl(failures):
                latest[str(row["site_id"])] = str(row["why"])
    return sorted(s for s, why in latest.items() if s not in fetched and is_credit_refusal(why))


def by_source(
    sites: Sequence[str], candidate_run: Path, confirmed: Collection[tuple[str, str]] = ()
) -> tuple[list[str], list[str], list[str]]:
    """`(candidate sites, import sites, sites for Claude)`.

    The candidate sites are those the candidate run holds a target for whose `depicts` verdict a
    Claude model gave, or a Claude re-check confirmed (`confirmed`). A site the run holds a target
    for whose verdict is MiniMax's and unconfirmed goes to the third list: it is not released, it is
    judged again first (owner decisions D6, D10; the candidate run of 2026-10-06 was judged by
    MiniMax alone). The rest are the waves that were seeded from the 2025 import's own links."""
    path = candidate_run / TARGETS
    if not path.is_file():
        raise CreditRefusalError(f"{path} does not exist - the candidate run holds the targets")
    targets = [row for row in _jsonl(path) if str(row["site_id"]) in set(sites)]
    verdicts_path = candidate_run / CJ.VERDICTS
    if not verdicts_path.is_file():
        raise CreditRefusalError(f"{verdicts_path} does not exist - the verdicts name the judge")
    try:
        waiting = CJ.targets_without_claude(targets, _jsonl(verdicts_path), confirmed)
    except ValueError as exc:
        raise CreditRefusalError(str(exc)) from exc
    for_claude = {site_id for site_id, _file, _model in waiting}
    targeted = {str(row["site_id"]) for row in targets}
    return (
        [s for s in sites if s in targeted and s not in for_claude],
        [s for s in sites if s not in targeted],
        [s for s in sites if s in for_claude],
    )


def commands(
    candidate_run: Path,
    new_run: Path,
    sites_file: Path | None,
    import_sites_file: Path | None,
    import_run: Path,
    recheck_runs: Sequence[Path] = (),
    claude_sites_file: Path | None = None,
) -> list[str]:
    """The operator's commands, in order: one new wave per source (`<new_run>-cand` for the
    candidate search's targets, `<new_run>-import` for the 2025 import's links). The five writer
    steps and `insert-accept` follow each, as in every INSERT wave."""
    run_py = "./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py"
    judge = "./.venv/Scripts/python.exe scripts/remediation/candidate_search/judge_run.py"
    fetch = "--root <offsite image root> --target insert --min-width 800 --min-height 300"
    lines: list[str] = []
    if claude_sites_file is not None:
        lines.append(
            f"# {claude_sites_file}: the candidate run judged these by MiniMax alone; judge them "
            "again with the Claude image roles (`image_roles/run.py pool` for these sites, then "
            "prefilter, depicts and recheck), then run this command again with "
            "--recheck-run <that run>"
        )
    if sites_file is not None:
        run = Path(f"{new_run}-cand")
        rechecks = "".join(f" --recheck-run {r}" for r in recheck_runs)
        lines += [
            f"{run_py} read --run-dir {run}",
            f"{judge} insert-claims --run-dir {candidate_run} --insert-run {run} "
            f"--sites {sites_file}{rechecks}",
            f"{run_py} fetch --run-dir {run} {fetch}",
            f"{run_py} insert-plan --run-dir {run}",
        ]
    if import_sites_file is not None:
        run = Path(f"{new_run}-import")
        lines += [
            f"{run_py} plan --run-dir {import_run}   # regenerates IMPORT_CLAIMS.json (it writes "
            "only into the run dir)",
            f"{run_py} read --run-dir {run}",
            f"{run_py} insert-seed --run-dir {run} --from-run {import_run} "
            f"--sites {import_sites_file}",
            f"{run_py} fetch --run-dir {run} {fetch}",
            f"{run_py} insert-plan --run-dir {run}",
        ]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="import_hero/credit_refusals.py", description=__doc__)
    parser.add_argument("--import-root", required=True, type=Path)
    parser.add_argument("--candidate-run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--recheck-run",
        type=Path,
        action="append",
        default=[],
        help="a run directory whose RECHECK_NN.jsonl confirms targets of the MiniMax-judged "
        "candidate run; repeatable",
    )
    parser.add_argument("--new-run", type=Path, default=Path("insert-2026-10-09"))
    parser.add_argument("--import-run", type=Path, default=Path("import-hero-2026-10-09"))
    args = parser.parse_args(argv)
    try:
        sites = credit_refusals(args.import_root)
        confirmed = {pair for run in args.recheck_run for pair in CJ.confirmed_by_recheck(run)}
        candidate_sites, import_sites, claude_sites = by_source(
            sites, args.candidate_run, confirmed
        )
    except CreditRefusalError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path | None] = {"candidate": None, "import": None, "claude": None}
    groups = (
        ("candidate", candidate_sites),
        ("import", import_sites),
        ("claude", claude_sites),
    )
    for kind, group in groups:
        if group:
            files[kind] = args.out / f"CREDIT_SITES_{kind.upper()}.txt"
            text = "".join(f"{s}\n" for s in group)
            files[kind].write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "candidate": len(candidate_sites),
        "import": len(import_sites),
        "needs_claude": len(claude_sites),
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    lines = commands(
        args.candidate_run,
        args.new_run,
        files["candidate"],
        files["import"],
        args.import_run,
        args.recheck_run,
        files["claude"],
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
