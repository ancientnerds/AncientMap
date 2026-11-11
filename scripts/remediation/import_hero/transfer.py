"""The files of an INSERT wave on the VPS before its rows, and the offsite copy's stray fetches.

`fetch` writes a wave's files into the offsite copy of the image tree; production serves the VPS
copy. A row that names a missing file shows a broken picture at once, while a file without a row is
shown nowhere - so the files go first. Until 2026-11-11 that step was typed by hand (October's
waves left only `FETCHED_PACKED.json` of a lost scratch script). Three steps live here, each a
command of `run.py`:

* `transfer` - the files of the planned rows (`chunk-0*/INSERT.jsonl`), sha256 on both ends.
  The offsite file must exist at its exact-case name and at the byte count its row will hold. The
  API container is asked what production holds of these names: a file with other bytes refuses the
  wave and is never overwritten, a file with the same bytes arrived on an earlier call and is not
  sent twice. The rest is packed, sent to `/tmp` on the VPS, its sha256 compared there, and only
  then unpacked into the tree with `tar -k`, which refuses an existing file. At the end every file
  of the wave is hashed inside the API container - the tree as production serves it - and compared
  with the offsite file. So a call that stopped anywhere is simply run again.
  `--rehearse` sends the whole wave the same way into a scratch directory under `/tmp` on the VPS,
  compares the hashes there and removes it: nothing lands in the tree.
* `served` - after the rows are written: every file of `TRANSFER.json` over HTTPS, 200,
  `image/webp`, and the bytes the transfer recorded.
* `offsite-merge` - the 2026-10 waves fetched with `--root` at the offsite root, so their files lie
  in `<offsite>/<id8>/` and not in `<offsite>/images/wiki/<id8>/`, where the lanes read them. A
  stray file whose bytes are the ones production serves is copied into the tree (and replaces a
  stale file of that name there); everything else is named and left where it is.

Nothing here writes to the database, and nothing here deletes a file on the VPS or in the offsite
copy: a transfer has no rollback of its own. `TRANSFER.json` says which files a call created, a
chunk that is abandoned afterwards leaves them on the VPS, unshown.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

_PILOT = Path(__file__).resolve().parents[1] / "vlm_pilot"
if str(_PILOT) not in sys.path:
    sys.path.insert(0, str(_PILOT))

import common as pilot  # noqa: E402  (the exact-case listing of an image tree, the shard rule)
import offsite_sync as O  # noqa: E402  (ssh, scp and sha256 between the workstation and the VPS)
from served_image import state as ST  # noqa: E402

from import_hero import insert as IN  # noqa: E402
from import_hero.fetch import ILLEGAL_IN_NAME  # noqa: E402
from import_hero.plan import ImportHeroError  # noqa: E402

#: The image tree production serves: on the VPS, and as the API container sees it.
VPS_TREE = "/var/www/ancientnerds/public/data/images/wiki"
API_CONTAINER = "ancient_nerds_api"
CONTAINER_TREE = "/app/public/data/images/wiki"
#: Where the tar waits for its sha256 and where a rehearsal unpacks. Every remote path this module
#: creates and removes begins with `REMOTE_PREFIX`.
REMOTE_TMP = "/tmp"  # noqa: S108  (a path on the VPS; the names below it carry a sha256)
REMOTE_PREFIX = f"{REMOTE_TMP}/import-hero-transfer-"
SITE = "https://ancientnerds.com"

#: The tree's own modes, measured 2026-11-11: every folder is 777 (4,017 of them belong to root)
#: and all 648 files written since 2026-10-05 are 666; the ssh user and the API container's user
#: share uid 1000. `unpack_command` sets the umask these modes need.
FILE_MODE = 0o666

RECORD = "TRANSFER.json"
REHEARSAL = "TRANSFER_REHEARSAL.json"
HTTP_RECORD = "TRANSFER_HTTP.json"
TAR = "TRANSFER.tar"
MERGE_RECORD = "OFFSITE_MERGE.json"
MERGE_PLAN = "OFFSITE_MERGE_PLAN.json"

#: A site's folder in an image tree: the first eight hex characters of its id (`pilot.shard_for`).
SHARD = re.compile(r"[0-9a-f]{8}")

# what the merge decides per stray file
SAME = "same"
COPY = "copy"
REPLACE = "replace"
NOT_ON_THE_VPS = "not_on_the_vps"
TREE_IS_PRODUCTION = "tree_is_production"
NOT_PRODUCTION = "not_production"
CASE_COLLISION = "case_collision"

TRANSPORT_ERRORS = (O.OffsiteError, subprocess.TimeoutExpired)


class TransferError(ImportHeroError):
    """The files cannot be sent, or did not arrive as they left. Named, never repaired."""


def _named(problems: Sequence[str], what: str) -> str:
    more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
    return f"{len(problems)} file(s) {what}: " + "; ".join(problems[:5]) + more


# ------------------------------------------------------------------------------ the wave's files
@dataclass(frozen=True)
class WaveFile:
    """One planned row's file: where it lies in an image tree and the byte count the row will hold."""

    site_id: str
    filename: str
    size: int

    @property
    def rel(self) -> str:
        return f"{pilot.shard_for(self.site_id)}/{self.filename}"


