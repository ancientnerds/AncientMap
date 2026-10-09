# SPDX-License-Identifier: AGPL-3.0-only
"""The VPS's load for the founders dashboard: is the server keeping up?

Lyra samples the host every five minutes into logs/server_load.jsonl (its
container mounts logs/ read-write; the API containers read the same file
read-only, like the referral and crawler logs). A container's /proc/stat,
/proc/loadavg and /proc/meminfo are the host's, and logs/ sits on the host's
root filesystem - the disk the images, Docker's volumes and the database
share - so one sampler sees the whole machine:

    {"t":"2026-10-10T08:05:00+00:00","cpu":3.1,"load1":0.4,"load5":0.3,
     "mem_used":31.2,"mem_total_mb":11960,"disk_used":59.1,"disk_free_gb":79.8,"cores":6}

``cpu`` is the share of all cores busy over the five minutes since the last
sample (None for the first one after a start); ``mem_used`` counts what the
kernel could not hand out without swapping (MemTotal - MemAvailable), which
is what runs out first on a host without swap. Lines older than the sampler
come from sysstat's history (scripts/server_load_backfill.py): ten-minute
samples, no disk.

Measured 2026-10-01..09 (sar): 2-4 % CPU a day, peak 37 % over ten minutes,
load peak 2.5 on six cores, 25-31 % memory, disk 59 % (114 of 193 GB). The
visitors are not the load: the API sits at 0.2 % CPU; Lyra, Theo, image
waves and deploys are.

Stdlib only: Lyra's image has no api/ tree, and the API image reads it too.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOG_PATH = Path(os.getenv("SERVER_LOAD_LOG_PATH", "/app/logs/server_load.jsonl"))
#: Seconds between two samples.
INTERVAL_S = 300
#: The tail one read parses: a line is ~170 bytes, 288 a day, so 8 MiB is a
#: good half year of samples.
MAX_TAIL_BYTES = 8 * 1024 * 1024

#: When the panel warns: amber at the first, red at the second (percent).
DISK_LIMITS = (80.0, 90.0)
MEMORY_LIMITS = (85.0, 95.0)
CPU_LIMITS = (80.0, 95.0)
#: A sampler that wrote nothing for this long is down (Lyra is not running).
SILENT_AFTER_S = 20 * 60


def _cpu_times(stat: str) -> tuple[int, int]:
    """(busy, total) jiffies from the first line of /proc/stat."""
    fields = [int(v) for v in stat.splitlines()[0].split()[1:]]
    idle = fields[3] + fields[4]  # idle + iowait
    total = sum(fields[:8])  # user..steal; guest is already inside user
    return total - idle, total


def _meminfo(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        out[key] = int(rest.split()[0])
    return out


def sample(
    previous: tuple[int, int] | None, disk: Path = LOG_PATH.parent
) -> tuple[dict[str, Any], tuple[int, int]]:
    """One line for the log and the CPU counters the next sample diffs against."""
    cpu_now = _cpu_times(Path("/proc/stat").read_text())
    cpu = None
    if previous is not None and cpu_now[1] > previous[1]:
        cpu = round(100 * (cpu_now[0] - previous[0]) / (cpu_now[1] - previous[1]), 1)
    load1, load5, _load15 = (float(v) for v in Path("/proc/loadavg").read_text().split()[:3])
    mem = _meminfo(Path("/proc/meminfo").read_text())
    # used / (used + available), the share df prints: the blocks reserved for
    # root are no space the containers can fill.
    usage = shutil.disk_usage(disk)
    line = {
        "t": datetime.now(UTC).isoformat(timespec="seconds"),
        "cpu": cpu,
        "load1": load1,
        "load5": load5,
        "mem_used": round(100 * (mem["MemTotal"] - mem["MemAvailable"]) / mem["MemTotal"], 1),
        "mem_total_mb": mem["MemTotal"] // 1024,
        "disk_used": round(100 * usage.used / (usage.used + usage.free), 1),
        "disk_free_gb": round(usage.free / 1024**3, 1),
        "cores": os.cpu_count(),
    }
    return line, cpu_now


def _run(path: Path, interval: float) -> None:
    previous = None
    while True:
        line, previous = sample(previous, path.parent)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        time.sleep(interval)


def start_sampler(path: Path = LOG_PATH, interval: float = INTERVAL_S) -> threading.Thread:
    """The background thread Lyra starts once: a sample now, then every
    `interval` seconds, for as long as the process lives."""
    thread = threading.Thread(target=_run, args=(path, interval), name="server-load", daemon=True)
    thread.start()
    logger.info("server load sampler writing to %s every %ss", path, interval)
    return thread


def parse_lines(lines: list[str]) -> list[dict[str, Any]]:
    """Every whole line; the tail starts mid-line, which is skipped."""
    out = []
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry["t"] = datetime.fromisoformat(entry["t"])
        out.append(entry)
    return sorted(out, key=lambda e: e["t"])


def read_samples() -> list[dict[str, Any]] | None:
    """The log's tail, parsed; None when there is no log (every dev box)."""
    try:
        size = LOG_PATH.stat().st_size
    except OSError:
        return None
    with LOG_PATH.open("rb") as fh:
        if size > MAX_TAIL_BYTES:
            fh.seek(size - MAX_TAIL_BYTES)
        blob = fh.read()
    return parse_lines(blob.decode("utf-8", "replace").splitlines())


