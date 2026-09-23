"""The sitelink lane's plan builder (`output/remediation/tools/sitelink_plan.py`): which UNVERIFIABLE
fields are still open, which item a site is given, which of its other-language articles are read,
and the records the fetch stage buys them through.

No test here reads production, Pi or the network: the mass run, the export, the census and every
lookup answer are small fabricated files and fetchers in the shape the real ones had on 2026-09-23.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import gap_plan as G  # noqa: E402
import lanes  # noqa: E402
import qid_repair  # noqa: E402
import sitelink_plan as SL  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

A = "aaaaaaaa-0000-4000-8000-00000000000a"
B = "aaaaaaaa-0000-4000-8000-00000000000b"


def _wave3(rule: str, name: str | None = None) -> qid_repair.Site:
    return next(
        site
        for site in qid_repair.WAVE3_SITES
        if site.rule == rule and (name is None or site.name == name)
    )


# ── the item a site is given ──────────────────────────────────────────────────────────────────


def test_every_wave_of_the_reviewed_repair_is_read() -> None:
    ids = [site.site_id for site in SL.REPAIRS]
    assert len(ids) == len(set(ids))
    for wave in qid_repair.WAVES.values():
        assert set(wave.sites) <= set(SL.REPAIRS), wave.number


def test_a_link_wave_three_found_right_is_given_although_the_classifier_suspected_it() -> None:
    """Psychro Cave's Q1643807 met Q2 (shared) until wave 2 repaired the Idaean Cave; wave 3's
    research reads it as right, and that verdict is the answer to the classifier's suspicion."""
    right = _wave3("link-right", "Psychro Cave")
    suspect = {right.site_id: (right.old_qid, "Q2")}
    assert SL.item_for(right.site_id, right.old_qid, shared={}, suspect=suspect) == (
        right.old_qid,
        None,
    )


def test_a_suspect_link_no_wave_answered_stays_withheld() -> None:
    suspect = {A: ("Q42", "Q1")}
    kept, why = SL.item_for(A, "Q42", shared={}, suspect=suspect)
    assert kept is None and "marks this link suspect (Q1" in str(why)
    # a suspicion about another item than the one production carries now says nothing about it
    assert SL.item_for(A, "Q43", shared={}, suspect=suspect) == ("Q43", None)


def test_a_type_link_and_a_duplicate_of_wave_three_are_withheld_by_the_repair() -> None:
    keep_type = _wave3("keep-type", "Nuraghes of Sardinia")
    suspect = {keep_type.site_id: (keep_type.old_qid, "Q1")}
    kept, why = SL.item_for(keep_type.site_id, keep_type.old_qid, shared={}, suspect=suspect)
    assert kept is None and "a type the record stands for" in str(why)
    duplicate = _wave3("duplicate-candidate")
    kept, why = SL.item_for(duplicate.site_id, duplicate.old_qid, shared={}, suspect={})
    assert kept is None and "duplicate candidate" in str(why)


# ── what is still open ────────────────────────────────────────────────────────────────────────


def _q(site_id: str, field: str, batch: str = "batch-0007") -> G.Question:
    return G.Question(
        site_id, field, batch, 0, SL.WHY, "the mass run's finder answered UNVERIFIABLE"
    )


def _site(site_id: str, **values: Any) -> dict[str, Any]:
    row = {
        "id": site_id,
        "name": f"Site {site_id[-1]}",
        "country": "Greece",
        "period_start": -500,
        "site_type": "temple",
        "description": "A temple.",
        "lat": 37.0,
        "lon": 22.0,
    }
    row.update(values)
    return row


def _exported(*sites: dict[str, Any], journal: tuple[dict[str, Any], ...] = ()) -> SL.Export:
    return SL.Export(
        sites={row["id"]: row for row in sites},
        cards={row["id"]: {"site_id": row["id"], "card_description": "A card."} for row in sites},
        external=[],
        journal=list(journal),
    )


def _journal(site_id: str, column: str, stamp: str = "phase3:batch-0003:chunk-0001") -> dict:
    table = "card_stats" if column == "card_description" else "unified_sites"
    return {
        "id": 1,
        "run_stamp": stamp,
        "table_name": table,
        "column_name": column,
        "row_pk": site_id,
        "site_id": site_id,
        "old_value": "x",
        "new_value": "y",
    }


def _judged(*sites: dict[str, Any]) -> dict[tuple[str, str], Any]:
    return {
        (row["id"], field): SP.stored_value(
            site=row, card={"card_description": "A card."}, field=field
        )
        for row in sites
        for field in SP.DISCOVER_FIELDS
    }


