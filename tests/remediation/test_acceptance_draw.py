"""Phase 6 item 6: the acceptance draw (`scripts/remediation/acceptance/draw.py`).

The protocol (`output/remediation/acceptance/PROTOCOL.md`) is sealed before the draw; this is the
draw's code, sealed with it. Offline: the four production reads are faked.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from acceptance import draw as D  # noqa: E402
from phase4.audit4 import draw_sample  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402

ACCEPTANCE = REPO / "output" / "remediation" / "acceptance"


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def _frame(n: int = 200) -> list[dict[str, Any]]:
    """n sites spread over the globe, alternating two countries far apart."""
    rows = []
    for i in range(n):
        west = i % 2 == 0
        rows.append(
            {
                "site_id": _uuid(i),
                "name": f"Site {i}",
                "country": "Peru" if west else "Japan",
                "lat": -13.0 + (i % 7) if west else 35.0 + (i % 7),
                "lon": -72.0 if west else 139.0,
            }
        )
    return rows


def _source(tmp_path: Path, name: str, ids: list[str], noise: str = "") -> tuple[str, Path]:
    path = tmp_path / name
    path.write_text(noise + "\n".join(ids) + "\n", encoding="utf-8")
    return name, path


# ------------------------------------------------------------------------------ the frame read
class TestTheFrame:
    def test_the_frame_is_shown_curated_sites_with_a_forward_judged_write(self):
        sql = D.FRAME_SQL
        assert "u.source_id = 'ancient_nerds'" in sql
        assert "u.scope_status IS DISTINCT FROM 'retired'" in sql  # NULL counts as shown
        assert "l.site_id_ref = u.id" in sql
        assert "l.run_stamp NOT LIKE '%-rollback' AND l.run_stamp NOT LIKE '%-probe'" in sql
        for table, column in D.JUDGED_WRITES:
            assert f"('{table}', '{column}')" in sql

    def test_every_judged_field_s_column_puts_a_site_in_the_frame(self):
        columns = set(D.JUDGED_WRITES)
        for pair in (
            ("unified_sites", "description"),
            ("unified_sites", "period_start"),
            ("unified_sites", "scope_status"),
            ("card_stats", "card_description"),
            ("wiki_images", "is_hero"),
        ):
            assert pair in columns
        assert not any(table == "site_external_ids" for table, _ in columns)

    def test_the_values_are_the_page_s_own(self):
        sql = D.VALUES_SQL
        assert "ORDER BY wi.is_hero DESC, wi.is_lead DESC, wi.sort_order" in sql
        assert "wi.is_excluded IS NOT TRUE" in sql
        for column in ("card_description", "description_citations", "_description_provenance"):
            assert column in sql


# ---------------------------------------------------------------------------- the exclusions
class TestTheExclusions:
    def test_every_frame_id_a_source_names_is_excluded_and_recorded(self, tmp_path):
        frame = {_uuid(i) for i in range(10)}
        source = _source(tmp_path, "pilot.jsonl", [_uuid(1), _uuid(2), _uuid(99)], "# note\n")
        excluded, (record,) = D.exclusions(frame, [source])
        assert excluded == {_uuid(1), _uuid(2)}  # 99 is not a frame site
        assert record["frame_ids_removed"] == [_uuid(1), _uuid(2)]
        assert record["sha256"] == hashlib.sha256(source[1].read_bytes()).hexdigest()

    def test_ids_are_read_in_any_case(self, tmp_path):
        _, path = _source(tmp_path, "x.json", [_uuid(3).upper()])
        assert D.ids_in(path) == {_uuid(3)}

    def test_a_missing_source_refuses(self, tmp_path):
        with pytest.raises(D.DrawError, match="does not exist"):
            D.exclusions({_uuid(1)}, [("gone", tmp_path / "gone.txt")])

    def test_the_fixed_sources_are_committed_and_pinned(self):
        """Sealed with the protocol: a source that changes after the seal breaks this test."""
        expected = json.loads((ACCEPTANCE / "EXCLUSIONS.sha256.json").read_text(encoding="utf-8"))
        assert {label for label, _ in D.FIXED_EXCLUSIONS} == set(expected)
        for label, path in D.FIXED_EXCLUSIONS:
            data = (REPO / path).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(data).hexdigest() == expected[label], label

    def test_the_materialised_lists_hold_sixty_sites_each(self):
        for name in ("EXCLUDE_ASSESSMENT_PILOT.txt", "EXCLUDE_OPUS_KEEP_SAMPLE.txt"):
            assert len(D.ids_in(ACCEPTANCE / name)) == 60, name


# ------------------------------------------------------------------------------------ the draw
class TestTheDraw:
    def test_the_draw_is_the_project_s_seeded_draw_over_the_pool(self, tmp_path):
        frame = _frame()
        excluded_ids = [_uuid(i) for i in range(0, 40, 3)]
        result = D.take_draw(frame, [_source(tmp_path, "s.txt", excluded_ids)])
        assert result["drawn"] == draw_sample(
            sorted(r["site_id"] for r in frame),
            seed=D.SEED,
            count=D.SAMPLE_SIZE,
            exclude=set(excluded_ids),
        )
        assert len(result["drawn"]) == D.SAMPLE_SIZE == 60
        assert not set(result["drawn"]) & set(excluded_ids)
        assert D.SEED == 20260925

    def test_the_draw_does_not_depend_on_the_frame_s_order(self, tmp_path):
        frame = _frame()
        a = D.take_draw(frame, [_source(tmp_path, "s.txt", [])])["drawn"]
        b = D.take_draw(list(reversed(frame)), [_source(tmp_path, "s.txt", [])])["drawn"]
        assert a == b

    def test_a_pool_smaller_than_the_sample_refuses(self, tmp_path):
        frame = _frame(70)
        source = _source(tmp_path, "s.txt", [_uuid(i) for i in range(20)])
        with pytest.raises(D.DrawError, match="60 needed"):
            D.take_draw(frame, [source])

    def test_a_frame_that_carries_a_site_twice_refuses(self, tmp_path):
        frame = _frame(80)
        with pytest.raises(D.DrawError, match="twice"):
            D.take_draw(frame + frame[:1], [_source(tmp_path, "s.txt", [])])


# -------------------------------------------------------------------------------- the canaries
class TestTheCanaries:
    def test_ten_distinct_sites_five_countries_five_points(self):
        frame = _frame()
        sample = frame[:60]
        rows = D.canaries(sample, frame)
        assert len(rows) == 10 and len({r["site_id"] for r in rows}) == 10
        assert [r["field"] for r in rows] == ["country"] * 5 + ["coordinates"] * 5
        assert rows == D.canaries(sample, frame)  # deterministic

    def test_a_country_canary_is_another_country_far_away(self):
        frame = _frame()
        # the first undrawn site by id is another country right next to the Peru sites: never a
        # donor, it is too close to be wrong by construction
        frame[60] = dict(frame[60], country="Bolivia", lat=-14.0, lon=-70.0)
        sample = frame[:60]
        by_id = {r["site_id"]: r for r in frame}
        for row in D.canaries(sample, frame):
            if row["field"] != "country":
                continue
            site = by_id[row["site_id"]]
            assert row["canary_value"] != site["country"]
            donor_id = row["why_wrong"].split("frame site ")[1].split(",")[0]
            donor = by_id[donor_id]
            assert donor_id not in {r["site_id"] for r in sample}
            distance = haversine_distance(site["lat"], site["lon"], donor["lat"], donor["lon"])
            assert distance >= D.COUNTRY_CANARY_MIN_KM

    def test_a_coordinate_canary_moves_five_degrees_and_turns_at_the_pole(self):
        assert D.shifted_point(10.0, 20.0) == (15.0, 20.0)
        assert D.shifted_point(82.0, 20.0) == (77.0, 20.0)
        frame = _frame()
        for row in D.canaries(frame[:60], frame):
            if row["field"] == "coordinates":
                lat, lon = (float(x) for x in row["true_stored"].split(","))
                new_lat, new_lon = (float(x) for x in row["canary_value"].split(","))
                assert abs(new_lat - lat) == pytest.approx(5.0) and new_lon == lon

    def test_too_few_eligible_sites_refuses(self):
        frame = _frame()
        sample = [dict(r, country=None) for r in frame[:60]]
        with pytest.raises(D.DrawError, match="10 needed"):
            D.canaries(sample, frame)


# -------------------------------------------------------------------------------- the command
class TestTheCommand:
    def _run(self, tmp_path, monkeypatch, *extra):
        frame = _frame()
        monkeypatch.setattr(D, "read_frame", lambda: frame)

        def values(ids):
            by_id = {r["site_id"]: r for r in frame}
            return [dict(by_id[i], description="text") for i in sorted(ids)]

        monkeypatch.setattr(D, "read_values", values)
        monkeypatch.setattr(
            D, "read_journal_mark", lambda: {"max_id": 40000, "max_applied_at": "t", "rows": 9}
        )
        monkeypatch.setattr(D, "FIXED_EXCLUSIONS", ())
        _, sample_file = _source(tmp_path, "p4-samples.txt", [_uuid(1)])
        out = tmp_path / "draw-2026-10-01"
        args = ["--out", str(out), "--phase4-audit-samples", str(sample_file), *extra]
        return D.main(args), out

    def test_a_draw_writes_its_files_and_pins_them(self, tmp_path, monkeypatch):
        code, out = self._run(tmp_path, monkeypatch)
        assert code == 0
        summary = json.loads((out / "DRAW.json").read_text(encoding="utf-8"))
        for name, digest in summary["sha256"].items():
            assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest, name
        assert summary["sample_size"] == 60 and summary["canaries"] == 10
        assert summary["journal_at_draw"]["max_id"] == 40000  # a later write voids the run
        assert (
            summary["draw_py_sha256"] == hashlib.sha256(Path(D.__file__).read_bytes()).hexdigest()
        )
        drawn = [
            json.loads(line)["site_id"] for line in (out / "SAMPLE.jsonl").read_text().splitlines()
        ]
        assert _uuid(1) not in drawn  # the Phase-4 audit sample is excluded

    def test_a_draw_is_taken_once(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch)[0] == 0
        code, _ = self._run(tmp_path, monkeypatch)
        assert code == 1

    def test_the_phase4_audit_samples_are_required(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(D, "read_frame", lambda: pytest.fail("read before the refusal"))
        assert D.main(["--out", str(tmp_path / "draw-x")]) == 1
        assert "Phase-4 audit" in capsys.readouterr().err


# ------------------------------------------------------------------------------------ the seal
def test_the_seal_holds():
    """PROTOCOL.md, draw.py and the draw's fixed inputs are what AUDIT_LOG sealed (LF bytes).
    Any edit after the seal fails here: a changed protocol is a new seal, recorded as such."""
    seal = json.loads((ACCEPTANCE / "SEAL.json").read_text(encoding="utf-8"))
    assert len(seal["sha256"]) == 5
    for path, digest in seal["sha256"].items():
        data = (REPO / path).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, path
    log = (REPO / "output" / "remediation" / "AUDIT_LOG.md").read_text(encoding="utf-8")
    for digest in seal["sha256"].values():
        assert digest in log  # recorded before the draw
