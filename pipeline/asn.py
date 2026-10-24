# SPDX-License-Identifier: AGPL-3.0-only
"""The network (AS number) behind an IPv4 address, from a local table.

The table is iptoasn.com's ``ip2asn-v4-u32.tsv.gz`` (public domain, PDDL):
one row per routed or unrouted IPv4 range, tab-separated,

    16777216	16777471	13335	US	CLOUDFLARENET

start and end as 32-bit integers, the AS number (0 for "Not routed"), the
country and the operator's name. The deploy downloads it into ./asn at most
weekly (.github/workflows/ci.yml) and docker-compose binds that read-only
into the API containers at /app/asn. No address ever leaves the server: the
lookup is a binary search in memory.

About 540,000 rows (2026-10-22), held as three ``array('L')`` columns, ~13 MB
per process; the API runs one uvicorn worker. The names are held once per AS.

IPv4 only, on purpose: nginx listens on IPv4 alone (no ``listen [::]`` in
ancientnerds-nginx-config, pinned by tests/pipeline/test_asn.py), so every
logged client address is IPv4, and an IPv6 address raises.

DATACENTER_ASNS is the vendored X4BNet list in pipeline/data/datacenter_asns.txt
(MIT; its header names the source, the fetch date and what was removed).

Stdlib only: the Lyra image ships pipeline/ without api/.
"""

from __future__ import annotations

import gzip
import ipaddress
import os
from array import array
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ASN_DB_PATH = Path(os.getenv("ASN_DB_PATH", "/app/asn/ip2asn-v4-u32.tsv.gz"))

DATACENTER_ASNS_PATH = Path(__file__).resolve().parent / "data" / "datacenter_asns.txt"

#: What lookup() answers for an address in no row of the table, and what the
#: table itself says for a range nobody announces.
NOT_ROUTED = (0, "Not routed")


def _datacenter_asns(path: Path) -> frozenset[int]:
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            out.add(int(token.removeprefix("AS")))
    return frozenset(out)


DATACENTER_ASNS = _datacenter_asns(DATACENTER_ASNS_PATH)


@dataclass(frozen=True)
class AsnTable:
    starts: array
    ends: array
    asns: array
    names: dict[int, str]
    #: The file's modification time: when iptoasn built the copy we hold
    #: (the deploy's curl -R keeps the server's Last-Modified).
    as_of: datetime

    def lookup(self, ip: str) -> tuple[int, str]:
        """(AS number, operator name) of an IPv4 address; NOT_ROUTED for an
        address in no announced range. An IPv6 address raises."""
        n = int(ipaddress.IPv4Address(ip))
        i = bisect_right(self.starts, n) - 1
        if i < 0 or n > self.ends[i] or self.asns[i] == 0:
            return NOT_ROUTED
        asn = self.asns[i]
        return asn, self.names[asn]


def parse(blob: bytes, as_of: datetime) -> AsnTable:
    """The table from the gzipped file's bytes. The rows are sorted by start."""
    starts, ends, asns = array("L"), array("L"), array("L")
    names: dict[int, str] = {}
    for line in gzip.decompress(blob).decode("utf-8").splitlines():
        start, end, asn, _country, name = line.split("\t")
        starts.append(int(start))
        ends.append(int(end))
        number = int(asn)
        asns.append(number)
        if number:
            names.setdefault(number, name)
    return AsnTable(starts, ends, asns, names, as_of)


_loaded: tuple[int, AsnTable] | None = None


def load() -> AsnTable | None:
    """The table, parsed once per file version; None when the file is not
    there (every dev box, and the VPS before the first deploy that fetches
    it)."""
    global _loaded
    try:
        mtime_ns = ASN_DB_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    if _loaded is None or _loaded[0] != mtime_ns:
        as_of = datetime.fromtimestamp(mtime_ns / 1e9, UTC)
        _loaded = (mtime_ns, parse(ASN_DB_PATH.read_bytes(), as_of))
    return _loaded[1]


def unavailable_reason() -> str:
    """Why the ASN columns are missing, in one English sentence for the panel."""
    return (
        f"The network table (iptoasn.com) is not readable at {ASN_DB_PATH}. The deploy "
        "downloads it into ./asn, bind-mounted read-only into the API containers "
        "(./asn:/app/asn:ro); a development box has none."
    )
