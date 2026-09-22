"""Does the discover pass ask every site about its own fields, one field per call, and record what
it could not buy instead of ending the batch?

Piece 5 of the Phase-3 runner. The census flagged 1,813 of the 5,004 sites and left 13 of the 17
sites that hold the 24 known-wrong fields alone, so this pass stops reading findings and starts
reading the snapshot: `plan --from-snapshot` writes one record per site, whose findings are its own
stored values, and `judge` buys one call per (site, field).

The interesting mistakes are not exceptions, they are *silently different* artefacts:

* a plan that is not byte-identical across runs, or that quietly drops a site id it was asked for;
* a value read from the wrong table - `card_description` lives in `card_stats`, and the truth
  fixture's own `stored_in` key is what this suite checks the plan against;
* a site whose whole audit ends because one page was too large, or a field whose evidence never
  arrived being judged as if it had;
* a question that cannot tell a wrong value from a missing one (3 of the 24 truth entries store
  nothing, and 22 (site, field) pairs across the snapshot do too);
* five calls for one site written into one answer file, so four of them are lost.

Each guard below has a test that fails when the guard is removed; the mutation evidence (the
mutation, the failing assertion and the sha256 of the restored file) is in
`output/remediation/phase3_runner/PIECE5.md`.

The plan tests read the *real* snapshot (`output/remediation/snapshot/`) and the real truth fixture
(`output/remediation/gold_standard/`), so a change in either fails here instead of in the paid
recall experiment. Nothing in this file opens a socket or starts a process.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

SNAPSHOT = REPO / "output" / "remediation" / "snapshot"
TRUTH_SITE_IDS = REPO / "output" / "remediation" / "gold_standard" / "truth_sites.txt"
TRUTH_FIELDS = REPO / "output" / "remediation" / "gold_standard" / "truth_fields.json"
WORKLIST = REPO / "output" / "remediation" / "phase3_worklist" / "WORKLIST.jsonl"

#: The snapshot is a production-database export and is **not** in the repository (`.gitignore` line
#: 216), so a CI checkout does not have it. The tests that read it are skipped with a reason there
#: instead of failing - the shape `test_t11.py:56` and `test_gallery_audit.py:169` already use for
#: local artefacts. Every other test in this module builds its own snapshot under `tmp_path`.
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / SP.UNIFIED_SITES_FILE).exists(),
    reason=f"production snapshot not present ({SNAPSHOT})",
)
#: The phase-3 worklist is built from that snapshot and is gitignored as well.
needs_worklist = pytest.mark.skipif(
    not WORKLIST.exists(), reason=f"phase-3 worklist not present ({WORKLIST})"
)
NO_EXTENSIONS = Path(__file__).resolve().parent / "fixtures" / "pi_probe_no_extensions.json"

#: Piece 1's plan anchor, recorded in `PIECE1.md:120-124` and re-measured on 2026-09-21. The
#: snapshot plan is a second plan; the worklist plan's bytes are not allowed to move because of it.
PIECE1_PLAN_SHA256 = "96704b808ae1b29d694806934569bd0265aa369d0b0532a6e6a8f35e4f6c8001"

#: Counts measured on the snapshot of 2026-09-20 (export 20:20:01+02:00, host `ancientnerds`).
SNAPSHOT_SITES = 5_004
SNAPSHOT_QIDS = 4_618
SNAPSHOT_EMPTY_CARDS = 7

#: The one truth site that carries no `site_external_ids` row at all, so it has no Wikidata route.
TRUTH_SITE_WITHOUT_QID = "58a2be59-ec1e-4667-96b9-3313ce406bc1"


# ── helpers ──────────────────────────────────────────────────────────────────────────────────


def _truth_ids() -> list[str]:
    return SP.read_site_ids(TRUTH_SITE_IDS)


def _answer() -> MS.ModelAnswer:
    """The captured settled answer, parsed - the numbers every scripted call replays."""
    lines = NO_EXTENSIONS.read_text(encoding="utf-8").splitlines()
    return MS.parse_stream(lines, source=str(NO_EXTENSIONS))


def _site_record(
    site_id: str = "site-1",
    *,
    name: str = "Cave 1",
    values: dict[str, Any] | None = None,
    qid: str | None = None,
) -> dict[str, Any]:
    """One plan-shaped record: one finding per discover field, values from `values`."""
    actual = dict.fromkeys(SP.DISCOVER_FIELDS, "a value")
    if values:
        actual.update(values)
    record: dict[str, Any] = {
        "findings": [SP.finding_row(name, actual[name]) for name in SP.DISCOVER_FIELDS],
        "name": name,
        "site_id": site_id,
    }
    if qid:
        record["wikidata_qid"] = qid
    return record


def _planned_row(record: dict[str, Any], field: str) -> dict[str, Any]:
    """The plan's own finding for one field of one record (the plan writes a list, in field order)."""
    rows = [row for row in record["findings"] if row["field"] == field]
    assert len(rows) == 1, f"{record['site_id']}: {len(rows)} findings for {field!r}"
    return rows[0]


def _batch(*sites: dict[str, Any]) -> dict[str, Any]:
    return {"batch_id": "batch-0001", "ordinal": 1, "pass": R.DISCOVER_PASS, "sites": list(sites)}


def _evidence_store(root: Path, *sites: str, chars: int = 40) -> F.EvidenceStore:
    """An evidence store with one enwiki page per named site."""
    store = F.EvidenceStore(root)
    for site_id in sites:
        path = store.path_for(site_id, F.FEATURE_ENWIKI)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Cave text " + "x" * chars, encoding="utf-8")
    return store


class ScriptedRunner:
    """A fake runner: counts the calls and returns a text that names the call. No process."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls: list[MS.ModelCall] = []
        self.answer = _answer()

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        return MS.ModelAnswer(text=f"VERDICT: CORRECT - {call.label}", usage=self.answer.usage)


class ReviewingRunner(ScriptedRunner):
    """The same scripted call, answering the reviewer's question instead of a field's."""

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        return MS.ModelAnswer(
            text="REFUTED: NO\nWHY: the page says exactly what the record says\n",
            usage=self.answer.usage,
        )


def _assert_no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything starts a Pi process. Used by every dry-run path."""

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(f"a dry run must not start a process: {args!r} {kwargs!r}")

    monkeypatch.setattr(MS.subprocess, "run", refuse)


