# SPDX-License-Identifier: AGPL-3.0-only
"""The owner's label rule (decision D58, 2026-10-24): only the medieval Old World is out after 500 AD.

"Only the medieval Old World of Europe, Byzantium and the Vikings is out; non-European sites of
500-1500 stay in; L'Anse aux Meadows stays out (Viking subject)." `passes_date_cutoff` is the region
half of that rule, and the one the remediation's scope lanes render as SQL from the same lists
(`tests/remediation/test_scope_unretire.py`); `label_scope` is the whole rule for a path that asks no
verdict - the loader, the Prospector and Lyra's promotion gate - which holds a borderline record and
puts a Viking subject out by its item. The numeric rule it replaced keeps its own name
(`passes_e3_cutoff`, `tests/pipeline/test_e3_oceania.py`). The points below are production's curated
rows where one exists (read-only, 2026-10-24).
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
            ("Poland", 51.56, 15.52),  # Chrobry Fortified Village
            ("England", 54.53, -1.07),  # Ruther Cross
            ("Scotland", 56.0, -4.0),
            ("Northern Ireland", 54.6, -5.9),
            ("Finland", 68.94, 27.29),  # Ukonkivi
            ("Sweden", 58.45, 11.34),
            ("Iceland", 64.1, -21.9),  # east of the Americas' window
            ("Portugal", 37.76, -25.23),  # the Azores: Portugal's, inside the window's east edge
            ("Russia", 58.72, 57.64),  # Kamennyy Gorod, west of the Urals
            ("Ukraine", 45.35, 36.60),  # Yenikale, Crimea
            ("Cyprus", 35.1, 33.4),  # Byzantium, then the Lusignans' Crusader kingdom
            ("CY", 35.1, 33.4),  # the ISO codes geonames and dare store
            ("Baltic Sea", 61.38, 18.45),  # the curated row of the Baltic Sea Anomaly
            ("gb", 51.5, -0.12),
            ("Bavaria, Germany", 48.1, 11.6),  # "Region, Country": the last part decides
            ("Spain", 40.4, -3.7),
            ("Russia", None, None),  # without a point the country decides
        ],
    )
    def test_the_medieval_old_world(
        self, country: str, lat: float | None, lon: float | None
    ) -> None:
        assert D.in_medieval_old_world(country, lat, lon)

    @pytest.mark.parametrize(
        ("country", "lat", "lon", "region"),
        [
            ("Cambodia", 13.45, 103.86, D.REST_OF_WORLD),  # Preah Palilay, Angkor Thom
            ("Indonesia", -7.75, 110.49, D.REST_OF_WORLD),  # Prambanan
            ("Japan", 34.47, 135.81, D.REST_OF_WORLD),  # Kameishi
            ("Pakistan", 26.39, 66.21, D.REST_OF_WORLD),  # Gondrani
            ("Turkmenistan", 37.66, 62.15, D.REST_OF_WORLD),  # Great Kyz Kala, Merv
            ("Ethiopia", 12.03, 39.04, D.REST_OF_WORLD),  # Lalibela
            ("Mongolia", 47.57, 102.87, D.REST_OF_WORLD),  # Khushuu Tsaidam
            ("Iraq", 33.09, 44.58, D.REST_OF_WORLD),  # Taq Kasra: Sasanian, never Byzantine
            ("Kazakhstan", 43.3, 68.3, D.REST_OF_WORLD),  # Central Asia in M49
            ("Lebanon", 33.58, 35.61, D.REST_OF_WORLD),  # borderline, but not Europe
            ("Türkiye", 37.18, 40.95, D.REST_OF_WORLD),  # Dara: borderline, the subject decides
            ("Turkey", 41.0, 28.98, D.REST_OF_WORLD),  # Constantinople: borderline as well
            ("TR", 40.5, 43.57, D.REST_OF_WORLD),  # Ani
            ("Russia", 43.07, 132.68, D.REST_OF_WORLD),  # Mount Livadiyskaya: east of the Urals
            ("Russia", 66.0, -172.0, D.REST_OF_WORLD),  # Chukotka beyond the antimeridian
            ("RU", 52.67, 88.53, D.REST_OF_WORLD),
            ("Spain", 28.1, -15.4, D.REST_OF_WORLD),  # Gran Canaria: the Guanche islands
            ("France", -21.12, 55.53, D.REST_OF_WORLD),  # Reunion
            ("France", -12.78, 45.23, D.REST_OF_WORLD),  # Mayotte
            ("France", -16.84, -151.36, D.OCEANIA),  # Raiatea: Oceania before Europe
            ("France", 4.9, -52.3, D.AMERICAS),  # French Guiana: the Americas' window first
            ("Greenland", 61.16, -45.43, D.AMERICAS),  # Hvalsey
            ("Mexico", 20.0, -100.0, D.AMERICAS),
            ("Australia", -33.75, 143.08, D.OCEANIA),
        ],
    )
    def test_the_other_regions(self, country: str, lat: float, lon: float, region: str) -> None:
        assert D.scope_region({"country": country, "lat": lat, "lon": lon}) == region

    def test_a_region_that_cannot_be_told_is_none(self) -> None:
        """Without a longitude nothing can be told; outside the Americas and Oceania a row without
        a country is the unplaced Old World (a point east of -30 may be Lisbon or Lagos), which
        keeps the stricter 500 AD."""
        assert D.scope_region({"country": "Poland", "lat": 51.0, "lon": None}) is None
        assert D.scope_region({"country": None, "lat": 51.0, "lon": 15.0}) == (D.UNPLACED_OLD_WORLD)
        assert D.scope_region({"country": None, "lat": 20.0, "lon": -100.0}) == D.AMERICAS
        assert D.scope_region({"country": None, "lat": -37.21, "lon": 144.81}) == (
            D.UNPLACED_OLD_WORLD
        )
        assert D.LABEL_CUTOFFS[D.UNPLACED_OLD_WORLD] == 500

    def test_the_urals_edge_counts_as_asia(self) -> None:
        assert D.scope_region({"country": "Russia", "lat": 56.8, "lon": 60.0}) == D.REST_OF_WORLD
        assert D.scope_region({"country": "Russia", "lat": 56.8, "lon": 59.99}) == (
            D.MEDIEVAL_OLD_WORLD
        )

    def test_the_lists_compare_like_the_rendered_sql(self) -> None:
        """`mechanical/lane.py` renders the lists into `<country_key> IN (...)`: every name must be
        what `country_key` yields for it, without a comma. Two keys are not ASCII (`türkiye`,
        `åland islands`): SQL's `lower` must agree with Python's on them, which the SQLite test of
        the rendered window proves for the spelling the curated rows carry (`Türkiye`)."""
        for name in (
            *D.MEDIEVAL_OLD_WORLD_COUNTRIES,
            *D.NON_EUROPEAN_PARTS,
            *D.LABEL_BORDERLINE_COUNTRIES,
        ):
            assert name == D.country_key(name) and name and "," not in name
        assert {n for n in D.MEDIEVAL_OLD_WORLD_COUNTRIES if not n.isascii()} == {"åland islands"}
        assert {n for n in D.LABEL_BORDERLINE_COUNTRIES if not n.isascii()} == {"türkiye"}

    def test_the_lists_do_not_overlap(self) -> None:
        """A borderline country is neither Oceania's nor the medieval Old World's (so the window
        keeps it through 1500 and only a verdict can put a site there out), and a medieval state's
        non-European parts belong to a listed state."""
        assert not D.LABEL_BORDERLINE_COUNTRIES & D.MEDIEVAL_OLD_WORLD_COUNTRIES
        assert not D.LABEL_BORDERLINE_COUNTRIES & D.OCEANIA_COUNTRIES
        assert not D.LABEL_BORDERLINE_COUNTRIES & set(D.OCEANIA_PARTS)
        assert not D.MEDIEVAL_OLD_WORLD_COUNTRIES & D.OCEANIA_COUNTRIES
        assert set(D.NON_EUROPEAN_PARTS) <= D.MEDIEVAL_OLD_WORLD_COUNTRIES

    def test_every_box_is_a_box(self) -> None:
        for boxes in D.NON_EUROPEAN_PARTS.values():
            for lon_min, lat_min, lon_max, lat_max in boxes:
                assert -180 <= lon_min < lon_max <= 180
                assert -90 <= lat_min < lat_max <= 90

    def test_a_state_s_code_has_the_state_s_boxes(self) -> None:
        for name, code in (("russia", "ru"), ("spain", "es"), ("france", "fr")):
            assert D.NON_EUROPEAN_PARTS[code] == D.NON_EUROPEAN_PARTS[name]

    def test_every_european_name_the_lookup_files_under_a_european_code_is_listed(self) -> None:
        """`country_lookup.NAME_TO_ISO` is the project's name -> ISO table: a name it files under a
        listed European or Byzantine code is a listed name too."""
        from pipeline.utils.country_lookup import NAME_TO_ISO

        codes = D.EUROPE_ISO_CODES | D.BYZANTIUM_ISO_CODES
        missing = sorted(
            name
            for name, iso in NAME_TO_ISO.items()
            if iso.lower() in codes and name not in D.MEDIEVAL_OLD_WORLD_COUNTRIES
        )
        assert missing == []

    def test_every_name_the_lookup_files_under_a_borderline_code_is_borderline(self) -> None:
        from pipeline.utils.country_lookup import NAME_TO_ISO

        codes = {c for c in D.LABEL_BORDERLINE_COUNTRIES if len(c) == 2}
        missing = sorted(
            name
            for name, iso in NAME_TO_ISO.items()
            if iso.lower() in codes and name not in D.LABEL_BORDERLINE_COUNTRIES
        )
        assert missing == []


class TestTheCutoff:
    def test_the_cutoffs(self) -> None:
        assert D.LABEL_CUTOFFS == {
            D.OCEANIA: 1500,
            D.AMERICAS: 1500,
            D.UNPLACED_OLD_WORLD: 500,
            D.MEDIEVAL_OLD_WORLD: 500,
            D.REST_OF_WORLD: 1500,
        }

    @pytest.mark.parametrize(
        ("record", "passes"),
        [
            (row("Cambodia", 13.45, 103.86, 1100), True),  # Preah Palilay: back in (D58)
            (row("Indonesia", -7.75, 110.49, 850), True),  # Prambanan
            (row("Ethiopia", 12.03, 39.04, 1200), True),  # Lalibela
            (row("Japan", 34.47, 135.81, 1500), True),  # "through" 1500 AD
            (row("Japan", 34.69, 135.53, 1583), False),  # Osaka Castle stays out
            (row("Pakistan", 31.62, 74.30, 1627), False),  # the Tomb of Jahangir stays out
            (row("Poland", 51.56, 15.52, 1000), False),  # Chrobry: Europe
            (row("Poland", 51.56, 15.52, 500), True),
            (row("Türkiye", 37.18, 40.95, 750), True),  # Dara: borderline, the window keeps it
            (row("Türkiye", 37.18, 40.95, 1600), False),  # past 1500
            (row("Cyprus", 35.1, 33.4, 600), False),
            (row("Russia", 58.72, 57.64, 1000), False),  # European Russia
            (row("Russia", 43.07, 132.68, 698), True),  # Asian Russia
            (row("Spain", 28.1, -15.4, 1200), True),  # the Canaries before the conquest
            (row("Lebanon", 33.58, 35.61, 975), True),  # borderline: the window keeps it
            (row("Greenland", 61.16, -45.43, 1300), True),
            (row("Australia", -37.21, 144.81, 1501), False),
            (row(None, 51.0, 15.0, 1200), False),  # no country: the Old World's 500 AD
            (row(None, 51.0, 15.0, 500), True),
            (row(None, 20.0, -100.0, 1200), True),  # the Americas need no country
            (row("Poland", 51.0, 15.0, None), True),  # no date: included
            (row("Poland", None, None, 3000), True),  # no longitude: included
        ],
    )
    def test_passes_date_cutoff(self, record: dict, passes: bool) -> None:
        assert D.passes_date_cutoff(record) is passes

    def test_period_end_decides_before_period_start(self) -> None:
        record = row("Cambodia", 13.45, 103.86, 1100)
        record["period_end"] = 1600
        assert not D.passes_date_cutoff(record)
        record["period_end"] = 0  # a 0 end falls through to the start, as `or` reads it
        assert D.passes_date_cutoff(record)

    def test_the_label_rule_keeps_what_e3_cut(self) -> None:
        """The difference D58 makes: a non-European site of 500-1500 passes now, failed before."""
        prambanan = row("Indonesia", -7.75, 110.49, 850)
        assert D.passes_date_cutoff(prambanan) and not D.passes_e3_cutoff(prambanan)
        chrobry = row("Poland", 51.56, 15.52, 1000)
        assert not D.passes_date_cutoff(chrobry) and not D.passes_e3_cutoff(chrobry)

    def test_the_loader_the_prospector_and_lyra_use_the_one_rule(self) -> None:
        from pipeline import unified_loader
        from pipeline.lyra import site_identifier
        from pipeline.lyra.prospector import extract_radar, resolve

        for module in (unified_loader, site_identifier, extract_radar, resolve):
            assert module.label_scope is D.label_scope
            assert not hasattr(module, "passes_date_cutoff"), module.__name__


class TestTheBorderline:
    @pytest.mark.parametrize(
        ("record", "borderline"),
        [
            (row("Lebanon", 33.58, 35.61, 975), True),  # the Fortress of Niha
            (row("Syria", 34.76, 36.29, 1142), True),  # a Crusader castle's date
            (row("Israel", 31.78, 35.23, 600), True),  # Byzantine Jerusalem
            (row("Egypt", 28.56, 33.98, 565), True),  # Saint Catherine's Monastery
            (row("Georgia", 41.84, 44.72, 1100), True),
            (row("Greenland", 61.16, -45.43, 1300), True),  # Hvalsey: Norse
            (row("Egypt", 29.98, 31.13, -2560), False),  # Giza: before 500
            (row("Egypt", 30.04, 31.26, 1600), False),  # past 1500: the window decides
            (row("Lebanon", 33.58, 35.61, 500), False),  # 500 itself is in every window
            (row("Iraq", 33.09, 44.58, 600), False),  # never Byzantine
            (row("Türkiye", 37.18, 40.95, 750), True),  # Dara: Byzantine
            (row("Turkey", 41.0, 28.98, 537), True),  # Hagia Sophia: Byzantine
            (row("TR", 40.5, 43.57, 1001), True),  # Ani: Armenian - the subject decides
            (row("Türkiye", 37.18, 40.95, 400), False),  # before 500
            (row("Cyprus", 35.1, 33.4, 600), False),  # the region decides: out
            (row("Lebanon", 33.58, 35.61, None), False),
            (row("Lebanon", None, None, 975), False),
        ],
    )
    def test_label_borderline(self, record: dict, borderline: bool) -> None:
        assert D.label_borderline(record) is borderline


class TestTheLabelScope:
    """`label_scope`: the whole rule for a path that admits a record without a verdict."""

    L_ANSE = row("Canada", 51.60, -55.53, 1000)

    def test_l_anse_aux_meadows_is_out_by_its_subject(self) -> None:
        """D58: the Americas' window keeps a Newfoundland site of 1000 AD; the Viking settlement is
        out by its item."""
        assert D.VIKING_SUBJECT_QIDS == {"Q189113": "L'Anse aux Meadows"}
        assert D.passes_date_cutoff(self.L_ANSE)
        assert D.label_scope(self.L_ANSE, ("Q189113",)) == D.LABEL_OUT_OF_SCOPE
        assert D.label_scope(self.L_ANSE, (None, "Q1", "Q189113")) == D.LABEL_OUT_OF_SCOPE
        undated = row(None, None, None, None)
        assert D.label_scope(undated, ("Q189113",)) == D.LABEL_OUT_OF_SCOPE
        assert D.label_scope(self.L_ANSE, ("Q1",)) == D.LABEL_IN_SCOPE
        assert D.label_scope(self.L_ANSE) == D.LABEL_IN_SCOPE

    @pytest.mark.parametrize(
        ("record", "answer"),
        [
            (row("Indonesia", -7.75, 110.49, 850), D.LABEL_IN_SCOPE),  # Prambanan
            (row("Poland", 51.56, 15.52, 1000), D.LABEL_OUT_OF_SCOPE),  # Chrobry: Europe
            (row("Japan", 34.69, 135.53, 1583), D.LABEL_OUT_OF_SCOPE),  # Osaka Castle
            (row("Syria", 34.76, 36.29, 1142), D.LABEL_QUESTION),  # Krak des Chevaliers' date
            (row("Greenland", 61.16, -45.43, 1300), D.LABEL_QUESTION),  # Hvalsey: Norse
            (row("Türkiye", 37.18, 40.95, 750), D.LABEL_QUESTION),  # Dara
            (row("Syria", 34.76, 36.29, 300), D.LABEL_IN_SCOPE),  # before 500: no question
            (row("Syria", 34.76, 36.29, 1600), D.LABEL_OUT_OF_SCOPE),
            (row("Poland", 51.0, 15.0, None), D.LABEL_IN_SCOPE),  # no date: included
        ],
    )
    def test_label_scope(self, record: dict, answer: str) -> None:
        assert D.label_scope(record) == answer

    def test_viking_subjects(self) -> None:
        assert D.viking_subjects(["Q189113", None, "", "Q189113", "Q5"]) == ["Q189113"]
        assert D.viking_subjects([]) == []
