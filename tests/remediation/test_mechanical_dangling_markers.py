"""The dangling-markers lane: a `[N]` of the description that has no citation entry is taken out of
the text, and the lane-L provenance hash is moved with it (`scripts/remediation/mechanical/
dangling_markers.py`, lane `dangling-markers`).

The Phase-6 acceptance's D1 holds when every marker of the description has an entry in
`raw_data.description_citations` and every entry is cited; D4 when `_description_provenance.
desc_sha256` is the sha256 of the description. The orphan-citations lane repaired the entries no
marker cites and listed the sites whose marker has no entry (HUMAN_ONLY D9). The owner's order of
2026-09-25 takes D9's option (b) for the sites Phase 4 held: a marker that points to no source is a
false attribution, so the marker goes and the claims stay - the text keeps its lane-L marking, which
says it is AI-generated. Both cells of a site are written in one transaction, each journalled.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from acceptance.checks import d1, d4  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import citations as C  # noqa: E402
from mechanical import dangling_markers as M  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from phase4.model4 import text_sha256  # noqa: E402

KILLA = "867f08af-8934-4ec0-bbcc-2c730bb2a93a"
AFRODIT = "c0e10d6e-fb0e-4e9c-a910-631da9e578ea"
FIGA = "fe4edbed-be84-4b80-b5de-62ab3e4c88ef"
KUNTUR = "fc514046-4f2c-42b1-a3f6-ca88404d2e18"
ACCI = "89f1d2b7-2579-4c33-82b3-8b58d7857c53"
BASIS = "description differs from pre-March snapshot d4526691 (plan section 15.3)"
SYSTEM = "2026-03 enrichment chain (LLM; model per site not recorded)"


def legacy(description: str) -> dict[str, Any]:
    """Lane L's provenance of `description`, keys in the order Postgres prints them."""
    return {
        "v": 1,
        "ai": "generated",
        "lane": "L",
        "basis": BASIS,
        "ai_system": SYSTEM,
        "desc_sha256": text_sha256(description),
    }


def cite(n: Any, claim: str = "a claim", url: str = "https://whc.unesco.org/en/list/1519/") -> dict:
    return {"n": n, "url": url, "claim": claim, "title": "X", "domain": "whc.unesco.org"}


def pg(value: Any) -> str:
    """A JSON value as Postgres prints jsonb (', ' and ': ', UTF-8)."""
    return json.dumps(value, ensure_ascii=False)


def premise(raw: dict[str, Any]) -> str:
    """`LANE.premise_sql` as Postgres computes it: the provenance without the hash this lane moves."""
    provenance = raw.get("_description_provenance")
    if provenance is None:
        return "null"
    return pg({key: value for key, value in provenance.items() if key != "desc_sha256"})


def site(sid: str, description: str | None, raw: Any, *, name: str = "A site") -> M.Site:
    return M.Site(
        site_id=sid,
        name=name,
        description=description,
        raw_data=None if raw is None else pg(raw),
        premise=premise(raw or {}),
    )


def raw_of(description: str, citations: list[dict] | None) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if citations is not None:
        raw["description_citations"] = citations
    raw["_description_provenance"] = legacy(description)
    return raw


def link(i: int, old: str | None, new: str | None, stamp: str = "phase4l:p4l-1250:chunk-0001"):
    return P.JournalLink(i, stamp, "P4/legacy-provenance", old, new)


APHRODITE = (
    "The Temple of Aphrodite at Aphrodisias is a UNESCO World Heritage Site [1]. The temple "
    "dates to the 3rd century BC [2]. Nearby quarries supplied the workshops [1]. It became a "
    "church around 500 AD [2]."
)
APHRODITE_AFTER = (
    "The Temple of Aphrodite at Aphrodisias is a UNESCO World Heritage Site [1]. The temple "
    "dates to the 3rd century BC. Nearby quarries supplied the workshops [1]. It became a "
    "church around 500 AD."
)
LLAMAS = "Killa Mach'ay is a rock art site in Peru at 3,400 m in Huancavelica Region [1][3][4]."
LLAMAS_AFTER = "Killa Mach'ay is a rock art site in Peru at 3,400 m in Huancavelica Region [1][3]."
LLAMA_ENTRIES = [cite(1, "rock paintings"), cite(2, "3,400 metres"), cite(3, "llamas")]