def wave_files(inserts: Sequence[IN.Insert]) -> list[WaveFile]:
    """The file of every planned row. A name travels as one line and as one tar member, so a name
    with a path separator or a control character is refused (`fetch.local_name` writes none)."""
    files = []
    for row in inserts:
        illegal = ILLEGAL_IN_NAME.search(row.filename)
        if illegal:
            raise TransferError(
                f"{row.site_id}: the planned row's filename {row.filename!r} carries "
                f"{illegal.group()!r}, which no file of the tree may carry"
            )
        files.append(WaveFile(row.site_id, row.filename, int(row.values["file_size_bytes"])))
    return files


def refuse_held_names(state: ST.State, files: Sequence[WaveFile]) -> None:
    """A planned row must not name a file that a row of its site already names.

    `insert.plan` refuses a site that holds the same `original_url`; two Commons files can still
    share one local name (`X.jpg` and `X.png` are both `X.webp`). Then the site's folder holds that
    name for the other row's picture, and the new row would credit one picture and show another.
    """
    held = [
        f"{file.rel} (row {row['id']})"
        for file in files
        for row in state.rows.get(file.site_id, ())
        if str(row.get("filename") or "") == file.filename
    ]
    if held:
        raise TransferError(
            _named(held, "of the plan carry a name that a row of the same site already holds")
            + " - nothing was sent; the site leaves the wave through a new INSERT run"
        )


def local_hashes(root: Path, files: Sequence[WaveFile]) -> dict[str, str]:
    """sha256 of every file of the wave in the offsite tree, each at its exact-case name and at the
    byte count its planned row holds."""
    if not root.is_dir():
        raise TransferError(f"--root {root} is not a directory")
    tree = pilot.build_tree(root)
    unfit = []
    for file in files:
        hit = pilot.resolve(tree, file.site_id, file.filename)
        if hit is None:
            unfit.append(f"{file.rel} is not under {root} at that exact name")
        elif hit[1] != file.size:
            unfit.append(f"{file.rel} has {hit[1]} bytes, its planned row {file.size}")
    if unfit:
        raise TransferError(_named(unfit, "of the wave cannot be sent"))
    return {file.rel: O.sha256_file(root / file.rel) for file in files}


def build_tar(root: Path, files: Sequence[WaveFile], out: Path) -> str:
    """The files as `<id8>/<filename>` members, uncompressed (WebP does not shrink). Returns the
    tar's sha256. Owner and mode are the tree's, not this workstation's."""
    with tarfile.open(out, "w") as tar:
        for file in files:
            path = root / file.rel
            info = tar.gettarinfo(str(path), arcname=file.rel)
            info.mode = FILE_MODE
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as handle:
                tar.addfile(info, handle)
    return O.sha256_file(out)