def _prepared_discover_run(
    tmp_path: Path, *sites: dict[str, Any], batch_id: str = "batch-0001"
) -> Path:
    """A run directory holding one prepared discover batch, exactly as `prepare` would write it."""
    run_dir = tmp_path / "runs"
    batch_dir = run_dir / batch_id
    batch_dir.mkdir(parents=True)
    payload = {"batch_id": batch_id, "ordinal": 1, "pass": R.DISCOVER_PASS, "sites": list(sites)}
    (batch_dir / "input.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return run_dir


def _tiny_snapshot(
    tmp_path: Path,
    *,
    unified: list[dict[str, Any]],
    cards: list[dict[str, Any]] | None = None,
    external: list[dict[str, Any]] | None = None,
) -> Path:
    """A snapshot directory built by hand, for the input shapes the real export happens to lack.

    Every file holds at least one row unless a test asks for less: `read_snapshot_jsonl` refuses an
    empty export, so a hand-built snapshot that is empty everywhere would exercise that refusal
    instead of the shape the test is about.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)

    def write(name: str, rows: list[dict[str, Any]]) -> None:
        with gzip.open(tmp_path / name, "wt", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    write(SP.UNIFIED_SITES_FILE, unified)
    write(
        SP.CARD_STATS_FILE,
        cards if cards is not None else [{"card_description": "A card", "site_id": "site-1"}],
    )
    write(
        SP.SITE_EXTERNAL_IDS_FILE,
        external
        if external is not None
        else [{"kind": "enwiki_title", "site_id": "site-1", "value": "Cave 1"}],
    )
    return tmp_path


def _plan(tmp_path: Path, *args: str) -> Path:
    out = tmp_path / "plan.jsonl"
    assert R.main(["plan", "--from-snapshot", "--out", str(out), *args]) == 0
    return out


# ── the plan: deterministic, complete, and reading the right table ───────────────────────────


@needs_snapshot
def test_the_snapshot_plan_is_byte_identical_across_runs_and_covers_all_5004_sites(
    tmp_path: Path,
) -> None:
    first = _plan(tmp_path, "--snapshot-dir", str(SNAPSHOT))
    second = tmp_path / "second.jsonl"
    assert (
        R.main(
            [
                "plan",
                "--from-snapshot",
                "--snapshot-dir",
                str(SNAPSHOT),
                "--out",
                str(second),
            ]
        )
        == 0
    )

    one, two = first.read_bytes(), second.read_bytes()
    assert one == two
    assert hashlib.sha256(one).hexdigest() == hashlib.sha256(two).hexdigest()
    assert b"\r\n" not in one  # newline pinned to LF
    assert not re.search(rb'"(at|ts|timestamp|generated_at|date)"', one)  # no timestamp

    batches = [json.loads(line) for line in one.decode("utf-8").splitlines()]
    assert len(batches) == 334  # ceil(5004 / 15)
    assert [b["batch_id"] for b in batches[:2]] == ["batch-0001", "batch-0002"]
    assert {b["pass"] for b in batches} == {R.DISCOVER_PASS}
    assert [len(b["sites"]) for b in batches[:2]] == [15, 15]
    assert sum(len(b["sites"]) for b in batches) == SNAPSHOT_SITES
    assert sum(len(row["findings"]) for b in batches for row in b["sites"]) == (
        SNAPSHOT_SITES * len(SP.DISCOVER_FIELDS)
    )


@needs_snapshot
def test_the_snapshot_plan_of_the_truth_ids_holds_exactly_those_sites_and_five_fields_each(
    tmp_path: Path,
) -> None:
    ids = _truth_ids()
    out = _plan(tmp_path, "--site-ids", str(TRUTH_SITE_IDS))

    batches = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [len(b["sites"]) for b in batches] == [15, 2]
    sites = [site for b in batches for site in b["sites"]]
    # The snapshot's own file order, filtered by the id list - not the order of the id list.
    wanted = set(ids)
    with gzip.open(SNAPSHOT / SP.UNIFIED_SITES_FILE, "rt", encoding="utf-8") as handle:
        expected = [row["id"] for row in map(json.loads, handle) if row["id"] in wanted]
    assert len(ids) == 17
    assert [site["site_id"] for site in sites] == expected

    for site in sites:
        assert [row["field"] for row in site["findings"]] == list(SP.DISCOVER_FIELDS)
        assert [row["test_id"] for row in site["findings"]] == [
            f"P3/{name}" for name in SP.DISCOVER_FIELDS
        ]
        assert site["name"]
        assert site["findings"][-1]["field"] == "card_description"


@needs_snapshot
def test_the_order_of_the_site_id_list_cannot_change_the_plan(tmp_path: Path) -> None:
    straight = _plan(tmp_path, "--site-ids", str(TRUTH_SITE_IDS))
    reversed_ids = tmp_path / "reversed.txt"
    reversed_ids.write_text(
        "\n".join(reversed(_truth_ids())) + "\n", encoding="utf-8", newline="\n"
    )
    other = tmp_path / "other.jsonl"
    assert (
        R.main(
            [
                "plan",
                "--from-snapshot",
                "--site-ids",
                str(reversed_ids),
                "--out",
                str(other),
            ]
        )
        == 0
    )

    assert straight.read_bytes() == other.read_bytes()


@needs_snapshot
def test_an_unknown_site_id_is_refused_rather_than_dropped(tmp_path: Path) -> None:
    asked = tmp_path / "ids.txt"
    missing = "00000000-0000-4000-8000-000000000000"
    asked.write_text("\n".join([*_truth_ids(), missing]) + "\n", encoding="utf-8", newline="\n")

    with pytest.raises(R.InputError, match="not in .*unified_sites.jsonl.gz"):
        R.main(
            [
                "plan",
                "--from-snapshot",
                "--site-ids",
                str(asked),
                "--out",
                str(tmp_path / "plan.jsonl"),
            ]
        )


def test_a_blank_or_repeated_site_id_is_refused(tmp_path: Path) -> None:
    ids = _truth_ids()
    blank = tmp_path / "blank.txt"
    blank.write_text(f"{ids[0]}\n\n{ids[1]}\n", encoding="utf-8", newline="\n")
    with pytest.raises(R.InputError, match="empty line"):
        SP.read_site_ids(blank)

    repeated = tmp_path / "repeated.txt"
    repeated.write_text(f"{ids[0]}\n{ids[0]}\n", encoding="utf-8", newline="\n")
    with pytest.raises(R.InputError, match="appears twice"):
        SP.read_site_ids(repeated)

    with pytest.raises(R.InputError, match="no site-id list at"):
        SP.read_site_ids(tmp_path / "absent.txt")


@needs_snapshot
def test_every_planned_value_comes_from_the_table_truth_fields_json_names() -> None:
    """The brief's own warning, as a test: five entries live in `card_stats`, not `unified_sites`."""
    entries = json.loads(TRUTH_FIELDS.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == 24

    records = {
        record["site_id"]: record
        for record in SP.build_discover_sites(snapshot_dir=SNAPSHOT, site_ids=_truth_ids())
    }
    compared = 0
    for entry in entries:
        stored_in = entry["stored_in"]
        if stored_in is None:
            # A scope decision is not a column value: no plan field may claim to answer it.
            assert entry["field"] not in SP.DISCOVER_FIELDS
            assert entry["stored_value"] is None
            continue
        assert SP.FIELD_STORED_IN[entry["field"]] == stored_in
        assert (
            _planned_row(records[entry["site_id"]], entry["field"])["current_value"]
            == (entry["stored_value"])
        ), entry
        compared += 1
    assert compared == 21  # 24 entries - the 3 scope decisions

    # The five that would have been read off the wrong table, named: card_description.
    card_entries = [e for e in entries if e["stored_in"] == "card_stats"]
    assert len(card_entries) == 5
    assert {e["field"] for e in card_entries} == {"card_description"}


def test_the_three_truth_entries_a_value_question_cannot_reach_are_scope_entries() -> None:
    """The one honest cap of this pass, pinned so it cannot move unnoticed.

    `scope` is not a stored value: the fixture's own `correct_value` for those entries is "out of
    scope - the record should be hidden or removed", and `stored_in` is null. A per-field value
    question cannot produce that, so the discover pass reaches 21 of the 24 entries by construction
    (`PIECE5.md` reports it rather than letting the recall number absorb it).
    """
    entries = json.loads(TRUTH_FIELDS.read_text(encoding="utf-8"))["entries"]
    missing = [e for e in entries if e["stored_value"] is None]
    assert len(missing) == 3
    assert {e["field"] for e in missing} == {"scope"}
    assert all(e["field"] not in SP.DISCOVER_FIELDS for e in missing)
    # Every entry the pass *can* reach stores a value: no planned field of the truth set is empty.
    reachable = [e for e in entries if e["field"] in SP.DISCOVER_FIELDS]
    assert len(reachable) == 21
    assert all(e["stored_value"] is not None for e in reachable)
    assert {e["field"] for e in reachable} == {
        "description",
        "period_start",
        "site_type",
        "card_description",
    }


def test_a_snapshot_row_without_a_name_or_without_an_id_is_refused(tmp_path: Path) -> None:
    nameless = _tiny_snapshot(tmp_path / "nameless", unified=[{"id": "site-1", "name": None}])
    with pytest.raises(R.InputError, match="name is None"):
        SP.build_discover_sites(snapshot_dir=nameless)

    anonymous = _tiny_snapshot(tmp_path / "anonymous", unified=[{"name": "Cave 1"}])
    with pytest.raises(R.InputError, match="carries no 'id'"):
        SP.build_discover_sites(snapshot_dir=anonymous)

    doubled = _tiny_snapshot(
        tmp_path / "doubled",
        unified=[{"id": "site-1", "name": "A"}, {"id": "site-1", "name": "A again"}],
    )
    with pytest.raises(R.InputError, match="duplicate site id"):
        SP.build_discover_sites(snapshot_dir=doubled)


def test_a_qid_row_that_is_not_a_q_number_is_refused_at_plan_time(tmp_path: Path) -> None:
    """A mangled id would fetch an empty entity set, which reads as "the item says nothing"."""
    rows = [{"id": "site-1", "name": "Cave 1"}]
    bad = _tiny_snapshot(
        tmp_path / "bad",
        unified=rows,
        external=[{"kind": "wikidata_qid", "site_id": "site-1", "value": "12345"}],
    )
    with pytest.raises(R.InputError, match=r"not a \(site, Q-number\) pair"):
        SP.build_discover_sites(snapshot_dir=bad)

    two_ids = _tiny_snapshot(
        tmp_path / "two",
        unified=rows,
        external=[
            {"kind": "wikidata_qid", "site_id": "site-1", "value": "Q1"},
            {"kind": "wikidata_qid", "site_id": "site-1", "value": "Q2"},
        ],
    )
    with pytest.raises(R.InputError, match="two wikidata_qid values"):
        SP.build_discover_sites(snapshot_dir=two_ids)

    # An unrelated kind is not a qid claim and is skipped, and a qid row for a site that is not in
    # the plan is not an error either: it routes nothing.
    ok = _tiny_snapshot(
        tmp_path / "ok",
        unified=rows,
        external=[
            {"kind": "enwiki_title", "site_id": "site-1", "value": "Cave 1"},
            {"kind": "wikidata_qid", "site_id": "gone", "value": "Q3"},
            {"kind": "wikidata_qid", "site_id": "site-1", "value": "Q4"},
        ],
    )
    assert SP.build_discover_sites(snapshot_dir=ok)[0]["wikidata_qid"] == "Q4"


@needs_snapshot
def test_the_snapshot_qid_comes_from_site_external_ids_not_from_the_vestigial_column() -> None:
    """Measured, because the brief's sentence and the export disagree.

    `card_stats.wikidata_qid` is NULL in all 5,004 exported rows and no code writes it (the only
    writer of a Q-id is `pipeline/lyra/prospector/external_ids.py:55`, into `site_external_ids`);
    `site_external_ids` carries 4,618. Reading the column would route **no** site to Wikidata.
    """
    cards = SP.read_snapshot_jsonl(SNAPSHOT / SP.CARD_STATS_FILE)
    assert len(cards) == SNAPSHOT_SITES
    assert all(row["wikidata_qid"] is None for row in cards)  # the vestigial column
    assert sum(1 for row in cards if (row["card_description"] or "").strip()) == (
        SNAPSHOT_SITES - SNAPSHOT_EMPTY_CARDS
    )
    rows = SP.read_snapshot_jsonl(SNAPSHOT / SP.SITE_EXTERNAL_IDS_FILE)
    qids = SP.qids_by_site(rows, origin="snapshot")
    assert len(qids) == SNAPSHOT_QIDS

    records = SP.build_discover_sites(snapshot_dir=SNAPSHOT, site_ids=_truth_ids())
    routed = [r for r in records if r.get("wikidata_qid")]
    assert len(routed) == 16  # 16 of the 17 truth sites carry a qid; `Font dels Coms` carries none
    # ... and every qid a record carries is the one the external-ids file holds for that site.
    for record in records:
        assert record.get("wikidata_qid") == qids.get(record["site_id"])


def test_a_missing_card_stats_row_reads_as_no_value_not_as_an_error(tmp_path: Path) -> None:
    """`card_description` lives in another table, so a row that is not there is a case, not a bug."""
    snapshot = _tiny_snapshot(
        tmp_path,
        unified=[{"country": "Spain", "id": "site-1", "name": "Cave 1"}],
        cards=[{"card_description": "another site's card", "site_id": "site-2"}],
    )
    record = SP.build_discover_sites(snapshot_dir=snapshot)[0]

    assert _planned_row(record, "card_description")["current_value"] is None
    assert _planned_row(record, "description")["current_value"] is None
    plan = DS.plan_batch(
        vocabulary=VOCAB,
        batch=_batch(record),
        store=F.EvidenceStore(tmp_path / "empty"),
        allow_absent=True,
    )
    assert 'stored="absent"' in plan.calls[-1].call.prompt  # the card_description call
    assert 'stored="absent"' in plan.calls[0].call.prompt  # the description call
    assert 'stored="present"' in plan.calls[3].call.prompt  # country: a value exists


#: A stand-in for the catalogue's value list. Three values are enough to prove the question carries
#: whatever list it is given, and that it refuses to be built without one; the real 70 come from the
#: snapshot (`snapshot_plan.site_type_vocabulary`) and are asserted against a written snapshot below.
VOCAB = ("Castle/palace", "Gate/archway/bridge", "Temple complex")

# ── routing: one question per field, one route per field ─────────────────────────────────────


def test_every_discover_field_has_a_route_and_a_question() -> None:
    assert set(DS.FIELD_CLAUSE) == set(SP.DISCOVER_FIELDS)
    questions = {name: DS.field_question(name, VOCAB) for name in SP.DISCOVER_FIELDS}
    for name in SP.DISCOVER_FIELDS:
        assert set(F.FEATURES_FOR_FIELD[name])
        assert f"`{name}`" in questions[name]
    assert len(set(questions.values())) == len(SP.DISCOVER_FIELDS)


def test_the_discover_routing_is_enwiki_by_name_and_wikidata_by_the_qid() -> None:
    site = _site_record("site-1", name="Ksar el Barka", qid="Q939166")
    targets = F.targets_for_site(site)

    assert [t.feature for t in targets] == [F.FEATURE_ENWIKI, F.FEATURE_WIKIDATA_ENTITY]
    assert "titles=Ksar%20el%20Barka" in targets[0].url
    assert "ids=Q939166" in targets[1].url
    for target in targets:
        F.assert_named_feature(target.url)
        assert target.label == f"site-1/{target.feature}"

    # No qid, no entity target - and no substitute: the name search answers the `name` question.
    without = F.targets_for_site(_site_record("site-2", name="Cave 2"))
    assert [t.feature for t in without] == [F.FEATURE_ENWIKI]

    # The two routes this piece added buy the same two features as the rest.
    for name in SP.DISCOVER_FIELDS:
        assert F.FEATURES_FOR_FIELD[name] == (F.FEATURE_ENWIKI, F.FEATURE_WIKIDATA_ENTITY)


def test_a_qid_that_is_not_a_q_number_is_refused_by_the_url_builder() -> None:
    for bad in ("12345", "Q", "Q0", "Q1 OR 1=1", "q42"):
        with pytest.raises(R.InputError, match="is not a Q-number"):
            F.wikidata_entity_url(bad)
    assert "ids=Q42" in F.wikidata_entity_url("Q42")


@needs_snapshot
def test_every_truth_site_is_routable_offline() -> None:
    """No site of the 17 is planned and then unfetchable: every route resolves, offline."""
    records = SP.build_discover_sites(snapshot_dir=SNAPSHOT, site_ids=_truth_ids())
    only_enwiki = []
    for record in records:
        targets = F.targets_for_site(record)
        assert 1 <= len(targets) <= 2
        if not any(t.feature == F.FEATURE_WIKIDATA_ENTITY for t in targets):
            only_enwiki.append(record["site_id"])
        for target in targets:
            F.assert_named_feature(target.url)
            assert target.url.startswith("https://")
            assert target.reason.startswith("P3/")
    # 16 of the 17 carry a qid; the one that does not has no `site_external_ids` row at all and is
    # judged on its article alone - which is found by name, so nothing is plan-only.
    assert only_enwiki == [TRUTH_SITE_WITHOUT_QID]


# ── one call per (site, field), and the question for a missing value ─────────────────────────


def test_every_site_buys_one_call_per_field_and_the_call_names_its_field(tmp_path: Path) -> None:
    store = _evidence_store(tmp_path / "evidence", "site-1", "site-2")
    plan = DS.plan_batch(
        vocabulary=VOCAB, batch=_batch(_site_record("site-1"), _site_record("site-2")), store=store
    )

    assert plan.skipped == []
    assert [item.call.label for item in plan.calls[:6]] == [
        "site-1/description",
        "site-1/period_start",
        "site-1/site_type",
        "site-1/country",
        "site-1/card_description",
        "site-2/description",
    ]
    assert len(plan.calls) == 2 * len(SP.DISCOVER_FIELDS)
    for item in plan.calls:
        name = item.call.field
        assert name in SP.DISCOVER_FIELDS
        assert DS.field_question(name, VOCAB) in item.call.prompt
        assert item.call.stage is M.Stage.FINDER
        # The five calls of one site carry five *different* questions: one question per call.
        for other in SP.DISCOVER_FIELDS:
            if other != name:
                assert DS.field_question(other, VOCAB) not in item.call.prompt
        # The site's evidence is read once and shared by its five calls.
        assert [e.feature for e in item.excerpts] == [F.FEATURE_ENWIKI]


def _discover_prompt(tmp_path: Path) -> str:
    store = _evidence_store(tmp_path / "evidence", "site-1")
    return (
        DS.plan_batch(vocabulary=VOCAB, batch=_batch(_site_record("site-1")), store=store)
        .calls[0]
        .call.prompt
    )


def test_the_question_asks_for_the_evidence_before_the_verdict(tmp_path: Path) -> None:
    """The first live run's central failure, pinned.

    `runs/gold` answered `VERDICT: CORRECT` after writing a sentence that placed the site's real
    dating in a different bucket from the stored one - the prompt's own rule, stated and then
    ignored, because the verdict was written first. Recall was 5/22. The evidence statement is
    therefore asked for *before* the verdict line, and this test is what keeps that order.
    """
    prompt = _discover_prompt(tmp_path)
    assert prompt.index("what the evidence in this message gives") < prompt.index(
        "VERDICT: CORRECT"
    )
    assert "the evidence **states** this field's value and it matches" in prompt
    assert 'saying "this is consistent" in the same breath does not change it' in prompt


def test_the_question_refuses_silence_as_agreement(tmp_path: Path) -> None:
    """`CORRECT` must mean the evidence states the value, not that it fails to contradict it.

    8 of the 11 `CORRECT` answers that missed a known-wrong field reasoned "the evidence does not
    contradict it", so a silent evidence block was being read as agreement.
    """
    prompt = _discover_prompt(tmp_path)
    assert "Silence is not" in prompt
    assert "never `CORRECT`" in prompt


def test_the_question_forbids_upholding_a_value_with_the_finders_own_knowledge(
    tmp_path: Path,
) -> None:
    """The other half of the misses: "4500-3000 BC is a standard attribution" upheld a wrong date.

    The pass exists to judge a stored value against fetched evidence, so its own subject knowledge
    may not be the thing that keeps a value alive.
    """
    prompt = _discover_prompt(tmp_path)
    assert "Your own knowledge of the subject is not " in prompt


def test_an_empty_stored_value_is_marked_absent_and_the_question_calls_it_wrong(
    tmp_path: Path,
) -> None:
    """3 of the 24 truth entries store nothing; across the snapshot 22 (site, field) pairs do.

    A question that only asked "is this wrong?" would read an empty field as nothing to report, so
    the prompt marks the value `stored="absent"` and the question says an empty field where a value
    belongs is `WRONG`.
    """
    store = _evidence_store(tmp_path / "evidence", "site-1")
    record = _site_record("site-1", values={"period_start": None, "description": ""})
    plan = DS.plan_batch(vocabulary=VOCAB, batch=_batch(record), store=store)
    by_field = {item.call.field: item.call.prompt for item in plan.calls}

    empty = by_field["period_start"]
    assert 'stored="absent"' in empty
    assert DS.ABSENT_VALUE_TEXT in empty
    assert "or the field stores no value where one belongs" in empty
    assert "If the evidence shows a value belongs in that field, that is `WRONG`" in empty
    assert 'the string "null"' in empty
    # The empty *description* is absent too, and an existing value is present.
    assert 'stored="absent"' in by_field["description"]
    assert 'stored="present"' in by_field["country"]
    assert DS.ABSENT_VALUE_TEXT not in by_field["country"]

    # A stored 0 is a value, not an absence: nothing here may read a falsy value as missing.
    zero = DS.plan_batch(
        vocabulary=VOCAB,
        batch=_batch(_site_record("site-1", values={"period_start": 0})),
        store=store,
    )
    assert 'stored="present"' in zero.calls[0].call.prompt


# ── the failure modes that must not end a batch ──────────────────────────────────────────────


def test_an_oversized_site_becomes_its_own_unverifiable_outcome_and_the_batch_carries_on(
    tmp_path: Path,
) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    over = MS.MAX_EVIDENCE_CHARS + 10
    store.path_for("site-big", F.FEATURE_ENWIKI).parent.mkdir(parents=True, exist_ok=True)
    store.path_for("site-big", F.FEATURE_ENWIKI).write_text("x" * over, encoding="utf-8")
    store.path_for("site-small", F.FEATURE_ENWIKI).write_text("Cave text", encoding="utf-8")

    runner = ScriptedRunner()
    report = DS.judge_discover_batch(
        vocabulary=VOCAB,
        batch=_batch(_site_record("site-big"), _site_record("site-small")),
        runner=runner,
        store=store,
        answers=F.EvidenceStore(tmp_path / "answers"),
        ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
    )

    assert [call.site_id for call in runner.calls] == ["site-small"] * len(SP.DISCOVER_FIELDS)
    assert report.calls == len(SP.DISCOVER_FIELDS)
    assert [s.site_id for s in report.skipped] == ["site-big"] * len(SP.DISCOVER_FIELDS)
    for skipped in report.skipped:
        assert skipped.field in SP.DISCOVER_FIELDS
        assert skipped.reason.startswith("site-big:")
        assert f"the evidence is {over} characters" in skipped.reason
        assert f"over the {MS.MAX_EVIDENCE_CHARS}-character bound" in skipped.reason
        assert "the batch carries on" in skipped.reason
        # One unverifiable finding for the field this skip is about, from the plan's own row.
        assert len(skipped.findings) == 1
        finding = skipped.findings[0]
        assert finding.verdict is M.Verdict.UNVERIFIABLE
        assert finding.field == skipped.field
        assert finding.test_id == f"P3/{skipped.field}"
        assert finding.note == skipped.reason
    # The report counts them, and no call was bought for the big site.
    assert report.unverifiable == len(SP.DISCOVER_FIELDS)
    assert {j.site_id for j in report.judgements} == {"site-small"}


def test_a_field_whose_evidence_was_never_fetched_is_recorded_not_attempted_and_the_batch_carries_on(
    tmp_path: Path,
) -> None:
    store = _evidence_store(tmp_path / "evidence", "site-2")
    reason = "enwiki: no response: GET https://en.wikipedia.org/...: ReadTimeout"
    runner = ScriptedRunner()
    report = DS.judge_discover_batch(
        vocabulary=VOCAB,
        batch=_batch(_site_record("site-1"), _site_record("site-2")),
        runner=runner,
        store=store,
        answers=F.EvidenceStore(tmp_path / "answers"),
        ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
        failures={"site-1": {F.FEATURE_ENWIKI: reason}},
    )

    assert [call.site_id for call in runner.calls] == ["site-2"] * len(SP.DISCOVER_FIELDS)
    assert len(report.skipped) == len(SP.DISCOVER_FIELDS)
    for skipped in report.skipped:
        assert skipped.site_id == "site-1"
        assert "no evidence file was read for this site (no model call bought)" in skipped.reason
        assert reason in skipped.reason
        assert skipped.findings[0].verdict is M.Verdict.UNVERIFIABLE
        assert skipped.findings[0].field == skipped.field
    # The lines that exist are site-2's: the site nobody could read bought nothing.
    lines = [
        json.loads(line)
        for line in (tmp_path / "LEDGER.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(lines) == len(SP.DISCOVER_FIELDS)
    assert all(line["label"].startswith("site-2/") for line in lines)


def test_partial_evidence_still_buys_the_call_and_the_prompt_names_the_failure(
    tmp_path: Path,
) -> None:
    """The other half: one target of a site failed, the site is judged anyway, and the prompt says
    which fact it is - "asked and failed", never "nothing there"."""
    store = _evidence_store(tmp_path / "evidence", "site-1")
    failure = "wikidata_entity: no response: GET https://www.wikidata.org/...: ReadTimeout"
    plan = DS.plan_batch(
        vocabulary=VOCAB,
        batch=_batch(_site_record("site-1", qid="Q1")),
        store=store,
        failures={"site-1": {F.FEATURE_WIKIDATA_ENTITY: failure}},
    )

    assert len(plan.calls) == len(SP.DISCOVER_FIELDS)
    assert plan.skipped == []
    prompt = plan.calls[0].call.prompt
    assert f'<evidence feature="{F.FEATURE_ENWIKI}" status="present"' in prompt
    assert f'<evidence feature="{F.FEATURE_WIKIDATA_ENTITY}" status="failed"' in prompt
    assert failure.split(": ", 1)[1] in prompt


def test_a_missing_evidence_file_with_no_recorded_failure_still_raises(tmp_path: Path) -> None:
    """Piece 4's guard, unchanged in the discover path: a hole in the record is not weather."""
    store = F.EvidenceStore(tmp_path / "evidence")
    with pytest.raises(MS.EvidenceUnusable, match="records no failure for it"):
        DS.plan_batch(vocabulary=VOCAB, batch=_batch(_site_record("site-1")), store=store)


def test_an_over_bound_site_is_recorded_before_anything_is_spent(tmp_path: Path) -> None:
    """The preview and the live run take the same decision, because it is a plan-time one."""
    store = F.EvidenceStore(tmp_path / "evidence")
    path = store.path_for("site-1", F.FEATURE_ENWIKI)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (MS.MAX_EVIDENCE_CHARS + 1), encoding="utf-8")

    plan = DS.plan_batch(vocabulary=VOCAB, batch=_batch(_site_record("site-1")), store=store)
    assert plan.calls == []
    assert len(plan.skipped) == len(SP.DISCOVER_FIELDS)


# ── the CLI: the same calls, previewed and then bought ───────────────────────────────────────


def test_prepare_writes_the_discover_pass_marker_verbatim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plan's `pass` marker is how `judge` knows which pass it is holding, so it has to survive
    `prepare` - which copies the batch rather than rebuilding one of its own."""
    plan = tmp_path / "plan.jsonl"
    plan.write_text(
        json.dumps(
            {
                "batch_id": "batch-0001",
                "ordinal": 1,
                "pass": R.DISCOVER_PASS,
                "sites": [_site_record("site-1")],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    run_dir = tmp_path / "runs"
    assert R.main(["prepare", "--plan", str(plan), "--run-dir", str(run_dir)]) == 0
    capsys.readouterr()

    written = json.loads((run_dir / "batch-0001" / "input.json").read_text(encoding="utf-8"))
    assert written["pass"] == R.DISCOVER_PASS
    assert [row["field"] for row in written["sites"][0]["findings"]] == list(SP.DISCOVER_FIELDS)


def test_judge_without_live_previews_the_discover_calls_and_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _assert_no_process(monkeypatch)
    # The judge reads the catalogue's value list from the production snapshot; this test is about the
    # two builders agreeing, not about that list, so it pins the list instead of reading it.
    monkeypatch.setattr(SP, "site_type_vocabulary", lambda: VOCAB)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"), _site_record("site-2"))
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        ["judge", "--run-dir", str(run_dir), "--batch-id", "batch-0001", "--ledger", str(ledger)]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["live"] is False
    assert payload["pass"] == R.DISCOVER_PASS
    assert payload["calls"] == 2 * len(SP.DISCOVER_FIELDS)
    assert payload["fields"] == list(SP.DISCOVER_FIELDS)
    assert payload["skipped"] == []
    assert [site["field"] for site in payload["sites"][:2]] == ["description", "period_start"]
    for site in payload["sites"]:
        assert site["prompt_chars"] == len(site["prompt"])
        assert site["prompt"] not in site["argv"]
        assert site["evidence"][0]["present"] is False  # the missing page is shown, not hidden
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "answers").exists()

    # The preview's prompt is the live prompt: one builder, and the dry run is not a second one.
    live_plan = DS.plan_batch(
        vocabulary=VOCAB,
        batch=json.loads((run_dir / "batch-0001" / "input.json").read_text(encoding="utf-8")),
        store=F.EvidenceStore(run_dir / "batch-0001" / "evidence"),
        allow_absent=True,
    )
    assert [p.call.prompt for p in live_plan.calls] == [s["prompt"] for s in payload["sites"]]


def test_judge_live_stores_one_answer_per_field_and_one_ledger_line_each(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Five calls for one site must leave five records. One answer key would lose four of them."""
    monkeypatch.setattr(MS, "PiRunner", ScriptedRunner)
    # The live path reads the catalogue's value list from the production snapshot; this test is about
    # the answer and ledger bookkeeping, so the list is pinned rather than read.
    monkeypatch.setattr(SP, "site_type_vocabulary", lambda: VOCAB)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"), _site_record("site-2"))
    _evidence_store(run_dir / "batch-0001" / "evidence", "site-1", "site-2")
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["pass"] == R.DISCOVER_PASS
    assert payload["totals"]["calls"] == 2 * len(SP.DISCOVER_FIELDS)
    assert payload["skipped"] == []
    assert [j["field"] for j in payload["judgements"][:5]] == list(SP.DISCOVER_FIELDS)
    assert [j["label"] for j in payload["judgements"][:5]] == [
        f"site-1/{name}" for name in SP.DISCOVER_FIELDS
    ]

    answers = sorted((run_dir / "batch-0001" / "answers").iterdir())
    assert {p.name for p in answers} == {
        f"{F.EvidenceStore.slug(f'site-{i}', name)}.txt"
        for i in (1, 2)
        for name in SP.DISCOVER_FIELDS
    }
    assert answers[0].read_text(encoding="utf-8").startswith("VERDICT: CORRECT")

    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [line["label"] for line in lines] == [j["label"] for j in payload["judgements"]]
    assert {line["kind"] for line in lines} == {"model_call"}
    assert {line["stage"] for line in lines} == {"finder"}

    stored = json.loads((run_dir / "batch-0001" / "model.json").read_text(encoding="utf-8"))
    assert stored["totals"]["calls"] == 2 * len(SP.DISCOVER_FIELDS)
    assert stored["stage"] == "finder"


def test_judge_refuses_the_reviewer_stage_when_the_batch_carries_no_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reviewer pass over a batch nobody judged would buy nothing and write empty verdicts.

    The refusal survives the widening of the stage's routing; what changed is its *condition*. The
    message must name the directory that is empty, because the caller has to know which pass to run
    first - an error that only says "not allowed" leaves them guessing.
    """
    _assert_no_process(monkeypatch)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"))
    answers = run_dir / "batch-0001" / "answers"

    with pytest.raises(R.InputError, match="carries none") as caught:
        R.main(
            [
                "judge",
                "--run-dir",
                str(run_dir),
                "--batch-id",
                "batch-0001",
                "--stage",
                "reviewer",
                "--live",
            ]
        )

    message = str(caught.value)
    assert str(answers) in message, message
    assert "--stage finder" in message, message


def test_judge_refuses_the_reviewer_stage_when_the_answers_folder_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty `answers/` is not a batch of findings - a killed run leaves one behind.

    This is the difference between "the directory exists" and "there are answers". A reviewer that
    trusted the directory would write a report of zero verdicts for five fields, and that receipt
    would claim a review happened.
    """
    _assert_no_process(monkeypatch)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"))
    (run_dir / "batch-0001" / "answers").mkdir(parents=True, exist_ok=True)

    with pytest.raises(R.InputError, match="carries none"):
        R.main(
            [
                "judge",
                "--run-dir",
                str(run_dir),
                "--batch-id",
                "batch-0001",
                "--stage",
                "reviewer",
                "--live",
            ]
        )


def test_judge_reviews_a_batch_that_carries_the_finders_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reviewer's path through the real CLI: one verdict per usable finding, its own report.

    Four of the five fields carry no finder answer here, so the report has to show them as
    unreviewable *with a reason* - a pass that reviewed one field and stayed silent about the other
    four would be indistinguishable from a pass that reviewed everything.
    """
    monkeypatch.setattr(MS, "PiRunner", ReviewingRunner)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"))
    _evidence_store(run_dir / "batch-0001" / "evidence", "site-1")
    answers = F.EvidenceStore(run_dir / "batch-0001" / "answers")
    answers.write(
        site_id="site-1",
        feature="description",
        body=(
            b"The page disagrees with the record.\n\nVERDICT: WRONG\nPROPOSED: Cave\n"
            b'SOURCE: https://en.wikipedia.org/w/api.php?titles=Cave - "Cave text"\n'
        ),
    )
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--stage",
            "reviewer",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["stage"] == "reviewer"
    assert payload["pass"] == R.DISCOVER_PASS
    assert payload["calls"] == 1, payload
    assert payload["resumed"] == 0
    assert payload["applies"] == 1, payload
    assert payload["unreviewable"] == len(SP.DISCOVER_FIELDS) - 1, payload
    assert [v["field"] for v in payload["verdicts"]] == list(SP.DISCOVER_FIELDS)
    unreviewed = [v for v in payload["verdicts"] if not v["asked"]]
    assert all("is not on disk" in v["unreviewable"] for v in unreviewed), unreviewed

    written = json.loads((run_dir / "batch-0001" / "review.json").read_text(encoding="utf-8"))
    assert written["stage"] == "reviewer"
    assert written["calls"] == 1
    assert not (run_dir / "batch-0001" / "model.json").exists(), (
        "the reviewer must not write the finder's report"
    )

    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1, lines
    assert lines[0]["stage"] == "reviewer"
    assert lines[0]["kind"] == "model_call"


def test_judge_refuses_a_pass_marker_it_does_not_know(tmp_path: Path) -> None:
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"))
    input_path = run_dir / "batch-0001" / "input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["pass"] = "sweep"  # noqa: S105 - a batch marker, not a credential
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(R.InputError, match="which this runner does not know"):
        R.main(["judge", "--run-dir", str(run_dir), "--batch-id", "batch-0001"])


def test_plan_refuses_the_two_inputs_at_once_and_site_ids_without_the_snapshot_flag(
    tmp_path: Path,
) -> None:
    out = tmp_path / "plan.jsonl"
    with pytest.raises(R.InputError, match="two different inputs"):
        R.main(
            [
                "plan",
                "--from-snapshot",
                "--worklist",
                str(tmp_path / "somewhere_else.jsonl"),
                "--out",
                str(out),
            ]
        )
    with pytest.raises(R.InputError, match="means nothing"):
        R.main(["plan", "--site-ids", str(TRUTH_SITE_IDS), "--out", str(out)])


@needs_worklist
def test_the_worklist_plan_still_hashes_to_the_piece_1_anchor(tmp_path: Path) -> None:
    """The existing plan's bytes are frozen: a new plan may not move the old one.

    The anchor comes from `PIECE1.md:120-124`, and `test_phase3_runner.py` pins only that the plan
    is reproducible - not what it is. This is the byte-level pin.
    """
    out = tmp_path / "worklist_plan.jsonl"
    assert R.main(["plan", "--worklist", str(WORKLIST), "--out", str(out)]) == 0

    assert hashlib.sha256(out.read_bytes()).hexdigest() == PIECE1_PLAN_SHA256
    assert b'"pass"' not in out.read_bytes()  # the marker is the discover plan's, not the default


def test_the_discover_modules_reach_no_network_client_and_no_shell() -> None:
    """The plan builder and the discover stage must start nothing and open nothing themselves."""
    banned = re.compile(r"\b(httpx|requests|urllib|socket|aiohttp|openai|anthropic|subprocess)\b")
    for module in (SP, DS):
        source = Path(module.__file__).read_text(encoding="utf-8")
        hits = sorted(set(banned.findall(source)))
        assert hits == [], f"{Path(module.__file__).name} reaches outside the process: {hits}"


# ── the catalogue's own value list, and the clause's precedence over the general rules ─────────


def test_the_site_type_question_carries_the_catalogues_own_value_list() -> None:
    """All four `site_type` flags of the second run were wrong, each by reading the evidence's own
    phrase as if it were the catalogue's bucket - "triumphal arch" against `Gate/archway/bridge`,
    "folly castle" against `Castle/palace`, "hill fort" against `Fortress/citadel`, "ahu" against
    `Megalithic statues`. The question names the list the answer has to come from, and no other
    field's question carries it.
    """
    question = DS.field_question("site_type", VOCAB)
    for value in VOCAB:
        assert f"`{value}`" in question
    assert f"list of {len(VOCAB)} values" in question
    assert "never because the evidence's own wording differs" in question
    for other in SP.DISCOVER_FIELDS:
        if other != "site_type":
            assert "Gate/archway/bridge" not in DS.field_question(other, VOCAB)


def test_the_site_type_question_refuses_to_be_built_without_the_value_list() -> None:
    """A question asking which catalogue value the evidence describes, while listing none, cannot be
    answered - and the failure would read as a thinner answer, not as an error."""
    empties: list[Any] = [[], ()]
    for empty in empties:
        with pytest.raises(R.InputError) as caught:
            DS.field_question("site_type", empty)
        assert "cannot be answered" in str(caught.value)
    # The other four clauses do not need it, so a batch is only refused for the field that does.
    assert DS.field_question("description")


def test_the_field_clause_is_stated_to_beat_the_general_rules() -> None:
    """The regression this pins: the second run's rewrite said `Only the evidence in this message
    decides`, and the model then flagged `England` as `WRONG` because the evidence wrote `United
    Kingdom` - citing the clause that allows it and overriding it in the same sentence.
    """
    for name in SP.DISCOVER_FIELDS:
        question = DS.field_question(name, VOCAB)
        assert "The clause above defines what `matches` means" in question
        assert "it beats the general rules" in question
    assert "are **the same answer**" in DS.field_question("country", VOCAB)


def _categorize_period_steps() -> list[tuple[int, str]]:
    """The bucket table, read off the site's own `categorizePeriod` rather than copied from it."""
    source = (REPO / "ancient-nerds-map" / "src" / "data" / "sites.ts").read_text(encoding="utf-8")
    steps = re.findall(r"if \(start < (-?\d+)\) return '([^']+)'", source)
    assert steps, "categorizePeriod's comparisons were not found in sites.ts"
    return [(int(bound), label) for bound, label in steps]


def test_the_period_question_gives_the_bucket_spans_and_not_only_lower_bounds() -> None:
    """`Bulls of Guisando` was flagged `WRONG` on arithmetic the model got wrong after its own
    verdict ("Wait - both -200/-100 and -500 fall in the same bucket. Let me correct.").

    The first repair wrote the spans but left the last boundaries open ("-1500 to -500 ..."), and
    the two surviving false positives of the third run sat on exactly those two values: a stored
    -1500 and a stored -500, both of which the question placed one bucket too early. Every span is
    therefore derived from `categorizePeriod` here - inclusive of its first year, exclusive of its
    second - so the question cannot drift from the code it describes.
    """
    question = DS.field_question("period_start", VOCAB)
    steps = _categorize_period_steps()
    assert steps[0] == (-4500, "< 4500 BC")
    assert f"below {steps[0][0]} is `{steps[0][1]}`" in question
    # Ragged on purpose: each step is compared with the one that follows it.
    for (previous, _), (bound, label) in zip(steps, steps[1:], strict=False):
        assert f"{previous} up to but not including {bound} is `{label}`" in question
    assert f"{steps[-1][0]} and later is `1500+ AD`" in question
    assert "-1500 belongs to `1500 - 500 BC` and -500 belongs to `500 BC - 1 AD`" in question
    assert "which span each of the two values falls in" in question

    # The century workaround must be *true*, not merely present: the spans it names have to agree
    # with the code for every year they cover. Round 3 flagged `Bulls of Guisando` (stored -500)
    # against evidence saying "2nd century BCE", and round 4 repeated it plus `Ocriticum` against
    # "4th century BC", both placing the evidence in `1500 - 500 BC` - one bucket too early, because
    # -200 and -400 are greater than -500.
    def label_of(year: int) -> str:
        for bound, label in steps:
            if year < bound:
                return label
        return "1500+ AD"

    for century, first, last in (("2nd", -200, -101), ("4th", -400, -301)):
        assert f"the {century} century BC is {first} up to but not including {last}" in question
        assert label_of(first) == label_of(last) == "500 BC - 1 AD"
    assert "both of those centuries fall in `500 BC - 1 AD`" in question


def test_the_site_type_vocabulary_is_read_from_the_snapshot_sorted_and_deduplicated(
    tmp_path: Path,
) -> None:
    """The list is read from the snapshot the plan was built from, not from a hand-copy of it, and
    a snapshot that yields no value at all is refused rather than producing a question with an empty
    list in it."""
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    rows: list[dict[str, Any]] = [
        {"id": "a", "site_type": "Temple complex"},
        {"id": "b", "site_type": "Castle/palace"},
        {"id": "c", "site_type": "Temple complex"},
        {"id": "d", "site_type": ""},
        {"id": "e", "site_type": None},
    ]
    with gzip.open(snapshot / SP.UNIFIED_SITES_FILE, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    assert SP.site_type_vocabulary(snapshot_dir=snapshot) == ("Castle/palace", "Temple complex")

    with gzip.open(snapshot / SP.UNIFIED_SITES_FILE, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "a", "site_type": " "}) + "\n")
    with pytest.raises(R.InputError) as caught:
        SP.site_type_vocabulary(snapshot_dir=snapshot)
    assert "no non-empty site_type value" in str(caught.value)


# ---------------------------------------------------------------------------------------------
# The correction and its source. Martin's requirement of 2026-09-21 is that the model **corrects**
# rather than only flags, and that every correction carries a page and a sentence. That sentence is
# then checked against the bytes the run itself fetched, which is what makes "with sources" a
# property of the artefact instead of a claim in prose. Before this, the question said the opposite
# in writing (`Never guess a replacement value.`), so these tests also pin that it no longer does.
# ---------------------------------------------------------------------------------------------

GOOD_WRONG = (
    "The article says the tomb was built in the 4th century BC.\n"
    "VERDICT: WRONG\n"
    "PROPOSED: -400\n"
    'SOURCE: https://en.wikipedia.org/wiki/Amyntas - "The tomb dates from the 4th century BC."\n'
)


def test_the_reason_is_the_sentence_the_question_asks_for() -> None:
    # The question asks for one sentence about what the evidence gives, *before* the verdict line, and
    # marks that sentence with nothing. The parser demanded an `EVIDENCE:` marker instead, which the
    # question never asks for: 0 of the round-6 gold run's 75 answers carry one, so the reviewer found
    # nothing to review in any of them, and the write path would have had nothing to apply. The shape
    # below is that gold run's own.
    answer = DS.parse_answer(
        "1. The Kounta arrived in 1690 at a place where a farming community already existed, and the "
        "earlier settlement is attributed to the Fula Jaawbe clan.\n"
        "\n"
        "VERDICT: WRONG\n"
        "PROPOSED: A ruined town in Mauritania, near Lake Gabou.\n"
        'SOURCE: https://en.wikipedia.org/w/api.php?titles=Ksar%20el%20Barka - "This town would '
        'later become Ksar el Barka."\n'
    )
    assert answer.evidence.startswith("1. The Kounta arrived in 1690")
    assert answer.problems == ()


def test_an_answer_without_a_reason_sentence_is_a_problem() -> None:
    answer = DS.parse_answer("VERDICT: UNVERIFIABLE\n")
    assert answer.verdict == "UNVERIFIABLE"
    assert any(
        "no sentence saying what the evidence gives" in problem for problem in answer.problems
    )


def test_an_evidence_marker_is_read_as_the_same_sentence() -> None:
    answer = DS.parse_answer(
        "EVIDENCE: the tomb dates from the 4th century BC.\nVERDICT: CORRECT\n"
    )
    assert answer.evidence == "the tomb dates from the 4th century BC."
    assert answer.problems == ()


def test_a_wrong_answer_keeps_its_proposed_value_and_its_source() -> None:
    answer = DS.parse_answer(GOOD_WRONG)
    assert answer.verdict == "WRONG"
    assert answer.proposed == "-400"
    assert answer.sources == (
        DS.SourceClaim(
            url="https://en.wikipedia.org/wiki/Amyntas",
            quote="The tomb dates from the 4th century BC.",
        ),
    )
    assert answer.problems == ()
    assert answer.complete


def test_a_wrong_answer_without_a_proposed_value_is_a_problem() -> None:
    answer = DS.parse_answer(GOOD_WRONG.replace("PROPOSED: -400\n", ""))
    assert any("no `PROPOSED:` value" in problem for problem in answer.problems)
    assert not answer.complete


def test_a_wrong_answer_without_a_source_is_a_problem() -> None:
    text = "\n".join(line for line in GOOD_WRONG.splitlines() if not line.startswith("SOURCE:"))
    answer = DS.parse_answer(text)
    assert any("no `SOURCE:` page" in problem for problem in answer.problems)


def test_a_correct_answer_carrying_a_correction_is_a_problem() -> None:
    answer = DS.parse_answer(GOOD_WRONG.replace("VERDICT: WRONG", "VERDICT: CORRECT"))
    assert any("carrying a correction" in problem for problem in answer.problems)


def test_a_source_line_without_a_url_and_a_quote_is_a_problem() -> None:
    # Built here rather than by editing GOOD_WRONG: a `str.replace` that does not match is a silent
    # no-op, and this test then asserts about the wrong text (it did, first time).
    text = (
        "The article says the tomb was built in the 4th century BC.\n"
        "VERDICT: WRONG\n"
        "PROPOSED: -400\n"
        "SOURCE: see the article above\n"
    )
    answer = DS.parse_answer(text)
    assert answer.sources == ()
    assert any("1 `SOURCE:` line(s), 0 carrying" in problem for problem in answer.problems)


def test_more_than_three_sources_are_a_problem_and_the_first_three_are_kept() -> None:
    extra = "".join(f'SOURCE: https://example.org/{n} - "quote {n}"\n' for n in range(1, 6))
    answer = DS.parse_answer(GOOD_WRONG + extra)
    assert len(answer.sources) == DS.MAX_SOURCES == 3
    assert [claim.url for claim in answer.sources][:2] == [
        "https://en.wikipedia.org/wiki/Amyntas",
        "https://example.org/1",
    ]
    assert any("6 sources; at most 3" in problem for problem in answer.problems)


def test_the_verdict_is_found_when_it_is_written_inline() -> None:
    answer = DS.parse_answer("The page is silent on the date.\n2. VERDICT: UNVERIFIABLE\n")
    assert answer.verdict == "UNVERIFIABLE"


def test_a_quote_is_recognised_across_json_escapes_in_the_evidence() -> None:
    # The enwiki/wikidata evidence files *are* the APIs' JSON responses and go into the prompt
    # verbatim, so the page spells a break `\n` and a non-ASCII letter `\u00c1vila` exactly where the
    # model reads a break and `Ávila`. Without undoing those escapes on both sides, every honest
    # quote would be reported as missing and the metric would be about JSON, not about citations.
    page = '{"extract":"in the municipality of El Tiemblo, \\u00c1vila,\\nSpain."}'
    assert DS.quote_occurs("in the municipality of El Tiemblo, Ávila, Spain.", page)
    assert DS.quote_occurs("El Tiemblo, \\u00c1vila,\\nSpain", page)


def test_a_quote_is_recognised_across_the_differences_a_retyping_has() -> None:
    page = "He built it\n  in the 4th century BC,\nas the sources say."
    assert DS.quote_occurs("in the 4th century BC,", page)
    assert DS.quote_occurs("He built it in the 4th century BC", page)
    assert DS.quote_occurs("as the sources say", page)


def test_a_quote_that_is_not_in_the_page_is_a_problem() -> None:
    answer = DS.parse_answer(GOOD_WRONG)
    problems = DS.source_problems(
        answer, {"https://en.wikipedia.org/wiki/Amyntas": "The tomb is Hellenistic."}
    )
    assert any("quote does not occur" in problem for problem in problems)


def test_a_cited_page_the_run_did_not_fetch_is_a_problem() -> None:
    answer = DS.parse_answer(GOOD_WRONG)
    problems = DS.source_problems(answer, {})
    assert any("was not fetched by this run" in problem for problem in problems)


def test_pages_from_excerpts_carries_only_the_pages_we_have() -> None:
    excerpts = [
        MS.EvidenceExcerpt(feature="article", url="https://a", path=Path("a"), text="text a"),
        MS.EvidenceExcerpt(
            feature="wikidata", url="https://b", path=Path("b"), text=None, failure="timeout"
        ),
    ]
    assert DS.pages_from_excerpts(excerpts) == {"https://a": "text a"}


def test_the_question_asks_for_a_correction_and_names_where_it_must_come_from() -> None:
    question = DS.field_question("description", ())
    assert "PROPOSED:" in question
    assert "SOURCE:" in question
    assert "must occur in that page" in question
    assert "Never guess a replacement value" not in question


# ── a call whose stream came back unreadable: a recorded hole, not the end of the batch ───────


class OneHoleRunner(ScriptedRunner):
    """The scripted discover runner, with one (site, field) answering with an unreadable stream."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hole = ("site-1", "country")

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        if (call.site_id, call.field) == self.hole:
            raise MS.UnreadableStream(
                f"{call.label} stdout:9 assistant message_end: the assistant message carries no "
                "text - an empty answer is not a result"
            )
        return MS.ModelAnswer(text=f"VERDICT: CORRECT - {call.label}", usage=self.answer.usage)


def test_an_unreadable_stream_for_one_field_is_a_hole_and_the_other_calls_are_bought(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measured 2026-09-21: 4 of the mass run's 334 batches died this way (`batch-0143.judge.log`).

    The whole live CLI path with one field's stream empty: the batch exits 0, `model.json` carries
    the hole with the field's name, the other nine calls are answered, and the ledger holds nine
    lines - the hole is not written as a zero-usage line.
    """
    monkeypatch.setattr(MS, "PiRunner", OneHoleRunner)
    monkeypatch.setattr(SP, "site_type_vocabulary", lambda: VOCAB)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"), _site_record("site-2"))
    _evidence_store(run_dir / "batch-0001" / "evidence", "site-1", "site-2")
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["pass"] == R.DISCOVER_PASS
    assert payload["totals"]["calls"] == 10
    assert len(payload["judgements"]) == 9
    assert "site-1/country" not in [j["label"] for j in payload["judgements"]]
    assert [f["field"] for f in payload["failures"]] == ["country"]
    assert payload["failures"][0]["site_id"] == "site-1"
    assert set(payload["failures"][0]) == {"site_id", "field", "reason"}
    assert "carries no text" in payload["failures"][0]["reason"]

    hole = run_dir / "batch-0001" / "answers" / f"{F.EvidenceStore.slug('site-1', 'country')}.txt"
    assert not hole.exists()
    assert (run_dir / "batch-0001" / "answers").glob("*.txt")
    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 9
    assert "site-1/country" not in [line["label"] for line in lines]

    stored = json.loads((run_dir / "batch-0001" / "model.json").read_text(encoding="utf-8"))
    assert stored["failures"] == payload["failures"]
    assert stored["totals"]["calls"] == 10


def test_the_reviewer_does_not_clear_a_field_whose_finder_call_was_a_hole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hole is not a finding, so there is nothing to clear: the field is recorded unreviewable.

    The finder's `model.json` here carries a `FailedCall` for `country` and answers for the other
    four fields. The reviewer is asked about the four; about `country` it says `asked=False`, and
    nothing in `review.json` can be read as "the record is right about the country".
    """
    monkeypatch.setattr(MS, "PiRunner", ReviewingRunner)
    run_dir = _prepared_discover_run(tmp_path, _site_record("site-1"))
    _evidence_store(run_dir / "batch-0001" / "evidence", "site-1")
    answered = [field for field in SP.DISCOVER_FIELDS if field != "country"]
    body = (
        b"The page disagrees with the record.\n\nVERDICT: WRONG\nPROPOSED: Cave\n"
        b'SOURCE: https://en.wikipedia.org/w/api.php?titles=Cave - "Cave text"\n'
    )
    answers = F.EvidenceStore(run_dir / "batch-0001" / "answers")
    for field in answered:
        answers.write(site_id="site-1", feature=field, body=body)
    model = _answer().usage
    MS.write_report(
        run_dir / "batch-0001" / "model.json",
        MS.BatchModelReport(
            batch_id="batch-0001",
            stage=M.Stage.FINDER,
            site_ids=["site-1"],
            judgements=[
                MS.SiteJudgement(
                    site_id="site-1",
                    label=f"site-1/{field}",
                    answer_chars=len(body),
                    input_tokens=model.input_tokens,
                    output_tokens=model.output_tokens,
                    cache_read_tokens=model.cache_read_tokens,
                    cache_write_tokens=model.cache_write_tokens,
                    cost_usd=model.cost_usd,
                    wrote=True,
                    field=field,
                )
                for field in answered
            ],
            failures=[
                MS.FailedCall(
                    site_id="site-1", field="country", reason="the stream carries no text"
                )
            ],
        ),
    )
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--stage",
            "reviewer",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["calls"] == len(answered)
    assert payload["applies"] == len(answered)
    country = [v for v in payload["verdicts"] if v["field"] == "country"][0]
    assert country["asked"] is False
    assert country["applies"] is False  # a hole cannot be a cleared finding
    assert "is not on disk" in country["unreviewable"]
    assert "country" not in [v["field"] for v in payload["verdicts"] if v["applies"]]
