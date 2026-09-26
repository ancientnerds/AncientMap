"""The orphan-citations lane: citation entries that no `[N]` of the description cites are taken
out of `raw_data` (`scripts/remediation/mechanical/citations.py`, lane `orphan-citations`).

The Phase-6 acceptance's D1 (`acceptance/checks.py`) holds when every marker of the description
has an entry in `raw_data.description_citations` and every entry is cited. The lane repairs the
half the data can settle: an entry no marker cites cites nothing, and the interactive popup lists
every entry as a source of the text all the same. A marker without an entry needs a source nobody
has, or a text edit: such a site is listed for a human and nothing of it is written. The planner is
a pure function of one read-only export; its values are read against the acceptance's own D1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from acceptance.checks import d1  # noqa: E402
from census.tests import t08_citation_markers as T08  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import citations as C  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from phase4.model4 import text_sha256  # noqa: E402

KUNTUR = "fc514046-4f2c-42b1-a3f6-ca88404d2e18"
KINAL = "56f6f878-19b8-4098-8e60-347661302422"
LAUS = "1c899f53-4414-4954-821d-9119802aa39a"
ABSALOM = "fb9e7ccb-2ffd-4bb8-a78d-1e2993881090"
LYRE = "0b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e"
HUICHUN = "2a1d1dfb-474c-44db-a3ea-81758fadf851"
PROVENANCE = {
    "v": 1,
    "ai": "generated",
    "lane": "L",
    "basis": "description differs from pre-March snapshot d4526691 (plan section 15.3)",
    "ai_system": "2026-03 enrichment chain (LLM; model per site not recorded)",
    "desc_sha256": "ab" * 32,
}
PLAIN = "Kuntur Amaya is a necropolis in Bolivia. It was declared a National Monument in 2006."


def cite(n: Any, claim: str = "a claim", url: str = "https://en.wikipedia.org/wiki/X") -> dict:
    return {"n": n, "url": url, "claim": claim, "title": "X", "domain": "en.wikipedia.org"}


def pg(value: Any) -> str:
    """A JSON value as Postgres prints jsonb (', ' and ': ', UTF-8)."""
    return json.dumps(value, ensure_ascii=False)


def site(sid: str, description: str | None, raw: Any, *, name: str = "A site") -> C.Site:
    return C.Site(
        site_id=sid,
        name=name,
        description=description,
        raw_data=None if raw is None else pg(raw),
        premise=text_sha256(description or ""),
    )


def link(i: int, old: str | None, new: str | None, stamp: str = "phase4l:p4l-1001:chunk-0001"):
    return P.JournalLink(i, stamp, "P4/legacy-provenance", old, new)


def d1_after(verdict: P.Verdict, description: str) -> str | None:
    """The acceptance's D1 on the written value."""
    raw = json.loads(str(verdict.new_value))
    return d1(
        {
            "site_id": verdict.site_id,
            "description": description,
            "description_citations": raw.get("description_citations"),
        }
    )


