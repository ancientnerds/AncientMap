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
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

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
        lambda args, **kw: subprocess.CompletedProcess(args, 3, stdout="", stderr="ERROR"),
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
