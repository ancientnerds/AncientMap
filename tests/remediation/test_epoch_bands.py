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