# ------------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_the_lane_writes_one_jsonb_cell_conditioned_on_the_description(self) -> None:
        lane = L.ORPHAN_CITATIONS
        assert L.LANES[lane.name] is lane and lane.name in L.LANE_READBACKS
        assert lane.target is L.UNIFIED_SITES
        assert lane.cells == (L.Column("raw_data", "jsonb"),)
        assert not lane.reverses_journal and lane.columns == ("raw_data",)
        assert (
            lane.premise_sql
            == "encode(sha256(convert_to(coalesce(u.description, ''), 'UTF8')), 'hex')"
        )
        assert lane.lock_timeout == L.LOCK_TIMEOUT and lane.statement_timeout == L.STATEMENT_TIMEOUT
        assert lane.out_dir_name == "mechanical_citations"
        assert A.lane_dir(lane) == REPO / "output" / "remediation" / "mechanical_citations"

    def test_the_premise_is_the_description_s_sha256_as_the_provenance_pins_it(self) -> None:
        """`text_sha256` is Postgres's `encode(sha256(convert_to(text, 'UTF8')), 'hex')` - the form
        of `_description_provenance.desc_sha256`, so a lane-L site's premise is its pin."""
        text = "Ağbulaq – a necropolis"
        assert C.premise_of(text) == text_sha256(text)
        assert C.premise_of(None) == text_sha256("")

    def test_the_residual_is_d1_read_with_the_census_marker(self) -> None:
        predicate = L.ORPHAN_CITATIONS.post_commit_residual.predicate
        assert T08._MARKER_RE.pattern in predicate
        assert L.ORPHAN_CITATIONS.rehearsal_residual == L.ORPHAN_CITATIONS.post_commit_residual
        assert L.CITATIONS_UNCITED in predicate and L.CITATIONS_UNANSWERED in predicate
        assert " OR " in predicate

    def test_the_readback_measures_both_halves_and_that_nothing_else_moved(self) -> None:
        readback = L.LANE_READBACKS[L.ORPHAN_CITATIONS.name]
        for metric in (
            "curated rows with a description_citations entry no marker cites",
            "curated rows with a marker no description_citations entry answers",
            "curated rows whose description is not the one its provenance hashes",
            "journal rows for this run that changed a raw_data key other than "
            "description_citations",
            "journal rows for this run that added a citation entry",
        ):
            assert f"'{metric}'" in readback
        assert readback.endswith("\nORDER BY 1;\n")