def plan_of(*sites: M.Site, journal: dict | None = None) -> P.Plan:
    return M.build(
        M.Export(tuple(sites), journal or {}, "2026-09-25 19:40+00"),
        built_at="2026-09-25T19:40:00+00:00",
    )


# ------------------------------------------------------------------------------------ the lane
def test_the_lane_writes_the_description_and_raw_data_of_a_site_in_one_transaction() -> None:
    lane = L.DANGLING_MARKERS
    assert L.LANES[lane.name] is lane and lane.name in L.LANE_READBACKS
    assert lane.target is L.UNIFIED_SITES and not lane.reverses_journal
    assert lane.cells == (L.Column("description", "text"), L.Column("raw_data", "jsonb"))
    assert lane.run_stamp == "2026-09-25_mechanical-dangling-markers"
    assert lane.test_id == "T08/dangling-markers"
    assert lane.lock_timeout == L.LOCK_TIMEOUT and lane.statement_timeout == L.STATEMENT_TIMEOUT
    assert A.lane_dir(lane) == REPO / "output" / "remediation" / "mechanical_dangling_markers"


def test_the_premise_is_the_legacy_provenance_without_the_hash_the_lane_moves() -> None:
    """Guard 5 refuses a site whose provenance is no longer lane L's (a Phase-4 text replaced it),
    and holds on the write and on its reversal alike: the lane moves only `desc_sha256`."""
    assert L.DANGLING_MARKERS.premise_sql == (
        "coalesce((u.raw_data -> '_description_provenance') - 'desc_sha256', 'null'::jsonb)::text"
    )
    raw = raw_of(APHRODITE, [cite(1)])
    moved = {**raw, "_description_provenance": legacy(APHRODITE_AFTER)}
    assert M.premise_of(raw) == M.premise_of(moved) == premise(raw)
    assert M.premise_of({"description_citations": [cite(1)]}) == "null"


def test_the_residual_is_d1_and_the_readback_measures_d4_and_what_the_journal_may_hold() -> None:
    lane = L.DANGLING_MARKERS
    assert lane.post_commit_residual == lane.rehearsal_residual
    assert lane.post_commit_residual == L.ORPHAN_CITATIONS.post_commit_residual
    readback = L.LANE_READBACKS[lane.name]
    for metric in (
        "curated rows with a marker no description_citations entry answers",
        "curated rows with a description_citations entry no marker cites",
        "curated rows whose description is not the one its provenance hashes",
        "journal rows for this run whose description differs in more than markers and whitespace",
        "journal rows for this run whose description gained a marker",
        "journal rows for this run whose raw_data changed more than the citations and the hash",
        "journal rows for this run whose citation array gained an entry",
        "journal rows for this run whose provenance hash is not the description it wrote",
        "journal rows for this run whose provenance is not lane L",
    ):
        assert f"'{metric}'" in readback
    assert readback.endswith("\nORDER BY 1;\n")


def test_every_raw_data_cast_of_the_readback_skips_the_description_rows() -> None:
    """The run journals description rows too, and their text is not JSON: a `::jsonb` on one of
    them raises on production. Only a CASE fixes the order Postgres evaluates the cast in."""
    readback = L.LANE_READBACKS[L.DANGLING_MARKERS.name]
    parts = [p for p in readback.split("UNION ALL") if "journal rows for this run whose" in p]
    casts = [p for p in parts if "::jsonb" in p]
    assert len(casts) == 4
    for part in casts:
        assert "CASE WHEN l.column_name = 'raw_data' THEN" in part and "ELSE false END" in part


def test_the_d4_predicate_is_shared_with_the_orphan_citations_readback() -> None:
    orphan = L.LANE_READBACKS[L.ORPHAN_CITATIONS.name]
    assert L.PROVENANCE_HASH_DIFFERS in orphan
    assert L.PROVENANCE_HASH_DIFFERS in L.LANE_READBACKS[L.DANGLING_MARKERS.name]


