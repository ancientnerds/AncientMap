"""Read-only access to the production snapshot.

The census never touches the database. It reads the JSONL export produced by
`scripts/remediation/01_export_snapshot.sh`, which makes a run reproducible, comparable
between runs, and safe to repeat - and it is the reason a test can be a pure function
instead of a query with side effects.

Trust boundary: the snapshot is only trustworthy if it is the snapshot the MANIFEST
describes. `Snapshot.verify()` re-checks line counts and sha256 against the manifest, so
a half-written export or a snapshot from an older run cannot be consumed silently.
`run.py` always verifies before the first test starts.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path("output/remediation/snapshot")

#: table -> primary key used to group child rows
TABLES = (
    "unified_sites",
    "card_stats",
    "wiki_images",
    "site_content_links",
    "site_external_ids",
    "unified_site_names",
)

CHILD_KEY = {
    "card_stats": "site_id",
    "wiki_images": "site_id",
    "site_content_links": "site_id",
    "site_external_ids": "site_id",
    "unified_site_names": "site_id",
    "unified_sites": "id",
}


class SnapshotError(RuntimeError):
    """The snapshot is missing, incomplete, or does not match its manifest."""


def _sha256_prefix(path: Path, n: int = 16) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:n]


class Snapshot:
    """Lazily-loaded tables, plus O(1) lookups by site id."""

    def __init__(self, directory: Path | str = DEFAULT_DIR) -> None:
        self.dir = Path(directory)
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._by_key: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._manifest: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------- raw loading
    def path(self, table: str) -> Path:
        if table not in TABLES:
            raise SnapshotError(f"unknown table {table!r}; known: {', '.join(TABLES)}")
        return self.dir / f"{table}.jsonl.gz"

    def rows(self, table: str) -> list[dict[str, Any]]:
        if table not in self._rows:
            p = self.path(table)
            if not p.exists():
                raise SnapshotError(f"snapshot table missing: {p} (run 01_export_snapshot.sh)")
            out: list[dict[str, Any]] = []
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise SnapshotError(f"{p}:{lineno}: invalid JSON ({exc})") from exc
            self._rows[table] = out
        return self._rows[table]

    def by(self, table: str, key: str | None = None) -> dict[str, list[dict[str, Any]]]:
        """Rows of `table` grouped by its key column (defaults to the table's site key)."""
        key = key or CHILD_KEY[table]
        cache_key = f"{table}.{key}"
        if cache_key not in self._by_key:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in self.rows(table):
                v = row.get(key)
                if v is not None:
                    grouped[str(v)].append(row)
            self._by_key[cache_key] = dict(grouped)
        return self._by_key[cache_key]

    def site(self, site_id: str) -> dict[str, Any] | None:
        if "unified_sites.id" not in self._by_key:
            self._by_key["unified_sites.id"] = {
                str(r["id"]): [r] for r in self.rows("unified_sites")
            }
        hit = self._by_key["unified_sites.id"].get(site_id)
        return hit[0] if hit else None

    # ------------------------------------------------------------- conveniences
    @property
    def sites(self) -> list[dict[str, Any]]:
        return self.rows("unified_sites")

    def site_ids(self) -> list[str]:
        return [str(r["id"]) for r in self.sites]

    def iter_sites(self) -> Iterator[dict[str, Any]]:
        yield from self.sites

    def ext_ids(self, site_id: str, kind: str | None = None) -> list[str]:
        """External-id values for a site, optionally filtered by `kind`."""
        out = [
            r["value"]
            for r in self.by("site_external_ids").get(site_id, [])
            if kind is None or r.get("kind") == kind
        ]
        return out

    def ids_of_kind(self, kind: str) -> dict[str, str]:
        """`kind` -> {site_id: value}; the first value wins per site."""
        return {
            str(r["site_id"]): r["value"]
            for r in self.rows("site_external_ids")
            if r.get("kind") == kind
        }

    def images(self, site_id: str) -> list[dict[str, Any]]:
        return self.by("wiki_images").get(site_id, [])

    def stats(self, site_id: str) -> dict[str, Any] | None:
        hit = self.by("card_stats").get(site_id)
        return hit[0] if hit else None

    def links(self, site_id: str) -> list[dict[str, Any]]:
        return self.by("site_content_links").get(site_id, [])

    # ------------------------------------------------------------- verification
    def read_manifest(self) -> dict[str, dict[str, Any]]:
        p = self.dir / "MANIFEST.txt"
        if not p.exists():
            raise SnapshotError(f"no MANIFEST.txt in {self.dir}")
        manifest: dict[str, dict[str, Any]] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 3 or len(parts[2]) != 16:
                continue
            # int() explicitly, not via isdigit(): isdigit() is True for characters
            # int() rejects (e.g. "\u00b2"), which would crash on a corrupted manifest.
            try:
                n_lines = int(parts[1])
            except ValueError:
                continue
            manifest[parts[0]] = {"lines": n_lines, "sha256": parts[2]}
        if not manifest:
            raise SnapshotError(f"{p}: no recognised manifest rows")
        self._manifest = manifest
        return manifest

    def verify(self, check_hashes: bool = True) -> dict[str, Any]:
        """Assert the files match MANIFEST.txt. Returns the manifest (for recording).

        Raises rather than warns: a mismatch means every number the census produces is
        about unknown data, and a census that silently describes the wrong snapshot is
        worse than one that refuses to run.
        """
        manifest = self.read_manifest()
        report: dict[str, Any] = {}
        for table, expect in manifest.items():
            p = self.path(table)
            if not p.exists():
                raise SnapshotError(f"manifest lists {table} but {p} is missing")
            # One pass: count, and parse. Counting alone is not enough - the first export
            # had exactly the right number of lines and a matching sha256 while almost
            # every row was unparseable, because COPY escaped already-valid JSON a second
            # time. A snapshot only counts as verified if its rows actually decode.
            n = 0
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    n += 1
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise SnapshotError(
                            f"{table}:{lineno}: unparseable JSON ({exc}) - "
                            "re-export with 01_export_snapshot.sh (do not use COPY TO STDOUT)"
                        ) from exc
            if n != expect["lines"]:
                raise SnapshotError(
                    f"{table}: {n} lines but MANIFEST says {expect['lines']} - stale or truncated"
                )
            got: dict[str, Any] = {"lines": n}
            if check_hashes:
                digest = _sha256_prefix(p)
                if digest != expect["sha256"]:
                    raise SnapshotError(
                        f"{table}: sha256 {digest} but MANIFEST says {expect['sha256']}"
                    )
                got["sha256"] = digest
            report[table] = got
        self._manifest = manifest
        return report

    @property
    def manifest(self) -> dict[str, dict[str, Any]]:
        return self._manifest or self.read_manifest()

    def exported_at(self) -> str | None:
        """The export timestamp from the manifest header, for the audit record."""
        p = self.dir / "MANIFEST.txt"
        if not p.exists():
            return None
        first = p.read_text(encoding="utf-8").splitlines()[0]
        return first.replace("snapshot exported", "").split("host=")[0].strip()

    def counts(self) -> dict[str, int]:
        return {t: len(self.rows(t)) for t in TABLES}


def iter_batched(items: Iterable[Any], n: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch
