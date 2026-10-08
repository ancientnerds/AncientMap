"""The one rule of which licences ask for a credit (D18 with X4, 2026-10-08)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import licenses as L  # noqa: E402


@pytest.mark.parametrize(
    "name", ["Public domain", "public domain", "PD-old-100", "PD-US", "PD", "CC0", "CC0 1.0"]
)
def test_a_public_domain_or_cc0_file_asks_for_no_credit(name):
    assert L.is_free(name) and L.credit_columns(name) == ()


@pytest.mark.parametrize("name", ["No restrictions", "Copyrighted free use"])
def test_commons_free_use_labels_ask_for_no_credit(name):
    assert L.credit_columns(name) == ()


def test_commons_attribution_asks_for_the_author_and_has_no_licence_page():
    assert L.credit_columns("Attribution") == ("author",)


@pytest.mark.parametrize(
    "name",
    [
        "CC BY 4.0",
        "CC BY-SA 3.0 de",
        "GFDL 1.2",
        "OGL 3",
        "FAL",
        "KOGL Type 1",
        "GPL",
        "unheard of",
    ],
)
def test_every_other_licence_name_asks_for_the_author_and_the_licence_url(name):
    assert not L.is_free(name)
    assert L.credit_columns(name) == ("author", "license_url")


def test_the_author_url_is_never_demanded():
    for name in ("CC BY 4.0", "Attribution", "Public domain", ""):
        assert "author_url" not in L.credit_columns(name)


def test_the_sql_predicate_is_built_from_the_same_names():
    sql = L.needs_attribution_sql("w.license")
    for exact in L.FREE_LICENSES:
        assert f"'{exact}'" in sql
    for prefix in L.FREE_LICENSE_PREFIXES:
        assert f"LIKE '{prefix}%'" in sql
    assert sql.startswith("(w.license IS NOT NULL AND w.license <> ''")
