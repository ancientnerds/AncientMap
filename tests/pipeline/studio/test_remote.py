from __future__ import annotations

import subprocess

import pytest

from pipeline.studio import remote
from pipeline.studio.errors import StudioError


def test_module_command_quotes_every_argument_for_the_remote_shell():
    cmd = remote.module_command("pipeline.lyra.theo_dossier", ["export", "a b;rm -rf /"])
    assert cmd[:2] == ["ssh", "-o"]
    assert cmd[-2] == "ancientnerds"
    assert cmd[-1] == (
        "docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier export "
        "'a b;rm -rf /'"
    )


def test_only_allowlisted_modules_run():
    with pytest.raises(StudioError, match="not allowed over ssh"):
        remote.module_command("os", ["system"])


def test_a_timeout_is_an_unknown_outcome_not_a_failure(monkeypatch):
    def fake_run(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=5)

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    with pytest.raises(remote.RemoteOutcomeUnknown, match="UNKNOWN"):
        remote.run_module("pipeline.lyra.theo_publish", ["--apply"], stdin=b"{}", timeout=5)


def test_run_module_returns_non_zero_results_to_the_caller(monkeypatch):
    seen = {}

    def fake_run(cmd, input, capture_output, timeout):
        seen["input"] = input
        return subprocess.CompletedProcess(cmd, 1, b'{"ok": false}', b"gate failed")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    result = remote.run_module("pipeline.lyra.theo_publish", ["--dry-run"], stdin=b"x", timeout=9)
    assert result == remote.RemoteResult(1, b'{"ok": false}', "gate failed")
    assert seen["input"] == b"x"


def test_check_module_raises_on_non_zero(monkeypatch):
    monkeypatch.setattr(
        remote.subprocess,
        "run",
        lambda cmd, **_k: subprocess.CompletedProcess(cmd, 2, b"", b"no such request"),
    )
    with pytest.raises(remote.RemoteError, match="exited 2: no such request"):
        remote.check_module("pipeline.lyra.theo_dossier", ["list"], timeout=9)


def test_parse_sha256sum_keys_by_basename():
    out = "ab12  /var/www/x/p1.jpg\ncd34  /var/www/x/p2.jpg\n"
    assert remote.parse_sha256sum(out) == {"p1.jpg": "ab12", "p2.jpg": "cd34"}


def test_upload_verifies_every_file(monkeypatch, tmp_path):
    f = tmp_path / "s1a2b3c4_stone.jpg"
    f.write_bytes(b"jpeg")
    calls = []

    def fake_run(cmd, **_k):
        calls.append(cmd)
        if cmd[0] == "ssh" and "sha256sum" in cmd[-1]:
            return subprocess.CompletedProcess(cmd, 0, f"{'0' * 64}  /x/{f.name}\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    with pytest.raises(remote.RemoteError, match="does not match the local file"):
        remote.upload_research_images("95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b", [f])
    assert calls[0][-1].startswith("mkdir -p /var/www/ancientnerds/public/data/research-images/")
    assert calls[1][0] == "scp"


def test_upload_passes_when_the_hashes_match(monkeypatch, tmp_path):
    f = tmp_path / "s1a2b3c4_stone.jpg"
    f.write_bytes(b"jpeg")
    good = remote.sha256_of(f)

    def fake_run(cmd, **_k):
        if cmd[0] == "ssh" and "sha256sum" in cmd[-1]:
            return subprocess.CompletedProcess(cmd, 0, f"{good}  /x/{f.name}\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    remote.upload_research_images("95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b", [f])
