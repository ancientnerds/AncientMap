"""The provenance markers of a site's period and point (`scripts/remediation/mechanical/field_prov.py`).

`raw_data._period_provenance` and `_coord_provenance` say where a stored value comes from, computed
from the journal and the lanes' decision files and nothing else. DB-less: production is a fixture
export, the SQL is asserted as rendered text. Each rule is asserted by the refusal it produces
(`mechanical/mutation_sweep.py "wd5: a marker"`).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import field_prov as F  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical.plan import SNAPSHOT_KIND, JournalLink, PlanError  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
PERIOD, COORD = F.SPECS["period"], F.SPECS["coord"]
MINIMAX = "minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)"
SONNET = "anthropic/claude-sonnet-5-5 (Claude Code agent)"
FOUND = [{"source": "https://en.wikipedia.org/wiki/X", "quote": "c. 2500 BC", "outcome": "found"}]
RULE_EVIDENCE = (
    {"source": "WD3 decision (derived, round 0, rule:derived_rule.json)", "status": "RULE",
     "model": None, "reasoning": "site_type 'Megalithic stones' lies in 'Neolithic'"},
)  # fmt: skip


def live(**over: Any) -> F.Live:
    base: dict[str, Any] = {
        "site_id": SITE, "name": "Corycus", "scope_status": None, "raw_data": None,
        "period_start": "-2500", "period_name": "3000 - 1500 BC", "lat": "35.1", "lon": "33.4",
        "premise": "-2500|3000 - 1500 BC",
    }  # fmt: skip
    base.update(over)
    return F.Live(**base)


def coord_live(**over: Any) -> F.Live:
    return live(premise="35.1|33.4", **over)


def row(id_: int, column: str = "period_start", confidence: str = "one_source",
        evidence: tuple[dict[str, Any], ...] = tuple(FOUND), old: str | None = None,
        new: str | None = "-2500", stamp: str = "2026-10-04_fields-wd3-s001") -> F.Row:  # fmt: skip
    return F.Row(id_, column, stamp, "WD3/structured-fields", confidence, old, new, tuple(evidence))


def decision(verdict: str, *, model: str | None = SONNET, stored: Any = "-2500", value: Any = None,
             quotes: list[dict[str, Any]] | None = None, field: str = "period_start",
             run: str = "wd5") -> F.Decision:  # fmt: skip
    return F.Decision(run, {"site_id": SITE, "field": field, "decision": verdict, "model": model,
                            "stored": stored, "value": value, "reasoning": "r",
                            "quotes": FOUND if quotes is None else quotes})  # fmt: skip


def classify(rows: list[F.Row], dec: F.Decision | None = None, *, spec: F.Spec = PERIOD,
             site: F.Live | None = None) -> Any:  # fmt: skip
    return F.classify(spec, site or live(), rows, dec)


def kind_of(result: Any) -> str:
    assert isinstance(result, F.Marker), result
    return result.kind


# ------------------------------------------------------------------------------ the lanes
class TestTheLanes:
    def test_a_step_is_a_lane_of_its_own_per_kind(self) -> None:
        period, coord = (
            F.prov_lane("period", "2026-10-20", 3),
            F.prov_lane("coord", "2026-10-20", 3),
        )
        assert period.name == "period-prov-2026-10-20-s003" and period.key_prefix == period.name
        assert period.run_stamp == "2026-10-20_period-prov-s003"
        assert period.test_id == "FP/period-provenance" and coord.test_id == "FP/coord-provenance"
        assert period.out_dir_name == "mechanical_field_prov/period/2026-10-20/s003"
        assert period.plan_table == "_period_prov_plan" and coord.plan_table == "_coord_prov_plan"
        assert period.cells == (L.Column("raw_data", "jsonb", fills_null=True, clears=True),)
        for field in ("name", "run_stamp", "out_dir_name", "plan_table", "test_id", "label"):
            assert getattr(period, field) != getattr(coord, field)
        assert period.run_stamp != F.prov_lane("period", "2026-10-20", 4).run_stamp
        assert period.rollback_run_stamp == "2026-10-20_period-prov-s003-rollback"

    def test_the_name_resolves_through_the_registry_and_its_readback(self) -> None:
        assert L.resolve_lane("period-prov-2026-10-20b-s012") == F.prov_lane(
            "period", "2026-10-20b", 12
        )
        assert L.resolve_lane("coord-prov-2026-10-20-s001") == F.prov_lane("coord", "2026-10-20", 1)
        lane = F.prov_lane("period", "2026-10-20", 1)
        assert A.readback_for(lane) == F.prov_readback(lane)
        assert "_period_provenance" in F.prov_readback(lane)
        assert "not an object" in F.prov_readback(lane) or "hash their value" in F.prov_readback(
            lane
        )

    @pytest.mark.parametrize(
        "name",
        [
            "period-prov-2026-10-20-s1",
            "years-prov-2026-10-20-s001",
            "period-prov-x-s001",
            "period-prov-2026-10-20",
            "coord-prov-2026-10-20-s0001",
        ],
    )
    def test_another_kind_or_a_malformed_name_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            L.resolve_lane(name)
        with pytest.raises(KeyError):
            F.lane_of(name)

    def test_a_wave_label_no_lane_resolves_is_refused(self) -> None:
        with pytest.raises(ValueError, match="wave label"):
            F.prov_lane("period", "20-10-2026", 1)

    def test_a_step_number_is_1_to_999(self) -> None:
        for step in (0, 1000):
            with pytest.raises(ValueError):
                F.step_name(step)

    def test_the_premise_is_the_value_described_and_the_sha_hashes_it(self) -> None:
        assert F.premise_sql(PERIOD) == (
            "coalesce(u.period_start::text, 'NULL') || '|' || coalesce(u.period_name, 'NULL')"
        )
        assert F.premise_sql(COORD) == "u.lat::text || '|' || u.lon::text"
        assert F.sha_sql(COORD, "") == (
            "encode(sha256(convert_to(lat::text || '|' || lon::text, 'UTF8')), 'hex')"
        )
        assert (
            F.sha_of("-2500|3000 - 1500 BC") == hashlib.sha256(b"-2500|3000 - 1500 BC").hexdigest()
        )
        lane = F.prov_lane("period", "2026-10-20", 1)
        assert lane.premise_sql == F.premise_sql(PERIOD)

    def test_the_vocabularies_are_the_owners(self) -> None:
        assert PERIOD.kinds == ("quote", "two_source", "authoritative", "import_kept",
                                "structured", "derived", "band", "undated")  # fmt: skip
        assert COORD.kinds == ("quote", "two_source", "authoritative", "import_kept", "unsourced")
        assert (PERIOD.key, COORD.key) == ("_period_provenance", "_coord_provenance")

    def test_the_lane_checks_the_marker_inside_the_transaction_and_probes_it(self) -> None:
        lane = F.prov_lane("period", "2026-10-20", 1)
        record = A.ChangeRecord(
            site_id=SITE, site_name="a", old_value=None, new_value='{"_period_provenance": {}}',
            rule="period-prov-quote", condition="x", reason="r", evidence=({"source": "t", "quote": "q"},),
            column="raw_data", premise="-2500|3000 - 1500 BC",
        )  # fmt: skip
        sql = A.render_transaction([record], site_ids={SITE}, lane=lane)
        assert "(raw_data IS NOT NULL AND jsonb_typeof(raw_data) <> 'object')" in sql
        assert "hold no period marker of a known kind that hashes their value" in sql
        assert "'no such kind'" not in sql and "'band'" in sql and "'undated'" in sql
        undo = A.render_transaction([record], site_ids={SITE}, lane=lane, rollback=True)
        assert "jsonb_typeof(raw_data) <> 'object'" in undo  # holds after a reversal too
        assert "hold no period marker" not in undo  # a reversal removes the marker
        foreign = {"id": OTHER, "name": "x", "premise": "p"}
        names = [name for name, *_ in A.probe_cases([record], lane, foreign)]
        for wanted in ("guard1-other-source", "guard3-foreign-old-value", "guard5-premise",
                       "invariant-lane", "invariant-raw_data"):  # fmt: skip
            assert wanted in names, (wanted, names)


# ------------------------------------------------------------------------------ the kinds
class TestWhatAMarkerNames:
    def test_an_empty_start_is_undated_and_the_origin_is_the_import_or_the_journal(self) -> None:
        site = live(period_start=None, period_name="Undated", premise="NULL|Undated")
        assert classify([], site=site) == F.Marker(
            "undated", "import", None, F.sha_of("NULL|Undated")
        )
        cleared = row(9, new=None, old="-4000", stamp="2026-10-09_fields-wd5-s001")
        got = classify([cleared], site=site)
        assert (got.kind, got.run, got.journal_id) == ("undated", "2026-10-09_fields-wd5-s001", 9)

    @pytest.mark.parametrize("via", ["derived", "band", "structured"])
    def test_a_rule_row_names_its_rule_and_never_a_quote(self, via: str) -> None:
        evidence = ({**RULE_EVIDENCE[0], "source": f"WD3 decision ({via}, round 0, rule:x)"},)
        for confidence in ("one_source", "two_source", "authoritative"):
            got = classify([row(5, confidence=confidence, evidence=evidence)])
            assert got.kind == via and got.journal_id == 5

    def test_a_rule_row_whose_rule_is_unknown_is_listed(self) -> None:
        odd = ({**RULE_EVIDENCE[0], "source": "WD3 decision (guessed, round 0)"},)
        got = classify([row(5, evidence=odd)])
        assert isinstance(got, F.Refused) and got.reason == "rule-unknown"

    def test_a_rule_made_start_is_a_quote_only_when_claude_kept_it_with_a_found_quote(self) -> None:
        rule_row = row(5, evidence=RULE_EVIDENCE)
        kept = classify([rule_row], decision("keep"))
        assert (kept.kind, kept.run, kept.journal_id) == ("quote", "wd5", None)
        for other in (
            decision("keep", model=MINIMAX),           # a MiniMax keep is no confirmation
            decision("keep", quotes=[]),               # a keep with no quote
            decision("keep", quotes=[{**FOUND[0], "outcome": "not-found"}]),
            decision("keep", stored="-3000"),          # about another value
            decision("replace", value="-2000"),
            decision("unresolved"),
        ):  # fmt: skip
            assert kind_of(classify([rule_row], other)) == "derived", other.row

    def test_a_quote_row_claude_kept_names_the_decisions_run_and_its_own_row(self) -> None:
        got = classify([row(7)], decision("keep"))
        assert (got.kind, got.run, got.journal_id) == ("quote", "wd5", 7)

    @pytest.mark.parametrize(("confidence", "kind"), [("two_source", "two_source"),
                                                      ("authoritative", "authoritative"),
                                                      ("one_source", "quote")])  # fmt: skip
    def test_a_sourced_journal_row_names_its_confidence(self, confidence: str, kind: str) -> None:
        assert kind_of(classify([row(7, confidence=confidence)])) == kind

    def test_one_source_without_a_found_quote_and_unknown_confidences_are_listed(self) -> None:
        bare = classify([row(7, evidence=())])
        assert isinstance(bare, F.Refused) and bare.reason == "no-found-quote"
        unfound = classify([row(7, evidence=({"quote": "q", "outcome": "not-found"},))])
        assert unfound.reason == "no-found-quote"
        odd = classify([row(7, confidence="opus-checked")])
        assert odd.reason == "unknown-confidence" and "opus-checked" in odd.note

    def test_a_value_wd5_withdrew_is_unsourced_whatever_its_confidence_says(self) -> None:
        withdrawal = {"source": "WD5 decision (counted, round 1, x)", "decision": "unresolved",
                      "status": "none", "reasoning": "r"}  # fmt: skip
        point = classify([row(9, column="lat", evidence=(withdrawal,), new="36.5")],
                         spec=COORD, site=coord_live())  # fmt: skip
        assert (point.kind, point.journal_id) == ("unsourced", 9)
        period = classify([row(9, evidence=(withdrawal,))])
        assert isinstance(period, F.Refused) and period.reason == "unsourced-period"

    def test_the_newest_journal_row_decides(self) -> None:
        rows = [row(5, evidence=RULE_EVIDENCE), row(8, confidence="two_source", old="-2500")]
        assert classify(rows).kind == "two_source" and classify(rows).journal_id == 8

    def test_a_minimax_value_is_listed_until_claude_confirmed_it(self) -> None:
        minimax_row = row(6, evidence=({**FOUND[0], "model": MINIMAX},))
        got = classify([minimax_row])
        assert isinstance(got, F.Refused) and got.reason == "minimax-unconfirmed"
        confirmed = classify([minimax_row], decision("keep"))
        assert (confirmed.kind, confirmed.run, confirmed.journal_id) == ("quote", "wd5", None)
        assert (
            classify([minimax_row], decision("keep", model=MINIMAX)).reason == "minimax-unconfirmed"
        )

    def test_a_value_with_no_journal_row_is_the_imports(self) -> None:
        assert classify([]) == F.Marker(
            "import_kept", "import", None, F.sha_of("-2500|3000 - 1500 BC")
        )
        about_other = decision("unresolved", stored="-1000")
        assert kind_of(classify([], about_other)) == "import_kept"  # a decision about another value

    def test_wd1_s_keep_is_the_import_kept_and_a_later_lanes_keep_is_a_quote(self) -> None:
        wd1 = classify([], decision("keep", model=None, run="wd1"))
        assert (wd1.kind, wd1.run) == ("import_kept", "wd1")
        wd5 = classify([], decision("keep"))
        assert (wd5.kind, wd5.run) == ("quote", "wd5")

    def test_a_period_nobody_dated_and_a_minimax_decision_get_no_marker(self) -> None:
        for verdict in ("unresolved", "held", "replace"):
            got = classify([], decision(verdict))
            assert isinstance(got, F.Refused) and got.reason == "unsourced-period"
        assert classify([], decision("keep", model=MINIMAX)).reason == "minimax-unconfirmed"
        assert classify([], decision("unresolved", model=MINIMAX)).reason == "minimax-unconfirmed"

    def test_a_point_nobody_sourced_is_unsourced(self) -> None:
        kw = {"spec": COORD, "site": coord_live()}
        for verdict in ("unresolved", "held"):
            got = classify([], decision(verdict, stored="35.1, 33.4", field="coordinates"), **kw)
            assert got.kind == "unsourced" and got.run == "wd5" and got.journal_id is None
        refused = classify([], decision("replace", stored="35.1, 33.4", value="36.5, 34.1",
                                        field="coordinates"), **kw)  # fmt: skip
        assert refused.kind == "unsourced"  # a better point a guard refused: nothing wrote it
        kept = classify([], decision("keep", stored="35.1, 33.4", field="coordinates"), **kw)
        assert kept.kind == "quote"

    def test_a_point_is_read_from_the_newest_of_lat_and_lon(self) -> None:
        rows = [row(3, "lat", "two_source", new="35.1"), row(9, "lon", "authoritative", new="33.4")]
        got = classify(rows, spec=COORD, site=coord_live())
        assert (got.kind, got.journal_id, got.sha) == ("authoritative", 9, F.sha_of("35.1|33.4"))

    def test_the_marker_is_the_four_keys_and_nothing_else(self) -> None:
        marker = classify([row(7)])
        assert list(marker.as_dict()) == ["kind", "run", "journal_id", "sha"]
        assert marker.as_dict()["sha"] == F.sha_of("-2500|3000 - 1500 BC")


# ------------------------------------------------------------------------------ the plan
def verdict(rows: list[F.Row], dec: F.Decision | None = None, site: F.Live | None = None,
            spec: F.Spec = PERIOD) -> Any:  # fmt: skip
    return F.site_verdict(spec, site or live(), rows, dec, SITE)


class TestTheSiteCell:
    def test_the_marker_is_set_and_every_other_key_stays(self) -> None:
        raw = {"_description_provenance": {"lane": "W"}, "description_citations": [1]}
        out = verdict([row(7)], site=live(raw_data=json.dumps(raw, ensure_ascii=False)))
        assert out.ok and out.column == "raw_data" and out.rule == "period-prov-quote"
        new = json.loads(out.new_value)
        assert new["_description_provenance"] == {"lane": "W"} and new["description_citations"] == [
            1
        ]
        assert new["_period_provenance"] == {"kind": "quote", "run": "2026-10-04_fields-wd3-s001",
                                             "journal_id": 7, "sha": F.sha_of("-2500|3000 - 1500 BC")}  # fmt: skip
        assert out.old_value == json.dumps(raw) and out.premise == "-2500|3000 - 1500 BC"
        assert out.evidence[0]["source"].startswith("remediation_change_log id 7")

    def test_a_site_without_raw_data_gets_an_object_of_the_marker_alone(self) -> None:
        out = verdict([row(7)])
        assert out.ok and out.old_value is None
        assert list(json.loads(out.new_value)) == ["_period_provenance"]

    def test_a_marker_that_is_already_there_is_listed_not_written_again(self) -> None:
        first = verdict([row(7)])
        again = verdict([row(7)], site=live(raw_data=first.new_value))
        assert not again.ok and again.reason == "already-marked"
        stale = F.Marker("derived", "x", None, "0" * 64).as_dict()
        moved = json.dumps({"_period_provenance": stale})
        assert verdict([row(7)], site=live(raw_data=moved)).ok  # a stale marker is replaced

    def test_a_site_that_is_gone_retired_or_oddly_stored_is_listed(self) -> None:
        assert F.site_verdict(PERIOD, None, [], None, SITE).reason == "not-a-curated-site"
        assert verdict([row(7)], site=live(scope_status="retired")).reason == "retired"
        assert verdict([row(7)], site=live(raw_data="[1]")).reason == "raw-data-not-an-object"
        assert verdict([row(7)], site=live(raw_data='{"a":1}')).reason == "raw-data-not-reprinted"

    def test_a_journal_that_does_not_end_at_the_live_value_is_listed(self) -> None:
        assert verdict([row(7, new="-999")]).reason == "journal-disagrees"
        chain = [row(7, old=None, new="-3000"), row(8, old="-2500", new="-2500")]
        assert verdict(chain).reason == "journal-chain-broken"
        point = [row(7, "lat", new="35.2")]
        assert verdict(point, site=coord_live(), spec=COORD).reason == "journal-disagrees"
        # a coordinate is compared as a number: the journal keeps the text a writer gave
        number = [row(7, "lat", "two_source", new="35.10"), row(8, "lon", "two_source", new="33.4")]
        assert verdict(number, site=coord_live(), spec=COORD).ok

    def test_the_raw_data_journal_must_end_at_the_live_raw_data_too(self) -> None:
        raw = '{"a": 1}'
        fine = F.Row(3, "raw_data", "s", "t", "authoritative", None, raw, ())
        assert verdict([row(7), fine], site=live(raw_data=raw)).ok
        wrong = F.Row(3, "raw_data", "s", "t", "authoritative", None, '{"b": 2}', ())
        assert verdict([row(7), wrong], site=live(raw_data=raw)).reason == "journal-disagrees"

    def test_a_listed_site_carries_the_reason_and_no_cell(self) -> None:
        out = verdict([row(7, confidence="opus-checked")])
        assert not out.ok and out.reason == "unknown-confidence" and out.new_value is None


# ------------------------------------------------------------------------------ the decisions
class TestTheDecisions:
    def test_the_latest_file_wins_per_field(self, tmp_path: Path) -> None:
        first, second = tmp_path / "wd3" / "DECISIONS.jsonl", tmp_path / "wd5" / "DECISIONS.jsonl"
        for path, verdict_ in ((first, "unresolved"), (second, "keep")):
            path.parent.mkdir()
            path.write_text(json.dumps({"site_id": SITE, "field": "period_start",
                                        "decision": verdict_}) + "\n", encoding="utf-8")  # fmt: skip
        got = F.read_decisions([first, second])[(SITE, "period_start")]
        assert (got.run, got.verdict) == ("wd5", "keep")
        assert F.read_decisions([second, first])[(SITE, "period_start")].verdict == "unresolved"

    def test_a_missing_file_is_refused_by_name(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError, match="is missing"):
            F.read_decisions([tmp_path / "gone.jsonl"])


# ------------------------------------------------------------------------------ the steps
def tagged(rows: dict[str, list[dict[str, Any]]]) -> str:
    lines = [json.dumps({"kind": kind, "row": r}) for kind, items in rows.items() for r in items]
    lines.append(
        json.dumps({"kind": SNAPSHOT_KIND, "row": {"exported_at": "2026-10-20 10:00:00+00"}})
    )
    return "\n".join(lines) + "\n"


def site_row(site: str, **over: Any) -> dict[str, Any]:
    base = {"site_id": site, "name": "Corycus", "scope_status": None, "source_id": "ancient_nerds",
            "raw_data": None, "period_start": "-2500", "period_name": "3000 - 1500 BC",
            "lat": "35.1", "lon": "33.4", "premise": "-2500|3000 - 1500 BC"}  # fmt: skip
    return {**base, **over}


def journal_row(site: str, id_: int = 7, **over: Any) -> dict[str, Any]:
    base = {"id": id_, "row_pk": site, "column_name": "period_start",
            "run_stamp": "2026-10-04_fields-wd3-s001", "test_id": "WD3/structured-fields",
            "confidence": "one_source", "old_value": None, "new_value": "-2500",
            "evidence": FOUND}  # fmt: skip
    return {**base, **over}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    return tmp_path / "out"


@pytest.fixture
def decisions(tmp_path: Path) -> Path:
    path = tmp_path / "wd5" / "DECISIONS.jsonl"
    path.parent.mkdir()
    path.write_text("", encoding="utf-8")
    return path


class TestTheWaveAndTheSteps:
    @staticmethod
    def reader(sites: list[str]):  # type: ignore[no-untyped-def]
        def read(script: str) -> str:
            if (
                "u.id::text AS site_id FROM unified_sites u WHERE" in script
                and "journal" not in script
            ):
                return tagged({"site": [{"site_id": s} for s in sites]})
            return tagged({"site": [site_row(SITE)], "journal": [journal_row(SITE)]})

        return read

    def test_the_wave_lists_the_unmarked_sites_in_steps_of_100(
        self, tree: Path, decisions: Path
    ) -> None:
        sites = [f"00000000-0000-4000-8000-{n:012d}" for n in range(250)]
        result = F.build_wave(
            "period", "2026-10-20", [decisions], read=self.reader(sites), root=tree
        )
        assert result == {"kind": "period", "wave": "2026-10-20", "sites": 250, "steps": 3}
        record = F.read_wave("period", "2026-10-20", tree)
        assert [len(s) for s in record["steps"]] == [100, 100, 50] and record["steps"][0] == sites[
            :100
        ]
        assert record["decisions"] == {decisions.as_posix(): F.sha256_file(decisions)}

    def test_a_wave_is_planned_once_and_an_edited_one_is_refused(
        self, tree: Path, decisions: Path
    ) -> None:
        F.build_wave("period", "2026-10-20", [decisions], read=self.reader([SITE]), root=tree)
        with pytest.raises(PlanError, match="planned once"):
            F.build_wave("period", "2026-10-20", [decisions], read=self.reader([SITE]), root=tree)
        wave = F.wave_dir("period", "2026-10-20", tree) / F.WAVE_FILE
        wave.write_text(
            wave.read_text(encoding="utf-8").replace('"sites": 1', '"sites": 2'), encoding="utf-8"
        )
        with pytest.raises(PlanError, match="not the pinned wave"):
            F.read_wave("period", "2026-10-20", tree)
        with pytest.raises(PlanError, match="is missing"):
            F.read_wave("period", "2099-01-01", tree)

    def test_a_wave_label_no_lane_resolves_is_refused(self, tree: Path, decisions: Path) -> None:
        with pytest.raises(ValueError, match="wave label"):
            F.build_wave("period", "tomorrow", [decisions], read=self.reader([SITE]), root=tree)

    def test_a_step_is_planned_from_a_fresh_read_and_writes_its_files(
        self, tree: Path, decisions: Path
    ) -> None:
        F.build_wave("period", "2026-10-20", [decisions], read=self.reader([SITE]), root=tree)
        result = F.plan_step("period", "2026-10-20", 1, read=self.reader([SITE]), root=tree)
        assert result["cells"] == 1 and result["kind:quote"] == 1
        out = tree / "period" / "2026-10-20" / "s001"
        plan = json.loads((out / "PLAN.jsonl").read_text(encoding="utf-8"))
        assert plan["column"] == "raw_data" and plan["change_key"] == (
            f"period-prov-2026-10-20-s001:{SITE}:raw_data"
        )
        assert plan["run_stamp"] == "2026-10-20_period-prov-s001"
        assert plan["premise"] == "-2500|3000 - 1500 BC"
        assert "2026-10-20_period-prov-s001-rollback" in (out / "ROLLBACK.sql").read_text(
            encoding="utf-8"
        )
        assert (out / "export.jsonl").exists() and (out / "SKIPPED.jsonl").exists()
        with pytest.raises(PlanError, match="exists"):
            F.plan_step("period", "2026-10-20", 1, read=self.reader([SITE]), root=tree)

    def test_a_step_waits_for_the_one_before_it(self, tree: Path, decisions: Path) -> None:
        sites = [f"00000000-0000-4000-8000-{n:012d}" for n in range(101)]
        F.build_wave("period", "2026-10-20", [decisions], read=self.reader(sites), root=tree)
        with pytest.raises(PlanError, match="step 1 is not accepted"):
            F.plan_step("period", "2026-10-20", 2, read=self.reader([SITE]), root=tree)
        with pytest.raises(PlanError, match="steps 1..2"):
            F.plan_step("period", "2026-10-20", 3, read=self.reader([SITE]), root=tree)

    def test_a_decision_file_that_changed_since_the_wave_is_refused(
        self, tree: Path, decisions: Path
    ) -> None:
        F.build_wave("period", "2026-10-20", [decisions], read=self.reader([SITE]), root=tree)
        decisions.write_text('{"site_id": "x"}\n', encoding="utf-8")
        with pytest.raises(PlanError, match="not the decision file the wave was built from"):
            F.plan_step("period", "2026-10-20", 1, read=self.reader([SITE]), root=tree)

    def test_a_step_holds_at_most_a_hundred_sites(self) -> None:
        many = [f"00000000-0000-4000-8000-{n:012d}" for n in range(101)]
        with pytest.raises(PlanError, match="at most 100"):
            F.build_step(PERIOD, "2026-10-20", 1, many, {}, {}, {}, built_at="t")

    def test_the_counters_name_the_kinds_and_the_reasons(self) -> None:
        sites = {SITE: live(), OTHER: live(site_id=OTHER, scope_status="retired")}
        journal = {SITE: [row(7)], OTHER: [row(8)]}
        built = F.build_step(
            PERIOD, "2026-10-20", 1, [SITE, OTHER], sites, journal, {}, built_at="t"
        )
        assert built.plan.counters == {"cells": 1, "retired": 1, "kind:quote": 1}
        assert built.plan.lane == F.prov_lane("period", "2026-10-20", 1)

    def test_the_acceptance_reads_production_back_and_records_it_once(
        self, tree: Path, decisions: Path
    ) -> None:
        F.build_wave("period", "2026-10-20", [decisions], read=self.reader([SITE]), root=tree)
        F.plan_step("period", "2026-10-20", 1, read=self.reader([SITE]), root=tree)
        lane = F.prov_lane("period", "2026-10-20", 1)
        plan = json.loads(
            (tree / "period" / "2026-10-20" / "s001" / "PLAN.jsonl").read_text(encoding="utf-8")
        )

        def after(**site: Any):  # type: ignore[no-untyped-def]
            def read(script: str) -> str:
                written = {"row_pk": SITE, "column_name": "raw_data", "run_stamp": lane.run_stamp,
                           "old_value": None, "new_value": plan["new_value"]}  # fmt: skip
                return tagged({"site": [site_row(SITE, raw_data=plan["new_value"], **site)],
                               "journal": [written]})  # fmt: skip

            return read

        code, found = F.accept_step("period", "2026-10-20", 1, read=after(), root=tree)
        assert (code, found) == (0, [])
        assert (tree / "period" / "2026-10-20" / "s001" / F.ACCEPTED_FILE).exists()
        # the value moved after the write: the marker no longer hashes it
        code, found = F.accept_step(
            "period", "2026-10-20", 1, read=after(premise="-3000|x"), root=tree
        )
        assert code == 1 and "does not hash the live value" in found[0]

    def test_the_acceptance_names_what_production_lacks(self) -> None:
        lane = F.prov_lane("period", "2026-10-20", 1)
        planned = [{"site_id": SITE, "new_value": '{"_period_provenance": {"sha": "x"}}'}]
        found = F.deviations(PERIOD, lane, planned, {SITE: live()}, [])
        assert any("1 planned" in f for f in found)
        assert any("does not hold the planned value" in f for f in found)
        undone = [{"row_pk": SITE, "run_stamp": lane.rollback_run_stamp}]
        assert any(
            "rollback journal row" in f
            for f in F.deviations(PERIOD, lane, planned, {SITE: live()}, undone)
        )


class TestTheMarkersAreTheJournals:
    def test_a_marker_never_names_a_kind_the_journal_does_not(self) -> None:
        """For every journal confidence and evidence shape, the kind a marker names is in the
        vocabulary, and a rule row is never `quote` whatever its confidence says."""
        evidences = [(), tuple(FOUND), RULE_EVIDENCE, ({**FOUND[0], "model": MINIMAX},)]
        for confidence in ("one_source", "two_source", "authoritative", "opus-checked", ""):
            for evidence in evidences:
                got = classify([row(5, confidence=confidence, evidence=evidence)])
                if isinstance(got, F.Refused):
                    continue
                assert got.kind in PERIOD.kinds
                if any(e.get("status") == "RULE" for e in evidence):
                    assert got.kind in F.RULE_VIA

    def test_no_marker_without_a_row_names_a_sourced_kind_but_the_imports(self) -> None:
        for dec in (None, decision("keep", model=None), decision("keep", quotes=[])):
            assert kind_of(classify([], dec)) in ("import_kept", "quote")
        assert all(
            kind_of(classify([], d)) != "quote" for d in (None, decision("keep", model=None))
        )
