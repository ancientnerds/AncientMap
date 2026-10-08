# SPDX-License-Identifier: AGPL-3.0-only
"""Is the served public/data/sites/index.json the database's state? (D25, 2026-10-08)

The globe popup shows each site's `d` (the first 500 characters of the description) and `cd` (the
card text) from this file, so after a write wave the file must carry exactly what the database
carries. This compares, for every shown site (the exporter's own predicate, `not_retired("us")`),
sha256(left(description, 500)) and sha256(card_description) in the database with the same hashes
of the file's `d` and `cd`; a site the file lacks or still lists although it is retired, and an id
listed twice, count as differences too. It prints the differing count and exits 1 when it is not 0.

It runs INSIDE the API container, because the file is 362 MB and the database is only there:

    scp scripts/remediation/static_export_check.py ancientnerds:/tmp/static_export_check.py
    ssh ancientnerds "docker cp /tmp/static_export_check.py ancient_nerds_api:/tmp/x.py \\
        && docker exec ancient_nerds_api python /tmp/x.py"

(copied with docker cp, not piped over `docker exec -i`, which swallows the ssh stdin). It reads the
file as a stream, one site at a time, and asks the database for 5,000 ids at a time: the host has
about 3.6 GB free and the file is 362 MB. The only write is none: the transaction is read-only.

    python /tmp/x.py [--index public/data/sites/index.json]

Exit 0: no difference. 1: differences (listed, 20 ids per kind). 2: the file is unusable (truncated,
not the exporter's shape, or its `count` is not the number of sites).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.utils.public_sites import not_retired

DEFAULT_INDEX = Path("public/data/sites/index.json")
BATCH = 5000
CHUNK = 1 << 20
SHOWN_EXAMPLES = 20

_PREFIX = '{"sites":['


class IndexFileError(Exception):
    """The file is not a complete index.json of the exporter."""


def read_sites(fh: TextIO, chunk_size: int = CHUNK, meta: dict[str, Any] | None = None):
    """Yield the site objects of the exporter's index one at a time.

    The exporter writes `{"sites":[...],"count":N,"by_source":{...},"exported_at":"..."}` on one
    line with the array first; the rest after the array is stored in ``meta`` when it is given.
    """
    decoder = json.JSONDecoder()
    buf = fh.read(chunk_size)
    if not buf.startswith(_PREFIX):
        raise IndexFileError(f"the file does not start with {_PREFIX!r}")
    pos = len(_PREFIX)
    while True:
        if pos >= len(buf) or buf[pos] == ",":
            if pos < len(buf):
                pos += 1
                continue
            more = fh.read(chunk_size)
            if not more:
                raise IndexFileError("the file ends inside the sites array")
            buf, pos = more, 0
            continue
        if buf[pos] == "]":
            break
        try:
            site, end = decoder.raw_decode(buf, pos)
        except json.JSONDecodeError:
            more = fh.read(chunk_size)
            if not more:
                raise IndexFileError(
                    "the file ends inside a site (truncated, or not valid JSON there)"
                ) from None
            buf, pos = buf[pos:] + more, 0
            continue
        yield site
        pos = end
    rest = buf[pos + 1 :] + fh.read()
    try:
        tail = json.loads("{" + rest.lstrip(","))
    except json.JSONDecodeError:
        raise IndexFileError("the file ends inside the part after the sites array") from None
    if meta is not None:
        meta.update(tail)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class Report:
    sites: int = 0
    exported_at: str | None = None
    description: list[str] = field(default_factory=list)
    card: list[str] = field(default_factory=list)
    only_in_file: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    shown_missing_from_file: int = 0

    @property
    def differing(self) -> int:
        return (
            len(set(self.description) | set(self.card))
            + len(self.only_in_file)
            + len(self.duplicates)
            + self.shown_missing_from_file
        )


def _lookup_sql() -> Any:
    # left() counts characters and so does Python's slice: the file's `d` is description[:500].
    return text(f"""
        SELECT us.id::text AS id,
               encode(sha256(convert_to(left(COALESCE(us.description, ''), 500), 'UTF8')), 'hex') AS dh,
               encode(sha256(convert_to(COALESCE(cs.card_description, ''), 'UTF8')), 'hex') AS ch
        FROM unified_sites us
        LEFT JOIN card_stats cs ON cs.site_id = us.id
        WHERE us.id = ANY(CAST(:ids AS uuid[])) AND {not_retired("us")}
    """)


def _compare_batch(session: Any, batch: list[dict], report: Report) -> None:
    ids = [site["i"] for site in batch]
    found = {r.id: r for r in session.execute(_lookup_sql(), {"ids": ids})}
    for site in batch:
        row = found.get(site["i"])
        if row is None:
            report.only_in_file.append(site["i"])
            continue
        if sha(site.get("d", "")) != row.dh:
            report.description.append(site["i"])
        if sha(site.get("cd", "")) != row.ch:
            report.card.append(site["i"])


def check(index_fh: TextIO, session: Any, batch_size: int = BATCH) -> Report:
    """Compare the index with the database in one read-only transaction."""
    session.execute(text("SET TRANSACTION READ ONLY"))
    report = Report()
    meta: dict[str, Any] = {}
    seen: set[bytes] = set()
    batch: list[dict] = []
    for site in read_sites(index_fh, meta=meta):
        report.sites += 1
        key = bytes.fromhex(site["i"].replace("-", ""))
        if key in seen:
            report.duplicates.append(site["i"])
            continue
        seen.add(key)
        batch.append(site)
        if len(batch) == batch_size:
            _compare_batch(session, batch, report)
            batch = []
    if batch:
        _compare_batch(session, batch, report)
    if meta.get("count") != report.sites:
        raise IndexFileError(
            f"the file declares count={meta.get('count')} but lists {report.sites} sites"
        )
    report.exported_at = meta.get("exported_at")
    shown = session.execute(
        text(f"SELECT count(*) FROM unified_sites us WHERE {not_retired('us')}")
    ).scalar()
    report.shown_missing_from_file = shown - (len(seen) - len(report.only_in_file))
    return report


def _print(report: Report) -> None:
    print(f"index.json exported_at: {report.exported_at}; sites in the file: {report.sites}")
    for label, ids in (
        ("description (d) differs from the database", report.description),
        ("card text (cd) differs from the database", report.card),
        ("in the file, not shown by the database (retired or gone)", report.only_in_file),
        ("listed more than once", report.duplicates),
    ):
        if ids:
            print(f"  {label}: {len(ids)}; first: {', '.join(ids[:SHOWN_EXAMPLES])}")
    if report.shown_missing_from_file:
        print(f"  shown by the database, missing from the file: {report.shown_missing_from_file}")
    print(f"differing sites: {report.differing}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args(argv)
    try:
        with open(args.index, encoding="utf-8") as fh, get_session() as session:
            report = check(fh, session)
    except IndexFileError as exc:
        print(f"error: {args.index}: {exc}", file=sys.stderr)
        return 2
    _print(report)
    return 1 if report.differing else 0


if __name__ == "__main__":
    sys.exit(main())