# ---------------------------------------------------------------------------- the removal rule
@pytest.mark.parametrize(
    ("text", "dangling", "expected"),
    [
        ("worship [2]. The city", {2}, "worship. The city"),
        ("Region [1][3][4].", {4}, "Region [1][3]."),
        ("Region [4][1].", {4}, "Region [1]."),
        ("Region [4][5].", {4, 5}, "Region."),
        ("the claim [4] and the next [2].", {4}, "the claim and the next [2]."),
        ("A [2]\tB [2].", {2}, "A\tB."),
        ("A line\n[2] and more", {2}, "A line\n and more"),
        ("cost [3,000] and [L]etters [1]", {1}, "cost [3,000] and [L]etters"),
        ("the tenth [10] and the first [1]", {1}, "the tenth [10] and the first"),
    ],
)
def test_a_dangling_marker_goes_with_the_space_before_its_run(
    text: str, dangling: set[int], expected: str
) -> None:
    """The frontend's marker shape (`seo/text.ts` stripCitations: `[^\\S\\n]*\\[\\d+\\]`), taken as a
    run: a run loses exactly its dangling markers, and its space only when no marker is left."""
    assert M.without_dangling(text, dangling) == expected


def test_the_removal_changes_nothing_but_the_tokens_and_the_space_before_them() -> None:
    new = M.without_dangling(APHRODITE, {2})
    assert new == APHRODITE_AFTER
    assert M.removal_faults(APHRODITE, new, {2}) == []
    assert re.sub(r"\s", "", new) == re.sub(r"\s", "", APHRODITE.replace("[2]", ""))


@pytest.mark.parametrize(
    ("old", "new", "dangling", "fault"),
    [
        ("[2] A tomb [1].", " A tomb [1].", {2}, "leading whitespace"),
        ("A tomb ([2]).", "A tomb ().", {2}, "empty brackets"),
        ("A tomb [2].", "A tomb .", {2}, "space before punctuation"),
        ("A  tomb [1].", "A  tomb.", {2}, "the kept markers"),
        ("A tomb [2].", "A tomb, [1].", {2}, "other characters"),
        ("A tomb [2] [1].", "A tomb  [1].", {2}, "double space"),
        ("A tomb [2]", "A tomb ", {2}, "trailing whitespace"),
    ],
)
def test_a_removal_that_is_not_clean_is_named(
    old: str, new: str, dangling: set[int], fault: str
) -> None:
    assert any(fault in named for named in M.removal_faults(old, new, dangling))


# ------------------------------------------------------------------------------ the decision
def test_a_site_d1_holds_on_is_no_candidate() -> None:
    text = "A tomb [1]. A cairn [2]."
    assert M.classify(site(ACCI, text, raw_of(text, [cite(1), cite(2)])), {}) is None
    assert M.classify(site(ACCI, "A tomb.", None), {}) is None


def test_the_orphan_citations_class_is_listed_not_repaired_here() -> None:
    """Entries no marker cites, with every marker answered, are the orphan-citations lane's."""
    text = "A tomb [1]."
    (verdict,) = M.classify(site(KUNTUR, text, raw_of(text, [cite(1), cite(2)])), {})
    assert not verdict.ok and verdict.reason == M.NO_DANGLING and verdict.new_value is None


def test_a_dangling_marker_is_removed_and_the_hash_moves_in_the_same_site() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    verdicts = M.classify(site(AFRODIT, APHRODITE, raw, name="Afrodit Tapınağı"), {})
    assert verdicts is not None and [v.column for v in verdicts] == ["description", "raw_data"]
    text, data = verdicts
    assert text.ok and data.ok
    assert (text.old_value, text.new_value) == (APHRODITE, APHRODITE_AFTER)
    assert (text.rule, text.finding_test_id) == (M.RULE_REMOVED, "T08/marker-without-entry")
    assert data.old_value == pg(raw)
    written = json.loads(str(data.new_value))
    assert written == {**raw, "_description_provenance": legacy(APHRODITE_AFTER)}
    assert list(written) == list(raw) and list(written["_description_provenance"]) == list(
        raw["_description_provenance"]
    )
    assert (data.rule, data.finding_test_id) == (M.RULE_HASH, "D4/provenance-hash")
    assert text.premise == data.premise == premise(raw)
    assert "[2]" in text.note and "HUMAN_ONLY.md D9" in text.note
    quotes = " ".join(e["quote"] for e in text.evidence)
    assert "3rd century BC [2]" in quotes


