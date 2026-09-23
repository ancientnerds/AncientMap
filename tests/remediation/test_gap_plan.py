"""The gap plan: the questions the mass run holds no readable verdict for, and the records that re-ask
them - built from a production export, with the reviewed id repair and the shared-item rule applied.

No test here reads production or the network: the mass run, the export and the sitelinks are small
fabricated directories in the shape the real ones have.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import gap_plan as G  # noqa: E402
import lanes  # noqa: E402
import qid_repair  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

BIG = "aaaaaaaa-0000-4000-8000-000000000001"
SMALL = "aaaaaaaa-0000-4000-8000-000000000002"
FIELDS = list(SP.DISCOVER_FIELDS)
CLARE = next(site for site in qid_repair.SITES if site.name == "Clare, Suffolk")
TIKAL = next(site for site in qid_repair.SITES if site.rule == "unresolved")


def _mass_run(tmp_path: Path) -> Path:
    """One mass batch: BIG over the bound (five skips), SMALL with an empty stream and no verdict."""
    batch = tmp_path / "mass" / "batch-0007"
    (batch / "answers").mkdir(parents=True)
    (batch / "input.json").write_text(
        json.dumps({"batch_id": "batch-0007", "sites": [{"site_id": BIG}, {"site_id": SMALL}]}),
        encoding="utf-8",
    )
    reason = (
        f"{BIG}: the evidence is 78430 characters, over the 64000-character bound, so no bounded "
        "prompt exists for any of this site's fields"
    )
    (batch / "model.json").write_text(
        json.dumps(
            {
                "skipped": [{"site_id": BIG, "field": name, "reason": reason} for name in FIELDS],
                "failures": [
                    {"site_id": SMALL, "field": "country", "reason": "no text - not a result"}
                ],
            }
        ),
        encoding="utf-8",
    )
    store = F.EvidenceStore(batch / "answers")
    store.write(
        site_id=SMALL, feature="period_start", body=b"The item says -471.\nPROPOSED: -471\n"
    )
    store.write(
        site_id=SMALL, feature="site_type", body=b"The page says a wall.\nVERDICT: CORRECT\n"
    )
    return tmp_path / "mass"


def test_the_census_finds_the_three_classes_in_the_runs_own_order(tmp_path: Path) -> None:
    questions = G.census(_mass_run(tmp_path))
    assert [(q.site_id, q.field, q.why) for q in questions] == [
        *((BIG, name, G.OVER_BOUND) for name in FIELDS),
        (SMALL, "period_start", G.NO_VERDICT),
        (SMALL, "country", G.EMPTY_STREAM),
    ]
    assert questions[0].detail == "evidence 78430 characters, bound 64000"
    assert {q.source_batch for q in questions} == {"batch-0007"}


def test_the_census_refuses_a_skip_that_is_not_the_bound_and_a_partial_site(tmp_path: Path) -> None:
    run = _mass_run(tmp_path)
    model = run / "batch-0007" / "model.json"
    payload = json.loads(model.read_text(encoding="utf-8"))
    payload["skipped"].append({"site_id": SMALL, "field": "description", "reason": "no evidence"})
    model.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="not the evidence bound"):
        G.census(run)
    payload["skipped"] = payload["skipped"][:4]
    model.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="without all five fields"):
        G.census(run)


def test_a_repaired_or_unresolved_or_shared_item_is_withheld_and_the_rest_is_kept() -> None:
    kept, why = G.withheld_reason(BIG, "Q42", shared={"Q42": 1})
    assert (kept, why) == ("Q42", None)
    kept, why = G.withheld_reason(CLARE.site_id, CLARE.old_qid, shared={})
    assert kept is None and f"replaces it with {CLARE.new_qid}" in str(why)
    assert G.withheld_reason(CLARE.site_id, CLARE.new_qid, shared={}) == (CLARE.new_qid, None)
    with pytest.raises(SystemExit, match="neither"):
        G.withheld_reason(CLARE.site_id, "Q1", shared={})
    kept, why = G.withheld_reason(TIKAL.site_id, TIKAL.old_qid, shared={})
    assert kept is None and "unresolved" in str(why)
    kept, why = G.withheld_reason(BIG, "Q173527", shared={"Q173527": 2})
    assert kept is None and "carried by 2 curated sites" in str(why)
    assert G.withheld_reason(BIG, None, shared={}) == (None, None)


def test_a_link_the_repair_replaces_does_not_make_an_item_shared() -> None:
    """The Tomb of Artaxerxes III wrongly carries Persepolis' Q129072; Persepolis keeps its item."""
    tomb = next(site for site in qid_repair.SITES if site.name == "Tomb of Artaxerxes III")
    counts = G.shared_counts(
        [
            {"site_id": tomb.site_id, "value": tomb.old_qid},
            {"site_id": "persepolis", "value": tomb.old_qid},
        ]
    )
    assert counts == {tomb.old_qid: 1}