# ------------------------------------------------------------------------------ the decision
class TestTheDecision:
    def test_a_site_d1_holds_on_is_no_candidate(self) -> None:
        cited = "A tomb [1]. A cairn [2]."
        assert (
            C.classify(site(KUNTUR, cited, {"description_citations": [cite(1), cite(2)]}), ())
            is None
        )
        assert C.classify(site(KUNTUR, PLAIN, None), ()) is None
        assert C.classify(site(KUNTUR, PLAIN, {"_description_provenance": PROVENANCE}), ()) is None
        gap = "A tomb [1]. A cairn [3]."
        assert (
            C.classify(site(KUNTUR, gap, {"description_citations": [cite(1), cite(3)]}), ()) is None
        )

    def test_entries_of_a_text_without_markers_go_with_their_key_and_nothing_else_moves(
        self,
    ) -> None:
        raw = {"description_citations": [cite(1)], "_description_provenance": PROVENANCE}
        verdict = C.classify(site(KUNTUR, PLAIN, raw, name="Kuntur Amaya"), ())
        assert verdict is not None and verdict.ok
        assert (verdict.rule, verdict.column, verdict.finding_test_id) == (
            C.RULE_NO_MARKERS,
            "raw_data",
            "T08/no-markers",
        )
        assert verdict.old_value == pg(raw)
        assert verdict.new_value == pg({"_description_provenance": PROVENANCE})
        assert verdict.premise == text_sha256(PLAIN)
        assert d1_after(verdict, PLAIN) is None
        assert any("https://en.wikipedia.org/wiki/X" in e["quote"] for e in verdict.evidence)

    def test_an_array_that_was_the_only_key_leaves_an_empty_object(self) -> None:
        verdict = C.classify(site(HUICHUN, PLAIN, {"description_citations": [cite(1)]}), ())
        assert verdict is not None and verdict.ok and verdict.new_value == "{}"

    def test_uncited_entries_go_and_the_cited_stay_byte_for_byte(self) -> None:
        text = "Kinal is a Maya site [1][2]. It was found in the 1960s [1][2]."
        entries = [cite(1, "first"), cite(2, "second"), cite(3, "Discovered in the 1960s")]
        raw = {"description_citations": entries, "_description_provenance": PROVENANCE}
        verdict = C.classify(site(KINAL, text, raw), ())
        assert verdict is not None and verdict.ok
        assert (verdict.rule, verdict.finding_test_id) == (C.RULE_UNCITED, "T08/entry-never-cited")
        written = json.loads(str(verdict.new_value))
        assert written == {
            "description_citations": entries[:2],
            "_description_provenance": PROVENANCE,
        }
        assert list(written) == list(raw)
        assert d1_after(verdict, text) is None
        assert "Discovered in the 1960s" in " ".join(e["quote"] for e in verdict.evidence)

    def test_a_numbering_gap_stays_the_text_is_never_renumbered(self) -> None:
        text = "A cairn [1]. A cist [3]."
        raw = {"description_citations": [cite(1), cite(2), cite(3)]}
        verdict = C.classify(site(KINAL, text, raw), ())
        assert verdict is not None and verdict.ok
        assert [e["n"] for e in json.loads(str(verdict.new_value))["description_citations"]] == [
            1,
            3,
        ]

    def test_a_marker_without_an_entry_is_listed_and_nothing_of_the_site_is_written(self) -> None:
        text = "Laüs was a colony [1][2]. The site lies east of Marcellina [3]."
        verdict = C.classify(site(LAUS, text, {"description_citations": [cite(1), cite(2)]}), ())
        assert verdict is not None and not verdict.ok
        assert verdict.reason == C.MARKER_WITHOUT_ENTRY and verdict.new_value is None
        assert "[3]" in verdict.note and "east of Marcellina" in " ".join(
            e["quote"] for e in verdict.evidence
        )

    def test_a_site_with_both_halves_is_listed_whole_not_repaired_in_part(self) -> None:
        """Absalom's Tomb: the entries no marker cites (4, 5) carry the claims of the sentences
        marked [6], [7] - dropping them would destroy what a human needs to renumber."""
        text = "A tomb [1][6]. Dated to the 1st century AD [3]. An inscription [7]. Near [2]."
        entries = [cite(n) for n in range(1, 7)]
        verdict = C.classify(site(ABSALOM, text, {"description_citations": entries}), ())
        assert verdict is not None and not verdict.ok
        assert verdict.reason == C.MARKER_WITHOUT_ENTRY
        assert "[7]" in verdict.note and "4, 5" in verdict.note

    def test_markers_without_any_citations_are_listed(self) -> None:
        verdict = C.classify(site(LYRE, "A lyre [1].", None), ())
        assert verdict is not None and not verdict.ok and verdict.reason == C.MARKER_WITHOUT_ENTRY

    @pytest.mark.parametrize("citations", [{"n": 1}, [{"n": "1"}], [{"n": True}], ["[1] a string"]])
    def test_unreadable_citations_are_listed(self, citations: Any) -> None:
        verdict = C.classify(site(LYRE, PLAIN, {"description_citations": citations}), ())
        assert verdict is not None and not verdict.ok and verdict.reason == C.NOT_READABLE

    def test_the_raw_data_journal_is_compared_as_json(self) -> None:
        """Postgres prints jsonb keys in its own order: a journal row written in another order or
        spacing is the same value, not a break."""
        raw = {"description_citations": [cite(1)], "_description_provenance": PROVENANCE}
        before = {"description_citations": [cite(1)]}
        reordered = json.dumps(
            {"_description_provenance": PROVENANCE, "description_citations": [cite(1)]},
            separators=(",", ":"),
        )
        verdict = C.classify(site(KUNTUR, PLAIN, raw), (link(9, pg(before), reordered),))
        assert verdict is not None and verdict.ok

    def test_a_journal_that_does_not_end_at_the_live_value_is_listed(self) -> None:
        raw = {"description_citations": [cite(1)], "_description_provenance": PROVENANCE}
        other = pg({"description_citations": [cite(2)]})
        verdict = C.classify(site(KUNTUR, PLAIN, raw), (link(9, None, other),))
        assert verdict is not None and not verdict.ok and verdict.reason == "journal-disagrees"
        broken = (link(9, None, pg({"a": 1})), link(12, pg({"b": 2}), pg(raw)))
        verdict = C.classify(site(KUNTUR, PLAIN, raw), broken)
        assert verdict is not None and not verdict.ok and verdict.reason == "journal-chain-broken"

    def test_a_raw_data_the_writer_would_not_print_as_postgres_does_is_listed(self) -> None:
        """The journal records the plan's text: it must be Postgres's own print of the value."""
        packed = C.Site(
            site_id=KUNTUR,
            name="Kuntur Amaya",
            description=PLAIN,
            raw_data='{"description_citations":[{"n":1,"url":"https://x.org"}]}',
            premise=text_sha256(PLAIN),
        )
        verdict = C.classify(packed, ())
        assert verdict is not None and not verdict.ok and verdict.reason == C.NOT_REPRINTED


