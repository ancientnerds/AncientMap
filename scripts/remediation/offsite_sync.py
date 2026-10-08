"""D24: the workstation <-> VPS cross-copy, as a routine (owner decision 2026-10-08; A4/A5 dropped).

Run on the workstation (Windows Task Scheduler, weekly, Sunday about 06:00 UTC, after the VPS's
04:15 drill; runbook: `docs/procedures/PROJECT_LESSONS.md`, "Backups: the cross-copy"). Two directions:

* **VPS -> workstation.** The newest `database_*.dump` under `/var/www/ancientnerds/backups/<dir>/`
  is copied to `<offsite>/db/`. sha256 is taken on the VPS (`sha256sum` over ssh) and on the
  workstation (hashlib) and must be equal; a `SHA256SUMS` file is written on both sides. The newest
  2 dumps stay locally (each about 0.9 GB).
* **Workstation -> VPS.** `output/remediation` of the main checkout is packed (no `*.env`, no
  `handoff/`, `pages/`, `cache/`), pushed to `/var/www/ancientnerds/backups/remediation-evidence/`
  and verified the same way. The newest 2 tars stay locally, the newest 4 on the VPS.

A copy lands under its final name only after its sha256 matched. A mismatch, a failed ssh/scp or a
missing dump stops the run with one line (exit 2); nothing is retried or substituted. The VPS cron
has no `MAILTO`, so this routine is the alarm for a failed nightly backup: when the newest dump is
older than 26 h the run still copies, then prints one loud `OFFSITE-SYNC STALE` line and exits 1.

`--check-only` lists the newest dump and judges its age, copying nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import shlex
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

SSH_HOST = "ancientnerds"
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15"]
REMOTE_BACKUPS = "/var/www/ancientnerds/backups"
REMOTE_EVIDENCE = f"{REMOTE_BACKUPS}/remediation-evidence"
DEFAULT_OFFSITE = Path("C:/PythonProjects/AncientMap-Offsite")
DEFAULT_CHECKOUT = Path("C:/PythonProjects/AncientMap")
MAX_AGE_HOURS = 26
KEEP_LOCAL = 2
KEEP_REMOTE_EVIDENCE = 4
SUMS = "SHA256SUMS"
EVIDENCE_PREFIX = "remediation-evidence_"
EVIDENCE_SUFFIX = ".tar.gz"
#: Directory names (at any depth) that are caches or hand-off scratch, not evidence.
EXCLUDED_DIRS = frozenset({"handoff", "pages", "cache"})
#: A dump of 0.9 GB over the office line; the scp is the only step that needs this long.
COPY_TIMEOUT_S = 3600
SSH_TIMEOUT_S = 600


class OffsiteError(RuntimeError):
    """A step failed; the message is the one line the run prints."""


@dataclass(frozen=True)
class Dump:
    path: str
    mtime: int
    size: int

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[1]

    @property
    def directory(self) -> str:
        return self.path.rsplit("/", 1)[0]


# ---- pure parts ------------------------------------------------------------------------------


def remote_listing_command(remote_backups: str) -> str:
    """The VPS clock, then `mtime size path` of every dump under the backup root."""
    return f"date +%s; stat -c '%Y %s %n' {shlex.quote(remote_backups)}/*/database_*.dump"


def parse_dump_listing(text: str) -> tuple[int, list[Dump]]:
    lines = text.splitlines()
    now = int(lines[0])
    dumps = []
    for line in lines[1:]:
        parts = line.split(" ", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            raise OffsiteError(f"unreadable listing line: {line!r}")
        dumps.append(Dump(path=parts[2], mtime=int(parts[0]), size=int(parts[1])))
    if not dumps:
        raise OffsiteError("no database_*.dump on the VPS under the backup root")
    return now, dumps


def newest_dump(dumps: list[Dump]) -> Dump:
    return max(dumps, key=lambda d: d.mtime)


def is_stale(*, now: int, mtime: int, max_age_hours: float) -> bool:
    return now - mtime > max_age_hours * 3600


def stale_message(name: str, *, age_hours: float, max_age_hours: float) -> str:
    return (
        f"OFFSITE-SYNC STALE: newest dump {name} is {age_hours:.1f} h old "
        f"(limit {max_age_hours:g} h) - the nightly backup on the VPS did not run"
    )


def names_to_prune(names: list[str], *, keep: int) -> list[str]:
    """All but the newest `keep` names; the names carry their date, so name order is age order."""
    return sorted(names)[:-keep] if keep else sorted(names)


def format_sums(sums: dict[str, str]) -> str:
    return "".join(f"{digest}  {name}\n" for name, digest in sums.items())


def parse_sums(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        digest, sep, name = line.partition(" ")
        name = name.removeprefix(" ").removeprefix("*")
        if not sep or len(digest) != 64 or not name or set(digest) - set("0123456789abcdef"):
            raise OffsiteError(f"unreadable {SUMS} line: {line!r}")
        out[name] = digest
    return out


def require_same_hash(name: str, local: str, remote: str) -> None:
    if local != remote:
        raise OffsiteError(f"sha256 differs for {name}: workstation {local}, VPS {remote}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def evidence_excluded(rel: str) -> bool:
    """`rel` is a posix path below `output/remediation`."""
    parts = rel.split("/") if rel else []
    return rel.endswith(".env") or any(p in EXCLUDED_DIRS for p in parts)


def evidence_name(date: str) -> str:
    return f"{EVIDENCE_PREFIX}{date}{EVIDENCE_SUFFIX}"


def build_evidence_tar(source: Path, out: Path) -> None:
    """Pack `source` (output/remediation) as `remediation/...`, without the excluded paths."""
    if not source.is_dir():
        raise OffsiteError(f"evidence source is not a directory: {source}")

    def keep(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        rel = info.name.removeprefix("remediation").removeprefix("/")
        return None if evidence_excluded(rel) else info

    with tarfile.open(out, "w:gz") as tar:
        tar.add(source, arcname="remediation", filter=keep)


# ---- transport -------------------------------------------------------------------------------


def _run(argv: list[str], timeout: int) -> str:
    proc = subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False
    )
    if proc.returncode != 0:
        raise OffsiteError(f"{argv[0]} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def ssh(host: str, command: str, timeout: int = SSH_TIMEOUT_S) -> str:
    return _run(["ssh", *SSH_OPTIONS, host, command], timeout)


def scp_from(host: str, remote: str, local: Path) -> None:
    _run(["scp", "-q", "-p", *SSH_OPTIONS, f"{host}:{remote}", str(local)], COPY_TIMEOUT_S)


def scp_to(host: str, local: Path, remote: str) -> None:
    _run(["scp", "-q", *SSH_OPTIONS, str(local), f"{host}:{remote}"], COPY_TIMEOUT_S)


def remote_sha256(host: str, directory: str, name: str) -> str:
    out = ssh(host, f"cd {shlex.quote(directory)} && sha256sum {shlex.quote(name)}", COPY_TIMEOUT_S)
    return parse_sums(out)[name]


def write_local_sums(directory: Path, pattern: str) -> dict[str, str]:
    sums = {p.name: sha256_file(p) for p in sorted(directory.glob(pattern))}
    (directory / SUMS).write_text(format_sums(sums), encoding="utf-8", newline="\n")
    return sums


# ---- the two directions ----------------------------------------------------------------------


def sync_dump(host: str, dump: Dump, offsite_db: Path, keep: int) -> None:
    offsite_db.mkdir(parents=True, exist_ok=True)
    remote_hash = remote_sha256(host, dump.directory, dump.name)
    final = offsite_db / dump.name
    if final.exists():
        require_same_hash(dump.name, sha256_file(final), remote_hash)
        print(f"dump {dump.name}: already on the workstation, sha256 {remote_hash}")
    else:
        part = offsite_db / (dump.name + ".part")
        scp_from(host, dump.path, part)
        local_hash = sha256_file(part)
        if local_hash != remote_hash:
            part.unlink()
        require_same_hash(dump.name, local_hash, remote_hash)
        os.replace(part, final)
        print(f"dump {dump.name}: copied, sha256 {remote_hash} on both sides")
    for name in names_to_prune([p.name for p in offsite_db.glob("database_*.dump")], keep=keep):
        (offsite_db / name).unlink()
        print(f"dump {name}: removed locally (keep newest {keep})")
    write_local_sums(offsite_db, "database_*.dump")
    ssh(
        host,
        f"cd {shlex.quote(dump.directory)} && sha256sum {shlex.quote(dump.name)} > {SUMS}",
    )


def sync_evidence(
    host: str, source: Path, offsite_evidence: Path, remote_dir: str, date: str, keep: int
) -> None:
    offsite_evidence.mkdir(parents=True, exist_ok=True)
    name = evidence_name(date)
    final = offsite_evidence / name
    part = offsite_evidence / (name + ".part")
    build_evidence_tar(source, part)
    local_hash = sha256_file(part)
    os.replace(part, final)
    remote_part = f"{remote_dir}/{name}.part"
    scp_to(host, final, remote_part)
    require_same_hash(name, local_hash, remote_sha256(host, remote_dir, name + ".part"))
    ssh(host, f"mv {shlex.quote(remote_part)} {shlex.quote(remote_dir + '/' + name)}")
    listing = ssh(
        host,
        f"cd {shlex.quote(remote_dir)} && ls -1 {EVIDENCE_PREFIX}*{EVIDENCE_SUFFIX}",
    ).split()
    for old in names_to_prune(listing, keep=KEEP_REMOTE_EVIDENCE):
        ssh(host, f"rm {shlex.quote(remote_dir + '/' + old)}")
        print(f"evidence {old}: removed on the VPS (keep newest {KEEP_REMOTE_EVIDENCE})")
    sums_text = ssh(
        host,
        f"cd {shlex.quote(remote_dir)} && sha256sum {EVIDENCE_PREFIX}*{EVIDENCE_SUFFIX}"
        f" > {SUMS} && cat {SUMS}",
        COPY_TIMEOUT_S,
    )
    require_same_hash(name, local_hash, parse_sums(sums_text)[name])
    for old in names_to_prune(
        [p.name for p in offsite_evidence.glob(f"{EVIDENCE_PREFIX}*{EVIDENCE_SUFFIX}")], keep=keep
    ):
        (offsite_evidence / old).unlink()
        print(f"evidence {old}: removed locally (keep newest {keep})")
    write_local_sums(offsite_evidence, f"{EVIDENCE_PREFIX}*{EVIDENCE_SUFFIX}")
    print(f"evidence {name}: pushed, sha256 {local_hash} on both sides")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default=SSH_HOST)
    ap.add_argument("--remote-backups", default=REMOTE_BACKUPS)
    ap.add_argument("--remote-evidence", default=REMOTE_EVIDENCE)
    ap.add_argument("--offsite", type=Path, default=DEFAULT_OFFSITE)
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    ap.add_argument("--max-age-hours", type=float, default=MAX_AGE_HOURS)
    ap.add_argument("--keep", type=int, default=KEEP_LOCAL)
    ap.add_argument("--check-only", action="store_true", help="judge the newest dump's age only")
    args = ap.parse_args(argv)
    try:
        now, dumps = parse_dump_listing(ssh(args.host, remote_listing_command(args.remote_backups)))
        dump = newest_dump(dumps)
        age_hours = (now - dump.mtime) / 3600
        stale = is_stale(now=now, mtime=dump.mtime, max_age_hours=args.max_age_hours)
        print(f"newest dump {dump.path} ({dump.size} bytes, {age_hours:.1f} h old)")
        if not args.check_only:
            sync_dump(args.host, dump, args.offsite / "db", args.keep)
            date = dt.datetime.fromtimestamp(now, dt.UTC).strftime("%Y-%m-%d")
            sync_evidence(
                args.host,
                args.checkout / "output" / "remediation",
                args.offsite / "evidence",
                args.remote_evidence,
                date,
                args.keep,
            )
    except (OffsiteError, subprocess.TimeoutExpired) as exc:
        print(f"OFFSITE-SYNC FAILED: {exc}", file=sys.stderr)
        return 2
    if stale:
        print(
            stale_message(dump.name, age_hours=age_hours, max_age_hours=args.max_age_hours),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
