"""What every remediation lane that writes to production shares: one transport, one pin.

* **The transport.** ssh to the VPS, then psql inside the database container - the way this project
  reaches production (no local database exists). `-i` on `docker exec` is load-bearing: without it
  psql receives empty stdin and silently does nothing. No `-F`: ssh hands the command to a remote
  login shell, which reads a bare `|` as a pipe. `ConnectTimeout` and the keepalives end a dead
  channel instead of letting it sit for the whole timeout.
* **A timeout says what it means.** psql may be halfway through a transaction whose COMMIT never
  reached us, so `subprocess.TimeoutExpired` becomes `OutcomeUnknown`, never a plain failure: a
  caller cannot read it as "nothing happened" and retry blindly. What *did* happen is the journal's
  to say - each lane reads its run stamp's journal rows before any retry.
* **The pin.** A generated statement carries `-- plan sha256 <64 hex>` naming the plan it was
  rendered from, so a statement on disk can be refused when it no longer belongs to its plan.

Extracted on 2026-09-22 from `gallery_audit/persist_verdicts.py`, where all three were first built,
so the mechanical lanes use the same code rather than a copy (`[H] SECURITY 3 / BACKEND B7`).
Standard library only; both lanes import it with `scripts/remediation` on `sys.path`.
"""

from __future__ import annotations

import re
import shlex
import subprocess

PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1"
PSQL_ROWS = PSQL + " -t -A"
SSH_HOST = "ancientnerds"
SSH_OPTIONS = "-o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"

#: `-- plan sha256 <64 hex>`: the digest of the plan a delivered script was rendered from.
DIGEST_RE = re.compile(r"^-- plan sha256 ([0-9a-f]{64})\b", re.MULTILINE)


class OutcomeUnknown(RuntimeError):
    """The write may or may not have landed. Never retried without reading the journal first."""


def send(
    sql: str, *, host: str = SSH_HOST, timeout: int = 900, rows: bool = False
) -> subprocess.CompletedProcess[str]:
    """Send `sql` to production and return psql's result, whatever its exit code.

    The caller decides what a non-zero exit means; a timeout is decided here, because it is the
    one outcome no exit code describes.
    """
    try:
        return subprocess.run(
            shlex.split(f"ssh {SSH_OPTIONS} {host} {PSQL_ROWS if rows else PSQL}"),
            input=sql,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OutcomeUnknown(
            f"psql did not answer within {timeout}s: whether the transaction committed is UNKNOWN. "
            "Do not retry before reading the journal."
        ) from exc


def pin_line(digest: str) -> str:
    """The header line that pins a statement to the plan it was rendered from."""
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"{digest!r} is not a sha256 hex digest")
    return f"-- plan sha256 {digest}"
