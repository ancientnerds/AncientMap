# SPDX-License-Identifier: AGPL-3.0-only
"""The E3 scope rule with Oceania (owner decision O7, 2026-09-26: "Ozeanien wie Amerika").

`passes_date_cutoff` is the one rule the loader, the prospector, Lyra's promotion gate and the
remediation's census and lanes share (the lanes render it as SQL from the same lists, pinned in
`tests/remediation/test_mechanical_scope.py`). Oceania is decided by the row's country - the UN
M49 list - or, for the rows that carry a state's name, by the Pacific island group the point lies
on. The coordinates below are production's rows where one exists (read-only, 2026-09-26).
"""

from __future__ import annotations

import pytest

from pipeline.normalizers import dates as D


def row(country: str | None, lat: float | None, lon: float | None, start: int | None) -> dict:
    return {"country": country, "lat": lat, "lon": lon, "period_start": start, "period_end": None}


class TestTheRegion:
    @pytest.mark.parametrize(
        ("country", "lat", "lon"),
        [
            ("Australia", -33.75, 143.08),  # Lake Mungo
            ("Northern Mariana Islands", 14.97, 145.62),  # House of Taga
            ("Chile", -27.11, -109.39),  # Ahu Akivi, Rapa Nui
            ("France", -16.84, -151.36),  # Taputapuatea Marae, Raiatea
            ("France", -22.27, 166.45),  # Noumea, New Caledonia
            ("France", -13.28, -176.17),  # Wallis
            ("United States", 19.42, -155.29),  # Hawaii Island
            ("USA", 13.44, 144.79),  # Guam
            ("United States of America", -14.28, -170.70),  # Tutuila, American Samoa
            ("United Kingdom", -25.07, -130.10),  # Pitcairn
            ("New Zealand", -41.29, 174.78),
            ("  Papua New Guinea ", -6.0, 147.0),  # spaces around the name are stripped
            ("TONGA", -21.13, -175.20),  # case does not matter
            # the ISO codes geonames and dare store
            ("AU", -33.75, 143.08),
            ("GU", 13.44, 144.79),
            ("PF", -17.53, -149.57),
            ("US", 19.42, -155.29),  # Hawaii Island
            ("CL", -27.11, -109.39),  # Rapa Nui
            # "Region, Country" as earth_impacts and radiocarbon_paleo store it
            ("Queensland, Australia", -27.0, 153.0),
            ("Western Australia, Australia", -22.59, 117.18),
            ("Chile, Easter Island", None, None),  # the island's own name needs no point
            ("Hawaii, United States", 19.42, -155.29),
        ],
    )
    def test_oceania(self, country: str, lat: float | None, lon: float | None) -> None:
        assert D.in_oceania(country, lat, lon)

    @pytest.mark.parametrize(
        ("country", "lat", "lon", "region"),
        [
            ("Chile", -33.45, -70.65, D.AMERICAS),  # Santiago
            ("Chile", -33.64, -78.83, D.AMERICAS),  # Juan Fernandez: South America in M49
            ("France", 48.85, 2.35, D.REST_OF_WORLD),  # Paris
            ("France", -21.12, 55.53, D.REST_OF_WORLD),  # Reunion
            ("United States", 34.05, -118.24, D.AMERICAS),  # Los Angeles
            ("United States", 52.93, 173.0, D.REST_OF_WORLD),  # Attu, Aleutians: no Pacific box
            ("United Kingdom", 51.5, -0.12, D.REST_OF_WORLD),
            ("Indonesia", -4.0, 138.0, D.REST_OF_WORLD),  # Western New Guinea: Asia in M49
            ("Japan", 24.44, 123.01, D.REST_OF_WORLD),  # Yonaguni
            (None, -33.75, 143.08, D.REST_OF_WORLD),  # no country: the longitude alone decides
            ("Mexico", 20.0, -100.0, D.AMERICAS),
            ("US", 34.05, -118.24, D.AMERICAS),  # the code of a state is placed by its boxes too
            ("FR", 48.85, 2.35, D.REST_OF_WORLD),
            ("Texas, United States", 31.0, -100.0, D.AMERICAS),
            ("Korea, South", 37.57, 126.98, D.REST_OF_WORLD),
            ("Congo, Republic of the", -4.27, 15.28, D.REST_OF_WORLD),
            ("ID", -4.0, 138.0, D.REST_OF_WORLD),
            ("Australia,", -33.75, 143.08, D.REST_OF_WORLD),  # nothing after the last comma
        ],
    )
    def test_not_oceania(self, country: str | None, lat: float, lon: float, region: str) -> None:
        assert D.e3_region({"country": country, "lat": lat, "lon": lon}) == region

    def test_a_box_edge_counts(self) -> None:
        lon_min, lat_min, lon_max, lat_max = D.OCEANIA_PARTS["chile"][0]
        for lat, lon in ((lat_min, lon_min), (lat_max, lon_max)):
            assert D.in_oceania("Chile", lat, lon)
        assert not D.in_oceania("Chile", lat_min - 0.01, lon_min)

    def test_a_state_s_box_needs_the_point(self) -> None:
        """A state named without a point cannot be placed on an island group."""
        assert not D.in_oceania("France", None, None)
        assert D.in_oceania("Fiji", None, None)

    def test_without_a_longitude_the_region_is_unknown(self) -> None:
        assert D.e3_region({"country": "Australia", "lat": -30.0, "lon": None}) is None

    def test_the_lists_compare_like_the_rendered_sql(self) -> None:
        """`mechanical/lane.py` renders the lists into `<country_key> IN (...)`: every name must be
        what `country_key` yields for it, in ASCII, where SQL's lower and Python's agree - and
        without a comma, which `country_key` never leaves in a key."""
        for name in (*D.OCEANIA_COUNTRIES, *D.OCEANIA_PARTS):
            assert name.isascii() and name == D.country_key(name) and name and "," not in name
        assert D.country_key("  New Zealand ") == "new zealand"
        assert D.country_key("Northern Territory, Australia") == "australia"
        assert D.country_key("a, b ,  C ") == "c"
        assert D.country_key("Australia,") == ""
        assert D.country_key(None) is None

    def test_the_codes_are_the_names_of_the_project_s_own_table(self) -> None:
        """`country_lookup.NAME_TO_ISO` is the project's name -> ISO table: a name it files under an
        Oceania code is in the list, and a listed name it knows has a listed code - except the
        island names placed on their state (Easter Island is CL, whose Rapa Nui is a part)."""
        from pipeline.utils.country_lookup import NAME_TO_ISO

        islands = {"hawaii", "easter island", "rapa nui"}
        for name, iso in NAME_TO_ISO.items():
            if iso.lower() in D.OCEANIA_ISO_CODES:
                assert name in D.OCEANIA_COUNTRIES, name
            elif name in D.OCEANIA_COUNTRIES:
                assert name in islands and iso.lower() in D.OCEANIA_PARTS, name

    def test_every_name_lookup_country_gives_an_oceania_territory_is_listed(self) -> None:
        """`lookup_country` (the loader's and Lyra's reverse geocoder) answers with the `name` of
        `data/boundaries/countries.geojson`; for every territory under an Oceania code that name is
        in the list, so a row it placed is Oceania by its name."""
        import json

        from pipeline.utils.country_lookup import COUNTRIES_FILE

        features = json.loads(COUNTRIES_FILE.read_text(encoding="utf-8"))["features"]
        names = {
            f["properties"]["name"]
            for f in features
            if str(f["properties"]["ISO3166-1-Alpha-2"]).lower() in D.OCEANIA_ISO_CODES
        }
        assert len(names) >= 20
        assert all(D.country_key(name) in D.OCEANIA_COUNTRIES for name in names), names

    def test_no_state_with_a_pacific_box_is_oceania_as_a_whole(self) -> None:
        """A state in both lists would make its boxes dead code - and its mainland Oceania."""
        assert not set(D.OCEANIA_PARTS) & D.OCEANIA_COUNTRIES

    def test_a_state_s_code_has_the_state_s_boxes(self) -> None:
        for name, code in (
            ("chile", "cl"),
            ("france", "fr"),
            ("united kingdom", "gb"),
            ("united states", "us"),
        ):
            assert D.OCEANIA_PARTS[code] == D.OCEANIA_PARTS[name]

    def test_every_box_is_a_box(self) -> None:
        for boxes in D.OCEANIA_PARTS.values():
            for lon_min, lat_min, lon_max, lat_max in boxes:
                assert -180 <= lon_min < lon_max <= 180
                assert -90 <= lat_min < lat_max <= 90


