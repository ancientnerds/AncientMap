# SPDX-License-Identifier: AGPL-3.0-only
"""nginx's own logs under /app/logs, read as a rotated family.

logrotate (ops/logrotate/ancientnerds) rotates crawlers.log, referrals.log
and requests.log daily with dateext: yesterday's lines move to
``requests.log-YYYYMMDD``, which is gzipped one day later (delaycompress),
and a file older than 30 days is deleted. So a family on disk reads

    requests.log-20261020.gz  requests.log-20261021  requests.log

oldest first; the date suffix sorts chronologically. With ``dateyesterday``
the suffix is the day of the lines, the same name the one-off split of the
history from before the rule (the sudo command that installed it) gives its
files. A rotated file can still reach a little past its day: it also holds
every line written between local midnight and the moment the timer fired
(logrotate.timer has AccuracySec=1h, and a Persistent catch-up after downtime
runs later still), and the VPS runs Europe/Berlin while ``since`` is in UTC.

Stdlib only: the Lyra image ships pipeline/ without api/.
"""

from __future__ import annotations

import gzip
import re
from datetime import datetime, timedelta
from pathlib import Path

_ROTATED = re.compile(r"-(\d{8})(\.gz)?$")


def family(path: Path) -> list[Path]:
    """The rotated files of ``path`` and ``path`` itself, as far as they
    exist, oldest first. A rotated file that does not exist yet is simply not
    in the family."""
    rotated = []
    for p in path.parent.glob(f"{path.name}-*"):
        match = _ROTATED.fullmatch(p.name[len(path.name) :])
        if match:
            # A day's plain file and its .gz never coexist; if they ever did,
            # the plain one is the newer and sorts after.
            rotated.append((match.group(1), match.group(2) is None, p))
    out = [p for _day, _plain, p in sorted(rotated)]
    if path.exists():
        out.append(path)
    return out


def file_identity(p: Path) -> tuple[int, int, int]:
    """(inode, mtime_ns, size): the key of a per-file parse cache. A rotated
    file never changes again, so it is parsed once per process; only the live
    file is re-read."""
    stat = p.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def read_file(p: Path) -> list[str]:
    """One file's lines, gunzipped where it is a ``.gz``."""
    blob = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
    return blob.decode("utf-8", "replace").splitlines()


def rotated_before(p: Path, since: datetime) -> bool:
    """A rotated file whose every line is older than ``since``. Its suffix day
    bounds its lines from above only loosely (module docstring), so a file is
    skipped only when its day lies at least two days before ``since``'s; the
    caller windows each line by its time and makes the exact cut."""
    match = _ROTATED.search(p.name)
    return match is not None and match.group(1) < (since - timedelta(days=1)).strftime("%Y%m%d")
