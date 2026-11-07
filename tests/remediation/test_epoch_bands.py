"""The D136 table `EPOCH_BANDS.md` is written from `pipeline.periods.epoch_band` (owner decision
D136, 2026-11-07): one row per epoch, and the countries whose own start lies in another band."""

from __future__ import annotations

from pipeline import periods as P
from scripts.remediation.fields import epoch_bands as EB


def test_the_table_has_one_row_per_epoch() -> None:
    rows = [line for line in EB.table().splitlines() if line.startswith("| ") and "---" not in line]
    assert len(rows) - 1 == len(P.PERIODS)  # less the header row


def test_a_row_names_its_band_its_edge_and_the_countries_in_another_band() -> None:
    row = next(line for line in EB.table().splitlines() if line.startswith("| bronze age |"))
    assert "| 3000 - 1500 BC | -3000 |" in row
    assert "4500 - 3000 BC: " in row and "greece" in row
    assert "1500 - 500 BC: finland" in row


def test_a_country_in_the_conventional_band_is_not_listed() -> None:
    assert "england" not in str(EB.other_bands("bronze age"))
    assert EB.other_bands("victorian") == {}


def test_a_period_word_that_names_another_thing_is_no_epoch_of_the_site() -> None:
    for text, key in [
        ("There is access to the site and The Drift is part of the Viking Way trail.", "viking"),
        ("Telmessos (Hittite: Kuwalapassa) was a city", "hittite"),
        ("petroglyphs, primarily lines, geometric shapes", "geometric"),
        ("situated in the Chavin de Huantar District", "chavin"),
        ("at the entrance to the old Roman tunnel known as the Crypta Neapolitana", "roman"),
        ("Roman Rig", "roman"),
    ]:
        assert EB.names_another_thing(text, key), text
    for text, key in [
        ("Rockbourne Roman Villa is a Roman villa", "roman"),
        ("Cadbury Castle is an Iron Age Hillfort close to Bickleigh", "iron age"),
        ("a sanctuary of the Geometric period", "geometric"),
    ]:
        assert not EB.names_another_thing(text, key), text


def test_a_generic_article_cached_for_a_site_is_not_its_own() -> None:
    assert not EB.shares_a_word("Hillfort", "Dinas Dinlle")
    assert EB.shares_a_word("Dundon Hill Hillfort", "Compton Dundon")
    assert EB.shares_a_word("Kerzérho", "Alignements de Kerzerho")