def unavailable_reason() -> str:
    return (
        f"The server load log is not readable at {LOG_PATH}. Lyra writes it on the VPS "
        "(logs/ is bind-mounted into the containers); a development box has none."
    )


def _peak(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return max(known) if known else None


def _mean(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known), 1) if known else None


def level(value: float | None, limits: tuple[float, float]) -> str:
    """'ok', 'warn' or 'bad' against an amber and a red limit."""
    if value is None or value < limits[0]:
        return "ok"
    return "warn" if value < limits[1] else "bad"


def load_report(samples: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The newest sample, one point per UTC day (CPU average and peak, load,
    memory and disk peaks), the levels the warnings read, and whether the
    sampler has gone quiet."""
    by_day: defaultdict[date, list[dict[str, Any]]] = defaultdict(list)
    for s in samples:
        by_day[s["t"].astimezone(UTC).date()].append(s)
    days = [
        {
            "day": day.isoformat(),
            "cpu_avg": _mean([s["cpu"] for s in rows]),
            "cpu_peak": _peak([s["cpu"] for s in rows]),
            "load_peak": _peak([s["load5"] for s in rows]),
            "mem_peak": _peak([s["mem_used"] for s in rows]),
            "disk_used": _peak([s.get("disk_used") for s in rows]),
        }
        for day, rows in sorted(by_day.items())
    ]
    last = samples[-1] if samples else None
    with_disk = [s for s in samples if s.get("disk_used") is not None]
    disk_last = with_disk[-1] if with_disk else None
    today = days[-1] if days and days[-1]["day"] == now.date().isoformat() else None
    return {
        "now": None
        if last is None
        else {
            "t": last["t"].isoformat(),
            "cpu": last["cpu"],
            "load5": last["load5"],
            "mem_used": last["mem_used"],
            "mem_total_mb": last.get("mem_total_mb"),
            "cores": last.get("cores"),
            "disk_used": disk_last["disk_used"] if disk_last else None,
            "disk_free_gb": disk_last["disk_free_gb"] if disk_last else None,
        },
        "days": days,
        "levels": {
            "disk": level(disk_last["disk_used"] if disk_last else None, DISK_LIMITS),
            "memory": level(today["mem_peak"] if today else None, MEMORY_LIMITS),
            "cpu": level(today["cpu_peak"] if today else None, CPU_LIMITS),
        },
        "silent": last is None or (now - last["t"]).total_seconds() > SILENT_AFTER_S,
        "limits": {"disk": DISK_LIMITS, "memory": MEMORY_LIMITS, "cpu": CPU_LIMITS},
    }
