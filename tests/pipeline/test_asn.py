# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/asn.py: the network behind an IPv4 address, from iptoasn.com's
table, and the vendored datacenter list."""

from __future__ import annotations

import gzip
import ipaddress
import os
from pathlib import Path

import pytest

from pipeline import asn

ROOT = Path(__file__).resolve().parents[2]


def _u32(ip: str) -> int:
    return int(ipaddress.IPv4Address(ip))


#: Five rows in the file's shape: start, end, AS, country, name - with a gap
#: between the second and the third row, and an unrouted range.
ROWS = [
    (_u32("1.0.0.0"), _u32("1.0.0.255"), 13335, "US", "CLOUDFLARENET"),
    (_u32("1.0.1.0"), _u32("1.0.3.255"), 0, "None", "Not routed"),
    (_u32("8.8.4.0"), _u32("8.8.4.255"), 15169, "US", "GOOGLE"),
    (_u32("8.8.8.0"), _u32("8.8.8.255"), 15169, "US", "GOOGLE"),
    (_u32("47.79.0.0"), _u32("47.79.255.255"), 45102, "US", "ALIBABA-CN-NET Alibaba US"),
]


@pytest.fixture
def table(tmp_path, monkeypatch):
    path = tmp_path / "ip2asn-v4-u32.tsv.gz"
    text = "".join("\t".join(str(v) for v in row) + "\n" for row in ROWS)
    path.write_bytes(gzip.compress(text.encode()))
    monkeypatch.setattr(asn, "ASN_DB_PATH", path)
    monkeypatch.setattr(asn, "_loaded", None)
    loaded = asn.load()
    assert loaded is not None
    return loaded


def test_lookup_finds_the_range_of_an_address(table):
    assert table.lookup("8.8.8.8") == (15169, "GOOGLE")
    assert table.lookup("1.0.0.0") == (13335, "CLOUDFLARENET")
    assert table.lookup("47.79.255.255") == (45102, "ALIBABA-CN-NET Alibaba US")


def test_an_unrouted_or_unlisted_address_is_asn_zero(table):
    assert table.lookup("1.0.2.1") == (0, "Not routed")  # a "Not routed" row
    assert table.lookup("8.8.5.1") == (0, "Not routed")  # between two rows
    assert table.lookup("0.0.0.1") == (0, "Not routed")  # before the first row
    assert table.lookup("200.1.1.1") == (0, "Not routed")  # after the last row


def test_an_ipv6_address_raises(table):
    with pytest.raises(ipaddress.AddressValueError):
        table.lookup("2001:db8::1")


def test_the_table_carries_the_file_date(table):
    mtime = asn.ASN_DB_PATH.stat().st_mtime
    assert table.as_of.timestamp() == pytest.approx(mtime, abs=1e-3)


def test_the_table_is_parsed_once_per_file_version(table, monkeypatch):
    assert asn.load() is table
    os.utime(asn.ASN_DB_PATH, ns=(0, 1_000_000_000))
    assert asn.load() is not table


def test_a_missing_file_gives_none_and_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(asn, "ASN_DB_PATH", tmp_path / "missing.tsv.gz")
    monkeypatch.setattr(asn, "_loaded", None)
    assert asn.load() is None
    assert str(asn.ASN_DB_PATH) in asn.unavailable_reason()


def test_nginx_listens_on_ipv4_only():
    """asn.py is IPv4 only because no client reaches nginx over IPv6."""
    config = (ROOT / "ancientnerds-nginx-config").read_text(encoding="utf-8")
    assert "listen [::]" not in config
    assert "listen 443" in config


def test_the_datacenter_list_leaves_out_the_networks_people_browse_through():
    for number in (36183, 20940, 16625, 54113, 15169):
        assert number not in asn.DATACENTER_ASNS
    # Upstream entries that stay: AWS, Hetzner, Alibaba US.
    assert {16509, 24940, 45102} <= asn.DATACENTER_ASNS


def test_the_datacenter_list_carries_the_mit_notice_and_its_fetch_date():
    header = asn.DATACENTER_ASNS_PATH.read_text(encoding="utf-8")
    assert "Copyright (c) 2024 X4B (Mathew Heard)" in header
    assert "Permission is hereby granted, free of charge" in header
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in header
    assert "fetched 2026-10-22" in header