def test_an_entry_the_removal_leaves_uncited_goes_with_the_orphan_citations_rule() -> None:
    """Killa Mach'ay: [4] has no entry, and entry 2 is cited by nothing. Once [4] is gone the
    site is the orphan-citations lane's `uncited-entries` case, and D1 holds only without it."""
    raw = raw_of(LLAMAS, LLAMA_ENTRIES)
    text, data = M.classify(site(KILLA, LLAMAS, raw, name="Killa Mach'ay"), {})
    assert text.new_value == LLAMAS_AFTER
    written = json.loads(str(data.new_value))
    assert written["description_citations"] == [LLAMA_ENTRIES[0], LLAMA_ENTRIES[2]]
    assert written["_description_provenance"]["desc_sha256"] == text_sha256(LLAMAS_AFTER)
    assert data.rule == M.RULE_HASH_ENTRIES
    assert "3,400 metres" in " ".join(e["quote"] for e in data.evidence)


def test_every_planned_value_passes_the_acceptance_s_d1_and_d4() -> None:
    for sid, description, entries in (
        (AFRODIT, APHRODITE, [cite(1)]),
        (KILLA, LLAMAS, LLAMA_ENTRIES),
        (FIGA, "A shelter [1]. Dated [2]. Tools [3][3]. A survey [4].", [cite(1)]),
    ):
        text, data = M.classify(site(sid, description, raw_of(description, entries)), {})
        written = json.loads(str(data.new_value))
        after = {
            "site_id": sid,
            "description": text.new_value,
            "description_citations": written.get("description_citations"),
            "description_provenance": written["_description_provenance"],
        }
        assert d1(after) is None and d4(after) is None


def test_a_site_with_live_phase4_provenance_is_refused() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    raw["_description_provenance"] = {**legacy(APHRODITE), "lane": "W"}
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), {})
    assert not verdict.ok and verdict.reason == M.PHASE4


def test_a_provenance_that_does_not_read_is_listed() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    raw["_description_provenance"] = {**legacy(APHRODITE), "basis": "a guess"}
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), {})
    assert not verdict.ok and verdict.reason == M.PROVENANCE_NOT_READABLE


def test_a_site_without_the_lane_l_marking_is_refused() -> None:
    """The claims stay because lane L says the text is AI-generated; without it, no removal."""
    raw = {"description_citations": [cite(1)]}
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), {})
    assert not verdict.ok and verdict.reason == M.NO_PROVENANCE


def test_a_provenance_that_already_disagrees_with_the_text_is_listed() -> None:
    raw = raw_of("another text", [cite(1)])
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), {})
    assert not verdict.ok and verdict.reason == M.HASH_DIFFERS


def test_grouped_markers_are_listed() -> None:
    text = "A tomb [1, 2]. A cairn [1]."
    (verdict,) = M.classify(site(AFRODIT, text, raw_of(text, [cite(1)])), {})
    assert not verdict.ok and verdict.reason == M.GROUPED


def test_unreadable_citations_are_listed() -> None:
    raw = {"description_citations": {"n": 1}, "_description_provenance": legacy(APHRODITE)}
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), {})
    assert not verdict.ok and verdict.reason == C.NOT_READABLE


def test_a_removal_that_is_not_clean_is_listed() -> None:
    text = "[2] A tomb [1]."
    (verdict,) = M.classify(site(AFRODIT, text, raw_of(text, [cite(1)])), {})
    assert not verdict.ok and verdict.reason == M.NOT_CLEAN
    assert "leading whitespace" in verdict.note


def test_the_description_journal_must_end_at_the_live_text() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    journal = {(AFRODIT, "description"): (link(7, "old", "another text"),)}
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), journal)
    assert not verdict.ok and verdict.reason == "journal-disagrees"


def test_the_raw_data_journal_is_compared_as_json_and_must_end_at_the_live_value() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    reordered = json.dumps(dict(reversed(list(raw.items()))), separators=(",", ":"))
    ok = M.classify(
        site(AFRODIT, APHRODITE, raw), {(AFRODIT, "raw_data"): (link(9, None, reordered),)}
    )
    assert ok is not None and all(v.ok for v in ok)
    other = {(AFRODIT, "raw_data"): (link(9, None, pg({"description_citations": [cite(2)]})),)}
    (verdict,) = M.classify(site(AFRODIT, APHRODITE, raw), other)
    assert not verdict.ok and verdict.reason == "journal-disagrees"


def test_a_raw_data_the_writer_would_not_print_as_postgres_does_is_listed() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    packed = M.Site(AFRODIT, "x", APHRODITE, json.dumps(raw, separators=(",", ":")), premise(raw))
    (verdict,) = M.classify(packed, {})
    assert not verdict.ok and verdict.reason == C.NOT_REPRINTED


