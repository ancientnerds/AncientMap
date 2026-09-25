"""Does S0 read every curated site once, flag it from data, and put it in the design's order?

`phase4/plan4.py` (WB-A3): the one read-only production SELECT (through a recording runner here -
no test reaches a database), the derived flags (shared anchors, scope-pending, duplicate pairs,
cleared defects, T03), the order (pilot, cleared defects, T03, the rest) and the batches of 15.
The mutation cases are `PHASE4_SOURCES_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import run as R  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import plan4 as P  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402

from tests.remediation.test_phase4_sources import Web  # noqa: E402

MAIN_OUTPUT = REPO / "output" / "remediation"


def uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def row(n: int, **over: Any) -> dict[str, Any]:
    """One row in the exact shape `PLAN_SQL` returns (measured on production 2026-09-23)."""
    description = over.pop("description", f"Site {n} is an archaeological site.")
    card = over.pop("card", None)
    base: dict[str, Any] = {
        "id": uuid(n),
        "name": f"Site {n}",
        "country": "Malta",
        "site_type": "Temple complex",
        "period_start": -3000,
        "period_end": None,
        "lat": 35.0 + n,
        "lon": 14.0,
        "description": description,
        "description_sha256": None if description is None else M.text_sha256(description),
        "raw_data": None,
        "raw_data_sha256": None,
        "source_url": None,
        "card": card,
        "card_sha256": None if card is None else M.text_sha256(card),
        "wikidata_qid": f"Q{1000 + n}",
        "enwiki_title": f"Site {n}",
        "names": [f"Site {n}"],
        "in_snapshot": True,
        "snapshot_description": None,
    }
    base.update(over)
    return base


def build(
    rows: list[dict[str, Any]],
    *,
    cleared: Mapping[str, set[str]] | None = None,
    t03: Mapping[str, Mapping[str, str]] | None = None,
    gold: list[str] | None = None,
    item_names: Mapping[str, list[str]] | None = None,
) -> list[M.PlanSite]:
    shared = P.shared_qids_of(rows)
    names = item_names if item_names is not None else {qid: [] for qid in shared}
    return P.build_plan(
        rows, cleared=cleared or {}, t03=t03 or {}, gold=gold or [], item_names=names
    )


def by_id(sites: list[M.PlanSite]) -> dict[str, M.PlanSite]:
    return {site.site_id: site for site in sites}


# ======================================================================================= the read


def test_the_read_is_one_select_and_nothing_else() -> None:
    sql = P.PLAN_SQL
    assert sql.startswith("SELECT to_jsonb(t)::text FROM (SELECT ")
    assert sql.count(";") == 1 and sql.endswith(";")
    for verb in (
        "INSERT",
        "UPDATE",
        "DELETE",
        "ALTER",
        "DROP",
        "CREATE",
        "TRUNCATE",
        "GRANT",
        "COPY",
        "apply_remediation_change",
        "BEGIN",
        "COMMIT",
    ):
        assert not re.search(rf"\b{verb}\b", sql, re.IGNORECASE), verb
    assert "WHERE u.source_id = 'ancient_nerds'" in sql
    assert f"s.snapshot_id = '{P.SNAPSHOT_ID}'" in sql
    assert P.SNAPSHOT_ID.startswith("d4526691")


def test_the_hashes_are_postgres_own_and_the_ids_come_from_site_external_ids() -> None:
    sql = P.PLAN_SQL
    for column in ("u.description", "u.raw_data::text", "c.card_description"):
        assert f"encode(sha256(convert_to({column}, 'UTF8')), 'hex')" in sql
    assert "e.kind = 'wikidata_qid'" in sql and "e.kind = 'enwiki_title'" in sql
    assert "unified_site_names" in sql


def test_the_read_goes_through_the_runner_it_is_given(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []

    def runner(sql: str, *, host: str) -> str:
        # A fake psql refuses what production would never be sent here: anything but one SELECT.
        if not sql.startswith("SELECT ") or sql.count(";") != 1 or not sql.endswith(";"):
            raise AssertionError(f"not one read-only statement: {sql[:80]!r}")
        seen.append((sql, host))
        return json.dumps(row(1)) + "\n" + json.dumps(row(2)) + "\n"

    args = argparse.Namespace(out=str(tmp_path / "rows.jsonl"), host="vps")
    assert P.cmd_read(args, runner=runner) == 0

    assert seen == [(P.PLAN_SQL, "vps")]
    assert [r["id"] for r in R.read_jsonl(tmp_path / "rows.jsonl")] == [uuid(1), uuid(2)]


def test_a_read_line_that_is_not_a_json_object_stops_the_read() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        P.read_rows(lambda sql, *, host: "BEGIN\n")


# ================================================================================== the flags


def test_every_row_becomes_a_plan_site_with_its_old_values() -> None:
    raw = {"description_citations": [{"n": 1}]}
    one = row(1, raw_data=raw, raw_data_sha256="a" * 64, card="A card.", snapshot_description="old")

    (site,) = build([one])

    assert site.site_id == uuid(1)
    assert site.raw_data == raw and site.raw_data_sha256 == "a" * 64
    assert site.card == "A card." and site.card_sha256 == M.text_sha256("A card.")
    assert site.in_snapshot is True and site.snapshot_description == "old"
    assert site.flags == frozenset()


def test_the_read_tells_a_site_absent_from_the_snapshot_from_a_null_text_in_it() -> None:
    """`snapshot_description` is NULL both for a site d4526691 does not have and for one it holds
    without a description; lane L may claim the second and never the first, so the read asks for
    the row itself (`in_snapshot`) and the plan carries it."""
    assert (
        "EXISTS (SELECT 1 FROM snapshot_rows s "
        f"WHERE s.snapshot_id = '{P.SNAPSHOT_ID}' AND s.site_id = u.id) AS in_snapshot"
    ) in P.PLAN_SQL
    absent, null_text = build([row(1, in_snapshot=False), row(2)])
    assert (absent.in_snapshot, absent.snapshot_description) == (False, None)
    assert (null_text.in_snapshot, null_text.snapshot_description) == (True, None)


def test_a_digest_that_is_not_the_texts_is_refused() -> None:
    bad = row(1)
    bad["description_sha256"] = M.text_sha256("another text")
    with pytest.raises(ValueError, match="description_sha256"):
        build([bad])


def test_a_row_of_another_shape_is_refused() -> None:
    extra = row(1)
    extra["updated_at"] = "2026-08-17"
    with pytest.raises(R.InputError, match="unknown keys"):
        build([extra])
    missing = row(1)
    del missing["names"]
    with pytest.raises(R.InputError, match="missing keys"):
        build([missing])
    for names in ("Site 1", ["Site 1", None], None):
        with pytest.raises(R.InputError, match="names is not a list of strings"):
            build([row(1, names=names)])


def test_the_aliases_are_the_other_stored_names_once_each_in_order() -> None:
    one = row(1, names=["Site 1", "Tarxien", "Ħal Tarxien", "Tarxien"])
    (site,) = build([one])
    assert site.aliases == ("Tarxien", "Ħal Tarxien")


def test_a_qid_or_title_two_sites_store_is_shared_and_one_site_is_not() -> None:
    rows = [
        row(1, wikidata_qid="Q9", enwiki_title="Stonehenge"),
        row(2, wikidata_qid="Q9", enwiki_title="Altar Stone"),
        row(3, enwiki_title="Stonehenge"),
        row(4),
    ]
    sites = by_id(build(rows))
    assert M.SiteFlag.SHARED_QID in sites[uuid(1)].flags
    assert M.SiteFlag.SHARED_QID in sites[uuid(2)].flags
    assert M.SiteFlag.SHARED_QID not in sites[uuid(3)].flags
    assert M.SiteFlag.SHARED_TITLE in sites[uuid(1)].flags
    assert M.SiteFlag.SHARED_TITLE in sites[uuid(3)].flags
    assert M.SiteFlag.SHARED_TITLE not in sites[uuid(2)].flags
    assert sites[uuid(4)].flags == frozenset()


def test_a_missing_qid_or_title_is_never_shared() -> None:
    rows = [
        row(1, wikidata_qid=None, enwiki_title=None),
        row(2, wikidata_qid=None, enwiki_title=None),
    ]
    assert all(site.flags == frozenset() for site in build(rows))


@pytest.mark.parametrize(
    ("period_start", "period_end", "lon", "pending"),
    [
        (-3000, None, 14.0, False),
        (400, 900, 14.0, True),  # rest of the world: after 500 AD
        (1200, 1400, -90.0, False),  # the Americas: up to 1500 AD
        (1200, 1600, -90.0, True),
        (None, None, 14.0, True),  # undated: E4 hides it too
        (None, 300, 14.0, False),
    ],
)
def test_a_site_outside_the_date_window_or_undated_is_scope_pending(
    period_start: int | None, period_end: int | None, lon: float, pending: bool
) -> None:
    (site,) = build([row(1, period_start=period_start, period_end=period_end, lon=lon)])
    assert (M.SiteFlag.SCOPE_PENDING in site.flags) is pending


def test_the_cleared_defects_flag_their_own_text() -> None:
    rows = [row(1), row(2), row(3)]
    cleared = {uuid(1): {"description"}, uuid(2): {"card_description"}}
    sites = by_id(build(rows, cleared=cleared))
    assert sites[uuid(1)].flags == {M.SiteFlag.CLEARED_DESCRIPTION_DEFECT}
    assert sites[uuid(2)].flags == {M.SiteFlag.CLEARED_CARD_DEFECT}


def test_t03_severe_is_flagged_only_for_the_description() -> None:
    rows = [row(1), row(2), row(3)]
    t03 = {
        uuid(1): {"description": "severe"},
        uuid(2): {"card_description": "severe"},
        uuid(3): {"description": "moderate"},
    }
    sites = by_id(build(rows, t03=t03))
    assert sites[uuid(1)].flags == {M.SiteFlag.T03, M.SiteFlag.T03_SEVERE}
    assert sites[uuid(2)].flags == {M.SiteFlag.T03}
    assert sites[uuid(3)].flags == {M.SiteFlag.T03}


def _pair(km_apart: float, *, second_name: str = "Templos de Tarxien") -> list[dict[str, Any]]:
    degrees = km_apart / 111.195
    return [
        row(1, name="Tarxien Temples", wikidata_qid="Q1", lat=35.8686, lon=14.5117),
        row(2, name=second_name, wikidata_qid="Q1", lat=35.8686 + degrees, lon=14.5117),
    ]


NAMES = {"Q1": ["Tarxien Temples", "Templos de Tarxien", "Tempji ta' Ħal Tarxien"]}


def test_two_sites_named_by_their_shared_item_within_2_km_are_a_duplicate_pair() -> None:
    sites = build(_pair(1.0), item_names=NAMES)
    assert all(M.SiteFlag.DUPLICATE_PAIR in site.flags for site in sites)


def test_a_shared_item_beyond_2_km_or_under_another_name_is_no_pair() -> None:
    far = build(_pair(3.0), item_names=NAMES)
    unnamed = build(_pair(1.0, second_name="Tarxien South Temple"), item_names=NAMES)
    assert not any(M.SiteFlag.DUPLICATE_PAIR in site.flags for site in far + unnamed)


def test_the_pair_names_are_compared_folded() -> None:
    sites = build(_pair(1.0, second_name="templos de TARXIEN"), item_names=NAMES)
    assert all(M.SiteFlag.DUPLICATE_PAIR in site.flags for site in sites)
    assert SG.fold("Tempji ta' Ħal Tarxien") == "tempji ta ħal tarxien"


def test_one_fold_serves_the_gate_the_pairs_and_web_identity() -> None:
    """The name fold is `subject_gate.fold`, imported - never a second copy (review 2026-09-23:
    plan4, route_stage and subject_gate each carried their own)."""
    for module in ("plan4", "route_stage"):
        tree = ast.parse(
            (REPO / "scripts" / "remediation" / "phase4" / f"{module}.py").read_text(
                encoding="utf-8"
            )
        )
        defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert not {"fold_name", "_fold_text", "_fold", "fold"} & defined, module
        calls = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "SG"
        }
        assert "fold" in calls, module
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "normalize_name" not in imported, module


def test_a_shared_item_without_its_names_stops_the_plan() -> None:
    with pytest.raises(R.InputError, match="no labels or aliases"):
        build(_pair(1.0), item_names={})


# ================================================================================== the order


def test_the_order_is_pilot_then_cleared_then_t03_then_the_rest() -> None:
    rows = [row(n) for n in range(1, 8)]
    sites = build(
        rows,
        gold=[uuid(6), uuid(2)],
        cleared={uuid(5): {"description"}, uuid(2): {"card_description"}},
        t03={uuid(7): {"description": "severe"}, uuid(4): {"card_description": "moderate"}},
    )
    assert [site.site_id for site in sites] == [
        uuid(6), uuid(2),  # the pilot, in the order given
        uuid(5),  # a cleared defect (uuid(2) is already placed)
        uuid(4), uuid(7),  # T03, by site id
        uuid(1), uuid(3),  # the rest
    ]  # fmt: skip


@pytest.mark.parametrize("field", ["cleared", "t03", "gold"])
def test_a_site_id_that_is_not_a_curated_row_stops_the_plan(field: str) -> None:
    stranger = uuid(99)
    wanted: dict[str, Any] = {
        "cleared": {"cleared": {stranger: {"description"}}},
        "t03": {"t03": {stranger: {"description": "severe"}}},
        "gold": {"gold": [stranger]},
    }[field]
    with pytest.raises(R.InputError, match="not curated rows"):
        build([row(1)], **wanted)


def test_a_pilot_site_listed_twice_or_a_row_listed_twice_stops_the_plan() -> None:
    with pytest.raises(R.InputError, match="twice"):
        build([row(1)], gold=[uuid(1), uuid(1)])
    with pytest.raises(R.InputError, match="twice"):
        build([row(1), row(1)])


def test_a_cleared_field_that_is_not_a_text_field_stops_the_plan() -> None:
    with pytest.raises(R.InputError, match="not text fields"):
        build([row(1)], cleared={uuid(1): {"country"}})


# ================================================================================== the files


def test_the_plan_is_batches_of_15_named_p4_and_byte_identical_across_runs(tmp_path: Path) -> None:
    sites = build([row(n) for n in range(1, 32)])
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"

    P.write_plan(first, sites, pilot=0)
    P.write_plan(second, sites, pilot=0)

    assert first.read_bytes() == second.read_bytes()
    batches = R.read_jsonl(first)
    assert [b["batch_id"] for b in batches] == ["p4-0001", "p4-0002", "p4-0003"]
    assert [len(b["sites"]) for b in batches] == [15, 15, 1]
    back = [M.PlanSite.from_dict(s) for b in batches for s in b["sites"]]
    assert back == sites


def test_the_pilots_sites_fill_their_own_batches_and_the_rest_continue_the_numbering(
    tmp_path: Path,
) -> None:
    """The pilot runs its own batches (design pilot_and_thresholds; the mass run takes the plan's
    later batches in the same run directory): a batch that held pilot sites and other sites would
    put the others into the pilot's model calls and its audit. So the pilot's last batch may be
    short, and the rest start a new batch."""
    sites = build([row(n) for n in range(1, 33)], gold=[uuid(n) for n in range(1, 18)])
    path = tmp_path / "PLAN4.jsonl"

    P.write_plan(path, sites, pilot=17)

    batches = R.read_jsonl(path)
    assert [(b["batch_id"], b["ordinal"]) for b in batches] == [
        ("p4-0001", 1), ("p4-0002", 2), ("p4-0003", 3)
    ]  # fmt: skip
    assert [len(b["sites"]) for b in batches] == [15, 2, 15]
    pilot = [s["site_id"] for b in batches[:2] for s in b["sites"]]
    assert pilot == [uuid(n) for n in range(1, 18)]
    assert [M.PlanSite.from_dict(s) for b in batches for s in b["sites"]] == sites


def test_the_pilot_is_a_leading_part_of_the_plan(tmp_path: Path) -> None:
    sites = build([row(n) for n in range(1, 4)])
    with pytest.raises(R.InputError, match="pilot"):
        P.write_plan(tmp_path / "PLAN4.jsonl", sites, pilot=4)
    assert not (tmp_path / "PLAN4.jsonl").exists()


def test_the_cleared_defects_are_the_report_only_rows_of_the_write_dry_run() -> None:
    rows = [
        {"site_id": uuid(1), "field": "description", "rule": "report-only-field"},
        {"site_id": uuid(1), "field": "card_description", "rule": "report-only-field"},
        {"site_id": uuid(2), "field": "country", "rule": "reviewer-did-not-clear"},
    ]
    assert P.cleared_defects(rows) == {uuid(1): {"description", "card_description"}}
    with pytest.raises(R.InputError, match="outside the two text fields"):
        P.cleared_defects([{"site_id": uuid(3), "field": "country", "rule": "report-only-field"}])


def test_the_t03_findings_keep_the_worst_severity_per_field() -> None:
    rows = [
        {"site_id": uuid(1), "field": "description", "severity": "moderate"},
        {"site_id": uuid(1), "field": "description", "severity": "severe"},
        {"site_id": uuid(1), "field": "card_description", "severity": "moderate"},
    ]
    assert P.t03_findings(rows) == {
        uuid(1): {"description": "severe", "card_description": "moderate"}
    }
    with pytest.raises(R.InputError, match="cannot place"):
        P.t03_findings([{"site_id": uuid(2), "field": "description", "severity": "fatal"}])


# ============================================================================ the shared items


def _names_answer(qids: list[str]) -> bytes:
    return json.dumps(
        {
            "entities": {
                qid: {
                    "id": qid,
                    "labels": {"en": {"language": "en", "value": f"Item {qid}"}},
                    "aliases": {"es": [{"language": "es", "value": f"Cosa {qid}"}]},
                }
                for qid in qids
            }
        }
    ).encode("utf-8")


def test_the_shared_items_names_are_read_ten_at_a_time_and_stored(tmp_path: Path) -> None:
    qids = [f"Q{n}" for n in range(1, 26)]
    web = Web()
    for start in range(0, 25, 10):
        chunk = sorted(qids)[start : start + 10]
        web.add(P.item_names_url(chunk), _names_answer(chunk))

    names = P.fetch_item_names(
        qids,
        fetcher=web.fetcher(),
        evidence=tmp_path / "evidence",
        ledger=tmp_path / "LEDGER.jsonl",
        sleep=lambda _: None,
    )

    assert set(names) == set(qids)
    assert names["Q7"] == ["Cosa Q7", "Item Q7"]
    assert len(web.asked("props=labels%7Caliases")) == 3
    assert len(list((tmp_path / "evidence").iterdir())) == 3


def test_a_names_request_that_fails_stops_the_plan(tmp_path: Path) -> None:
    web = Web().add(P.item_names_url(["Q1"]), b"", status=500)
    with pytest.raises(R.InputError, match="could not be read"):
        P.fetch_item_names(
            ["Q1"],
            fetcher=web.fetcher(),
            evidence=tmp_path / "evidence",
            ledger=tmp_path / "LEDGER.jsonl",
            sleep=lambda _: None,
        )


def test_an_item_the_answer_does_not_have_stops_the_plan() -> None:
    body = json.dumps({"entities": {"Q1": {"id": "Q1", "missing": ""}}}).encode()
    with pytest.raises(R.InputError, match="no such item"):
        P.parse_item_names(body, ["Q1"])


# ======================================================================================== CLI


def test_build_writes_the_plan_and_prints_its_exit_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [row(1), row(2, enwiki_title="Site 2" + chr(10) + "https://example.org/2")]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "names.json").write_text("{}")
    (tmp_path / "refused.jsonl").write_text(
        json.dumps({"site_id": uuid(2), "field": "description", "rule": "report-only-field"}) + "\n"
    )
    (tmp_path / "t03.jsonl").write_text(
        json.dumps({"site_id": uuid(1), "field": "description", "severity": "severe"}) + "\n"
    )
    (tmp_path / "gold.json").write_text(json.dumps({"records": [{"site_id": uuid(1)}]}))

    code = P.main(
        [
            "build",
            f"--rows={tmp_path / 'rows.jsonl'}",
            f"--names={tmp_path / 'names.json'}",
            f"--refused={tmp_path / 'refused.jsonl'}",
            f"--t03={tmp_path / 't03.jsonl'}",
            f"--gold={tmp_path / 'gold.json'}",
            f"--out={tmp_path / 'PLAN4.jsonl'}",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0 and out.rstrip().endswith("STAGE_EXIT=0")
    # The gold site is the pilot: it fills its own batch, and the rest starts the next one.
    pilot, rest = R.read_jsonl(tmp_path / "PLAN4.jsonl")
    assert [s["site_id"] for s in pilot["sites"]] == [uuid(1)]
    assert [s["site_id"] for s in rest["sites"]] == [uuid(2)]
    summary = json.loads(out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert summary["invalid_titles"] == [uuid(2)]
    assert (summary["pilot_sites"], summary["pilot_batches"]) == (1, 1)


def _build_inputs(tmp_path: Path, rows: list[dict[str, Any]]) -> list[str]:
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "names.json").write_text("{}")
    (tmp_path / "refused.jsonl").write_text(
        json.dumps({"site_id": uuid(2), "field": "description", "rule": "report-only-field"}) + "\n"
    )
    (tmp_path / "t03.jsonl").write_text(
        json.dumps({"site_id": uuid(1), "field": "description", "severity": "severe"}) + "\n"
    )
    return [
        "build",
        f"--rows={tmp_path / 'rows.jsonl'}",
        f"--names={tmp_path / 'names.json'}",
        f"--refused={tmp_path / 'refused.jsonl'}",
        f"--t03={tmp_path / 't03.jsonl'}",
        f"--out={tmp_path / 'PLAN4.jsonl'}",
    ]


def test_build_takes_the_pilot_from_pilot_jsonl_in_its_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The design's pilot is about 120 sites (PILOT.jsonl, `phase4/pilot4.py`), not only the 36
    gold sites: `--pilot` names it, and its sites lead the plan in PILOT.jsonl's order."""
    argv = _build_inputs(tmp_path, [row(n) for n in range(1, 5)])
    pilot = tmp_path / "PILOT.jsonl"
    lines = [{"site_id": uuid(4), "strata": ["gold"]}, {"site_id": uuid(3), "strata": ["draw-W"]}]
    pilot.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")

    assert P.main([*argv, f"--pilot={pilot}"]) == 0

    out = capsys.readouterr().out
    first, second = R.read_jsonl(tmp_path / "PLAN4.jsonl")
    assert [s["site_id"] for s in first["sites"]] == [uuid(4), uuid(3)]
    assert [s["site_id"] for s in second["sites"]] == [uuid(2), uuid(1)]  # cleared, then T03
    summary = json.loads(out.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert (summary["pilot_sites"], summary["pilot_batches"]) == (2, 1)


def test_a_pilot_line_without_a_site_id_stops_the_plan(tmp_path: Path) -> None:
    argv = _build_inputs(tmp_path, [row(1), row(2)])
    pilot = tmp_path / "PILOT.jsonl"
    pilot.write_text(json.dumps({"strata": ["gold"]}) + "\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="site id"):
        P.main([*argv, f"--pilot={pilot}"])


def test_the_pilot_comes_from_the_gold_standard_or_from_pilot_jsonl_never_both(
    tmp_path: Path,
) -> None:
    argv = _build_inputs(tmp_path, [row(1)])
    with pytest.raises(SystemExit):
        P.main([*argv, f"--gold={tmp_path / 'gold.json'}", f"--pilot={tmp_path / 'PILOT.jsonl'}"])


def test_a_stored_title_with_a_control_character_is_listed_for_the_repair() -> None:
    """Petra's row stores `Petra`, a newline and a second URL as its enwiki_title (production,
    2026-09-23): MediaWiki refuses the title. The plan is built anyway (S1 routes the site) and
    names the row."""
    petra = row(2, enwiki_title="Petra" + chr(10) + "https://www.khanacademy.org/a/petra")
    rows = [row(1), petra, row(3, enwiki_title="Site" + chr(9) + "3"), row(4, enwiki_title=None)]
    assert P.invalid_titles(rows) == [uuid(2), uuid(3)]
    assert len(build(rows)) == 4


def test_a_failing_step_still_prints_its_exit_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(FileNotFoundError):
        P.main(["build", f"--rows={tmp_path / 'absent.jsonl'}"])
    assert capsys.readouterr().out.rstrip().endswith("STAGE_EXIT=1")


def test_names_reads_the_shared_items_of_the_rows(tmp_path: Path) -> None:
    rows = [row(1, wikidata_qid="Q5"), row(2, wikidata_qid="Q5"), row(3)]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    web = Web().add(P.item_names_url(["Q5"]), _names_answer(["Q5"]))
    args = argparse.Namespace(
        rows=str(tmp_path / "rows.jsonl"),
        out=str(tmp_path / "names.json"),
        evidence=str(tmp_path / "evidence"),
        ledger=str(tmp_path / "LEDGER.jsonl"),
        pacing_dir=str(tmp_path / "pacing"),
    )

    assert P.cmd_names(args, fetcher=web.fetcher()) == 0

    assert json.loads((tmp_path / "names.json").read_text()) == {"Q5": ["Cosa Q5", "Item Q5"]}


# ======================================================================== lane L's own plan


def test_the_legacy_plan_is_every_curated_site_in_id_order_from_batch_1001(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Owner decision 2026-09-24 ("Alle kennzeichnen"): lane L marks every March-AI text Phase 4
    did not write, so its population is every curated site of a fresh read - not a Phase-4 run's
    batches. Its plan is its own: batches of 15 marked `pass: phase4-legacy`, numbered from p4-1001
    so no L write batch (`p4l-NNNN`) names a P4 plan batch, in site-id order whatever the read's
    order, and no flag is derived (they steer Phase 4's stages; lane L asks none)."""
    rows = [row(n) for n in range(16, 0, -1)]
    rows[0]["period_start"] = rows[0]["period_end"] = None  # would be scope-pending in `build`
    rows[1]["raw_data"] = {M.PROVENANCE_KEY: {"lane": "W"}}
    rows[1]["raw_data_sha256"] = "b" * 64
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "LEGACY4.jsonl"

    code = P.main(["legacy", f"--rows={tmp_path / 'rows.jsonl'}", f"--out={out}"])

    printed = capsys.readouterr().out
    assert code == 0 and printed.rstrip().endswith("STAGE_EXIT=0")
    batches = R.read_jsonl(out)
    assert [(b["batch_id"], b["ordinal"], b["pass"]) for b in batches] == [
        ("p4-1001", 1001, "phase4-legacy"),
        ("p4-1002", 1002, "phase4-legacy"),
    ]
    sites = [M.PlanSite.from_dict(s) for b in batches for s in b["sites"]]
    assert [s.site_id for s in sites] == [uuid(n) for n in range(1, 17)]
    assert all(site.flags == frozenset() for site in sites)
    summary = json.loads(printed.rstrip().rsplit("STAGE_EXIT=", 1)[0])
    assert (summary["sites"], summary["batches"]) == (16, 2)
    assert (summary["first_batch"], summary["last_batch"]) == ("p4-1001", "p4-1002")
    assert summary["provenance_at_read"] == {"W": 1, "none": 15}
    assert summary["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()


def test_the_legacy_plan_carries_what_lane_l_decides_on_byte_for_byte(tmp_path: Path) -> None:
    """The description, raw_data and the snapshot's text as the read found them - the old value
    the L row's guard compares and the claim's two sides - and the same plan from the same read."""
    raw = {"description_citations": [{"n": 1}]}
    rows = [
        row(1, raw_data=raw, raw_data_sha256="a" * 64, snapshot_description="The pre-March text."),
        row(2, in_snapshot=False),
    ]
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    P.write_legacy_plan(first, P.legacy_sites(rows))
    P.write_legacy_plan(second, P.legacy_sites(list(reversed(rows))))
    assert first.read_bytes() == second.read_bytes()
    one, two = [M.PlanSite.from_dict(s) for b in R.read_jsonl(first) for s in b["sites"]]
    assert (one.description, one.raw_data, one.snapshot_description) == (
        "Site 1 is an archaeological site.",
        raw,
        "The pre-March text.",
    )
    assert (two.in_snapshot, two.snapshot_description) == (False, None)


def test_a_legacy_plan_from_rows_of_another_shape_or_a_site_twice_is_refused() -> None:
    with pytest.raises(R.InputError, match="twice"):
        P.legacy_sites([row(1), row(1)])
    bad = row(2)
    del bad["in_snapshot"]
    with pytest.raises(R.InputError, match="missing keys"):
        P.legacy_sites([row(1), bad])


# ============================================================================ the real inputs


needs_inputs = pytest.mark.skipif(
    not (MAIN_OUTPUT / "logs" / "_write_dry" / "ALL_REFUSED.jsonl").exists()
    or not (MAIN_OUTPUT / "run_t03" / "findings.jsonl").exists()
    or not (MAIN_OUTPUT / "gold_standard" / "sites.json").exists(),
    reason="the gitignored remediation inputs are not in this checkout (output/remediation/...)",
)


@needs_inputs
def test_the_real_inputs_carry_the_counts_the_design_names() -> None:
    cleared = P.cleared_defects(
        R.read_jsonl(MAIN_OUTPUT / "logs" / "_write_dry" / "ALL_REFUSED.jsonl")
    )
    fields = [f for fields in cleared.values() for f in fields]
    assert (len(cleared), fields.count("description"), fields.count("card_description")) == (
        946,
        322,
        709,
    )
    assert len(P.t03_findings(R.read_jsonl(MAIN_OUTPUT / "run_t03" / "findings.jsonl"))) == 875
    assert len(R._gold_site_ids(MAIN_OUTPUT / "gold_standard" / "sites.json")) == 36