NOBODY = SL.HandDecided(countries=frozenset(), political=frozenset(), duplicates=frozenset())


def _open(questions, exported, *, judged=None, planned=(), hand=NOBODY, by_mass=()):
    return SL.open_questions(
        questions,
        exported=exported,
        judged=judged if judged is not None else _judged(*exported.sites.values()),
        planned=set(planned),
        hand=hand,
        written_by_mass=set(by_mass),
    )


def test_a_question_nobody_decided_since_stays_open() -> None:
    kept, dropped = _open([_q(A, "period_start")], _exported(_site(A)))
    assert [(q.site_id, q.field) for q in kept] == [(A, "period_start")] and dropped == []


def test_each_rule_drops_its_question_with_its_reason_first_match_wins() -> None:
    sites = [_site(A), _site(B, period_start=-300)]
    exported = _exported(*sites, journal=(_journal(A, "site_type", "gap:gap-0002:chunk-0001"),))
    judged = _judged(*sites)
    judged[(B, "period_start")] = -500  # the finder judged -500; production holds -300 now
    hand = SL.HandDecided(
        countries=frozenset({A}), political=frozenset({B}), duplicates=frozenset()
    )
    questions = [
        _q(A, "site_type"),
        _q(A, "period_start"),
        _q(A, "country"),
        _q(B, "country"),
        _q(B, "period_start"),
        _q(B, "description"),
    ]
    kept, dropped = _open(
        questions, exported, judged=judged, planned={(A, "period_start")}, hand=hand
    )
    assert [(q.site_id, q.field) for q in kept] == [(B, "description")]
    assert [(row["site_id"], row["field"], row["rule"]) for row in dropped] == [
        (A, "site_type", "written"),
        (A, "period_start", "mass-plan"),
        (A, "country", "hand-country"),
        (B, "country", "political-line"),
        (B, "period_start", "changed"),
    ]
    assert "written in production by gap:gap-0002" in dropped[0]["reason"]
    assert "judged -500, now -300" in dropped[4]["reason"]


def test_every_field_of_a_duplicate_is_left_to_the_owner() -> None:
    hand = SL.HandDecided(countries=frozenset(), political=frozenset(), duplicates=frozenset({A}))
    exported = _exported(_site(A), journal=(_journal(A, "site_type"),))
    kept, dropped = _open([_q(A, "site_type"), _q(A, "country")], exported, hand=hand)
    assert kept == [] and {row["rule"] for row in dropped} == {"duplicate"}


def test_a_site_the_export_lacks_stops_the_build() -> None:
    with pytest.raises(SystemExit, match="not in the export"):
        _open([_q(B, "country")], _exported(_site(A)))


def test_a_write_the_older_written_keys_list_names_must_be_in_the_fresh_journal() -> None:
    """`logs/search_lane/written_keys.txt` is the journal's mass-lane keys, exported earlier. A
    fresh export whose journal lacks one of them for its own sites is partial - and the `written`
    rule would then let a written field through. A site outside the export is none of its business."""
    exported = _exported(_site(A), journal=(_journal(A, "site_type"),))
    _open([_q(A, "country")], exported, by_mass={(A, "site_type"), (B, "country")})
    with pytest.raises(SystemExit, match="partial"):
        _open([_q(A, "country")], exported, by_mass={(A, "period_start")})


def _write_bcases(root: Path, *, b2=(), losers=(), held=()) -> Path:
    lanes.write_jsonl(root / "b2.jsonl", [{"site_id": site_id} for site_id in b2])
    lanes.write_jsonl(root / "DUPLICATES.jsonl", [{"loser_id": site_id} for site_id in losers])
    lanes.write_jsonl(root / "DUPLICATES_HELD.jsonl", [{"site_ids": list(held)}] if held else [])
    return root