# ------------------------------------------------------------------------------ the VPS
def hash_script(directory: str) -> str:
    """`sha256sum` of every name on stdin (one per line) that is a file below `directory`; a name
    that is no file there prints nothing. The names never enter the command line."""
    return (
        f"cd {shlex.quote(directory)} && "
        'while IFS= read -r f; do if [ -f "$f" ]; then sha256sum -- "$f"; fi; done'
    )


def container_command(container: str, directory: str) -> str:
    """The same question inside a container: the tree as the API serves it."""
    return f"docker exec -i {shlex.quote(container)} sh -c {shlex.quote(hash_script(directory))}"


def unpack_command(tree: str, remote_tar: str) -> str:
    """`-k`: an existing file is an error, never replaced. The umask leaves the tar's 666 and the
    777 of a new folder as they are (`FILE_MODE`)."""
    return f"umask 000 && tar -C {shlex.quote(tree)} -xkf {shlex.quote(remote_tar)}"


def read_hashes(text: str, asked: Sequence[str]) -> dict[str, str]:
    got = O.parse_sums(text)
    unasked = sorted(set(got) - set(asked))
    if unasked:
        raise TransferError(f"the VPS answered for a file nobody asked about: {unasked[:3]}")
    return got


class Vps:
    """ssh and scp to the VPS: the seam the tests replace with two directories."""

    def __init__(
        self,
        host: str = O.SSH_HOST,
        tree: str = VPS_TREE,
        container: str = API_CONTAINER,
        container_tree: str = CONTAINER_TREE,
    ) -> None:
        self.host = host
        self.tree = tree
        self.container = container
        self.container_tree = container_tree

    def _hashes(self, command: str, rels: Sequence[str]) -> dict[str, str]:
        names = "".join(rel + "\n" for rel in rels).encode("utf-8")
        return read_hashes(O.ssh(self.host, command, O.COPY_TIMEOUT_S, stdin=names), rels)

    def in_production(self, rels: Sequence[str]) -> dict[str, str]:
        """sha256 of those of `rels` the API container finds in the served tree. Read-only."""
        return self._hashes(container_command(self.container, self.container_tree), rels)

    def in_directory(self, directory: str, rels: Sequence[str]) -> dict[str, str]:
        return self._hashes(hash_script(directory), rels)

    def send(self, tar: Path, sha256: str) -> str:
        """The tar into `/tmp` on the VPS, its sha256 compared there. Returns the remote path."""
        remote = f"{REMOTE_PREFIX}{sha256[:16]}.tar"
        O.scp_to(self.host, tar, remote)
        name = remote.rsplit("/", 1)[1]
        O.require_same_hash(name, sha256, O.remote_sha256(self.host, REMOTE_TMP, name))
        return remote

    def unpack(self, remote_tar: str, into: str) -> None:
        O.ssh(self.host, unpack_command(into, remote_tar), O.COPY_TIMEOUT_S)

    def make_scratch(self, sha256: str) -> str:
        scratch = f"{REMOTE_PREFIX}rehearsal-{sha256[:16]}"
        O.ssh(self.host, f"mkdir {shlex.quote(scratch)}")
        return scratch

    def remove(self, path: str) -> None:
        """Only what this class put under `/tmp`: never a path of the tree."""
        if not path.startswith(REMOTE_PREFIX) or "/" in path[len(REMOTE_PREFIX) :]:
            raise TransferError(f"{path} is not a scratch path of the transfer: not removed")
        O.ssh(self.host, f"rm -rf {shlex.quote(path)}")


