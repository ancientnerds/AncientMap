"""The WD1 structured-field lane: what the mechanical writer gained for it (2026-09-26).

`Column.clears` (a lane may empty a column: owner decision O6), the `double precision` and
`geometry` cell types (`unified_sites.lat`/`lon`/`geom`), and `SiteInvariant` (a condition every
planned site satisfies after the write, inside the transaction). The existing lanes render byte for
byte as before - pinned in `test_mechanical.py` and `test_mechanical_cells.py`. Each rule here is
asserted by the refusal it produces, so the mechanical mutation sweep can prove each one.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
LANE = L.fields_lane("2026-09-27", 1)


def cell(**over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE,
        "site_name": "a site",
        "old_value": "-2500",
        "new_value": "-1200",
        "rule": "wd1-replace",
        "condition": "x",
        "reason": "fields-wd1 (wd1-replace): -2500 -> -1200",
        "evidence": ({"source": "test", "quote": "x"},),
        "column": "period_start",
    }
    base.update(over)
    return A.ChangeRecord(**base)


def rendered(records: list[A.ChangeRecord], **kw: Any) -> str:
    return A.render_transaction(records, site_ids={r.site_id for r in records}, lane=LANE, **kw)


class TestTheLane:
    def test_a_step_is_a_lane_of_its_own(self) -> None:
        assert LANE.run_stamp == "2026-09-27_fields-wd1-s001"
        assert LANE.rollback_run_stamp == "2026-09-27_fields-wd1-s001-rollback"
        assert LANE.out_dir_name == "fields/wd1/write/2026-09-27/s001"
        assert L.resolve_lane("fields-wd1-2026-09-27b-s012") == L.fields_lane("2026-09-27b", 12)
        assert L.fields_lane("2026-09-27", 2).run_stamp != LANE.run_stamp

    @pytest.mark.parametrize(("wave", "step"), [("27-09-2026", 1), ("2026-09-27", 0), ("x", 3)])
    def test_a_wave_label_and_step_are_checked(self, wave: str, step: int) -> None:
        with pytest.raises(ValueError, match="is not a WD1 wave label"):
            L.fields_lane(wave, step)
        with pytest.raises(KeyError):
            L.resolve_lane(f"fields-wd1-{wave}-s{step}")

    def test_the_cells_and_what_each_may_do(self) -> None:
        cells = {c.name: c for c in LANE.cells}
        assert set(cells) == {"lat", "lon", "geom", "period_start", "period_name", "site_type",
                              "source_url"}  # fmt: skip
        assert not cells["lat"].clears and not cells["lon"].clears
        assert cells["lat"].sql_type == cells["lon"].sql_type == "double precision"
        assert cells["geom"].sql_type == "geometry" and cells["geom"].fills_null
        for name in ("period_start", "period_name", "site_type", "source_url"):
            assert cells[name].clears and cells[name].fills_null
        assert "Temple" in cells["site_type"].allowed_new_values
        assert cells["period_name"].allowed_new_values[0] == "< 4500 BC"
        assert LANE.premise_sql is None

    def test_the_readback_is_the_step_s_own(self) -> None:
        text = A.readback_for(LANE)
        assert "2026-09-27_fields-wd1-s001" in text
        assert "curated rows whose geom is not their point" in text
        assert "journal rows for this run that empty a column" in text

    def test_a_site_invariant_is_checked_before_it_is_spliced(self) -> None:
        with pytest.raises(ValueError, match="cannot be spliced"):
            L.SiteInvariant("it's broken", "true", "geom", ("a", "b", "c"))
        with pytest.raises(ValueError, match="would end the DO block"):
            L.SiteInvariant("broken", "$$ true", "geom", ("a", "b", "c"))
        with pytest.raises(ValueError, match="three values"):
            L.SiteInvariant("broken", "true", "geom", ("a", "b"))
        with pytest.raises(ValueError, match="probes one of the lane's cells"):
            replace(
                LANE, site_invariants=(L.SiteInvariant("broken", "true", "name", ("a", "b", "c")),)
            )
        with pytest.raises(ValueError, match="belong to a cell lane"):
            replace(L.PERIOD_NAME, site_invariants=L.FIELDS_INVARIANTS)


class TestThePlanSideMirror:
    def test_a_clearing_column_may_end_in_null(self) -> None:
        A.validate_records([cell(new_value=None)], lane=LANE)
        A.validate_records([cell(column="source_url", old_value="https://x.org/a", new_value=None)],
                           lane=LANE)  # fmt: skip

    def test_a_column_that_does_not_clear_never_ends_in_null(self) -> None:
        with pytest.raises(P.PlanError, match="never clears a column"):
            A.validate_records([cell(column="lat", old_value="51.5", new_value=None)], lane=LANE)

    def test_null_to_null_is_no_change(self) -> None:
        with pytest.raises(P.PlanError, match="both NULL"):
            A.validate_records([cell(old_value=None, new_value=None)], lane=LANE)

    def test_an_emptied_owned_cell_owns_no_value(self) -> None:
        A.validate_records(
            [cell(column="site_type", old_value="Temple", new_value=None)], lane=LANE
        )
        with pytest.raises(P.PlanError, match="is not a value the"):
            A.validate_records(
                [cell(column="site_type", old_value="Temple", new_value="Pagoda")], lane=LANE
            )

    def test_the_reversal_of_a_clear_restores_the_value(self) -> None:
        undo = cell(old_value=None, new_value="-2500")
        A.validate_records([undo], lane=LANE, rollback=True)
        owned_undo = cell(column="site_type", old_value=None, new_value="Temple")
        A.validate_records([owned_undo], lane=LANE, rollback=True)

    def test_a_double_is_compared_as_a_number(self) -> None:
        with pytest.raises(P.PlanError, match="both"):
            A.validate_records([cell(column="lat", old_value="51.10", new_value="51.1")], lane=LANE)
        with pytest.raises(P.PlanError, match="is not a number"):
            A.validate_records([cell(column="lat", old_value="51.1", new_value="north")], lane=LANE)
        with pytest.raises(P.PlanError, match="not a finite number"):
            A.validate_records([cell(column="lat", old_value="51.1", new_value="nan")], lane=LANE)
        assert A.typed_value(LANE.cell("lat"), "51.10") == A.typed_value(LANE.cell("lat"), "51.1")


class TestTheStatement:
    def test_guard_2_lets_a_clearing_column_end_in_null(self) -> None:
        sql = rendered([cell()])
        assert (
            "WHEN 'period_start' THEN p.new_value::integer IS NOT DISTINCT FROM "
            "p.old_value::integer\n"
        ) in sql
        assert (
            "WHEN 'lat' THEN p.new_value::double precision IS NOT DISTINCT FROM "
            "p.old_value::double precision OR p.new_value IS NULL OR p.old_value IS NULL" in sql
        )
        undo = rendered([cell(old_value="-1200", new_value=None)], rollback=True)
        assert (
            "WHEN 'period_start' THEN p.new_value::integer IS NOT DISTINCT FROM "
            "p.old_value::integer\n"
        ) in undo

    def test_the_site_invariants_run_after_the_write_and_only_on_the_write(self) -> None:
        write = rendered([cell()])
        loop = write.index("END LOOP;")
        for invariant in L.FIELDS_INVARIANTS:
            at = write.index(f"RAISE EXCEPTION 'WD1 field correction: % {invariant.says}', bad;")
            assert at > loop
        assert "FROM _fields_wd1_plan q WHERE q.site_id = p.site_id" in write
        assert "u.geom IS DISTINCT FROM ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326)" in write
        undo = rendered([cell(old_value="-1200", new_value="-2500")], rollback=True)
        assert "site invariant" not in undo

    def test_every_comparison_of_a_coordinate_is_typed(self) -> None:
        sql = rendered([cell(column="lat", old_value="51.1", new_value="51.2")])
        assert "WHEN 'lat' THEN u.lat IS DISTINCT FROM p.old_value::double precision" in sql
        assert "WHEN 'geom' THEN u.geom IS DISTINCT FROM p.old_value::geometry" in sql


class TestTheProbes:
    FOREIGN = {"id": "11111111-1111-1111-1111-111111111111", "name": "elsewhere"}

    def test_each_invariant_gets_a_probe_that_breaks_it(self) -> None:
        records = [
            cell(column="lat", old_value="51.1", new_value="51.2"),
            cell(column="geom", old_value=None, new_value="SRID=4326;POINT(-1 51.2)"),
            cell(column="period_name", old_value="3000 - 1500 BC", new_value="1500 - 500 BC"),
        ]
        probes = {suffix: (mutated, says) for suffix, _n, mutated, says in
                  A.probe_cases(records, LANE, self.FOREIGN)}  # fmt: skip
        mutated, says = probes["invariant-geom"]
        assert mutated[1].new_value == "SRID=4326;POINT(0 0)"
        assert says == L.FIELDS_INVARIANTS[0].says
        mutated, says = probes["invariant-period_name"]
        assert mutated[2].new_value == "< 4500 BC"
        assert A.unprobed_invariants(records, LANE) == []

    def test_a_plan_without_the_probe_column_names_the_invariant_it_cannot_probe(self) -> None:
        records = [cell(column="site_type", old_value="Ruin", new_value="Temple")]
        suffixes = [suffix for suffix, *_ in A.probe_cases(records, LANE, self.FOREIGN)]
        assert not any(s.startswith("invariant-") for s in suffixes)
        assert A.unprobed_invariants(records, LANE) == [i.says for i in L.FIELDS_INVARIANTS]

    def test_the_probe_value_is_neither_the_old_nor_the_new_one(self) -> None:
        records = [cell(column="period_name", old_value="< 4500 BC", new_value="4500 - 3000 BC")]
        probes = {s: m for s, _n, m, _e in A.probe_cases(records, LANE, self.FOREIGN)}
        assert probes["invariant-period_name"][0].new_value == "3000 - 1500 BC"

    def test_a_never_stored_value_exists_for_every_cell_type(self) -> None:
        for name in L.CELL_TYPES:
            assert name in A.NEVER_STORED and name in A.NOT_OWNED