def _wave3(rule: str, name: str | None = None) -> qid_repair.Site:
    return next(
        site
        for site in qid_repair.WAVE3_SITES
        if site.rule == rule and (name is None or site.name == name)
    )


def test_a_link_wave_three_keeps_still_counts_toward_a_shared_item() -> None:
    """Pandavleni Caves' Q7130537 is right (link-right), and 'Cave 20 - Pandavleni Caves' carries it
    too: the item stays shared for both, so the one cave is not given the whole complex's articles.
    Only a link the repair replaces (rule A or B) stops counting."""
    kept = _wave3("link-right", "Pandavleni Caves")
    replaced = _wave3("B", "Siega Verde")
    counts = G.shared_counts(
        [
            {"site_id": kept.site_id, "value": kept.old_qid},
            {"site_id": "cave-20", "value": kept.old_qid},
            {"site_id": replaced.site_id, "value": replaced.old_qid},
            {"site_id": "coa-valley", "value": replaced.old_qid},
        ],
        repairs=qid_repair.WAVE3_SITES,
    )
    assert counts == {kept.old_qid: 2, replaced.old_qid: 1}


def test_wave_three_withholds_a_type_link_and_a_duplicate_and_keeps_a_right_link() -> None:
    wave3 = qid_repair.WAVE3_SITES
    keep_type = _wave3("keep-type", "Dolmens of Sardinia")
    kept, why = G.withheld_reason(keep_type.site_id, "Q101659", shared={}, repairs=wave3)
    assert kept is None and "a type" in str(why) and "wave3/PLAN.md" in str(why)
    duplicate = _wave3("duplicate-candidate")
    kept, why = G.withheld_reason(duplicate.site_id, duplicate.old_qid, shared={}, repairs=wave3)
    assert kept is None and "duplicate candidate" in str(why)
    right = _wave3("link-right", "Psychro Cave")
    assert G.withheld_reason(right.site_id, right.old_qid, shared={}, repairs=wave3) == (
        right.old_qid,
        None,
    )
    unresolved = _wave3("unresolved")
    kept, why = G.withheld_reason(unresolved.site_id, unresolved.old_qid, shared={}, repairs=wave3)
    assert kept is None and "unresolved" in str(why) and "wave3/PLAN.md" in str(why)
    replaced = _wave3("B", "Siega Verde")
    assert G.withheld_reason(replaced.site_id, replaced.new_qid, shared={}, repairs=wave3) == (
        replaced.new_qid,
        None,
    )


def test_a_kept_link_production_no_longer_carries_stops_the_plan() -> None:
    """A verdict that keeps a link was made about that link; another item in its place is news the
    plan must not read past."""
    for rule in ("keep-type", "duplicate-candidate", "link-right", "unresolved"):
        site = _wave3(rule)
        with pytest.raises(SystemExit, match="read the site again"):
            G.withheld_reason(site.site_id, "Q1", shared={}, repairs=qid_repair.WAVE3_SITES)


def _export(tmp_path: Path, rows: list[dict], external: list[dict]) -> Path:
    out = tmp_path / "export"
    lanes.write_jsonl(out / "unified_sites.jsonl", rows)
    lanes.write_jsonl(
        out / "card_stats.jsonl",
        [{"site_id": row["id"], "card_description": "a card"} for row in rows],
    )
    lanes.write_jsonl(out / "site_external_ids.jsonl", external)
    return out


