"""The sub-national place names that contain a country's name (`country_lookup.SUBNATIONAL_NAME_TO_ISO`).

Phase 4's pilot 3 (2026-09-24) held Lake Mungo because V14 read "Lake Mungo is a dry lake located in
New South Wales, Australia" as placing the site in Wales: the country regex matched the word "Wales"
inside the Australian state. The table lists such names, each mapped to its real ISO code; the
verifier's country regex reads them beside `NAME_TO_ISO`, longest first, so the whole name is read
before the country inside it. It is derived from data: the census run's pool sentences scanned for a
`NAME_TO_ISO` name directly preceded by a capitalised word or part of a longer proper name
(AUDIT_LOG, pilot 4), each entry verified. "South Wales" is Wales and stays out.
"""

from __future__ import annotations

import re

from pipeline.utils.country_lookup import NAME_TO_ISO, SUBNATIONAL_NAME_TO_ISO

#: The table, pinned: a new entry is a decision (verified, and recorded in the AUDIT_LOG's scan).
PINNED = {
    "new south wales": "AU",
    "new mexico": "US",
    "new england": "US",
    "central macedonia": "GR",
    "western macedonia": "GR",
    "eastern macedonia and thrace": "GR",
    "greek macedonia": "GR",
    "west azerbaijan province": "IR",
    "upper jordan valley": "IL",
    "jordan hill": "GB",
    "kraku lu jordan": "RS",
    "el peru": "GT",
    "inner niger delta": "ML",
    "lapis niger": "IT",
    "denmark fjord": "GL",
}


def test_the_table_is_the_verified_scan() -> None:
    assert SUBNATIONAL_NAME_TO_ISO == PINNED


def test_every_name_carries_a_country_name_and_maps_to_another_country() -> None:
    """Each entry exists because a country's name stands inside it as a whole word, and its real
    country differs from that name's (otherwise the country regex already reads it right)."""
    for name, iso in SUBNATIONAL_NAME_TO_ISO.items():
        assert name == name.lower() and name not in NAME_TO_ISO, name
        assert iso in set(NAME_TO_ISO.values()), name
        inside = [
            country
            for country in NAME_TO_ISO
            if re.search(rf"(?<!\w){re.escape(country)}(?!\w)", name)
        ]
        assert inside, f"{name} carries no country name"
        assert all(NAME_TO_ISO[country] != iso for country in inside), name


def test_south_wales_stays_wales() -> None:
    assert "south wales" not in SUBNATIONAL_NAME_TO_ISO
    assert NAME_TO_ISO["wales"] == "GB"
