# SPDX-License-Identifier: AGPL-3.0-only
"""Give the server panel its history: sysstat's records, in the sampler's format.

Runs on the VPS host, where sysstat keeps ten-minute records of the last
month in /var/log/sysstat/saDD (verified 2026-10-09: sysstat 12.6.1 on
Ubuntu 24.04, sa01..sa09 present, ``sadf -j`` answers in UTC). It writes the
records that are older than the first line of the target file, so it can run
again without doubling anything:

    python3 scripts/server_load_backfill.py logs/server_load.jsonl

``mem_used`` follows the sampler's definition (MemTotal - MemAvailable), not
sar's %memused, with MemTotal read from this host's /proc/meminfo. sysstat
keeps no disk usage, so those lines carry none.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SYSSTAT = Path("/var/log/sysstat")


def mem_total_kb() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1])
    raise SystemExit("MemTotal missing from /proc/meminfo")


def records(path: Path, total_kb: int) -> list[dict]:
    raw = subprocess.run(
        ["sadf", "-j", str(path), "--", "-u", "-q", "-r"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    host = json.loads(raw)["sysstat"]["hosts"][0]
    out = []
    for s in host["statistics"]:
        stamp = s["timestamp"]
        if stamp["utc"] != 1:
            raise SystemExit(f"{path}: sadf answered in local time")
        cpu = next(c for c in s["cpu-load"] if c["cpu"] == "all")
        out.append(
            {
                "t": datetime.fromisoformat(f"{stamp['date']}T{stamp['time']}+00:00").isoformat(),
                "cpu": round(100 - cpu["idle"], 1),
                "load1": s["queue"]["ldavg-1"],
                "load5": s["queue"]["ldavg-5"],
                "mem_used": round(100 * (total_kb - s["memory"]["avail"]) / total_kb, 1),
                "mem_total_mb": total_kb // 1024,
                "disk_used": None,
                "disk_free_gb": None,
                "cores": host["number-of-cpus"],
            }
        )
    return out


def main() -> None:
    target = Path(sys.argv[1])
    first = None
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.startswith("{"):
                t = datetime.fromisoformat(json.loads(line)["t"])
                first = t if first is None or t < first else first
    first = first or datetime.now(UTC)
    total_kb = mem_total_kb()
    older = [
        r
        for path in sorted(SYSSTAT.glob("sa[0-9][0-9]"))
        for r in records(path, total_kb)
        if datetime.fromisoformat(r["t"]) < first
    ]
    older.sort(key=lambda r: r["t"])
    with target.open("a", encoding="utf-8") as fh:
        for r in older:
            fh.write(json.dumps(r) + "\n")
    print(f"{len(older)} records older than {first.isoformat()} appended to {target}")


if __name__ == "__main__":
    main()
