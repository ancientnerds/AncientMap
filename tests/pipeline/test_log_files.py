# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/log_files.py: an nginx log and its dateext rotations, read as one
family, oldest first."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime

from pipeline import log_files


def _write(path, *lines, gz=False):
    blob = "".join(f"{line}\n" for line in lines).encode()
    path.write_bytes(gzip.compress(blob) if gz else blob)


def test_the_family_is_ordered_by_its_dateext_suffix(tmp_path):
    log = tmp_path / "requests.log"
    _write(tmp_path / "requests.log-20261021", "b")
    _write(tmp_path / "requests.log-20260930.gz", "old", gz=True)
    _write(tmp_path / "requests.log-20261020.gz", "a", gz=True)
    _write(log, "live")
    # Not of the family: another log, a stray suffix.
    _write(tmp_path / "referrals.log-20261020.gz", "x", gz=True)
    _write(tmp_path / "requests.log-backup", "x")
    _write(tmp_path / "requests.log-20261021.tmp", "x")
    assert [p.name for p in log_files.family(log)] == [
        "requests.log-20260930.gz",
        "requests.log-20261020.gz",
        "requests.log-20261021",
        "requests.log",
    ]


def test_a_plain_newest_rotation_and_gzipped_older_ones_are_read_in_order(tmp_path):
    # delaycompress: the newest rotated day stays plain for one more day.
    log = tmp_path / "crawlers.log"
    _write(tmp_path / "crawlers.log-20261019.gz", "1", "2", gz=True)
    _write(tmp_path / "crawlers.log-20261020.gz", "3", gz=True)
    _write(tmp_path / "crawlers.log-20261021", "4")
    _write(log, "5")
    lines = [line for p in log_files.family(log) for line in log_files.read_file(p)]
    assert lines == ["1", "2", "3", "4", "5"]


def test_only_a_file_two_days_before_since_is_skipped(tmp_path):
    since = datetime(2026, 10, 15, 6, 0, tzinfo=UTC)
    assert log_files.rotated_before(tmp_path / "requests.log-20261013.gz", since)
    # The file of the 14th can hold lines written after local midnight
    # (dateyesterday names it after the 14th, the timer fires later): it stays.
    assert not log_files.rotated_before(tmp_path / "requests.log-20261014.gz", since)
    assert not log_files.rotated_before(tmp_path / "requests.log-20261015", since)
    assert not log_files.rotated_before(tmp_path / "requests.log", since)


def test_a_missing_current_file_leaves_the_rotated_days_in_the_family(tmp_path):
    log = tmp_path / "requests.log"
    _write(tmp_path / "requests.log-20261021.gz", "a", gz=True)
    assert [p.name for p in log_files.family(log)] == ["requests.log-20261021.gz"]


def test_a_live_file_without_rotations_is_a_family_of_one(tmp_path):
    log = tmp_path / "referrals.log"
    _write(log, "a")
    assert log_files.family(log) == [log]


def test_the_identity_changes_with_an_append(tmp_path):
    log = tmp_path / "requests.log"
    _write(log, "a")
    before = log_files.file_identity(log)
    with log.open("a", encoding="utf-8") as fh:
        fh.write("b\n")
    assert log_files.file_identity(log) != before
    assert log_files.file_identity(log)[0] == before[0]
