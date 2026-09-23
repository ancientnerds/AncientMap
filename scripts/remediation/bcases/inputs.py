"""Where the owner-case classifier reads, and the one shape of every file it reads.

Two roots, because they are two kinds of thing:

* `--data` (default `output/remediation/`) holds what earlier steps produced and this package only
  reads: the T01/T02 census findings, the T01 claims cache and the phase-3 worklist. They are
  gitignored bulk that lives on the workstation, so a git worktree points `--data` at the main
  checkout's `output/remediation/`.
* `--cache` (default `output/remediation/cache/bcases/`) holds what `collect.py` fetched - the
  production export and the Wikidata and Wikipedia answers - as derived files of the form
  `{"meta": {...}, "records": {...}}`, the shape of the T01 cache's batch files.

A missing input is an error that names the file, never an empty result (CLAUDE.md: no silent fallback).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from phase3.run import read_jsonl  # noqa: E402 - the strict JSON-lines reader (no line skipped)
from vlm_pilot.common import read_jsonl_gz  # noqa: E402

DATA = REPO / "output" / "remediation"
OUT = DATA / "bcases"
CACHE = DATA / "cache" / "bcases"

#: The derived cache files `collect.py` writes and `classify.py` reads.
EXPORT_FILE = "sites.json"
NAMES_FILE = "wd_names.json"
P31_FILE = "p31_labels.json"
CLAIMS_FILE = "wd_claims.json"
ENWIKI_FILE = "enwiki_coords.json"

_QID_URL = re.compile(r"^https://www\.wikidata\.org/wiki/(Q[0-9]+)$")


class InputError(RuntimeError):
    """An input is missing or not the shape this package reads."""


def read_cache(path: Path) -> dict[str, Any]:
    """The `records` map of one derived cache file."""
    if not path.exists():
        raise InputError(f"{path} is missing - `run.py collect` writes it")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        raise InputError(f"{path} is not a derived cache file (no `records` map)")
    return records


def write_cache(path: Path, records: Mapping[str, Any], meta: Mapping[str, Any]) -> None:
    """Write a derived cache file atomically, keys sorted, so a re-collect diffs cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"meta": dict(meta), "records": dict(records)}, ensure_ascii=False, sort_keys=True
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_sites(cache: Path) -> dict[str, dict[str, Any]]:
    """The production export, `{site_id: row}`."""
    rows = read_cache(cache / EXPORT_FILE)
    if not rows:
        raise InputError(f"{cache / EXPORT_FILE} holds no rows")
    return rows


def qid_of_finding(finding: Mapping[str, Any]) -> str:
    """The Wikidata item a T01 finding compared against: its evidence names it by URL."""
    for entry in finding.get("evidence") or ():
        match = _QID_URL.match(str(entry.get("url") or ""))
        if match:
            return match.group(1)
    raise InputError(f"T01 finding for {finding.get('site_id')} names no Wikidata item")


def load_findings(data: Path, test: str) -> list[dict[str, Any]]:
    """`run_<test>/findings.jsonl`, e.g. `load_findings(data, "t01")`."""
    return read_jsonl(data / f"run_{test}" / "findings.jsonl")


def load_t01_claims(data: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str | None]]:
    """The T01 claims cache: `{qid: claims}` and the English labels of the P17 targets."""
    root = data / "cache" / "t01_wikidata_claims"
    entities: dict[str, dict[str, Any]] = {}
    labels: dict[str, str | None] = {}
    entity_files = sorted(root.glob("entities_*.json"))
    if not entity_files:
        raise InputError(f"{root} holds no entities_*.json - the T01 census collects them")
    for path in entity_files:
        entities.update(json.loads(path.read_text(encoding="utf-8"))["records"])
    for path in sorted(root.glob("labels_*.json")):
        for qid, record in json.loads(path.read_text(encoding="utf-8"))["records"].items():
            labels[qid] = record.get("label")
    return entities, labels


def load_census_links(data: Path) -> dict[str, dict[str, str]]:
    """`{site_id: {"wikidata_qid": ..., "enwiki_title": ...}}` as the census saw them (2026-09-20).

    The T01/T02 findings compared against these links, so a finding is classified against them - a
    link repaired since (the external-id repair of 2026-09-23) is reported as the record's state, not
    silently read as if the census had asked about it.
    """
    path = data / "snapshot" / "site_external_ids.jsonl.gz"
    if not path.exists():
        raise InputError(f"{path} is missing - the census snapshot (01_export_snapshot.sh)")
    links: dict[str, dict[str, str]] = {}
    for row in read_jsonl_gz(path):
        mine = links.setdefault(str(row["site_id"]), {})
        if row["kind"] in mine:
            raise InputError(f"{path}: {row['site_id']} carries two {row['kind']} rows")
        mine[str(row["kind"])] = str(row["value"])
    return links


def coords_only_sites(data: Path) -> set[str]:
    """The sites whose only census finding is `T01/coords` - the 285 of `COST.md:141`."""
    worklist = read_jsonl(data / "phase3_worklist" / "WORKLIST.jsonl")
    return {
        str(record["site_id"])
        for record in worklist
        if [f["test_id"] for f in record["findings"]] == ["T01/coords"]
    }


def qids_needed(
    sites: Mapping[str, Mapping[str, Any]], findings: Iterable[Mapping[str, Any]]
) -> set[str]:
    """Every item a site links today plus every item a T01 finding compared against."""
    wanted = {str(site["qid"]) for site in sites.values() if site.get("qid")}
    for finding in findings:
        if str(finding.get("test_id", "")).startswith("T01/"):
            wanted.add(qid_of_finding(finding))
    return wanted
