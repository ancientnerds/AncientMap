"""The shared file helpers of the Opus-handoff lanes (`scripts/remediation/run_files.py`): the
fresh acceptance (`acceptance/judge.py`) and lane WC (`wc/cli.py`) write their run files with them."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import run_files as RF  # noqa: E402
from acceptance import judge as J  # noqa: E402
from wc import cli as C  # noqa: E402


def test_the_writers_write_sorted_utf8_with_lf_and_create_the_parents(tmp_path: Path) -> None:
    RF.write_json(tmp_path / "a" / "b.json", {"z": "Ħal Saflieni", "a": [1]})
    assert (tmp_path / "a" / "b.json").read_bytes() == (
        '{\n "a": [\n  1\n ],\n "z": "Ħal Saflieni"\n}\n'.encode()
    )
    RF.write_jsonl(tmp_path / "c" / "d.jsonl", [{"b": 2, "a": 1}, {"c": "é"}])
    assert (tmp_path / "c" / "d.jsonl").read_bytes() == '{"a": 1, "b": 2}\n{"c": "é"}\n'.encode()


def test_the_clock_is_utc_to_the_second() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", RF.now())


def test_both_lanes_write_with_the_shared_helpers() -> None:
    """One body each, never a copy (the WC review of 2026-09-26)."""
    assert (J._now, J._write_json, J._write_jsonl) == (RF.now, RF.write_json, RF.write_jsonl)
    assert C.RF is RF
    assert not hasattr(C, "_write_json") and not hasattr(C, "_now")