def _census_list(path: Path, political: int, *, other: int = 1) -> Path:
    """`logs/_country_mismatches.txt`: id|name|stored|found|lat|lon, political rows first."""
    lines = [
        f"p{n:04d}|Kourion {n}|Cyprus|Akrotiri Sovereign Base Area|34.66|32.88"
        for n in range(political)
    ]
    lines += [f"o{n:04d}|Segura Bridge|Portugal|Spain|39.81|-6.98" for n in range(other)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_the_hand_decided_keys_are_read_from_the_classifier_and_the_b10_census_rows(
    tmp_path: Path,
) -> None:
    """B10 (HUMAN_ONLY, 2026-09-21) left the census's 29 geopolitical rows as they are. Six of them
    are not T02 findings and so not in `b2.jsonl` - among them Kourion Ancient Amphitheatre, Nebi
    Samuel and the Sanctuary of Apollo Hylates, whose `country` the lane would have asked again."""
    bcases = _write_bcases(tmp_path / "bcases", b2=[A], losers=[B], held=["h1", "h2"])
    census = _census_list(tmp_path / "mismatches.txt", SL.B10_ROWS)
    hand = SL.HandDecided.read(bcases, census)
    assert hand.countries == {A}
    assert hand.duplicates == {B, "h1", "h2"}
    assert len(hand.political) == SL.B10_ROWS
    assert not any(site_id.startswith("o") for site_id in hand.political)


def test_a_census_list_with_another_number_of_political_rows_stops_the_build(
    tmp_path: Path,
) -> None:
    bcases = _write_bcases(tmp_path / "bcases")
    for count in (SL.B10_ROWS - 1, SL.B10_ROWS + 1):
        census = _census_list(tmp_path / f"m{count}.txt", count)
        with pytest.raises(SystemExit, match="B10 decided"):
            SL.HandDecided.read(bcases, census)


def _pin_mass_plan(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> None:
    monkeypatch.setitem(lanes.REVIEWED_PLAN_KEYS_SHA256, lanes.MASS, lanes.keys_digest(rows))


def test_the_mass_plan_names_what_it_planned_and_what_written_keys_says_it_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {"change_key": "phase3:k1", "site_id": A, "column": "site_type"},
        {"change_key": "phase3:k2", "site_id": B, "column": "period_start"},
    ]
    lanes.write_jsonl(tmp_path / "ALL_ROWS.jsonl", rows)
    _pin_mass_plan(monkeypatch, rows)
    (tmp_path / "written_keys.txt").write_text("phase3:k2\n", encoding="utf-8")
    mass = SL.MassPlan.read(tmp_path / "ALL_ROWS.jsonl", tmp_path / "written_keys.txt")
    assert mass.planned == {(A, "site_type"), (B, "period_start")}
    assert mass.written == {(B, "period_start")}
    (tmp_path / "written_keys.txt").write_text("phase3:k2\nphase3:k9\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not rows of the mass lane's plan"):
        SL.MassPlan.read(tmp_path / "ALL_ROWS.jsonl", tmp_path / "written_keys.txt")


def test_a_rows_file_that_is_not_the_pinned_mass_plan_stops_the_build(tmp_path: Path) -> None:
    rows = [{"change_key": "k", "site_id": A, "column": "site_type"}]
    lanes.write_jsonl(tmp_path / "ALL_ROWS.jsonl", rows)
    (tmp_path / "written_keys.txt").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="was written from"):
        SL.MassPlan.read(tmp_path / "ALL_ROWS.jsonl", tmp_path / "written_keys.txt")


# ── a plan is built from the resolution its own inputs call for ──────────────────────────────


def _links(qid: str | None, withheld: str | None = None, **changes: Any) -> SL.SiteLinks:
    fields: dict[str, Any] = {
        "qid": qid,
        "withheld": withheld,
        "country": None if qid is None else "Greece",
        "room": None if qid is None else 20_000,
        "chosen": (),
        "skipped": (),
    }
    fields.update(changes)
    return SL.SiteLinks(**fields)


def test_a_resolution_made_under_other_inputs_is_named_stale() -> None:
    """`sitelinks.json` is written by the step that leaves the machine; `plan` reads it later, from
    the same export and rules. A site whose item, withholding, country or evidence room now reads
    differently was resolved for another question, and its articles would be ordered or cut wrong."""
    inputs = {
        A: {"qid": "Q1", "withheld": None, "country": "Greece", "room": 20_000},
        B: {
            "qid": None,
            "withheld": "Q2 is carried by 2 curated sites",
            "country": "Italy",
            "room": 9,
        },
    }
    fresh = {A: _links("Q1"), B: _links(None, "Q2 is carried by 2 curated sites")}
    assert SL.stale_sites(inputs, fresh) == []
    for site_id, changed in (
        (A, _links("Q9")),
        (A, _links("Q1", country="Italy")),
        (A, _links("Q1", room=19_999)),
        (A, _links(None, "Q1 is carried by 2 curated sites")),
        (B, _links("Q2")),
        (B, _links(None, "another reason")),
    ):
        assert SL.stale_sites(inputs, {**fresh, site_id: changed}) == [site_id]
    assert SL.stale_sites(inputs, {A: fresh[A]}) == [B]