def test_an_export_whose_premise_is_not_its_provenance_is_refused() -> None:
    raw = raw_of(APHRODITE, [cite(1)])
    wrong = M.Site(AFRODIT, "x", APHRODITE, pg(raw), premise=pg({"lane": "W"}))
    with pytest.raises(P.PlanError, match="premise"):
        M.classify(wrong, {})


# ------------------------------------------------------------------------------ the plan
def test_build_plans_both_cells_of_each_site_lists_the_rest_and_counts_both() -> None:
    plan = plan_of(
        site(AFRODIT, APHRODITE, raw_of(APHRODITE, [cite(1)])),
        site(KILLA, LLAMAS, raw_of(LLAMAS, LLAMA_ENTRIES)),
        site(ACCI, "A tomb [1].", raw_of("A tomb [1].", [cite(1)])),
        site(KUNTUR, "A tomb [1].", raw_of("A tomb [1].", [cite(1), cite(2)])),
    )
    assert [(v.site_id, v.column) for v in plan.changes] == [
        (KILLA, "description"),
        (KILLA, "raw_data"),
        (AFRODIT, "description"),
        (AFRODIT, "raw_data"),
    ]
    assert [(v.site_id, v.reason) for v in plan.skipped] == [(KUNTUR, M.NO_DANGLING)]
    assert dict(plan.counters) == {
        "curated": 4,
        "d1_holds": 1,
        "d1_fails": 3,
        "sites_written": 2,
        "cells": 4,
        M.RULE_REMOVED: 2,
        M.RULE_HASH: 1,
        M.RULE_HASH_ENTRIES: 1,
        M.NO_DANGLING: 1,
    }
    assert plan.lane is L.DANGLING_MARKERS


def test_a_plan_on_which_d1_would_still_fail_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(M, "repaired", lambda raw, markers: raw)
    with pytest.raises(P.PlanError, match="D1"):
        plan_of(site(KILLA, LLAMAS, raw_of(LLAMAS, LLAMA_ENTRIES)))


def test_a_plan_on_which_d4_would_fail_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(M, "rewritten", lambda raw, description, markers: raw)
    with pytest.raises(P.PlanError, match="D4"):
        plan_of(site(AFRODIT, APHRODITE, raw_of(APHRODITE, [cite(1)])))


def test_the_plan_is_one_the_framework_renders_and_reverses(tmp_path: Path) -> None:
    plan = plan_of(site(AFRODIT, APHRODITE, raw_of(APHRODITE, [cite(1)])))
    P.write_plan_jsonl(plan, tmp_path / "PLAN.jsonl")
    records = A.load_records(tmp_path / "PLAN.jsonl")
    A.validate_records(records, lane=L.DANGLING_MARKERS)
    sql = A.apply_statement(records, L.DANGLING_MARKERS)
    assert "WHEN 'description' THEN u.description IS DISTINCT FROM p.old_value::text" in sql
    assert "WHEN 'raw_data' THEN u.raw_data IS DISTINCT FROM p.old_value::jsonb" in sql
    assert f"WHERE ({L.DANGLING_MARKERS.premise_sql}) IS DISTINCT FROM p.premise" in sql
    undo = P.reversed_records(records, L.DANGLING_MARKERS)
    assert {(r.site_id, r.column, r.new_value, r.premise) for r in undo} == {
        (r.site_id, r.column, r.old_value, r.premise) for r in records
    }


# ------------------------------------------------------------------------ export and files
def export_text(sites: list[M.Site], journal: list[tuple[str, str, P.JournalLink]]) -> str:
    lines = [json.dumps({"kind": "site", "row": {**s.__dict__}}, ensure_ascii=False) for s in sites]
    for sid, column, j in journal:
        row = {
            "id": j.id,
            "row_pk": sid,
            "column_name": column,
            "run_stamp": j.run_stamp,
            "test_id": j.test_id,
            "old_value": j.old_value,
            "new_value": j.new_value,
        }
        lines.append(json.dumps({"kind": "journal", "row": row}, ensure_ascii=False))
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-09-25 19:40+00"}}))
    return "\n".join(lines) + "\n"


def three_sites() -> list[M.Site]:
    return [
        site(AFRODIT, APHRODITE, raw_of(APHRODITE, [cite(1)])),
        site(KILLA, LLAMAS, raw_of(LLAMAS, LLAMA_ENTRIES)),
        site(ACCI, "A tomb [1].", raw_of("A tomb [1].", [cite(1)])),
    ]


