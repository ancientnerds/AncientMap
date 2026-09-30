"""The studio's only way to production: ssh + `docker exec -i ancient_nerds_api`, and scp.

Credentials never leave the VPS: every production read or write is a deployed module run
inside the API container with the payload on stdin (the backfill-images.yml pattern).

* `run_module` returns the finished process whatever its exit code; the caller decides what
  a non-zero exit means (theo_publish exits 1 on a failed gate and still prints its outcome).
* A timeout is `RemoteOutcomeUnknown`, never a plain failure: a write may have committed.
  There are no automatic retries anywhere in this module.
* Only the modules in `ALLOWED_MODULES` can be run, and every argument is shell-quoted,
  because ssh hands the command line to the remote login shell.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pipeline.studio.config import check_request_id
from pipeline.studio.errors import StudioError
from pipeline.video.shorts_ledger import sha256_file as sha256_of

SSH_HOST = "ancientnerds"
SSH_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=4",
)
API_CONTAINER = "ancient_nerds_api"
RESEARCH_IMAGES_ROOT = PurePosixPath("/var/www/ancientnerds/public/data/research-images")
ALLOWED_MODULES = frozenset(
    {
        "pipeline.lyra.theo_dossier",
        "pipeline.lyra.theo_publish",
        "pipeline.studio.ledger_cli",
    }
)


class RemoteError(StudioError):
    """The remote command ran and failed (non-zero exit where success was required)."""


class RemoteOutcomeUnknown(StudioError):
    """No answer within the timeout: whether the remote write happened is UNKNOWN."""


@dataclass(frozen=True)
class RemoteResult:
    returncode: int
    stdout: bytes
    stderr: str


def module_command(module: str, args: list[str]) -> list[str]:
    """The local argv that runs `python -m <module> <args>` in the API container."""
    if module not in ALLOWED_MODULES:
        raise StudioError(f"module {module!r} is not allowed over ssh")
    remote = " ".join(
        shlex.quote(part)
        for part in ["docker", "exec", "-i", API_CONTAINER, "python", "-m", module, *args]
    )
    return ["ssh", *SSH_OPTIONS, SSH_HOST, remote]


def run_module(
    module: str, args: list[str], *, stdin: bytes | None = None, timeout: int
) -> RemoteResult:
    """Run a deployed module in the API container; return whatever it answered."""
    cmd = module_command(module, args)
    try:
        proc = subprocess.run(
            cmd, input=stdin if stdin is not None else b"", capture_output=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise RemoteOutcomeUnknown(
            f"{module} {' '.join(args)} gave no answer within {timeout}s: whether it changed "
            "anything is UNKNOWN. Read the journal (theo_paper_publications / studio_episodes) "
            "before running it again."
        ) from exc
    return RemoteResult(proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace"))


def check_module(
    module: str, args: list[str], *, stdin: bytes | None = None, timeout: int
) -> bytes:
    """Run a deployed module that must succeed; return its stdout."""
    result = run_module(module, args, stdin=stdin, timeout=timeout)
    if result.returncode != 0:
        raise RemoteError(
            f"{module} {' '.join(args)} exited {result.returncode}: {result.stderr[-800:]}"
        )
    return result.stdout


def _upload_step(cmd: list[str], what: str, *, timeout: int) -> str:
    """One step of an image upload; a non-zero exit or a stall is a RemoteError.

    An upload is safe to repeat (every file is named after its content and verified by
    sha256 afterwards), so a stalled step says so instead of an unknown outcome."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RemoteError(
            f"{what} gave no answer within {timeout}s; the files are named after their content "
            "and verified afterwards: run the upload again"
        ) from exc
    if proc.returncode != 0:
        raise RemoteError(f"{what} exited {proc.returncode}: {proc.stderr[-800:]}")
    return proc.stdout


def _ssh(command: str, *, timeout: int) -> str:
    return _upload_step(
        ["ssh", *SSH_OPTIONS, SSH_HOST, command], f"ssh {command!r}", timeout=timeout
    )


def parse_sha256sum(output: str) -> dict[str, str]:
    """`sha256sum` lines (`<hex>  <path>`) -> {basename: hex}."""
    sums: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        digest, _, path = line.partition("  ")
        sums[PurePosixPath(path.strip()).name] = digest.strip()
    return sums


def upload_research_images(request_id: str, files: list[Path], *, timeout: int = 900) -> None:
    """Copy `files` into research-images/<request_id>/ on the VPS and verify every byte.

    The studio names every selected image after its content hash, so a changed image always
    arrives under a new name and nginx's one-hour cache never serves a stale picture.
    The request id is checked first: it names the remote directory (a uuid holds nothing a
    remote shell or scp would read as a path or an operator).
    """
    remote_dir = RESEARCH_IMAGES_ROOT / check_request_id(request_id)
    if not files:
        raise StudioError("no images to upload")
    _ssh(f"mkdir -p {shlex.quote(str(remote_dir))}", timeout=60)
    _upload_step(
        ["scp", "-q", *SSH_OPTIONS, *[str(p) for p in files], f"{SSH_HOST}:{remote_dir}/"],
        f"scp to {remote_dir}",
        timeout=timeout,
    )
    listed = " ".join(shlex.quote(str(remote_dir / p.name)) for p in files)
    remote = parse_sha256sum(_ssh(f"sha256sum {listed}", timeout=120))
    for p in files:
        if remote.get(p.name) != sha256_of(p):
            raise RemoteError(f"{p.name}: the VPS copy does not match the local file")