class TestTheCutoff:
    def test_oceania_s_cutoff_is_the_americas(self) -> None:
        assert D.DATE_CUTOFF_OCEANIA == D.DATE_CUTOFF_AMERICAS == 1500
        assert D.DATE_CUTOFF_REST_OF_WORLD == 500
        assert D.E3_CUTOFFS == {D.OCEANIA: 1500, D.AMERICAS: 1500, D.REST_OF_WORLD: 500}

    @pytest.mark.parametrize(
        ("record", "passes"),
        [
            (row("Australia", -37.21, 144.81, 1200), True),
            (row("Australia", -37.21, 144.81, 1500), True),  # "through" 1500 AD
            (row("Australia", -37.21, 144.81, 1501), False),
            (row("France", -22.27, 166.45, 1200), True),  # New Caledonia: 500 AD before O7
            (row("France", 48.85, 2.35, 1200), False),
            (row("France", 48.85, 2.35, 500), True),
            (row("Indonesia", -4.0, 138.0, 1200), False),
            (row(None, -37.21, 144.81, 1200), False),  # no country: rest of world by longitude
            (row("Australia", -37.21, 144.81, None), True),  # no date: included, as before
            (row("Australia", None, None, 3000), True),  # no longitude: included, as before
        ],
    )
    def test_passes_date_cutoff(self, record: dict, passes: bool) -> None:
        assert D.passes_date_cutoff(record) is passes

    def test_period_end_decides_before_period_start(self) -> None:
        record = row("Australia", -37.21, 144.81, 1000)
        record["period_end"] = 1600
        assert not D.passes_date_cutoff(record)

    def test_the_loader_uses_the_one_rule(self) -> None:
        """The loader kept a private copy of the pre-O7 rule until 2026-09-26; it imports it now."""
        from pipeline import unified_loader

        assert unified_loader.passes_date_cutoff is D.passes_date_cutoff
        assert not hasattr(unified_loader, "DATE_CUTOFF_AMERICAS")