def test_the_export_is_one_read_only_snapshot_of_the_rows_and_both_journals() -> None:
    script = M.export_script()
    assert script.startswith("\\set QUIET on\nBEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
    for needle in (
        "u.raw_data::text AS raw_data",
        L.DANGLING_MARKERS.premise_sql,
        "u.source_id = 'ancient_nerds'",
        "l.column_name IN ('description', 'raw_data')",
    ):
        assert needle in script
    assert not any(word in script.upper() for word in ("UPDATE ", "INSERT ", "DELETE "))


def test_the_export_is_parsed_into_sites_and_each_cell_s_journal_in_id_order() -> None:
    journal = [
        (AFRODIT, "raw_data", link(9, None, pg({"a": 1}))),
        (AFRODIT, "raw_data", link(4, None, pg({"b": 1}))),
        (AFRODIT, "description", link(5, "a", "b")),
    ]
    export = M.parse_export(export_text(three_sites(), journal))
    assert [s.site_id for s in export.sites] == [AFRODIT, KILLA, ACCI]
    assert [j.id for j in export.journal[(AFRODIT, "raw_data")]] == [4, 9]
    assert [j.id for j in export.journal[(AFRODIT, "description")]] == [5]
    assert export.exported_at == "2026-09-25 19:40+00"


def test_write_writes_the_lane_s_files_from_the_export_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "export").mkdir()
    (tmp_path / "export" / "export.jsonl").write_text(
        export_text(three_sites(), []), encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(M, "write_tagged_export", _no_database)
    assert M.main(["--write", "--out", str(tmp_path)]) == 0
    records = A.load_records(tmp_path / "PLAN.jsonl")
    assert len(records) == 4
    P.verify_pinned(
        tmp_path / "ROLLBACK.sql",
        plan_path=tmp_path / "PLAN.jsonl",
        expected=A.rollback_statement(records, L.DANGLING_MARKERS),
    )
    text = (tmp_path / "PLAN.md").read_text(encoding="utf-8")
    assert "3rd century BC [2]." in text and "3rd century BC." in text
    assert "HUMAN_ONLY.md D9" in text


def test_export_reads_production_into_the_lane_s_export_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def export(script: str, path: Path) -> Path:
        sent.append(script)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export_text(three_sites(), []), encoding="utf-8")
        return path

    monkeypatch.setattr(M, "write_tagged_export", export)
    assert M.main(["--export", "--out", str(tmp_path)]) == 0
    assert sent == [M.export_script()]
    assert not (tmp_path / "PLAN.jsonl").exists()


def test_the_committed_plan_removes_only_dangling_markers_and_moves_only_the_hash() -> None:
    """The delivered plan, read cell by cell: each description is its old text less the rule's
    removal, each raw_data its old value with the new hash (and an uncited entry gone)."""
    records = A.load_records(A.lane_dir(L.DANGLING_MARKERS) / "PLAN.jsonl")
    A.validate_records(records, lane=L.DANGLING_MARKERS)
    by_site: dict[str, dict[str, A.ChangeRecord]] = {}
    for r in records:
        by_site.setdefault(r.site_id, {})[str(r.column)] = r
    assert sorted(by_site) == sorted([KILLA, AFRODIT, FIGA])
    for cells in by_site.values():
        text, data = cells["description"], cells["raw_data"]
        old, new = str(text.old_value), str(text.new_value)
        before, after = json.loads(str(data.old_value)), json.loads(str(data.new_value))
        numbers = {e["n"] for e in before["description_citations"]}
        dangling = {int(n) for n in re.findall(r"\[(\d+)\]", old)} - numbers
        assert dangling and new == M.without_dangling(old, dangling)
        assert M.removal_faults(old, new, dangling) == []
        assert after["_description_provenance"] == {
            **before["_description_provenance"],
            "desc_sha256": text_sha256(new),
        }
        assert before["_description_provenance"]["desc_sha256"] == text_sha256(old)
        record = {"site_id": text.site_id, "description": new}
        assert d1({**record, "description_citations": after["description_citations"]}) is None
        assert d4({**record, "description_provenance": after["_description_provenance"]}) is None


def _no_database(*_: Any, **__: Any) -> Any:
    raise AssertionError("--write plans from the export on disk and reads no database")
