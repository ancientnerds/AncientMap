# SPDX-License-Identifier: AGPL-3.0-only
"""The files of an INSERT wave on their way to the VPS, and the offsite copy's stray fetches.

Offline. `FakeVps` stands for the VPS with two directories and the semantics the real commands
have (`tar -k` refuses an existing file); the real command lines are pinned as text and, where a
POSIX shell and GNU tar exist, run against a temporary directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import offsite_sync as O  # noqa: E402
from import_hero import insert as IN  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from import_hero import run as IR  # noqa: E402
from import_hero import transfer as TR  # noqa: E402
from served_image import state as ST  # noqa: E402

SITE_A = "aaaaaaaa-1111-4111-8111-111111111111"
SITE_B = "bbbbbbbb-2222-4222-8222-222222222222"
NAME_A = "Kerkouane, vue générale (2019).webp"
NAME_B = "Dun Carloway Broch - 'the' view.webp"
BYTES_A = b"RIFF\x10\x00\x00\x00WEBP the first picture"
BYTES_B = b"RIFF\x10\x00\x00\x00WEBP the second picture, longer"
REL_A = f"aaaaaaaa/{NAME_A}"
REL_B = f"bbbbbbbb/{NAME_B}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _insert(site_id: str, filename: str, size: int) -> IN.Insert:
    return IN.Insert(
        site_id=site_id,
        demoted_id=None,
        old_thumbnail=None,
        new_thumbnail=ST.local_path(site_id, filename),
        change_key=f"{IN.LANE}:{site_id}",
        reason="a confirmed target",
        evidence=[],
        values={"filename": filename, "file_size_bytes": str(size)},
    )


def _inserts() -> list[IN.Insert]:
    return [_insert(SITE_A, NAME_A, len(BYTES_A)), _insert(SITE_B, NAME_B, len(BYTES_B))]


def _state(rows: dict[str, list[dict[str, Any]]] | None = None) -> ST.State:
    return ST.State(
        read_at="2026-11-11T00:00:00Z",
        sites={SITE_A: {"id": SITE_A}, SITE_B: {"id": SITE_B}},
        rows={sid: tuple(rs) for sid, rs in (rows or {}).items()},
        retired=frozenset(),
        sha256="0" * 64,
    )


def _put(root: Path, rel: str, data: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def offsite(tmp_path: Path) -> Path:
    root = tmp_path / "offsite" / "images" / "wiki"
    _put(root, REL_A, BYTES_A)
    _put(root, REL_B, BYTES_B)
    return root


@pytest.fixture
def run(tmp_path: Path) -> Path:
    directory = tmp_path / "insert-2026-11-11-s01"
    (directory / "chunk-001").mkdir(parents=True)
    (directory / "chunk-001" / "INSERT.jsonl").write_text(
        "".join(json.dumps(row.as_json(), ensure_ascii=False) + "\n" for row in _inserts()),
        encoding="utf-8",
    )
    (directory / "READ.json").write_text(
        json.dumps(
            {
                "read_at": "2026-11-11T00:00:00Z",
                "sites": [{"id": SITE_A}, {"id": SITE_B}],
                "images": [],
                "retired": [],
            }
        ),
        encoding="utf-8",
    )
    return directory


class FakeVps(TR.Vps):
    """The VPS as two directories: the served tree and `/tmp`."""

    def __init__(self, base: Path) -> None:
        super().__init__(host="test-vps")
        self.production = base / "vps-tree"
        self.tmp = base / "vps-tmp"
        self.production.mkdir()
        self.tmp.mkdir()
        self.unpacked: list[tuple[list[str], str]] = []
        self.spoil = False

    def _local(self, path: str) -> Path:
        if path == self.tree:
            return self.production
        assert path.startswith(TR.REMOTE_PREFIX), path
        return self.tmp / path[len(TR.REMOTE_TMP) + 1 :]

    @staticmethod
    def _hashes_in(directory: Path, rels: Any) -> dict[str, str]:
        return {rel: O.sha256_file(directory / rel) for rel in rels if (directory / rel).is_file()}

    def in_production(self, rels: Any) -> dict[str, str]:
        return self._hashes_in(self.production, rels)

    def in_directory(self, directory: str, rels: Any) -> dict[str, str]:
        return self._hashes_in(self._local(directory), rels)

    def send(self, tar: Path, sha256: str) -> str:
        remote = f"{TR.REMOTE_PREFIX}{sha256[:16]}.tar"
        shutil.copyfile(tar, self._local(remote))
        return remote

    def unpack(self, remote_tar: str, into: str) -> None:
        target = self._local(into)
        with tarfile.open(self._local(remote_tar)) as tar:
            members = tar.getmembers()
            for member in members:
                path = target / member.name
                if path.exists():
                    raise O.OffsiteError(f"tar: {member.name}: Cannot open: File exists")
                path.parent.mkdir(parents=True, exist_ok=True)
                body = tar.extractfile(member).read()
                path.write_bytes(body[:-1] if self.spoil else body)
        self.unpacked.append(([m.name for m in members], into))

    def make_scratch(self, sha256: str) -> str:
        scratch = f"{TR.REMOTE_PREFIX}rehearsal-{sha256[:16]}"
        self._local(scratch).mkdir()
        return scratch

    def remove(self, path: str) -> None:
        local = self._local(path)
        if local.is_dir():
            shutil.rmtree(local)
        else:
            local.unlink()


@pytest.fixture
def vps(tmp_path: Path) -> FakeVps:
    return FakeVps(tmp_path)


# ------------------------------------------------------------------------------ the wave's files
def test_the_wave_is_the_file_of_every_planned_row() -> None:
    files = TR.wave_files(_inserts())
    assert [(f.rel, f.size) for f in files] == [(REL_A, len(BYTES_A)), (REL_B, len(BYTES_B))]


@pytest.mark.parametrize("name", ["a/b.webp", "a\nb.webp", "a\\b.webp"])
def test_a_name_that_cannot_travel_as_one_line_and_one_member_is_refused(name: str) -> None:
    with pytest.raises(TR.TransferError, match="no file of the tree may carry"):
        TR.wave_files([_insert(SITE_A, name, 1)])


def test_a_name_a_row_of_the_site_already_holds_is_refused_before_anything_is_sent(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    state = _state({SITE_B: [{"id": 4711, "filename": NAME_B, "is_excluded": True}]})
    with pytest.raises(TR.TransferError, match=r"already holds: bbbbbbbb/.*\(row 4711\)"):
        TR.transfer(run, offsite, _inserts(), state, vps)
    assert vps.unpacked == []
    assert list(vps.production.iterdir()) == []


def test_a_row_of_another_site_with_the_same_name_does_not_refuse(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    state = _state({SITE_A: [{"id": 4711, "filename": NAME_B}]})
    assert TR.transfer(run, offsite, _inserts(), state, vps)["sent"] == 2


def test_a_file_the_offsite_tree_lacks_is_refused_by_name(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    (offsite / REL_B).unlink()
    with pytest.raises(TR.TransferError, match="is not under .* at that exact name"):
        TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert vps.unpacked == []


def test_a_file_in_another_case_is_not_the_rows_file(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    (offsite / REL_B).rename(offsite / "bbbbbbbb" / NAME_B.upper())
    with pytest.raises(TR.TransferError, match="at that exact name"):
        TR.transfer(run, offsite, _inserts(), _state(), vps)


def test_a_file_at_another_byte_count_than_its_row_is_refused(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    _put(offsite, REL_A, BYTES_A + b"!")
    with pytest.raises(TR.TransferError, match=f"has {len(BYTES_A) + 1} bytes, its planned row"):
        TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert vps.unpacked == []


# ------------------------------------------------------------------------------ the transfer
def test_the_transfer_lands_every_file_and_records_its_sha256(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    record = TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert (vps.production / REL_A).read_bytes() == BYTES_A
    assert (vps.production / REL_B).read_bytes() == BYTES_B
    assert record["mode"] == "transfer"
    assert record["sent"] == 2
    assert record["already_in_production"] == 0
    assert record["verified_in"] == f"{TR.API_CONTAINER}:{TR.CONTAINER_TREE}"
    assert record["files"] == [
        {
            "site_id": SITE_A,
            "file": REL_A,
            "bytes": len(BYTES_A),
            "sha256": _sha(BYTES_A),
            "sent": True,
        },
        {
            "site_id": SITE_B,
            "file": REL_B,
            "bytes": len(BYTES_B),
            "sha256": _sha(BYTES_B),
            "sent": True,
        },
    ]
    # nothing is left behind: neither the tar on the workstation nor anything under /tmp
    assert not (run / TR.TAR).exists()
    assert list(vps.tmp.iterdir()) == []


def test_a_name_production_holds_with_other_bytes_refuses_the_wave_and_is_never_overwritten(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    _put(vps.production, REL_A, b"another picture of that name")
    with pytest.raises(TR.TransferError, match="on the VPS with other bytes"):
        TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert (vps.production / REL_A).read_bytes() == b"another picture of that name"
    assert not (vps.production / REL_B).exists()
    assert vps.unpacked == []


def test_a_file_that_arrived_whole_on_an_earlier_call_is_not_sent_twice(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    _put(vps.production, REL_A, BYTES_A)
    record = TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert vps.unpacked == [([REL_B], vps.tree)]
    assert [(f["file"], f["sent"]) for f in record["files"]] == [(REL_A, False), (REL_B, True)]
    assert (record["sent"], record["already_in_production"]) == (1, 1)


def test_a_wave_that_is_wholly_there_sends_nothing_and_is_still_verified(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    _put(vps.production, REL_A, BYTES_A)
    _put(vps.production, REL_B, BYTES_B)
    record = TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert vps.unpacked == []
    assert (record["sent"], record["tar_sha256"]) == (0, None)


def test_a_file_that_does_not_arrive_as_it_left_fails_the_transfer(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    vps.spoil = True
    with pytest.raises(TR.TransferError, match="did not arrive as they left"):
        TR.transfer(run, offsite, _inserts(), _state(), vps)


def test_a_transport_failure_says_that_the_same_command_is_run_again(
    run: Path, offsite: Path, vps: FakeVps, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(remote_tar: str, into: str) -> None:
        raise O.OffsiteError("ssh exited 255: Connection reset")

    monkeypatch.setattr(vps, "unpack", broken)
    with pytest.raises(TR.TransferError, match="Connection reset.*Run the same command again"):
        TR.transfer(run, offsite, _inserts(), _state(), vps)
    assert not (run / TR.TAR).exists()


def test_a_rehearsal_sends_the_whole_wave_into_a_scratch_directory_and_removes_it(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    _put(vps.production, REL_A, BYTES_A)
    record = TR.transfer(run, offsite, _inserts(), _state(), vps, rehearse=True)
    ((names, into),) = vps.unpacked
    assert names == [REL_A, REL_B]
    assert into.startswith(TR.REMOTE_PREFIX + "rehearsal-")
    assert record["mode"] == "rehearsal"
    assert record["sent"] == 2
    # the tree is as it was, and /tmp is empty again
    assert not (vps.production / REL_B).exists()
    assert list(vps.tmp.iterdir()) == []


def test_a_rehearsal_is_verified_in_its_scratch_directory(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    vps.spoil = True
    with pytest.raises(TR.TransferError, match="did not arrive as they left"):
        TR.transfer(run, offsite, _inserts(), _state(), vps, rehearse=True)
    assert list(vps.tmp.iterdir()) == []


# ------------------------------------------------------------------------------ the command
def test_the_command_writes_the_record_once(run: Path, offsite: Path, vps: FakeVps) -> None:
    summary = IR.cmd_transfer(run, root=offsite, vps=vps)
    record = json.loads((run / TR.RECORD).read_text(encoding="utf-8"))
    assert summary["files"] == 2
    assert summary["record"] == TR.RECORD
    assert record["run_id"] == run.name
    assert [f["sha256"] for f in record["files"]] == [_sha(BYTES_A), _sha(BYTES_B)]
    with pytest.raises(IH.ImportHeroError, match="the record is written once"):
        IR.cmd_transfer(run, root=offsite, vps=vps)


def test_a_rehearsal_writes_its_own_record_and_never_the_transfers(
    run: Path, offsite: Path, vps: FakeVps
) -> None:
    IR.cmd_transfer(run, root=offsite, rehearse=True, vps=vps)
    IR.cmd_transfer(run, root=offsite, rehearse=True, vps=vps)
    assert (run / TR.REHEARSAL).is_file()
    assert not (run / TR.RECORD).exists()


def test_a_failed_transfer_writes_no_record(run: Path, offsite: Path, vps: FakeVps) -> None:
    vps.spoil = True
    with pytest.raises(TR.TransferError):
        IR.cmd_transfer(run, root=offsite, vps=vps)
    assert not (run / TR.RECORD).exists()


def test_a_fetch_into_the_offsite_root_is_refused(tmp_path: Path) -> None:
    offsite_root = tmp_path / "offsite"
    (offsite_root / "images" / "wiki").mkdir(parents=True)
    with pytest.raises(IH.ImportHeroError, match="is the offsite root, not its image tree"):
        IR.cmd_fetch(tmp_path / "no-such-run", root=offsite_root, target="insert")
    assert sorted(p.name for p in offsite_root.iterdir()) == ["images"]


# ------------------------------------------------------------------------------ the real transport
class Calls:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, answers: dict[str, str]) -> None:
        self.ssh: list[tuple[str, bytes | None]] = []
        self.scp: list[tuple[str, str]] = []
        self.answers = answers
        monkeypatch.setattr(O, "ssh", self._ssh)
        monkeypatch.setattr(O, "scp_to", self._scp)

    def _ssh(self, host: str, command: str, timeout: int = 0, stdin: bytes | None = None) -> str:
        self.ssh.append((command, stdin))
        return next((out for key, out in self.answers.items() if key in command), "")

    def _scp(self, host: str, local: Path, remote: str) -> None:
        self.scp.append((str(local), remote))


def test_production_is_asked_inside_the_api_container_with_the_names_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = Calls(monkeypatch, {"docker exec": f"{_sha(BYTES_A)}  {REL_A}\n"})
    assert TR.Vps().in_production([REL_A, REL_B]) == {REL_A: _sha(BYTES_A)}
    ((command, stdin),) = calls.ssh
    assert command.startswith("docker exec -i ancient_nerds_api sh -c ")
    assert "/app/public/data/images/wiki" in command
    assert stdin == f"{REL_A}\n{REL_B}\n".encode()
    # no name on the command line: a Commons title may carry any character
    assert "Kerkouane" not in command


def test_an_answer_for_a_file_nobody_asked_about_is_refused() -> None:
    with pytest.raises(TR.TransferError, match="nobody asked about"):
        TR.read_hashes(f"{_sha(BYTES_A)}  cccccccc/other.webp\n", [REL_A])


def test_the_tar_is_unpacked_only_after_its_sha256_matched_on_the_vps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tar = tmp_path / "wave.tar"
    tar.write_bytes(b"a tar")
    sha256 = _sha(b"a tar")
    name = f"import-hero-transfer-{sha256[:16]}.tar"
    calls = Calls(monkeypatch, {"sha256sum": f"{'f' * 64}  {name}\n"})
    with pytest.raises(O.OffsiteError, match="sha256 differs"):
        TR.Vps().send(tar, sha256)
    assert calls.scp == [(str(tar), f"{TR.REMOTE_TMP}/{name}")]
    calls.answers = {"sha256sum": f"{sha256}  {name}\n"}
    assert TR.Vps().send(tar, sha256) == f"{TR.REMOTE_TMP}/{name}"


@pytest.mark.parametrize(
    "path",
    [
        TR.VPS_TREE,
        TR.REMOTE_TMP,
        TR.REMOTE_TMP + "/other",
        TR.REMOTE_PREFIX + "x/../../var/www",
        "/var/www/ancientnerds/public/data/images/wiki/aaaaaaaa",
    ],
)
def test_only_a_scratch_path_of_the_transfer_is_ever_removed(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = Calls(monkeypatch, {})
    with pytest.raises(TR.TransferError, match="not a scratch path"):
        TR.Vps().remove(path)
    assert calls.ssh == []


def test_a_scratch_path_is_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch, {})
    TR.Vps().remove(TR.REMOTE_PREFIX + "rehearsal-0123456789abcdef")
    assert calls.ssh == [("rm -rf /tmp/import-hero-transfer-rehearsal-0123456789abcdef", None)]


def test_the_unpack_never_replaces_a_file_and_keeps_the_trees_modes() -> None:
    assert TR.unpack_command(TR.VPS_TREE, "wave.tar") == (
        "umask 000 && tar -C /var/www/ancientnerds/public/data/images/wiki -xkf wave.tar"
    )
    assert TR.unpack_command("a tree", "wave's.tar") == (
        """umask 000 && tar -C 'a tree' -xkf 'wave'"'"'s.tar'"""
    )


def test_the_tar_holds_the_wave_under_its_tree_names_with_the_trees_mode(
    tmp_path: Path, offsite: Path
) -> None:
    out = tmp_path / "wave.tar"
    sha256 = TR.build_tar(offsite, TR.wave_files(_inserts()), out)
    assert sha256 == O.sha256_file(out)
    with tarfile.open(out) as tar:
        members = tar.getmembers()
        assert [m.name for m in members] == [REL_A, REL_B]
        assert {m.mode for m in members} == {0o666}
        assert {(m.uid, m.gid, m.uname, m.gname) for m in members} == {(0, 0, "", "")}
        assert tar.extractfile(members[0]).read() == BYTES_A


SH = shutil.which("sh")


def _sh(script: str, cwd: Path, stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [SH, "-c", script], cwd=cwd, input=stdin, capture_output=True, check=False
    )


def _gnu_tar(cwd: Path) -> bool:
    return SH is not None and b"GNU tar" in _sh("tar --version", cwd).stdout


@pytest.mark.skipif(SH is None, reason="no POSIX sh on PATH: the remote hash script is not run")
def test_the_hash_script_answers_for_the_files_that_exist_and_only_those(tmp_path: Path) -> None:
    awkward = "aaaaaaaa/It's 100% $HOME & (more) [x] #1.webp"
    _put(tmp_path / "tree", REL_B, BYTES_B)
    _put(tmp_path / "tree", awkward, BYTES_A)
    asked = [REL_B, awkward, "aaaaaaaa/not there.webp", "cccccccc/no folder.webp"]
    done = _sh(TR.hash_script("tree"), tmp_path, "".join(a + "\n" for a in asked).encode())
    assert done.returncode == 0, done.stderr
    assert TR.read_hashes(done.stdout.decode("utf-8"), asked) == {
        REL_B: _sha(BYTES_B),
        awkward: _sha(BYTES_A),
    }


@pytest.mark.skipif(SH is None, reason="no POSIX sh on PATH: the remote hash script is not run")
def test_the_hash_script_fails_when_the_tree_is_not_there(tmp_path: Path) -> None:
    assert _sh(TR.hash_script("no-tree"), tmp_path, b"a\n").returncode != 0


def test_the_unpack_command_lands_new_files_and_refuses_an_existing_one(
    tmp_path: Path, offsite: Path
) -> None:
    if not _gnu_tar(tmp_path):
        pytest.skip("no GNU tar behind a POSIX sh on PATH: the unpack command is not run")
    ascii_b = "bbbbbbbb/Dun Carloway Broch - 'the' view.webp"
    files = [TR.WaveFile(SITE_B, NAME_B, len(BYTES_B))]
    TR.build_tar(offsite, files, tmp_path / "wave.tar")
    (tmp_path / "tree").mkdir()
    first = _sh(TR.unpack_command("tree", "wave.tar"), tmp_path)
    assert first.returncode == 0, first.stderr
    assert (tmp_path / "tree" / ascii_b).read_bytes() == BYTES_B
    # a second unpack over a file of that name: an error, and the file is the one that was there
    (tmp_path / "tree" / ascii_b).write_bytes(b"held")
    second = _sh(TR.unpack_command("tree", "wave.tar"), tmp_path)
    assert second.returncode != 0
    assert (tmp_path / "tree" / ascii_b).read_bytes() == b"held"


# ------------------------------------------------------------------------------ served
def _record() -> dict[str, Any]:
    return {
        "mode": "transfer",
        "files": [
            {"file": REL_A, "sha256": _sha(BYTES_A)},
            {"file": REL_B, "sha256": _sha(BYTES_B)},
        ],
    }


def _site(answers: dict[str, tuple[int, str, bytes]]) -> Any:
    return lambda url: answers[url]


URL_A = (
    "https://ancientnerds.com/data/images/wiki/aaaaaaaa/"
    "Kerkouane%2C%20vue%20g%C3%A9n%C3%A9rale%20%282019%29.webp"
)
URL_B = (
    "https://ancientnerds.com/data/images/wiki/bbbbbbbb/"
    "Dun%20Carloway%20Broch%20-%20%27the%27%20view.webp"
)


def test_every_transferred_file_is_asked_at_its_quoted_url_and_accepted_at_its_bytes() -> None:
    result = TR.served(
        _record(), _site({URL_A: (200, "image/webp", BYTES_A), URL_B: (200, "image/webp", BYTES_B)})
    )
    assert result == {"files": 2, "ok": True, "problems": []}


@pytest.mark.parametrize(
    "answer",
    [
        (404, "image/webp", BYTES_B),
        (200, "text/html", BYTES_B),
        (200, "image/webp", BYTES_B[:-1]),
    ],
)
def test_a_file_that_is_not_served_as_it_was_sent_is_a_problem(
    answer: tuple[int, str, bytes],
) -> None:
    result = TR.served(_record(), _site({URL_A: (200, "image/webp", BYTES_A), URL_B: answer}))
    assert result["ok"] is False
    assert [p["file"] for p in result["problems"]] == [REL_B]
    assert result["problems"][0]["expected_sha256"] == _sha(BYTES_B)


def test_a_rehearsals_record_is_no_proof_of_a_served_file() -> None:
    with pytest.raises(TR.TransferError, match="not a transfer's"):
        TR.served({**_record(), "mode": "rehearsal"}, _site({}))


def test_served_before_a_transfer_is_refused_by_name(run: Path) -> None:
    with pytest.raises(IH.ImportHeroError, match="only a transferred file can be asked for"):
        IR.cmd_served(run, get=_site({}))
    assert not (run / TR.HTTP_RECORD).exists()


def test_the_served_command_records_and_exits_1_on_a_problem(
    run: Path, offsite: Path, vps: FakeVps, capsys: pytest.CaptureFixture[str]
) -> None:
    IR.cmd_transfer(run, root=offsite, vps=vps)
    good = _site({URL_A: (200, "image/webp", BYTES_A), URL_B: (200, "image/webp", BYTES_B)})
    assert IR.cmd_served(run, get=good) == 0
    assert json.loads((run / TR.HTTP_RECORD).read_text(encoding="utf-8"))["ok"] is True
    bad = _site({URL_A: (200, "image/webp", BYTES_A), URL_B: (502, "text/html", b"")})
    assert IR.cmd_served(run, get=bad) == 1
    assert json.loads((run / TR.HTTP_RECORD).read_text(encoding="utf-8"))["ok"] is False
    assert "REFUSED: 1 file(s) are not served as they were sent" in capsys.readouterr().err


# ------------------------------------------------------------------------------ the offsite merge
S, T, P = "s" * 64, "t" * 64, "p" * 64


@pytest.mark.parametrize(
    ("stray", "tree", "production", "outcome"),
    [
        (S, S, None, TR.SAME),
        (S, S, P, TR.SAME),
        (S, None, None, TR.NOT_ON_THE_VPS),
        (S, T, None, TR.NOT_ON_THE_VPS),
        (S, None, S, TR.COPY),
        (S, T, S, TR.REPLACE),
        (S, T, T, TR.TREE_IS_PRODUCTION),
        (S, None, P, TR.NOT_PRODUCTION),
        (S, T, P, TR.NOT_PRODUCTION),
    ],
)
def test_only_the_bytes_production_serves_enter_the_tree(
    stray: str, tree: str | None, production: str | None, outcome: str
) -> None:
    assert TR.merge_outcome(stray, tree, production) == outcome


@pytest.fixture
def drift(tmp_path: Path, vps: FakeVps) -> tuple[Path, Path]:
    """The offsite root with stray site folders beside its tree, and production's files."""
    stray = tmp_path / "offsite"
    root = stray / "images" / "wiki"
    root.mkdir(parents=True)
    (stray / "db").mkdir()
    (stray / "db" / "database.dump").write_bytes(b"not a picture")
    # same: in the tree already
    _put(stray, "11111111/same.webp", b"same")
    _put(root, "11111111/same.webp", b"same")
    # copy: production serves the stray bytes, the tree has no such file (and no such folder)
    _put(stray, "22222222/copy.webp", b"copy")
    _put(vps.production, "22222222/copy.webp", b"copy")
    # replace: the tree holds a stale file of that name
    _put(stray, "33333333/replace.webp", b"fresh")
    _put(root, "33333333/replace.webp", b"stale")
    _put(vps.production, "33333333/replace.webp", b"fresh")
    # not on the VPS: a fetch whose row was never written
    _put(stray, "44444444/orphan.webp", b"orphan")
    # the tree is production's, the stray file is the stale one
    _put(stray, "55555555/old.webp", b"old")
    _put(root, "55555555/old.webp", b"current")
    _put(vps.production, "55555555/old.webp", b"current")
    # production serves other bytes than the stray file, and the tree has none
    _put(stray, "66666666/other.webp", b"mine")
    _put(vps.production, "66666666/other.webp", b"theirs")
    return stray, root