def _row(site_id: str, name: str, **values: object) -> dict:
    return {
        "id": site_id,
        "name": name,
        "description": "a description",
        "period_start": -1500,
        "site_type": "Temple",
        "country": "Greece",
        "source_id": "ancient_nerds",
        **values,
    }


def test_the_records_carry_the_fresh_values_the_fields_to_ask_and_the_routes(
    tmp_path: Path,
) -> None:
    questions = G.census(_mass_run(tmp_path))
    export = _export(
        tmp_path,
        [_row(BIG, "Big Site"), _row(SMALL, "Small Site", period_start=-450, country="Georgia")],
        [
            {"site_id": BIG, "kind": "wikidata_qid", "value": "Q1000"},
            {"site_id": SMALL, "kind": "wikidata_qid", "value": "Q2000"},
        ],
    )
    sitelinks = {SMALL: {"qid": "Q2000", "title": "Small Site (Greece)", "refused": None}}
    big, small = G.site_records(questions, export_dir=export, sitelinks=sitelinks)
    assert big["rerun_fields"] == FIELDS and small["rerun_fields"] == ["period_start", "country"]
    # The gap run asks again; it buys no search - `search_fields` is the search lane's key alone.
    for record in (big, small):
        assert SE.SEARCH_FIELDS_KEY not in record and SE.search_slots(record) == ()
    assert small["source_batch"] == "batch-0007"
    assert small["gap_reasons"] == [G.EMPTY_STREAM, G.NO_VERDICT]
    values = {row["field"]: row["current_value"] for row in small["findings"]}
    assert (values["period_start"], values["country"]) == (-450, "Georgia")  # the export's, fresh
    assert big[F.WIKIDATA_ROUTE_KEY] == F.WIKIDATA_ROUTE_NARROW
    assert small[F.ENWIKI_SITELINK_KEY] == {"qid": "Q2000", "title": "Small Site (Greece)"}
    assert F.ENWIKI_SITELINK_KEY not in big
    features = [t.feature for t in F.targets_for_site(small)]
    assert features[:2] == [F.FEATURE_ENWIKI, F.FEATURE_ENWIKI_SITELINK]


def test_a_withheld_item_leaves_the_record_without_a_qid_and_says_why(tmp_path: Path) -> None:
    questions = G.census(_mass_run(tmp_path))
    export = _export(
        tmp_path,
        [_row(BIG, "Big Site"), _row(SMALL, "Small Site")],
        [
            {"site_id": BIG, "kind": "wikidata_qid", "value": "Q7"},
            {"site_id": SMALL, "kind": "wikidata_qid", "value": "Q7"},
        ],
    )
    for record in G.site_records(questions, export_dir=export, sitelinks={}):
        assert "wikidata_qid" not in record and F.WIKIDATA_ROUTE_KEY not in record
        assert record["withheld_wikidata_qid"]["qid"] == "Q7"
        assert [t.feature for t in F.targets_for_site(record)] == [F.FEATURE_ENWIKI]


def test_the_gap_batches_never_take_the_mass_lanes_ids() -> None:
    records = [{"site_id": str(n)} for n in range(31)]
    planned = G.batches(records)
    assert [b.batch_id for b in planned] == ["gap-0001", "gap-0002", "gap-0003"]
    assert [len(b.sites) for b in planned] == [15, 15, 1]
    assert {b.pass_name for b in planned} == {G.R.DISCOVER_PASS}
    # one chunking, the runner's own: its size guard holds here too
    with pytest.raises(G.R.InputError, match="batch size must be >= 1"):
        G.batches(records, size=0)
    assert [b.batch_id for b in G.R.assign_batches(records, 30)] == ["batch-0001", "batch-0002"]