# ------------------------------------------------------------------------------ the plan
def export_text(sites: list[C.Site], journal: list[P.JournalLink] | None = None) -> str:
    lines = [json.dumps({"kind": "site", "row": {**s.__dict__}}, ensure_ascii=False) for s in sites]
    for j in journal or []:
        row = {
            "id": j.id,
            "row_pk": KUNTUR,
            "run_stamp": j.run_stamp,
            "test_id": j.test_id,
            "old_value": j.old_value,
            "new_value": j.new_value,
        }
        lines.append(json.dumps({"kind": "journal", "row": row}, ensure_ascii=False))
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-09-25 16:00+00"}}))
    return "\n".join(lines) + "\n"


def five_sites() -> list[C.Site]:
    return [
        site(KINAL, "A cairn [1].", {"description_citations": [cite(1)]}),
        site(
            KUNTUR,
            PLAIN,
            {"description_citations": [cite(1)], "_description_provenance": PROVENANCE},
        ),
        site(HUICHUN, "A tomb [1].", {"description_citations": [cite(1), cite(2)]}),
        site(LAUS, "A colony [2].", {"description_citations": [cite(1)]}),
        site(LYRE, PLAIN, {"description_citations": {"n": 1}}),
    ]


class TestThePlan:
    def test_the_export_is_one_read_only_snapshot_of_the_curated_rows_and_their_raw_data_journal(
        self,
    ) -> None:
        script = C.export_script()
        assert script.startswith("\\set QUIET on\nBEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        for needle in (
            "u.raw_data::text AS raw_data",
            L.ORPHAN_CITATIONS.premise_sql,
            "u.source_id = 'ancient_nerds'",
            "l.column_name = 'raw_data'",
        ):
            assert needle in script
        assert not any(word in script.upper() for word in ("UPDATE ", "INSERT ", "DELETE "))

    def test_the_export_is_parsed_into_sites_and_each_site_s_journal(self) -> None:
        journal = [link(9, None, pg({"a": 1})), link(4, None, pg({"b": 1}))]
        export = C.parse_export(export_text(five_sites(), journal))
        assert [s.site_id for s in export.sites] == [s.site_id for s in five_sites()]
        assert [j.id for j in export.journal[KUNTUR]] == [4, 9]
        assert export.exported_at == "2026-09-25 16:00+00"

    def test_build_plans_the_repairable_lists_the_rest_and_counts_both(self) -> None:
        plan = C.build(
            C.parse_export(export_text(five_sites())), built_at="2026-09-25T16:00:00+00:00"
        )
        assert [(v.site_id, v.rule) for v in plan.changes] == sorted(
            [(KUNTUR, C.RULE_NO_MARKERS), (HUICHUN, C.RULE_UNCITED)]
        )
        assert sorted((v.site_id, v.reason) for v in plan.skipped) == sorted(
            [(LAUS, C.MARKER_WITHOUT_ENTRY), (LYRE, C.NOT_READABLE)]
        )
        assert dict(plan.counters) == {
            "curated": 5,
            "d1_holds": 1,
            "d1_fails": 4,
            C.RULE_NO_MARKERS: 1,
            C.RULE_UNCITED: 1,
            C.MARKER_WITHOUT_ENTRY: 1,
            C.NOT_READABLE: 1,
        }
        assert plan.lane is L.ORPHAN_CITATIONS

    def test_a_plan_whose_value_would_not_make_d1_hold_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The plan is read against the acceptance's own D1 before anything is written."""
        monkeypatch.setattr(C, "repaired", lambda raw, markers: raw)
        with pytest.raises(P.PlanError, match="D1"):
            C.build(C.parse_export(export_text(five_sites())), built_at="x")

    def test_the_plan_is_one_the_framework_renders_and_reverses(self, tmp_path: Path) -> None:
        plan = C.build(C.parse_export(export_text(five_sites())), built_at="x")
        P.write_plan_jsonl(plan, tmp_path / "PLAN.jsonl")
        records = A.load_records(tmp_path / "PLAN.jsonl")
        A.validate_records(records, lane=L.ORPHAN_CITATIONS)
        sql = A.apply_statement(records, L.ORPHAN_CITATIONS)
        assert "u.raw_data IS DISTINCT FROM p.old_value::jsonb" in sql
        assert f"WHERE ({L.ORPHAN_CITATIONS.premise_sql}) IS DISTINCT FROM p.premise" in sql
        undo = P.reversed_records(records, L.ORPHAN_CITATIONS)
        assert {(r.site_id, r.new_value) for r in undo} == {
            (r.site_id, r.old_value) for r in records
        }

    def test_write_writes_the_lane_s_files_from_the_export_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "export").mkdir()
        (tmp_path / "export" / "export.jsonl").write_text(
            export_text(five_sites()), encoding="utf-8", newline="\n"
        )
        monkeypatch.setattr(C, "write_tagged_export", _no_database)
        assert C.main(["--write", "--out", str(tmp_path)]) == 0
        records = A.load_records(tmp_path / "PLAN.jsonl")
        assert len(records) == 2
        P.verify_pinned(
            tmp_path / "ROLLBACK.sql",
            plan_path=tmp_path / "PLAN.jsonl",
            expected=A.rollback_statement(records, L.ORPHAN_CITATIONS),
        )
        skipped = [
            json.loads(line)
            for line in (tmp_path / "SKIPPED.jsonl").read_text("utf-8").splitlines()
        ]
        assert sorted(s["reason"] for s in skipped) == sorted(
            [C.MARKER_WITHOUT_ENTRY, C.NOT_READABLE]
        )
        text = (tmp_path / "PLAN.md").read_text(encoding="utf-8")
        assert LAUS in text and C.MARKER_WITHOUT_ENTRY in text and "HUMAN_ONLY.md" in text

    def test_export_reads_production_into_the_lane_s_export_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[str] = []

        def export(script: str, path: Path) -> Path:
            sent.append(script)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(export_text(five_sites()), encoding="utf-8")
            return path

        monkeypatch.setattr(C, "write_tagged_export", export)
        assert C.main(["--export", "--out", str(tmp_path)]) == 0
        assert sent == [C.export_script()]
        assert not (tmp_path / "PLAN.jsonl").exists()


def _no_database(*_: Any, **__: Any) -> Any:
    raise AssertionError("--write plans from the export on disk and reads no database")


def test_an_export_whose_premise_is_not_its_description_is_refused() -> None:
    """Audit 2026-09-25 m8: `premise_of` was only ever called by a test, and `classify` never
    compared the export's premise with the description it read - the dangling-markers lane does.
    A premise that is not the description's sha256 means the export is not one snapshot."""
    packed = C.Site(
        site_id=KUNTUR,
        name="Kuntur Amaya",
        description=PLAIN,
        raw_data='{"description_citations":[{"n":1,"url":"https://x.org"}]}',
        premise=text_sha256("another description"),
    )
    with pytest.raises(P.PlanError, match="premise"):
        C.classify(packed, ())