# ------------------------------------------------------------------------------ the transfer
def _ship(
    run: Path, root: Path, files: Sequence[WaveFile], vps: Vps, *, rehearse: bool
) -> tuple[str, dict[str, str]]:
    """Pack, send, compare the tar's sha256, unpack. Returns the tar's sha256 and, for a rehearsal,
    what the scratch directory held before it was removed."""
    tar = run / TAR
    try:
        sha256 = build_tar(root, files, tar)
        remote_tar = vps.send(tar, sha256)
    finally:
        tar.unlink(missing_ok=True)
    if not rehearse:
        vps.unpack(remote_tar, vps.tree)
        vps.remove(remote_tar)
        return sha256, {}
    scratch = vps.make_scratch(sha256)
    try:
        vps.unpack(remote_tar, scratch)
        landed = vps.in_directory(scratch, [file.rel for file in files])
    finally:
        vps.remove(scratch)
        vps.remove(remote_tar)
    return sha256, landed


def transfer(
    run: Path,
    root: Path,
    inserts: Sequence[IN.Insert],
    state: ST.State,
    vps: Vps,
    *,
    rehearse: bool = False,
) -> dict[str, Any]:
    """Send the wave's files and prove them on the far side; the record of what was done.

    Raises `TransferError` when a file cannot be sent, when production holds one of the names with
    other bytes, and when a file does not arrive with the sha256 it left with.
    """
    files = wave_files(inserts)
    refuse_held_names(state, files)
    local = local_hashes(root, files)
    rels = [file.rel for file in files]
    try:
        before = vps.in_production(rels)
        other = [
            f"{rel} (production {before[rel]}, offsite {local[rel]})"
            for rel in rels
            if rel in before and before[rel] != local[rel]
        ]
        if other:
            raise TransferError(
                _named(other, "of the wave are on the VPS with other bytes")
                + " - nothing was sent and nothing is overwritten"
            )
        to_send = list(files) if rehearse else [file for file in files if file.rel not in before]
        tar_sha256, landed = (
            _ship(run, root, to_send, vps, rehearse=rehearse) if to_send else (None, {})
        )
        after = landed if rehearse else vps.in_production(rels)
    except TRANSPORT_ERRORS as exc:
        raise TransferError(
            f"{exc} - the call stopped; a path beginning {REMOTE_PREFIX} may be left on "
            f"{vps.host}. Run the same command again: a file that arrived whole is found and not "
            "sent twice"
        ) from exc
    wrong = [
        f"{rel} ({after.get(rel) or 'not there'}, offsite {local[rel]})"
        for rel in rels
        if after.get(rel) != local[rel]
    ]
    if wrong:
        raise TransferError(_named(wrong, "did not arrive as they left"))
    sent = {file.rel for file in to_send}
    return {
        "mode": "rehearsal" if rehearse else "transfer",
        "host": vps.host,
        "tree": vps.tree,
        "verified_in": (
            f"a scratch directory under {REMOTE_TMP} on {vps.host}, removed"
            if rehearse
            else f"{vps.container}:{vps.container_tree}"
        ),
        "files": [
            {
                "site_id": file.site_id,
                "file": file.rel,
                "bytes": file.size,
                "sha256": local[file.rel],
                "sent": file.rel in sent,
            }
            for file in files
        ],
        "sent": len(sent),
        "already_in_production": len(before),
        "tar_sha256": tar_sha256,
    }


# ------------------------------------------------------------------------------ served
def served_url(rel: str) -> str:
    return f"{SITE}{pilot.URL_PREFIX}/{quote(rel)}"


def http_get(url: str) -> tuple[int, str, bytes]:
    import httpx

    try:
        response = httpx.get(url, timeout=60)
    except httpx.HTTPError as exc:
        raise TransferError(f"{url} did not answer: {exc}") from exc
    return response.status_code, response.headers.get("content-type", ""), response.content


def served(
    record: Mapping[str, Any], get: Callable[[str], tuple[int, str, bytes]] = http_get
) -> dict[str, Any]:
    """Every file of a transfer's record as the site serves it: 200, `image/webp`, the same bytes."""
    if record.get("mode") != "transfer":
        raise TransferError("this record is not a transfer's: a rehearsal put no file in the tree")
    problems = []
    for entry in record["files"]:
        url = served_url(entry["file"])
        status, content_type, body = get(url)
        sha256 = hashlib.sha256(body).hexdigest()
        if status != 200 or content_type != "image/webp" or sha256 != entry["sha256"]:
            problems.append(
                {
                    "file": entry["file"],
                    "url": url,
                    "status": status,
                    "content_type": content_type,
                    "sha256": sha256,
                    "expected_sha256": entry["sha256"],
                }
            )
    return {"files": len(record["files"]), "ok": not problems, "problems": problems}