def test_a_missing_article_is_told_from_a_page_and_from_a_cut_page(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    missing.write_text(
        json.dumps({"query": {"pages": {"-1": {"title": "X", "missing": ""}}}}), encoding="utf-8"
    )
    present = tmp_path / "present.txt"
    present.write_text(
        json.dumps({"query": {"pages": {"1": {"pageid": 1, "extract": "x"}}}}), encoding="utf-8"
    )
    cut = tmp_path / "cut.txt"
    cut.write_text('{"query": {"pages": {"1": {"extract": "' + "x" * F.MAX_PAGE_BYTES, "utf-8")
    broken = tmp_path / "broken.txt"
    broken.write_text("{not json", encoding="utf-8")
    assert G.enwiki_missing(missing) is True
    assert G.enwiki_missing(present) is False
    assert G.enwiki_missing(cut) is False
    with pytest.raises(SystemExit, match="neither JSON nor cut"):
        G.enwiki_missing(broken)


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        ({"error": {"code": "maxlag"}}, "without query.pages"),
        ({}, "without query.pages"),
        ({"batchcomplete": "", "query": {"pages": {}}}, "without query.pages"),
        (
            {"batchcomplete": "", "query": {"pages": {"-1": {"title": "A#B", "invalid": ""}}}},
            "neither an article",
        ),
    ],
)
def test_an_enwiki_answer_that_is_neither_an_article_nor_missing_is_refused(
    tmp_path: Path, answer: dict, why: str
) -> None:
    """Read as 'the article exists', each of these would silently keep a site off the sitelink route.

    Measured 2026-09-23 over all 5,004 enwiki files of the mass run: 3,699 articles or cut pages,
    1,305 missing, 0 of any other shape - so the refusal costs the real run nothing.
    """
    path = tmp_path / "answer.txt"
    path.write_text(json.dumps(answer), encoding="utf-8")
    with pytest.raises(SystemExit, match=why):
        G.enwiki_missing(path)


def test_a_question_the_census_finds_twice_is_refused(tmp_path: Path) -> None:
    """Two records of one (site, field) mean the run's own record is not the shape the census reads."""
    run = _mass_run(tmp_path)
    model = run / "batch-0007" / "model.json"
    payload = json.loads(model.read_text(encoding="utf-8"))
    payload["failures"].append(dict(payload["failures"][0]))
    model.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="is a gap question twice"):
        G.census(run)


def test_a_sitelink_resolved_for_another_item_than_the_exports_is_refused(tmp_path: Path) -> None:
    questions = G.census(_mass_run(tmp_path))
    export = _export(
        tmp_path,
        [_row(BIG, "Big Site"), _row(SMALL, "Small Site")],
        [
            {"site_id": BIG, "kind": "wikidata_qid", "value": "Q1000"},
            {"site_id": SMALL, "kind": "wikidata_qid", "value": "Q2000"},
        ],
    )
    stale = {SMALL: {"qid": "Q1999", "title": "Small Site (Greece)", "refused": None}}
    with pytest.raises(SystemExit, match="resolved for Q1999, not Q2000"):
        G.site_records(questions, export_dir=export, sitelinks=stale)


def _export_answers(rows: list[dict]) -> Any:
    def run(sql: str) -> str:
        if "FROM unified_sites WHERE" in sql:
            return "".join(json.dumps(row) + "\n" for row in rows)
        return ""

    return run


def test_an_export_that_misses_a_site_or_returns_a_foreign_one_is_refused(tmp_path: Path) -> None:
    questions = G.census(_mass_run(tmp_path))
    full = [_row(BIG, "Big Site"), _row(SMALL, "Small Site")]
    counts = G.export(questions, tmp_path / "ok", run=_export_answers(full))
    assert counts["unified_sites"] == 2
    with pytest.raises(SystemExit, match="missing"):
        G.export(questions, tmp_path / "short", run=_export_answers(full[:1]))
    foreign = [full[0], _row(SMALL, "Small Site", source_id="lyra")]
    with pytest.raises(SystemExit, match="not curated"):
        G.export(questions, tmp_path / "foreign", run=_export_answers(foreign))


def test_a_repair_rule_the_plan_does_not_read_stops_it() -> None:
    """A rule added to the repair later must be read here before any site under it is planned."""
    odd = qid_repair.Site(TIKAL.site_id, TIKAL.name, "keep-name", TIKAL.old_qid, None, "", None, ())
    with pytest.raises(SystemExit, match="none this plan reads"):
        G.withheld_reason(TIKAL.site_id, TIKAL.old_qid, shared={}, repairs=(odd,))
