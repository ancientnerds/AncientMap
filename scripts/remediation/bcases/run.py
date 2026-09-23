"""The owner-case command line: collect, classify, research, plan - and the plan's read-only checks.

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/bcases/run.py export      # production, read-only: the curated rows
    $PY scripts/remediation/bcases/run.py collect     # Wikidata and Wikipedia (cached)
    $PY scripts/remediation/bcases/run.py classify    # offline: output/remediation/bcases/*.jsonl
    $PY scripts/remediation/bcases/run.py research    # Wikidata/Wikipedia (cached): qid_research.jsonl
    $PY scripts/remediation/bcases/run.py research --suspects   # wave 3: qid_research_suspects.jsonl
    $PY scripts/remediation/bcases/run.py plan        # offline: the coordinate plan and its SQL
    $PY scripts/remediation/bcases/run.py check       # production, read-only: the old values hold
    $PY scripts/remediation/bcases/run.py verify      # production, read-only: after an apply

The coordinates' second wave (`web_witness.py`), a third witness from the web:

    $PY scripts/remediation/bcases/run.py web-verify  # the pages (cached): coords3/WEB_WITNESSES.jsonl
    $PY scripts/remediation/bcases/run.py web-verify --from-cache   # again, from the cached pages only
    $PY scripts/remediation/bcases/run.py reweigh     # offline: coords3/VERDICTS.jsonl, COUNTS.json
    $PY scripts/remediation/bcases/run.py plan --wave 2     # coords_plan_wave2/
    $PY scripts/remediation/bcases/run.py check --wave 2    # production, read-only
    $PY scripts/remediation/bcases/run.py verify --wave 2   # production, read-only

`--data` names the directory with the census findings, the census snapshot and the T01 cache (a git
worktree points it at the main checkout's `output/remediation`), `--cache` the derived files `collect`
writes, `--out` the deliverables. Nothing here writes to production; the plan's statements are sent by
the orchestrator, after the owner's go.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import httpx

_REPO = Path(__file__).resolve().parents[3]
for _root in (str(_REPO), str(_REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from census.fetch import Fetcher  # noqa: E402
from vlm_pilot.common import write_jsonl  # noqa: E402

from bcases import classify as C  # noqa: E402
from bcases import collect as K  # noqa: E402
from bcases import coord_plan as P  # noqa: E402
from bcases import inputs  # noqa: E402
from bcases import qid_research as R  # noqa: E402
from bcases import web_witness as W  # noqa: E402


def collect(data: Path, cache: Path) -> dict[str, int]:
    """Fetch and cache every Wikidata/Wikipedia answer the classifier reads."""
    sites = inputs.load_sites(cache)
    t01 = inputs.load_findings(data, "t01")
    t02 = inputs.load_findings(data, "t02")
    census_claims, _labels = inputs.load_t01_claims(data)
    with Fetcher(root=cache / "http", workers=1) as net:
        names = K.fetch_names(net, inputs.qids_needed(sites, t01))
        inputs.write_cache(cache / inputs.NAMES_FILE, names, K.meta(items=len(names)))
        items = C.coordinate_items(sites, t01, t02)
        claims = K.fetch_claims(net, items)
        inputs.write_cache(cache / inputs.CLAIMS_FILE, claims, K.meta(items=len(claims)))
        classes = {q for r in census_claims.values() for q in r.get("instance_qids") or ()}
        classes |= {q for r in claims.values() for q in r["p31"]}
        labels = K.fetch_labels(net, classes)
        inputs.write_cache(cache / inputs.P31_FILE, labels, K.meta(items=len(labels)))
        enwiki = K.fetch_enwiki_coords(net, C.enwiki_titles(sites, claims, items))
        inputs.write_cache(cache / inputs.ENWIKI_FILE, enwiki, K.meta(titles=len(enwiki)))
    return {
        "names": len(names),
        "claims": len(claims),
        "labels": len(labels),
        "enwiki": len(enwiki),
    }


#: Where each research selection is written.
RESEARCH_FILE = "qid_research.jsonl"
SUSPECTS_FILE = "qid_research_suspects.jsonl"


def research(cache: Path, out: Path, *, suspects: bool = False) -> dict[str, int]:
    """`qid_research.jsonl`: candidates for every wrong link the first repair wave left open.

    With `suspects` (wave 3), `qid_research_suspects.jsonl`: the same research, under the same rules,
    for every kept name whose link is a generic concept or a shared item (`R.suspect_links`).
    """
    sites = inputs.load_sites(cache)
    verdicts = inputs.read_jsonl(out / "names.jsonl")
    with Fetcher(root=cache / "http", workers=1) as net:
        if suspects:
            records = [R.research_suspect(net, v, sites) for v in R.suspect_links(verdicts)]
        else:
            records = [R.research(net, v, sites[v["site_id"]]) for v in R.wrong_links(verdicts)]
    write_jsonl(out / (SUSPECTS_FILE if suspects else RESEARCH_FILE), records)
    return {
        rule: sum(1 for r in records if r["suggestion"]["rule"] == rule)
        for rule in ("A", "B", "unresolved")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bcases")
    parser.add_argument(
        "command",
        choices=(
            "export",
            "collect",
            "classify",
            "research",
            "web-verify",
            "reweigh",
            "plan",
            "check",
            "verify",
        ),
    )
    parser.add_argument("--data", default=str(inputs.DATA))
    parser.add_argument("--cache", default=str(inputs.CACHE))
    parser.add_argument("--out", default=str(inputs.OUT))
    parser.add_argument(
        "--wave",
        type=int,
        choices=sorted(P.WAVES),
        help="plan, check, verify: the coordinate plan's wave (default 1)",
    )
    parser.add_argument(
        "--suspects",
        action="store_true",
        help="research: the kept names on a suspect link (wave 3), not the wrong links (wave 2)",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="web-verify: prove the candidates again from the previous run's cached pages, "
        "asking nothing",
    )
    args = parser.parse_args(argv)
    if args.suspects and args.command != "research":
        parser.error("--suspects belongs to the research command")
    if args.from_cache and args.command != "web-verify":
        parser.error("--from-cache belongs to web-verify")
    if args.wave is not None and args.command not in ("plan", "check", "verify"):
        parser.error("--wave belongs to plan, check and verify")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    data, cache, out = Path(args.data), Path(args.cache), Path(args.out)
    if args.command == "export":
        from mechanical.plan import psql_json_reader

        count = K.export(cache, reader=psql_json_reader())
        print(f"export: {count} curated rows -> {cache / inputs.EXPORT_FILE}")
        return 0
    if args.command == "collect":
        print(json.dumps(collect(data, cache)))
        return 0
    if args.command == "classify":
        print(json.dumps(C.write_all(data, cache, out), indent=1, ensure_ascii=False))
        return 0
    if args.command == "research":
        print(json.dumps(research(cache, out, suspects=args.suspects)))
        return 0
    if args.command == "web-verify":
        inner = W.CacheOnly() if args.from_cache else httpx.HTTPTransport()
        with W.open_fetcher(cache / "web", inner) as net:
            print(json.dumps(W.web_verify(net, out, from_cache=args.from_cache), indent=1))
        return 0
    if args.command == "reweigh":
        counts = W.reweigh(cache, out, atlas=C.CC.load_countries())
        print(json.dumps(counts, indent=1, ensure_ascii=False))
        return 0
    wave = P.WAVES[1 if args.wave is None else args.wave]
    if args.command == "plan":
        rows = P.write_files(out, wave)
        which = "" if wave.number == 1 else f", wave {wave.number}"
        print(
            f"coordinate plan{which}: {len(rows) // len(P.COLUMNS)} sites, "
            f"{len(rows)} journalled changes"
        )
        return 0
    return P.run_readonly(args.command, out, wave=wave)


if __name__ == "__main__":
    sys.exit(main())
