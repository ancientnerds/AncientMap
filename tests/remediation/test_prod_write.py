"""The shared production transport: a timeout is an unknown outcome, a dead channel cannot hang,
and the pin names exactly one plan digest.

`scripts/remediation/prod_write.py` is used by the gallery lane and by every mechanical lane, so
its rules are pinned here once, against the module itself. No ssh is ever run: `subprocess.run` is
replaced by fakes that record the argv or raise what the real call raises.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import prod_write as W  # noqa: E402


def test_a_timeout_is_an_unknown_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=900)

    monkeypatch.setattr(W.subprocess, "run", fake_run)
    with pytest.raises(W.OutcomeUnknown, match="whether the transaction committed is UNKNOWN"):
        W.send("SELECT 1;")


def test_a_dead_channel_cannot_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a connect timeout and keepalives a hung channel sits for the full 900 s."""
    argv: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        argv.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(W.subprocess, "run", fake_run)
    W.send("SELECT 1;", rows=True)
    joined = " ".join(argv[0])
    assert "ConnectTimeout=" in joined and "ServerAliveInterval=" in joined
    assert joined.endswith(W.PSQL_ROWS) and " ancientnerds " in joined


def test_a_non_zero_exit_is_the_caller_s_to_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed exit may follow a COMMIT (a post-commit read failed): only the journal can say."""
    monkeypatch.setattr(
        W.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 3, stdout=b"", stderr=b"ERROR"),
    )
    assert W.send("SELECT 1;").returncode == 3


def test_the_pin_names_one_sha256_digest() -> None:
    digest = "0123456789abcdef" * 4
    assert W.pin_line(digest) == f"-- plan sha256 {digest}"
    assert W.DIGEST_RE.findall(W.pin_line(digest) + "\nSELECT 1;\n") == [digest]


@pytest.mark.parametrize("bad", ["", "abc", "0123456789ABCDEF" * 4, "0123456789abcdef" * 4 + "0"])
def test_pin_line_refuses_what_is_not_a_digest(bad: str) -> None:
    with pytest.raises(ValueError, match="not a sha256 hex digest"):
        W.pin_line(bad)


def _hex_echo_child(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[list[str]]:
    """Run the real `subprocess.run` with every keyword `send` chose, but against a local child
    that prints the bytes it received on stdin as hex - so what the channel carries is measured,
    not assumed. Returns the argv each call would have run."""
    real_run = subprocess.run
    child = [sys.executable, "-c", "import sys; print(sys.stdin.buffer.read().hex())"]
    argv: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> Any:
        argv.append(args)
        return real_run(child, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)
    return argv


def test_send_delivers_a_newline_as_lf_on_every_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-09-25 audit M2: `text=True` wrote stdin through a TextIOWrapper, which on Windows turns
    every LF into CR LF - a multi-line literal would have been stored with a stray CR, and
    every guard and read-back would have sent the same translated literal."""
    _hex_echo_child(monkeypatch, W)
    sql = "SELECT 'a\nb';\n-- é\n"
    proc = W.send(sql)
    assert proc.returncode == 0
    assert bytes.fromhex(proc.stdout.strip()) == sql.encode("utf-8")


def test_the_phase_stages_send_through_prod_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """`write_stage.run_sql` (phases 3-5) is `prod_write.send`: the same LF-preserving channel,
    the same channel timeouts, and a timeout that is an unknown outcome, not a raw
    `TimeoutExpired` (audit M2/M3)."""
    from phase3 import write_stage as WS

    argv = _hex_echo_child(monkeypatch, W)
    sql = "SELECT 'a\nb';\n"
    assert bytes.fromhex(WS.run_sql(sql).strip()) == sql.encode("utf-8")
    joined = " ".join(argv[0])
    assert joined.startswith("ssh ") and "ConnectTimeout=" in joined
    assert joined.endswith(W.PSQL_ROWS)

    def timeout(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=900)

    monkeypatch.setattr(W.subprocess, "run", timeout)
    with pytest.raises(W.OutcomeUnknown):
        WS.run_sql("SELECT 1;")
    assert WS.PSQL_ROWS is W.PSQL_ROWS and WS.SSH_HOST is W.SSH_HOST