def _outcomes(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {row["file"]: row["outcome"] for row in rows}


def test_the_merge_plan_reads_the_site_folders_beside_the_tree_and_asks_production(
    drift: tuple[Path, Path], vps: FakeVps
) -> None:
    stray, root = drift
    rows = TR.merge_plan(stray, root, vps)
    assert _outcomes(rows) == {
        "11111111/same.webp": TR.SAME,
        "22222222/copy.webp": TR.COPY,
        "33333333/replace.webp": TR.REPLACE,
        "44444444/orphan.webp": TR.NOT_ON_THE_VPS,
        "55555555/old.webp": TR.TREE_IS_PRODUCTION,
        "66666666/other.webp": TR.NOT_PRODUCTION,
    }
    assert TR.merge_summary(rows)["stray_files"] == 6


def test_production_is_not_asked_about_a_file_the_tree_already_holds(
    drift: tuple[Path, Path], vps: FakeVps, monkeypatch: pytest.MonkeyPatch
) -> None:
    stray, root = drift
    asked: list[str] = []
    real = vps.in_production

    def spy(rels: Any) -> dict[str, str]:
        asked.extend(rels)
        return real(rels)

    monkeypatch.setattr(vps, "in_production", spy)
    TR.merge_plan(stray, root, vps)
    assert "11111111/same.webp" not in asked
    assert len(asked) == 5


def test_a_name_the_tree_holds_in_another_case_is_left_alone(
    drift: tuple[Path, Path], vps: FakeVps
) -> None:
    stray, root = drift
    _put(stray, "77777777/Huelva.webp", b"huelva")
    _put(root, "77777777/HUELVA.webp", b"huelva")
    _put(vps.production, "77777777/Huelva.webp", b"huelva")
    rows = TR.merge_plan(stray, root, vps)
    row = next(r for r in rows if r["file"] == "77777777/Huelva.webp")
    assert (row["outcome"], row["tree_name"]) == (TR.CASE_COLLISION, "HUELVA.webp")
    TR.merge_apply(stray, root, rows)
    assert sorted(p.name for p in (root / "77777777").iterdir()) == ["HUELVA.webp"]


def test_the_merge_copies_what_production_serves_and_leaves_everything_else(
    drift: tuple[Path, Path], vps: FakeVps
) -> None:
    stray, root = drift
    before = {p.relative_to(stray).as_posix(): p.read_bytes() for p in stray.rglob("*.webp")}
    assert TR.merge_apply(stray, root, TR.merge_plan(stray, root, vps)) == 2
    assert (root / "22222222/copy.webp").read_bytes() == b"copy"
    assert (root / "33333333/replace.webp").read_bytes() == b"fresh"
    assert (root / "55555555/old.webp").read_bytes() == b"current"
    assert not (root / "44444444").exists()
    assert not (root / "66666666").exists()
    assert list(root.rglob("*.part")) == []
    # the stray files stay where they are: the merge copies, the owner clears the disk
    after = {p.relative_to(stray).as_posix(): p.read_bytes() for p in stray.rglob("*.webp")}
    assert {k: v for k, v in after.items() if not k.startswith("images/")} == {
        k: v for k, v in before.items() if not k.startswith("images/")
    }
    # a second plan finds nothing left to do
    assert not {TR.COPY, TR.REPLACE} & set(_outcomes(TR.merge_plan(stray, root, vps)).values())


def test_a_stray_file_that_changed_since_the_plan_is_not_merged(
    drift: tuple[Path, Path], vps: FakeVps
) -> None:
    stray, root = drift
    rows = TR.merge_plan(stray, root, vps)
    _put(stray, "33333333/replace.webp", b"changed since")
    with pytest.raises(TR.TransferError, match="changed since it was planned"):
        TR.merge_apply(stray, root, rows)
    assert (root / "33333333/replace.webp").read_bytes() == b"stale"
    assert list(root.rglob("*.part")) == []


def test_the_tree_is_not_merged_into_itself(tmp_path: Path, vps: FakeVps) -> None:
    (tmp_path / "tree").mkdir()
    with pytest.raises(TR.TransferError, match="nothing strays from itself"):
        TR.merge_plan(tmp_path / "tree", tmp_path / "tree", vps)


def test_the_merge_command_plans_without_apply_and_records_an_apply_once(
    drift: tuple[Path, Path], vps: FakeVps, tmp_path: Path
) -> None:
    stray, root = drift
    record_dir = tmp_path / "offsite-merge"
    planned = IR.cmd_offsite_merge(record_dir, stray=stray, root=root, vps=vps)
    assert (planned["applied"], planned["merged"]) == (False, 0)
    assert planned["outcomes"][TR.COPY] == 1
    assert not (root / "22222222").exists()
    assert (record_dir / TR.MERGE_PLAN).is_file()
    assert not (record_dir / TR.MERGE_RECORD).exists()
    applied = IR.cmd_offsite_merge(record_dir, stray=stray, root=root, apply=True, vps=vps)
    assert (applied["applied"], applied["merged"]) == (True, 2)
    record = json.loads((record_dir / TR.MERGE_RECORD).read_text(encoding="utf-8"))
    assert _outcomes(record["files"])["33333333/replace.webp"] == TR.REPLACE
    with pytest.raises(IH.ImportHeroError, match="written once"):
        IR.cmd_offsite_merge(record_dir, stray=stray, root=root, apply=True, vps=vps)


# ------------------------------------------------------------------------------ offsite_sync
def test_stdin_reaches_the_far_side_byte_for_byte() -> None:
    echo = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
    names = f"{REL_A}\n{REL_B}\n"
    assert O._run([sys.executable, "-c", echo], 30, names.encode("utf-8")) == names


def test_a_failed_command_is_one_line_with_its_stderr() -> None:
    fail = "import sys; sys.stderr.write('no route'); sys.exit(3)"
    with pytest.raises(O.OffsiteError, match="exited 3: no route"):
        O._run([sys.executable, "-c", fail], 30)
