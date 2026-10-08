"""D24: the workstation <-> VPS cross-copy routine (`scripts/remediation/offsite_sync.py`).

Offline: the pure parts (listing parse, age gate, retention, tar exclusions, SHA256SUMS text,
hash comparison). The ssh/scp transport is not exercised here; it is run by hand on the workstation.
"""

from __future__ import annotations

import hashlib
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import offsite_sync as O  # noqa: E402

LISTING = """\
1791000000
1791000000 892757235 /var/www/ancientnerds/backups/2026-10-08_remediation/database_2026-10-08_remediation.dump
1790900000 892000000 /var/www/ancientnerds/backups/2026-10-07_remediation/database_2026-10-07_remediation.dump
1700000000 800000000 /var/www/ancientnerds/backups/2026-09-19_pre-audit/database_2026-09-19_pre-audit.dump
"""


def test_parse_listing_returns_remote_clock_and_dumps():
    now, dumps = O.parse_dump_listing(LISTING)
    assert now == 1791000000
    assert [d.mtime for d in dumps] == [1791000000, 1790900000, 1700000000]
    assert dumps[0].size == 892757235
    assert dumps[0].path == (
        "/var/www/ancientnerds/backups/2026-10-08_remediation/database_2026-10-08_remediation.dump"
    )
    assert dumps[0].name == "database_2026-10-08_remediation.dump"


def test_newest_dump_is_the_latest_mtime_not_the_last_line():
    _, dumps = O.parse_dump_listing(LISTING)
    assert O.newest_dump(list(reversed(dumps))).mtime == 1791000000


def test_no_dump_is_an_error():
    with pytest.raises(O.OffsiteError, match="no database_"):
        O.parse_dump_listing("1791000000\n")


def test_parse_listing_refuses_a_malformed_line():
    with pytest.raises(O.OffsiteError, match="listing line"):
        O.parse_dump_listing("1791000000\nnot a stat line\n")


def test_age_gate_is_strictly_over_the_limit():
    limit = 26 * 3600
    assert not O.is_stale(now=limit, mtime=0, max_age_hours=26)
    assert O.is_stale(now=limit + 1, mtime=0, max_age_hours=26)


def test_stale_message_is_one_loud_line():
    msg = O.stale_message("x.dump", age_hours=30.04, max_age_hours=26)
    assert "\n" not in msg
    assert msg.startswith("OFFSITE-SYNC STALE:")
    assert "x.dump" in msg and "30.0" in msg and "26" in msg


def test_names_to_prune_keeps_the_newest_by_name():
    names = ["database_2026-10-06.dump", "database_2026-10-08.dump", "database_2026-10-07.dump"]
    assert O.names_to_prune(names, keep=2) == ["database_2026-10-06.dump"]
    assert O.names_to_prune(names, keep=3) == []


def test_sha256sums_round_trip():
    a, b = "a" * 64, "b" * 64
    text = O.format_sums({"x.dump": a, "y.tar.gz": b})
    assert text == f"{a}  x.dump\n{b}  y.tar.gz\n"
    assert O.parse_sums(text) == {"x.dump": a, "y.tar.gz": b}


def test_parse_sums_accepts_the_binary_marker_of_sha256sum():
    a = "c" * 64
    assert O.parse_sums(f"{a} *x.dump\n") == {"x.dump": a}


def test_parse_sums_refuses_garbage():
    with pytest.raises(O.OffsiteError, match="SHA256SUMS"):
        O.parse_sums("nonsense\n")


def test_require_same_hash_names_both_sides():
    O.require_same_hash("f", "a" * 64, "a" * 64)
    with pytest.raises(O.OffsiteError) as e:
        O.require_same_hash("f", "a" * 64, "b" * 64)
    assert "a" * 64 in str(e.value) and "b" * 64 in str(e.value) and "f" in str(e.value)


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc" * 1_000_000)
    assert O.sha256_file(p) == hashlib.sha256(b"abc" * 1_000_000).hexdigest()


@pytest.mark.parametrize(
    "rel, excluded",
    [
        ("AUDIT_LOG.md", False),
        ("fields/wd3/plan.json", False),
        ("secrets.env", True),
        ("lane/prod-db.env", True),
        ("handoff", True),
        ("handoff/batch1/q.jsonl", True),
        ("gallery_audit/pages/p1.html", True),
        ("cache/x.json", True),
        ("mechanical/cache", True),
        ("acceptance/pagesize.json", False),
        ("environment.md", False),
    ],
)
def test_evidence_exclusions(rel, excluded):
    assert O.evidence_excluded(rel) is excluded


def test_build_evidence_tar_excludes_and_roots_under_output_remediation(tmp_path):
    src = tmp_path / "output" / "remediation"
    (src / "handoff").mkdir(parents=True)
    (src / "handoff" / "q.jsonl").write_text("x")
    (src / "fields" / "pages").mkdir(parents=True)
    (src / "fields" / "pages" / "p.html").write_text("x")
    (src / "cache").mkdir()
    (src / "cache" / "c.json").write_text("x")
    (src / "keep").mkdir()
    (src / "keep" / "a.txt").write_text("keep")
    (src / "my.env").write_text("SECRET=1")
    (src / "AUDIT_LOG.md").write_text("log")
    out = tmp_path / "evidence_2026-10-08.tar.gz"
    O.build_evidence_tar(src, out)
    with tarfile.open(out) as t:
        names = sorted(t.getnames())
    assert names == [
        "remediation",
        "remediation/AUDIT_LOG.md",
        "remediation/fields",
        "remediation/keep",
        "remediation/keep/a.txt",
    ]


def test_build_evidence_tar_refuses_a_missing_source(tmp_path):
    with pytest.raises(O.OffsiteError, match="not a directory"):
        O.build_evidence_tar(tmp_path / "nope", tmp_path / "o.tar.gz")


def test_evidence_name_is_dated_and_sortable():
    assert O.evidence_name("2026-10-08") == "remediation-evidence_2026-10-08.tar.gz"
    assert O.evidence_name("2026-10-08") > O.evidence_name("2026-09-21")


def test_remote_listing_command_quotes_the_root():
    cmd = O.remote_listing_command("/var/www/ancient nerds/backups")
    assert "'/var/www/ancient nerds/backups'/*/database_*.dump" in cmd
    assert cmd.startswith("date +%s;")
