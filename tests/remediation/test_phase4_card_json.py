"""`public/data/card_descriptions.json` for the P5 sitting (WB-D3): pre-render, regenerate, check.

The file is what every API boot upserts into `card_stats`, so it must be byte for byte what the
journalled P5 write leaves in the database, rendered in the one form that reproduces today's file,
with today's key order, new keys appended in UUID order and cleared keys removed - and it must stay
readable by the importer (`api.services.card_descriptions.load_card_descriptions`). Mutation cases:
`PHASE4_WRITE_MUTATIONS` ("p4 card_json") in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from phase4 import card_json as C  # noqa: E402

from api.services.card_descriptions import load_card_descriptions  # noqa: E402
from tests.remediation import phase4_write_fixtures as FX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M  # noqa: E402

A = "aaaaaaaa-0000-4000-8000-000000000001"
B = "bbbbbbbb-0000-4000-8000-000000000002"
C_ = "cccccccc-0000-4000-8000-000000000003"
D = "dddddddd-0000-4000-8000-000000000004"


def _file(tmp_path: Path, cards: dict[str, str], *, crlf: bool = False) -> Path:
    path = tmp_path / "card_descriptions.json"
    text = C.canonical({"descriptions": cards})
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    return path


def _production(cards: dict[str, str | None]):
    answer = "".join(json.dumps({"id": k, "card": v}) + "\n" for k, v in cards.items())
    return lambda sql: answer


def test_the_canonical_form_reproduces_todays_file_byte_for_byte() -> None:
    """The committed blob is LF; a `core.autocrlf` working copy shows CRLF, normalised on read."""
    path = REPO / "public" / "data" / "card_descriptions.json"
    text = C.read_text(path)
    assert C.canonical(json.loads(text)) == text
    assert list(json.loads(text)) == ["descriptions"]


def test_existing_keys_keep_their_place_new_keys_append_in_uuid_order_cleared_keys_go() -> None:
    current = {C_: "c", A: "a", B: "b"}
    rendered = C.file_from_cards(current, {A: "a2", B: None, C_: "c", D: "d"})["descriptions"]
    assert list(rendered) == [C_, A, D]
    assert rendered == {C_: "c", A: "a2", D: "d"}
    new_keys = C.file_from_cards({}, {D: "d", B: "b", A: "a"})["descriptions"]
    assert list(new_keys) == [A, B, D]


def test_a_key_that_is_not_a_curated_site_is_refused() -> None:
    with pytest.raises(C.CardFileRefused, match="not curated"):
        C.file_from_cards({A: "a", B: "b"}, {A: "a"})


def test_a_card_longer_than_the_column_is_refused() -> None:
    with pytest.raises(C.CardFileRefused, match="200"):
        C.file_from_cards({}, {A: "x" * 201})


def test_the_file_shape_does_not_change(tmp_path: Path) -> None:
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"descriptions": {}, "provenance": {}}), encoding="utf-8")
    with pytest.raises(C.CardFileRefused, match="exactly one top-level key"):
        C.read_cards(path)


def _plan4(tmp_path: Path, sites: list[M.PlanSite]) -> Path:
    path = tmp_path / "PLAN4.jsonl"
    path.write_text(
        json.dumps({"batch_id": FX.BATCH, "ordinal": 3, "sites": [s.to_dict() for s in sites]})
        + "\n",
        encoding="utf-8",
    )
    return path


def _p5_root(tmp_path: Path, rows: list[W4.Row4]) -> Path:
    root = tmp_path / "_write_apply_p5"
    plan = W4.WritePlan4(group=W4.Group.P5, batch_id="p5-0003", rows=rows)
    W4.write_plan_files(root / plan.batch_id, plan, W4.chunk_for(plan))
    return root


def _card_row(site: M.PlanSite, new: str | None) -> W4.Row4:
    return W4.make_row(
        group=W4.Group.P5,
        site=site,
        column="card_description",
        old_value=site.card,
        new_value=new,
        test_id=W4.TEST_CARD if new is not None else W4.TEST_CARD_CLEAR,
        evidence={"group": "P5"},
    )


def test_the_prerender_is_the_s0_cards_with_the_p5_rows_on_top(tmp_path: Path) -> None:
    kept = FX.plan_site(FX.SITE_A, card="kept")
    written = FX.plan_site(FX.SITE_B, card="old card")
    cleared = FX.plan_site(FX.SITE_C, card="wrong card")
    plan4 = _plan4(tmp_path, [kept, written, cleared])
    root = _p5_root(tmp_path, [_card_row(written, "new card"), _card_row(cleared, None)])
    cards = C.planned_cards(plan4, root)
    assert cards == {FX.SITE_A: "kept", FX.SITE_B: "new card", FX.SITE_C: None}
    path = _file(tmp_path, {FX.SITE_C: "wrong card", FX.SITE_B: "old card", FX.SITE_A: "kept"})
    text = C.prerender(path, plan4=plan4, p5_root=root)
    assert json.loads(text)["descriptions"] == {FX.SITE_B: "new card", FX.SITE_A: "kept"}
    assert path.read_bytes() == text.encode("utf-8")


def test_a_p5_row_that_starts_from_another_card_than_s0_read_is_refused(tmp_path: Path) -> None:
    site = FX.plan_site(FX.SITE_A, card="the card S0 read")
    plan4 = _plan4(tmp_path, [site])
    stale = _card_row(FX.plan_site(FX.SITE_A, card="another card"), "new")
    with pytest.raises(C.CardFileRefused, match="another card"):
        C.planned_cards(plan4, _p5_root(tmp_path, [stale]))


def test_a_p5_row_for_a_site_outside_the_plan_is_refused(tmp_path: Path) -> None:
    plan4 = _plan4(tmp_path, [FX.plan_site(FX.SITE_A, card="kept")])
    foreign = _card_row(FX.plan_site(FX.SITE_B, card="old card"), "new card")
    with pytest.raises(C.CardFileRefused, match="is not a site of the plan"):
        C.planned_cards(plan4, _p5_root(tmp_path, [foreign]))


def test_a_file_whose_card_is_not_a_string_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "card_descriptions.json"
    path.write_text(json.dumps({"descriptions": {A: "a", B: None}}), encoding="utf-8")
    with pytest.raises(C.CardFileRefused, match=f"the card of {B} is not a string"):
        C.read_cards(path)


def test_regenerate_is_identical_only_when_production_holds_the_prerender(tmp_path: Path) -> None:
    path = _file(tmp_path, {A: "a", B: "b"}, crlf=True)
    identical, _ = C.regenerate(path, run=_production({A: "a", B: "b", C_: None}))
    assert identical and not path.with_name(path.name + ".regenerated").exists()
    identical, text = C.regenerate(path, run=_production({A: "a", B: "other", C_: None}))
    assert not identical
    assert path.with_name(path.name + ".regenerated").read_text(encoding="utf-8") == text
    assert json.loads(C.read_text(path))["descriptions"][B] == "b"  # never overwritten here


def test_check_finds_every_kind_of_difference(tmp_path: Path) -> None:
    path = _file(tmp_path, {A: "a", B: "b", D: "d"})
    found = C.check(path, run=_production({A: "a", B: "changed", C_: "db only"}))
    kinds = sorted(line.split()[0] for line in found)
    assert kinds == ["DIFFERS", "MISSING", "NOT"]
    assert C.check(_file(tmp_path, {A: "a"}), run=_production({A: "a", B: None})) == []


def test_check_refuses_a_file_that_is_not_in_its_canonical_form(tmp_path: Path) -> None:
    path = tmp_path / "card_descriptions.json"
    path.write_text(json.dumps({"descriptions": {A: "a"}}), encoding="utf-8")
    assert any(line.startswith("FORM") for line in C.check(path, run=_production({A: "a"})))


def test_the_importer_reads_the_rendered_file_to_the_same_cards(tmp_path: Path) -> None:
    """Compatibility with the boot import (api/services/card_descriptions.py)."""
    cards = {A: "Ein Kärtchen.", B: "b"}
    path = tmp_path / "rendered.json"
    path.write_text(C.canonical(C.file_from_cards({}, cards)), encoding="utf-8", newline="\n")
    assert load_card_descriptions(path) == cards


def test_the_check_prints_its_own_accept_exit_line(tmp_path, capsys) -> None:
    path = _file(tmp_path, {A: "a"})
    fake = lambda sql, *, host: json.dumps({"id": A, "card": "a"}) + "\n"  # noqa: E731
    assert C.main(["--check", "--file", str(path)], runner=fake) == 0
    assert capsys.readouterr().out.rstrip().endswith("ACCEPT_EXIT=0")