# ------------------------------------------------------------------------------ the offsite merge
def merge_outcome(stray: str, tree: str | None, production: str | None) -> str:
    """What happens to one stray file, from three sha256: the stray file's, the tree's file of that
    name (None: the tree holds none), production's (None: the VPS serves no such file).

    Only bytes production serves enter the tree: the tree is production's copy, and a file the VPS
    does not hold is a fetch whose row was never written.
    """
    if tree == stray:
        return SAME
    if production is None:
        return NOT_ON_THE_VPS
    if production == stray:
        return COPY if tree is None else REPLACE
    if production == tree:
        return TREE_IS_PRODUCTION
    return NOT_PRODUCTION


def merge_plan(stray: Path, root: Path, vps: Vps) -> list[dict[str, Any]]:
    """One row per file in a site folder directly under `stray`, with its outcome. Read-only."""
    if not stray.is_dir() or not root.is_dir():
        raise TransferError(f"{stray} and {root} must both be directories")
    if stray.resolve() == root.resolve():
        raise TransferError(f"--stray and --root are both {root}: nothing strays from itself")
    folders = {s: names for s, names in pilot.build_tree(stray).items() if SHARD.fullmatch(s)}
    tree = pilot.build_tree(root)
    rows: list[dict[str, Any]] = []
    for shard in sorted(folders):
        there = tree.get(shard, {})
        other_case = {name.casefold(): name for name in there}
        for name in sorted(folders[shard]):
            row: dict[str, Any] = {
                "file": f"{shard}/{name}",
                "bytes": folders[shard][name],
                "sha256": O.sha256_file(stray / shard / name),
                "tree_sha256": None,
            }
            if name in there:
                row["tree_sha256"] = O.sha256_file(root / shard / name)
            elif name.casefold() in other_case:
                # NTFS would write over the other spelling and keep its name
                row["outcome"] = CASE_COLLISION
                row["tree_name"] = other_case[name.casefold()]
            rows.append(row)
    ask = [
        row["file"] for row in rows if "outcome" not in row and row["tree_sha256"] != row["sha256"]
    ]
    try:
        production = vps.in_production(ask) if ask else {}
    except TRANSPORT_ERRORS as exc:
        raise TransferError(f"production could not be asked: {exc}") from exc
    for row in rows:
        if "outcome" not in row:
            row["production_sha256"] = production.get(row["file"])
            row["outcome"] = merge_outcome(
                row["sha256"], row["tree_sha256"], row["production_sha256"]
            )
    return rows


def merge_apply(stray: Path, root: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    """Copy every `copy` and `replace` row into the tree; the stray file stays where it is. The copy
    is written beside its target and swapped in only at the planned sha256."""
    done = 0
    for row in rows:
        if row["outcome"] not in (COPY, REPLACE):
            continue
        target = root / row["file"]
        target.parent.mkdir(exist_ok=True)
        part = target.with_name(target.name + ".part")
        shutil.copyfile(stray / row["file"], part)
        copied = O.sha256_file(part)
        if copied != row["sha256"]:
            part.unlink()
            raise TransferError(
                f"{row['file']}: the copy has sha256 {copied}, the plan {row['sha256']} - the "
                f"stray file changed since it was planned; {done} file(s) were merged before it"
            )
        os.replace(part, target)
        done += 1
    return done


def merge_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_outcome: dict[str, int] = {}
    for row in rows:
        by_outcome[row["outcome"]] = by_outcome.get(row["outcome"], 0) + 1
    return {
        "stray_files": len(rows),
        "stray_bytes": sum(int(row["bytes"]) for row in rows),
        "outcomes": dict(sorted(by_outcome.items())),
    }
