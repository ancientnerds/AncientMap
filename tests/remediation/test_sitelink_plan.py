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


def _verdict(qid: str, rule: str = "suspect-link") -> SL.Verdict:
    return SL.Verdict(qid=qid, rule=rule, why=f"the classifier's words on {qid}")


def test_a_link_wave_three_found_right_is_given_although_the_classifier_suspected_it() -> None:
    """Psychro Cave's Q1643807 met Q2 (shared) until wave 2 repaired the Idaean Cave; wave 3's
    research reads it as right, and that verdict is the answer to the classifier's suspicion."""
    right = _wave3("link-right", "Psychro Cave")
    verdicts = {right.site_id: (_verdict(right.old_qid),)}
    assert SL.item_for(right.site_id, right.old_qid, shared={}, verdicts=verdicts) == (
        right.old_qid,
        None,
    )


def test_a_suspect_link_no_wave_answered_stays_withheld() -> None:
    verdicts = {A: (_verdict("Q42"),)}
    kept, why = SL.item_for(A, "Q42", shared={}, verdicts=verdicts)
    assert kept is None and why == "Q42: suspect-link - the classifier's words on Q42"
    # a suspicion about another item than the one production carries now says nothing about it
    assert SL.item_for(A, "Q43", shared={}, verdicts=verdicts) == ("Q43", None)


@pytest.mark.parametrize("rule", ["container-item", "item-is-not-the-site", "item-is-a-locality"])
def test_an_item_the_classifier_found_is_not_the_site_is_withheld_under_its_rule(rule: str) -> None:
    """The town, the commune, the state or the island that holds the site: its articles give the
    place's date and type, not the site's."""
    verdicts = {A: (_verdict("Q42", rule),)}
    kept, why = SL.item_for(A, "Q42", shared={}, verdicts=verdicts)
    assert kept is None and why == f"Q42: {rule} - the classifier's words on Q42"
    assert SL.item_for(A, "Q43", shared={}, verdicts=verdicts) == ("Q43", None)


def test_wave_threes_right_link_answers_the_suspicion_and_no_other_verdict() -> None:
    """Wave 3 researched the suspect links (a generic or a shared item); whether the item is the
    place that holds the site is a question it never asked."""
    right = _wave3("link-right", "Psychro Cave")
    for rule in sorted(SL.NOT_THE_SITE_RULES):
        verdicts = {right.site_id: (_verdict(right.old_qid), _verdict(right.old_qid, rule))}
        kept, why = SL.item_for(right.site_id, right.old_qid, shared={}, verdicts=verdicts)
        assert kept is None and f"{right.old_qid}: {rule} - " in str(why)


def test_a_type_link_and_a_duplicate_of_wave_three_are_withheld_by_the_repair() -> None:
    keep_type = _wave3("keep-type", "Nuraghes of Sardinia")
    verdicts = {keep_type.site_id: (_verdict(keep_type.old_qid),)}
    kept, why = SL.item_for(keep_type.site_id, keep_type.old_qid, shared={}, verdicts=verdicts)
    assert kept is None and "a type the record stands for" in str(why)
    duplicate = _wave3("duplicate-candidate")
    kept, why = SL.item_for(duplicate.site_id, duplicate.old_qid, shared={}, verdicts={})
    assert kept is None and "duplicate candidate" in str(why)


#: The cases the independent check of 2026-09-23 named, and the pilot's Hebbariyeh Roman Temple,
#: which it did not: `site_id -> (the item the classifier judged, the rule the site is withheld by)`.
#: The first verdict read wins - `names.jsonl` before `coords.jsonl`.
OWNER_CASES = {
    # Colima - Eastern Shaft Tomb: Q61309 is the Mexican state of Colima
    "a2704598-c3b7-4cbb-9fdc-4055c445cec1": ("Q61309", "item-is-not-the-site"),
    # Kintradwell Broch: Q990677 is the village of Brora
    "43ee9ef2-ada7-4796-98eb-4d2ba9728d74": ("Q990677", "item-is-a-locality"),
    # Kameishi: Q752397 is the village of Asuka
    "9b5751dd-d54e-4e8a-b4c0-7b4dc2a863c7": ("Q752397", "item-is-a-locality"),
    # Site de Tiklat: Q1649095 is the commune of El Kseur
    "37321e41-a629-4d79-820d-3104c7713860": ("Q1649095", "item-is-a-locality"),
    # The Roman Bridge (Elguentra): Q3050002 is the commune of El Kantara
    "6a43a3e7-66c7-4133-a91c-58a52cc5e0dc": ("Q3050002", "item-is-a-locality"),
    # Archaeological Site of Ancient Thasos: Q204096 is the island
    "33d2d754-e50a-4305-beff-87d2ad2c0227": ("Q204096", "container-item"),
    # Ahin Posh Tape: Q4695118 is a village in Pakistan (HUMAN_ONLY B1/B2 item 4, open)
    "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6": ("Q4695118", "container-item"),
    # Hebbariyeh Roman Temple, a pilot site: Q5695359 is the village of Hebbariye
    "6a20e653-5320-440d-ac6c-2e86bb56e09e": ("Q5695359", "item-is-a-locality"),
}


def test_the_named_owner_cases_are_withheld_on_the_classifiers_own_output() -> None:
    verdicts = SL.classifier_verdicts(lanes.REMEDIATION / "bcases")
    for site_id, (qid, rule) in OWNER_CASES.items():
        kept, why = SL.item_for(site_id, qid, shared={}, verdicts=verdicts)
        assert kept is None and str(why).startswith(f"{qid}: {rule} - "), (site_id, why)


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


# ── the census of the mass run's UNVERIFIABLE answers ─────────────────────────────────────────


def _mass_site(site_id: str, **values: Any) -> dict[str, Any]:
    return SP.discover_site_record(
        site=_site(site_id, **values), card={"card_description": "A card."}, qid=None
    )


def _mass_run(tmp_path: Path, answers: dict[str, dict[str, str]]) -> Path:
    """One mass batch holding A and B, one finder answer per (site, field) in `answers`."""
    batch = tmp_path / "mass" / "batch-0007"
    payload = {
        "batch_id": "batch-0007",
        "ordinal": 7,
        "pass": "discover",
        "sites": [_mass_site(A), _mass_site(B, period_start=-300)],
    }
    batch.mkdir(parents=True)
    (batch / "input.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    store = F.EvidenceStore(batch / "answers")
    for site_id, fields in answers.items():
        for field, verdict in fields.items():
            store.write(
                site_id=site_id,
                feature=field,
                body=f"The page is silent.\nVERDICT: {verdict}\n".encode(),
            )
    return tmp_path / "mass"


def test_the_census_takes_the_unverifiable_answers_of_its_scope_in_the_runs_order(
    tmp_path: Path,
) -> None:
    run = _mass_run(
        tmp_path,
        {
            A: {"card_description": "UNVERIFIABLE", "period_start": "UNVERIFIABLE"},
            B: {"country": "UNVERIFIABLE", "site_type": "CORRECT", "description": "UNVERIFIABLE"},
        },
    )
    writable = SL.census(run, scope="writable")
    assert [(q.site_id, q.field) for q in writable] == [(A, "period_start"), (B, "country")]
    assert {(q.source_batch, q.why) for q in writable} == {("batch-0007", SL.WHY)}
    everything = SL.census(run, scope="all", site_ids=[B])
    assert [(q.site_id, q.field) for q in everything] == [(B, "description"), (B, "country")]


def test_the_census_refuses_an_unknown_scope_a_missing_site_and_an_empty_answer(
    tmp_path: Path,
) -> None:
    run = _mass_run(tmp_path, {A: {"period_start": "UNVERIFIABLE"}})
    with pytest.raises(SystemExit, match="scope 'writeable'"):
        SL.census(run, scope="writeable")
    with pytest.raises(SystemExit, match="sites the mass run does not hold"):
        SL.census(run, scope="all", site_ids=[A, "not-a-site"])
    with pytest.raises(SystemExit, match="no UNVERIFIABLE answer"):
        SL.census(run, scope="all", site_ids=[B])


def test_the_judged_value_is_the_one_each_batch_record_carried(tmp_path: Path) -> None:
    judged = SL.judged_values(_mass_run(tmp_path, {}))
    assert judged[(B, "period_start")] == -300 and judged[(A, "country")] == "Greece"
    assert judged[(A, "card_description")] == "A card."


# ── the export ────────────────────────────────────────────────────────────────────────────────


def test_the_journal_query_reads_every_stamp_of_the_five_fields_by_site_and_by_row() -> None:
    sql = SL.journal_sql([A, B])
    assert "remediation_change_log" in sql and "run_stamp" in sql and "LIKE" not in sql
    assert f"site_id_ref::text IN ('{A}', '{B}')" in sql and f"row_pk IN ('{A}', '{B}')" in sql
    assert (
        "(table_name = 'unified_sites' AND column_name IN "
        "('description', 'period_start', 'site_type', 'country'))" in sql
    )
    assert "(table_name = 'card_stats' AND column_name IN ('card_description'))" in sql


def test_the_export_writes_the_gap_lanes_tables_and_the_journal(tmp_path: Path) -> None:
    asked: list[str] = []
    answers = {
        "FROM unified_sites WHERE": [{**_site(A), "source_id": "ancient_nerds"}],
        "FROM card_stats": [{"site_id": A, "card_description": "A card."}],
        "FROM site_external_ids": [{"site_id": A, "kind": "wikidata_qid", "value": "Q1"}],
        "FROM remediation_change_log": [_journal(A, "country")],
    }

    def run(sql: str) -> str:
        asked.append(sql)
        rows = next(rows for marker, rows in answers.items() if marker in sql)
        return "\n".join(json.dumps(row) for row in rows) + "\n"

    counts = SL.export([_q(A, "country")], tmp_path / "export", run=run)
    assert counts == {"unified_sites": 1, "card_stats": 1, "site_external_ids": 1, "journal": 1}
    assert any("remediation_change_log" in sql for sql in asked)
    exported = SL.Export.read(tmp_path / "export")
    assert exported.journal[0]["column_name"] == "country" and A in exported.sites


def test_a_journal_row_without_its_site_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "export"
    lanes.write_jsonl(root / "unified_sites.jsonl", [_site(A)])
    lanes.write_jsonl(root / "card_stats.jsonl", [])
    lanes.write_jsonl(root / "site_external_ids.jsonl", [])
    lanes.write_jsonl(root / "journal.jsonl", [{**_journal(A, "country"), "site_id": None}])
    with pytest.raises(SystemExit, match="without the site they belong to"):
        SL.Export.read(root)


def _name_row(site_id: str, cls: str, qid: str, **extra: Any) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "class": cls,
        "qid": qid,
        "qid_now": qid,
        "link_suspect": [],
        **extra,
    }


def _coord_row(site_id: str, cls: str | None, qid: str | None, **extra: Any) -> dict[str, Any]:
    row = {"site_id": site_id, "qid": qid, "p31": ["village"], "reason": f"why {cls}", **extra}
    return row if cls is None else {**row, "class": cls}


def _write_verdicts(root: Path, names: list[dict], coords: list[dict]) -> Path:
    lanes.write_jsonl(root / "names.jsonl", names)
    lanes.write_jsonl(root / "coords.jsonl", coords)
    return root


def test_a_suspect_link_is_read_from_the_classifiers_class_or_its_link_suspect_list(
    tmp_path: Path,
) -> None:
    _write_verdicts(
        tmp_path,
        [
            _name_row(A, "Q2", "Q10"),
            _name_row(B, "N1", "Q11", link_suspect=["Q4", "Q1"]),
            _name_row("c", "N1", "Q12"),
        ],
        [],
    )
    verdicts = SL.classifier_verdicts(tmp_path)
    assert {site: [(v.qid, v.rule) for v in rows] for site, rows in verdicts.items()} == {
        A: [("Q10", "suspect-link")],
        B: [("Q11", "suspect-link")],
    }
    assert verdicts[B][0].why == (
        "the owner-case classifier marks this link suspect (Q1/Q4, bcases/names.jsonl)"
    )


def test_a_verdict_is_about_the_item_it_judged_not_the_link_the_site_carried_later(
    tmp_path: Path,
) -> None:
    """Kourion's amphitheatre met Q1 on the census's Q11635 ("amphitheatre", the class); wave 1
    replaced it with Q4453457 before the classifier ran. The suspicion is about Q11635."""
    _write_verdicts(
        tmp_path,
        [{**_name_row(A, "Q1", "Q11635"), "qid_now": "Q4453457"}],
        [_coord_row(B, "container-item", "Q7", p31=["commune of France"])],
    )
    verdicts = SL.classifier_verdicts(tmp_path)
    assert [v.qid for v in verdicts[A]] == ["Q11635"]
    assert SL.item_for(A, "Q4453457", shared={}, verdicts=verdicts) == ("Q4453457", None)
    assert SL.item_for(B, "Q7", shared={}, verdicts=verdicts)[0] is None


def test_the_verdicts_that_the_item_is_not_the_site_are_read_and_no_other(tmp_path: Path) -> None:
    _write_verdicts(
        tmp_path,
        [
            _name_row("e", "N7", "Q13", n7="anchor-is-locality", p31=["village"]),
            _name_row("f", "N7", "Q14", n7="anchor-is-a-site", p31=["palace"]),
        ],
        [
            _coord_row("g", "container-item", "Q15", p31=["state of Mexico"]),
            _coord_row("h", "item-is-not-the-site", "Q16", p31=["archaeological site"]),
            # a point somewhere on a road or in a park: a question of the point, not of the item
            _coord_row("i", "linear-or-areal-item", "Q17"),
            # counted from production's own links by the shared rule, not from the census's
            _coord_row("j", "shared-item", "Q18"),
            _coord_row("k", None, "Q19", verdict="stored-agrees"),
        ],
    )
    verdicts = SL.classifier_verdicts(tmp_path)
    assert {site: [(v.qid, v.rule) for v in rows] for site, rows in verdicts.items()} == {
        "e": [("Q13", "item-is-a-locality")],
        "g": [("Q15", "container-item")],
        "h": [("Q16", "item-is-not-the-site")],
    }
    assert verdicts["e"][0].why == (
        "the owner-case classifier reads the place the stored name is anchored to as a locality, "
        "not the site (N7 anchor-is-locality; P31 village; bcases/names.jsonl)"
    )
    assert verdicts["g"][0].why == (
        "the owner-case classifier: why container-item (P31 state of Mexico; bcases/coords.jsonl)"
    )


def test_the_plans_inputs_withhold_the_item_the_classifier_found_is_not_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remediation = tmp_path / "remediation"
    _write_verdicts(
        remediation / "bcases", [], [_coord_row(A, "container-item", "Q1", p31=["island"])]
    )
    monkeypatch.setattr(lanes, "REMEDIATION", remediation)
    exported = SL.Export(
        sites={A: _site(A), B: _site(B)},
        cards={},
        external=_external((A, "Q1"), (B, "Q2")),
        journal=[],
    )
    inputs = SL.site_inputs(
        [_q(A, "period_start"), _q(B, "site_type")], exported=exported, mass=tmp_path
    )
    assert inputs[A]["qid"] is None
    assert str(inputs[A]["withheld"]).startswith("Q1: container-item - the owner-case classifier")
    assert (inputs[B]["qid"], inputs[B]["withheld"]) == ("Q2", None)


@pytest.mark.parametrize(
    ("names", "coords"),
    [
        ([_name_row(A, "Q2", "Q10") | {"qid": None}], []),
        ([_name_row(A, "N7", "Q10", n7="anchor-is-locality") | {"qid": None}], []),
        ([], [_coord_row(A, "container-item", None)]),
    ],
)
def test_a_verdict_that_does_not_name_the_item_it_judged_stops_the_build(
    tmp_path: Path, names: list[dict], coords: list[dict]
) -> None:
    _write_verdicts(tmp_path, names, coords)
    with pytest.raises(SystemExit, match="does not name the item it judged"):
        SL.classifier_verdicts(tmp_path)


# ── which of the item's articles are read ─────────────────────────────────────────────────────


def _sl(title: str, url: str | None, *badges: str) -> F.Sitelink:
    return F.Sitelink(title=title, badges=tuple(badges), url=url)


def test_the_candidates_are_the_items_wikipedias_their_language_read_off_the_url() -> None:
    usable, refused = SL.candidates(
        {
            "be_x_oldwiki": _sl("Арэні-1", "https://be-tarask.wikipedia.org/wiki/A"),
            "dewiki": _sl("Areni-1", "https://de.wikipedia.org/wiki/Areni-1"),
            "commonswiki": _sl("Category:Areni-1", "https://commons.wikimedia.org/wiki/C"),
            "enwiki": _sl("Areni-1 cave", "https://en.wikipedia.org/wiki/A"),
            "simplewiki": _sl("Areni-1", "https://simple.wikipedia.org/wiki/A"),
            "cebwiki": _sl("Areni-1", "https://ceb.wikipedia.org/wiki/A"),
            "frwiki": _sl("Areni", "https://fr.wikipedia.org/wiki/A", "Q70893996"),
            "itwiki": _sl("Areni", "https://it.wikipedia.org/wiki/A", "Q70894304"),
            "eswiki": _sl("Areni-1", "https://es.wikipedia.org/wiki/A", "Q17437796"),
        }
    )
    assert usable == [
        SL.Candidate("be_x_oldwiki", "be-tarask", "Арэні-1"),
        SL.Candidate("dewiki", "de", "Areni-1"),
        SL.Candidate("eswiki", "es", "Areni-1"),
    ]
    assert {row["wiki"]: row["rule"] for row in refused} == {
        "cebwiki": "bot-generated",
        "enwiki": "english",
        "frwiki": "redirect-badge",
        "itwiki": "redirect-badge",
        "simplewiki": "english",
    }
    assert "Q70893996 sitelink to redirect" in next(
        row["reason"] for row in refused if row["wiki"] == "frwiki"
    )


def test_a_sitelink_without_url_or_with_a_foreign_shape_stops_the_build() -> None:
    with pytest.raises(SystemExit, match="without its url"):
        SL.candidates({"dewiki": _sl("Areni-1", None)})
    with pytest.raises(SystemExit, match="not a Wikipedia site id and subdomain"):
        SL.candidates({"de": _sl("Areni-1", "https://de.wikipedia.org/wiki/A")})
    with pytest.raises(SystemExit, match="not a Wikipedia site id and subdomain"):
        SL.candidates({"dewiki": _sl("Areni-1", "https://de_x.wikipedia.org/wiki/A")})


def _c(wiki: str) -> SL.Candidate:
    return SL.Candidate(wiki, wiki.removesuffix("wiki"), f"T {wiki}")


def test_the_order_is_the_countrys_own_wikis_then_the_fixed_order_then_the_rest_by_id() -> None:
    usable = [_c(w) for w in ("zuwiki", "frwiki", "elwiki", "aawiki", "dewiki", "trwiki")]
    assert [c.wiki for c in SL.order(usable, "Greece")] == [
        "elwiki",
        "dewiki",
        "frwiki",
        "trwiki",
        "aawiki",
        "zuwiki",
    ]
    assert [c.wiki for c in SL.order(usable, "Cyprus")][:2] == ["elwiki", "trwiki"]
    assert [c.wiki for c in SL.order(usable, "England")][:2] == ["dewiki", "frwiki"]


def test_a_stored_country_the_table_lacks_stops_the_build() -> None:
    assert SL.country_key("Türkiye") == "TR" and SL.country_key("Baltic Sea") == "baltic sea"
    with pytest.raises(SystemExit, match="not in COUNTRY_WIKIS"):
        SL.country_key("Atlantis")


def _pin(wiki: str, length: int, title: str | None = None) -> SL.Pin:
    return SL.Pin(wiki, wiki.removesuffix("wiki"), title or f"T {wiki}", 100, length)


def test_an_article_costs_its_source_line_its_capped_length_and_the_marker() -> None:
    small, big = _pin("dewiki", 5_000), _pin("dewiki", 10 * F.MAX_PAGE_BYTES)
    header = len(F.wiki_article_header(small.sitelink()))
    tail = 1 + len(F.TRUNCATION_MARKER)
    assert SL.article_estimate(small) == header + 5_000 + tail
    assert SL.article_estimate(big) == header + F.MAX_PAGE_BYTES + tail


def test_the_room_is_the_bound_less_the_stored_english_page_and_the_narrow_reserve(
    tmp_path: Path,
) -> None:
    store = F.EvidenceStore(tmp_path / "batch-0007" / "evidence")
    store.write(site_id=A, feature=F.FEATURE_ENWIKI, body=b"e" * 12_345)
    room = SL.evidence_room(A, "batch-0007", mass_run=tmp_path)
    assert room == SL.MS.MAX_EVIDENCE_CHARS - 12_345 - SL.NARROW_RESERVE_CHARS
    unfetched = SL.evidence_room(B, "batch-0007", mass_run=tmp_path)
    full = F.MAX_PAGE_BYTES + len(F.TRUNCATION_MARKER)
    assert unfetched == SL.MS.MAX_EVIDENCE_CHARS - full - SL.NARROW_RESERVE_CHARS


def test_the_walk_takes_what_fits_skips_the_rest_with_its_reason_and_stops_at_three() -> None:
    order = [_c(w) for w in ("elwiki", "dewiki", "frwiki", "itwiki", "eswiki", "nlwiki")]
    pins: dict[tuple[str, str], SL.Pin | str] = {
        order[0].key: "'T elwiki' is a redirect, not an article",
        order[1].key: _pin("dewiki", 1_000, "T dewiki"),
        order[2].key: _pin("frwiki", 50_000, "T frwiki"),
        order[3].key: _pin("itwiki", 1_000, "T itwiki"),
        order[4].key: _pin("eswiki", 1_000, "T eswiki"),
        order[5].key: _pin("nlwiki", 1_000, "T nlwiki"),
    }
    selection = SL.select(order, pins, room=20_000)
    assert [pin.wiki for pin in selection.chosen] == ["dewiki", "itwiki", "eswiki"]
    assert [(row["wiki"], row["rule"]) for row in selection.skipped] == [
        ("elwiki", "not-the-items-article"),
        ("frwiki", "room"),
        ("nlwiki", "cap"),
    ]
    assert selection.need == ()
    spent = sum(SL.article_estimate(pin) for pin in selection.chosen)
    assert spent <= 20_000


def test_an_unpinned_candidate_stops_the_walk_and_names_what_to_pin_next() -> None:
    order = [_c(w) for w in ("elwiki", "dewiki", "frwiki", "itwiki", "eswiki")]
    selection = SL.select(order, {order[0].key: _pin("elwiki", 10, "T elwiki")}, room=90_000)
    assert selection.chosen == () and selection.skipped == ()
    assert [c.wiki for c in selection.need] == ["dewiki", "frwiki"]
    assert SL.select(order, {}, room=90_000).need == tuple(order[:3])


# ── the lookups the plan makes ────────────────────────────────────────────────────────────────


class _Pages:
    """A `Fetcher` answering each request with the next (status, body, retry_after) of a list."""

    def __init__(self, *answers: tuple[int, bytes, float | None], truncated: bool = False) -> None:
        self.answers = list(answers)
        self.truncated = truncated
        self.asked: list[str] = []

    def get(self, url: str) -> F.FetchedPage:
        self.asked.append(url)
        status, body, retry_after = self.answers.pop(0)
        return F.FetchedPage(status, url, body, self.truncated, retry_after)


def test_a_lookup_the_host_refused_for_now_is_asked_again_after_the_backoff() -> None:
    slept: list[float] = []
    fetcher = _Pages((429, b"", 40.0), (503, b"", None), (200, b"ok", None))
    assert SL.lookup(fetcher, "u", sleep=slept.append).body == b"ok"
    assert slept == [40.0, SL.LOOKUP_BACKOFF_SECONDS[1]]  # the host's longer ask, then ours


def test_a_lookup_that_cannot_answer_stops_the_build() -> None:
    slept: list[float] = []
    with pytest.raises(SystemExit, match="HTTP 404"):
        SL.lookup(_Pages((404, b"", None)), "u", sleep=slept.append)
    with pytest.raises(SystemExit, match="HTTP 503"):
        SL.lookup(_Pages(*[(503, b"", None)] * F.MAX_ATTEMPTS), "u", sleep=slept.append)
    with pytest.raises(SystemExit, match="truncated=True"):
        SL.lookup(_Pages((200, b"{", None), truncated=True), "u", sleep=slept.append)
    long_wait = F.RETRY_AFTER_CAP_SECONDS + 1
    with pytest.raises(SystemExit, match="HTTP 429"):
        SL.lookup(_Pages((429, b"", long_wait), (200, b"ok", None)), "u", sleep=slept.append)
    assert slept == list(SL.LOOKUP_BACKOFF_SECONDS)


def _pages_answer(*pages: dict[str, Any], normalized: tuple = ()) -> bytes:
    query: dict[str, Any] = {"pages": list(pages)}
    if normalized:
        query["normalized"] = [{"from": a, "to": b} for a, b in normalized]
    return json.dumps({"batchcomplete": True, "query": query}).encode()


def _meta(title: str, qid: str, revid: int = 7, **changes: Any) -> dict[str, Any]:
    page = {
        "title": title,
        "lastrevid": revid,
        "length": 4_000,
        "revisions": [{"revid": revid}],
        "pageprops": {"wikibase_item": qid},
    }
    page.update(changes)
    return {key: value for key, value in page.items() if value is not None}


def test_a_pin_is_the_items_own_article_at_its_latest_revision() -> None:
    """A title the wiki normalises is found under its new spelling and refused: the fetch asks for
    the pinned title, and an answer under another title is refused there too
    (`fetch_stage.wiki_page_refusal`)."""
    fetcher = _Pages(
        (
            200,
            _pages_answer(
                _meta("Areni 1", "Q1", 11),
                _meta("Areni-2", "Q2", redirect=True),
                _meta("Areni-3", "Q3", 12),
                normalized=(("Areni_1", "Areni 1"),),
            ),
            None,
        )
    )
    pins = SL.pin_titles(
        {
            ("de", "Areni_1"): ("dewiki", "Q1"),
            ("de", "Areni-2"): ("dewiki", "Q2"),
            ("de", "Areni-3"): ("dewiki", "Q3"),
        },
        fetcher=fetcher,
        sleep=lambda _s: None,
    )
    assert pins[("de", "Areni-3")] == SL.Pin("dewiki", "de", "Areni-3", 12, 4_000)
    assert pins[("de", "Areni_1")] == "the answer is for 'Areni 1', not 'Areni_1'"
    assert pins[("de", "Areni-2")] == "'Areni-2' is a redirect, not an article"
    assert len(fetcher.asked) == 1


def test_a_pin_answer_that_omits_a_title_or_names_no_latest_revision_stops_the_build() -> None:
    wanted = {("de", "Areni-1"): ("dewiki", "Q1")}
    for answer, message in (
        (_pages_answer(), "was asked for and is absent"),
        (_pages_answer(_meta("Areni-1", "Q1", lastrevid=9)), "revision 7/9"),
        (_pages_answer(_meta("Areni-1", "Q1", length=None)), "length None"),
        (_pages_answer(_meta("Areni-1", "Q1", length=True)), "length True"),
    ):
        with pytest.raises(SystemExit, match=message):
            SL.pin_titles(wanted, fetcher=_Pages((200, answer, None)), sleep=lambda _s: None)


def test_the_pins_are_asked_fifty_titles_at_a_time_per_wiki() -> None:
    wanted = {("de", f"T{n:02d}"): ("dewiki", "Q1") for n in range(51)}
    wanted[("fr", "T")] = ("frwiki", "Q1")

    class _Echo:
        asked: list[str] = []

        def get(self, url: str) -> F.FetchedPage:
            self.asked.append(url)
            titles = parse_qs(urlsplit(url).query)["titles"][0].split("|")
            body = _pages_answer(*(_meta(t, "Q1") for t in titles))
            return F.FetchedPage(200, url, body, False)

    echo = _Echo()
    pins = SL.pin_titles(wanted, fetcher=echo, sleep=lambda _s: None)
    assert len(pins) == 52 and len(echo.asked) == 3
    assert [urlsplit(u).netloc for u in echo.asked] == ["de.wikipedia.org"] * 2 + [
        "fr.wikipedia.org"
    ]


def test_the_items_sitelinks_are_asked_ten_at_a_time_and_every_one_must_answer() -> None:
    class _Items:
        asked: list[str] = []

        def get(self, url: str) -> F.FetchedPage:
            self.asked.append(url)
            ids = parse_qs(urlsplit(url).query)["ids"][0].split("|")
            body = json.dumps({"entities": {q: {"sitelinks": {}} for q in ids if q != "Q13"}})
            return F.FetchedPage(200, url, body.encode(), False)

    items = _Items()
    qids = [f"Q{n}" for n in range(100, 112)]
    assert set(SL.item_sitelinks([*qids, qids[0]], fetcher=items, sleep=lambda _s: None)) == set(
        qids
    )
    assert len(items.asked) == 2 and "sitelinks%2Furls" in items.asked[0]
    with pytest.raises(SystemExit, match="Q13: asked for, and absent"):
        SL.item_sitelinks(["Q12", "Q13"], fetcher=_Items(), sleep=lambda _s: None)


class _Wiki:
    """Wikidata and the Wikipedias of a small world: the items' sitelinks and every page's pin."""

    def __init__(self, items: dict[str, dict[str, Any]], pages: dict[tuple[str, str], dict]):
        self.items = items
        self.pages = pages
        self.asked: list[str] = []

    def get(self, url: str) -> F.FetchedPage:
        self.asked.append(url)
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if parts.netloc == "www.wikidata.org":
            ids = query["ids"][0].split("|")
            body = {"entities": {q: {"sitelinks": self.items[q]} for q in ids}}
        else:
            lang = parts.netloc.split(".")[0]
            titles = query["titles"][0].split("|")
            body = {"query": {"pages": [self.pages[(lang, t)] for t in titles]}}
        return F.FetchedPage(200, url, json.dumps(body).encode(), False)


def _wd(lang: str, title: str) -> dict[str, Any]:
    return {"title": title, "badges": [], "url": f"https://{lang}.wikipedia.org/wiki/{title}"}


def test_resolution_orders_pins_and_selects_every_kept_site_and_records_the_withheld() -> None:
    world = _Wiki(
        items={
            "Q1": {
                "elwiki": _wd("el", "Ναός"),
                "dewiki": _wd("de", "Tempel"),
                "frwiki": _wd("fr", "Temple"),
                "itwiki": _wd("it", "Tempio"),
                "enwiki": _wd("en", "Temple"),
            }
        },
        pages={
            ("el", "Ναός"): _meta("Ναός", "Q1", 1),
            ("de", "Tempel"): _meta("Tempel", "Q9", 2),  # another item's article
            ("fr", "Temple"): _meta("Temple", "Q1", 3),
            ("it", "Tempio"): _meta("Tempio", "Q1", 4),
        },
    )
    decided = SL.resolve(
        {
            A: {"qid": "Q1", "withheld": None, "country": "Greece", "room": 60_000},
            B: {"qid": None, "withheld": "Q2 is carried by 2 curated sites", "country": "Italy"},
        },
        fetcher=world,
        sleep=lambda _s: None,
    )
    assert [pin["wiki"] for pin in decided[A].chosen] == ["elwiki", "frwiki", "itwiki"]
    assert decided[A].chosen[0]["estimate"] == SL.article_estimate(
        SL.Pin("elwiki", "el", "Ναός", 1, 4_000)
    )
    assert {(row["wiki"], row["rule"]) for row in decided[A].skipped} == {
        ("enwiki", "english"),
        ("dewiki", "not-the-items-article"),
    }
    assert decided[B] == SL.SiteLinks(None, "Q2 is carried by 2 curated sites", None, None, (), ())
    assert not any("Q2" in url for url in world.asked)


def test_one_article_claimed_by_two_items_stops_the_resolution() -> None:
    world = _Wiki(
        items={"Q1": {"dewiki": _wd("de", "T")}, "Q2": {"dewiki": _wd("de", "T")}}, pages={}
    )
    sites = {
        A: {"qid": "Q1", "withheld": None, "country": "Greece", "room": 60_000},
        B: {"qid": "Q2", "withheld": None, "country": "Greece", "room": 60_000},
    }
    with pytest.raises(SystemExit, match="is linked by"):
        SL.resolve(sites, fetcher=world, sleep=lambda _s: None)


# ── the records ───────────────────────────────────────────────────────────────────────────────


def _chosen(wiki: str, title: str, revid: int) -> dict[str, Any]:
    pin = SL.Pin(wiki, wiki.removesuffix("wiki"), title, revid, 4_000)
    return {**SL.asdict(pin), "estimate": SL.article_estimate(pin)}


def _external(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"site_id": site, "kind": "wikidata_qid", "value": qid} for site, qid in pairs]


def test_a_record_asks_its_open_fields_with_its_pinned_articles_and_says_what_it_skipped() -> None:
    exported = SL.Export(
        sites={A: _site(A), B: _site(B)},
        cards={A: {"card_description": "A card."}},
        external=_external((A, "Q1"), (B, "Q2")),
        journal=[],
    )
    skipped = ({"wiki": "enwiki", "rule": "english", "title": "T", "reason": "English"},)
    sitelinks = {
        A: _links("Q1", chosen=(_chosen("elwiki", "Ναός", 5),), skipped=skipped),
        B: _links(None, "Q2 is carried by 2 curated sites"),
    }
    questions = [_q(A, "period_start"), _q(A, "country"), _q(B, "site_type")]
    records, unlinked = SL.site_records(questions, exported=exported, sitelinks=sitelinks)
    assert unlinked == [
        {
            "site_id": B,
            "field": "site_type",
            "rule": "item-withheld",
            "reason": "Q2 is carried by 2 curated sites",
        }
    ]
    (record,) = records
    assert record[SE.RERUN_FIELDS_KEY] == ["period_start", "country"]
    assert record["source_batch"] == "batch-0007" and record["wikidata_qid"] == "Q1"
    assert record[F.WIKIDATA_ROUTE_KEY] == F.WIKIDATA_ROUTE_NARROW
    assert record[F.WIKI_SITELINKS_KEY] == [
        {"lang": "el", "revid": 5, "title": "Ναός", "wiki": "elwiki"}
    ]
    assert record["wiki_sitelinks_skipped"] == [dict(skipped[0])]
    assert "sitelink.elwiki" in [t.feature for t in F.targets_for_site(record)]


def test_a_site_with_no_usable_article_is_left_out_under_its_own_rule() -> None:
    exported = SL.Export(sites={A: _site(A)}, cards={}, external=_external((A, "Q1")), journal=[])
    records, unlinked = SL.site_records(
        [_q(A, "country")], exported=exported, sitelinks={A: _links("Q1")}
    )
    assert records == [] and unlinked[0]["rule"] == "no-article"


def test_a_record_is_refused_for_an_unresolved_site_or_a_stale_item() -> None:
    exported = SL.Export(sites={A: _site(A)}, cards={}, external=_external((A, "Q1")), journal=[])
    with pytest.raises(SystemExit, match="not in sitelinks.json"):
        SL.site_records([_q(A, "country")], exported=exported, sitelinks={})
    stale = {A: _links("Q7", chosen=(_chosen("elwiki", "Ναός", 5),))}
    with pytest.raises(SystemExit, match="resolved for Q7, the export carries Q1"):
        SL.site_records([_q(A, "country")], exported=exported, sitelinks=stale)


def test_the_batches_are_the_lanes_own_or_its_pilots() -> None:
    records = [{"site_id": f"s{n}"} for n in range(SL.BATCH_SIZE + 1)]
    lane = SL.batches(records, prefix=lanes.BATCH_PREFIX["sitelink"])
    assert [batch.batch_id for batch in lane] == ["slk-0001", "slk-0002"]
    assert [b.batch_id for b in SL.batches(records, prefix="slkg")] == ["slkg-0001", "slkg-0002"]
    with pytest.raises(SystemExit, match="the lane writes slk-NNNN"):
        SL.batches(records, prefix="gap")


# ── the country the stored point already verifies ─────────────────────────────────────────────


def _census_data(tmp_path: Path, status: dict[str, str], snapshot: list[dict[str, Any]]) -> Path:
    import gzip

    (tmp_path / "run_t02").mkdir(parents=True)
    rows = [{"site_id": s, "status": v, "test_id": "T02"} for s, v in status.items()]
    rows.append({"site_id": A, "status": "fail", "test_id": "T01"})
    (tmp_path / "run_t02" / "census.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    (tmp_path / "snapshot").mkdir()
    with gzip.open(tmp_path / "snapshot" / SP.UNIFIED_SITES_FILE, "wt", encoding="utf-8") as out:
        out.writelines(json.dumps(row) + "\n" for row in snapshot)
    return tmp_path


def test_a_country_is_verified_by_geometry_only_on_a_t02_pass_nobody_moved_since(
    tmp_path: Path,
) -> None:
    c, d = "cccccccc", "dddddddd"
    sites = [_site(A), _site(B), _site(c), _site(d, lat=37.5)]
    data = _census_data(
        tmp_path,
        {A: "pass", B: "flag", c: "pass", d: "pass"},
        [_site(A), _site(B), _site(c, country="Italy"), _site(d)],
    )
    questions = [_q(s["id"], "country") for s in sites] + [_q(A, "period_start")]
    result = SL.geometry(questions, exported=_exported(*sites), data=data)
    assert result["counts"] == {
        "asked": 4,
        "t02_flagged": 1,
        "t02_pass_but_country_or_point_changed_since": 2,
        "verified_by_geometry": 1,
    }
    assert result["verified_site_ids"] == [A]
    with pytest.raises(SystemExit, match="not in the T02 census"):
        SL.geometry([_q("eeeeeeee", "country")], exported=_exported(_site("eeeeeeee")), data=data)


# ── the pilot's scorer: the same four thresholds, the lane's own transport ───────────────────


def _pilot_batch(tmp_path: Path) -> Path:
    """One `slkg` batch: A with two articles, the German one stored, the Spanish one refused."""
    record = SP.discover_site_record(site=_site(A), card={"card_description": "A card."}, qid="Q1")
    record[F.WIKI_SITELINKS_KEY] = [
        {"wiki": "dewiki", "lang": "de", "title": "Tempel", "revid": 5},
        {"wiki": "eswiki", "lang": "es", "title": "Templo", "revid": 6},
    ]
    batch = tmp_path / "slkg-0001"
    batch.mkdir(parents=True)
    (batch / "input.json").write_text(
        json.dumps({"batch_id": "slkg-0001", "sites": [record]}), encoding="utf-8"
    )
    F.EvidenceStore(batch / "evidence").write(site_id=A, feature="sitelink.dewiki", body=b"text")
    report = {
        "sites": [
            {
                "site_id": A,
                "outcomes": [
                    {"feature": "sitelink.eswiki", "failure": "HTTP 200, answer refused: edited"}
                ],
            }
        ]
    }
    (batch / "fetch.json").write_text(json.dumps(report), encoding="utf-8")
    return batch


def test_the_sitelink_transport_counts_every_article_with_neither_a_file_nor_a_failure(
    tmp_path: Path,
) -> None:
    import score_search_pilot as SSP

    batch = _pilot_batch(tmp_path)
    assert SSP.sitelink_unaccounted(batch) == 0
    (batch / "fetch.json").write_text(json.dumps({"sites": []}), encoding="utf-8")
    assert SSP.sitelink_unaccounted(batch) == 1
    (batch / "fetch.json").unlink()
    F.EvidenceStore(batch / "evidence").path_for(A, "sitelink.dewiki").unlink()
    assert SSP.sitelink_unaccounted(batch) == 2


def test_each_lane_scores_its_own_pilot_with_its_own_transport() -> None:
    import score_search_pilot as SSP

    assert SSP.TRANSPORTS == {
        "search": SSP.search_unaccounted,
        "sitelink": SSP.sitelink_unaccounted,
    }
    assert SSP.PILOT_LANES["search"] == SSP.PilotLane(SSP.RUN, SSP.PREFIX, SSP.PROGRESS)
    sitelink = SSP.PILOT_LANES["sitelink"]
    assert sitelink.prefix == SL.PILOT_PREFIX and sitelink.run.name == "sitelink-gold"
    assert SSP.build_parser().parse_args([]).lane == "search"


def test_the_scorer_reads_the_sitelink_pilot_with_the_sitelink_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import score_search_pilot as SSP

    seen: list[Any] = []

    def sealed(batches, human, progress, *, transport):  # noqa: ANN001, ANN202
        seen.append((batches, transport))
        return True, ["sealed"]

    monkeypatch.setattr(SSP, "sealed", sealed)
    monkeypatch.setattr(
        SSP, "writer_decision", lambda batches, human: ["WRITER RESULT: NOT AVAILABLE"]
    )
    batch = _pilot_batch(tmp_path / "runs")
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({"records": []}), encoding="utf-8")
    progress = tmp_path / "progress.json"
    progress.write_text(json.dumps({"stopped": None, "failed": {}}), encoding="utf-8")
    argv = ["--lane", "sitelink", "--run-dir", str(tmp_path / "runs"), "--gold", str(gold)]
    assert SSP.main([*argv, "--progress", str(progress)]) == 0
    assert seen == [([batch], SSP.sitelink_unaccounted)]


def test_a_census_line_that_is_not_its_six_fields_stops_the_build(tmp_path: Path) -> None:
    census = _census_list(tmp_path / "m.txt", SL.B10_ROWS)
    census.write_text(census.read_text(encoding="utf-8") + "x|Kourion|Cyprus\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not id\\|name\\|stored\\|found\\|lat\\|lon"):
        SL.HandDecided.read(_write_bcases(tmp_path / "bcases"), census)


def test_the_room_is_spent_by_every_article_taken() -> None:
    """Two articles that each fit the room alone, and not together: the second one is skipped."""
    order = [_c("dewiki"), _c("frwiki")]
    each = SL.article_estimate(_pin("dewiki", 6_000, "T dewiki"))
    pins: dict[tuple[str, str], SL.Pin | str] = {
        order[0].key: _pin("dewiki", 6_000, "T dewiki"),
        order[1].key: _pin("frwiki", 6_000, "T frwiki"),
    }
    selection = SL.select(order, pins, room=each + each // 2)
    assert [pin.wiki for pin in selection.chosen] == ["dewiki"]
    assert [row["rule"] for row in selection.skipped] == ["room"]


def test_threshold_four_counts_what_the_lanes_transport_counts(tmp_path: Path) -> None:
    import score_search_pilot as SSP

    batch = _pilot_batch(tmp_path)
    record = json.loads((batch / "input.json").read_text(encoding="utf-8"))
    record["sites"][0][SE.RERUN_FIELDS_KEY] = ["period_start"]
    (batch / "input.json").write_text(json.dumps(record), encoding="utf-8")
    store = F.EvidenceStore(batch / "evidence")
    store.write(site_id=A, feature=F.FEATURE_ENWIKI, body=b"The temple of A.")
    store.write(site_id=A, feature=F.FEATURE_WIKIDATA_ENTITY, body=b"{}")
    F.EvidenceStore(batch / "answers").write(
        site_id=A, feature="period_start", body=b"Nothing dates it.\nVERDICT: UNVERIFIABLE\n"
    )
    (batch / "review.json").write_text(json.dumps({"verdicts": []}), encoding="utf-8")
    progress = {"stopped": None, "failed": {}}
    passed, lines = SSP.sealed([batch], {}, progress, transport=lambda _batch: 2)
    assert "  FAIL  4 transport: unaccounted slots 2, stopped None, failed {}" in lines
    passed, lines = SSP.sealed([batch], {}, progress, transport=SSP.sitelink_unaccounted)
    assert "  PASS  4 transport: unaccounted slots 0, stopped None, failed {}" in lines


# ── the command: census, then plan from the recorded resolution ───────────────────────────────


def _plan_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Every file `plan` reads, fabricated: A and B each asked one field; A resolved to one article."""
    run = _mass_run(tmp_path, {A: {"period_start": "UNVERIFIABLE"}, B: {"country": "UNVERIFIABLE"}})
    paths = {"mass": run, "questions": tmp_path / "questions.json"}
    assert SL.main(["census", "--mass-run", str(run), "--questions", str(paths["questions"])]) == 0
    export = tmp_path / "export"
    lanes.write_jsonl(export / "unified_sites.jsonl", [_site(A), _site(B, period_start=-300)])
    lanes.write_jsonl(export / "card_stats.jsonl", [])
    lanes.write_jsonl(export / "site_external_ids.jsonl", _external((A, "Q1"), (B, "Q2")))
    lanes.write_jsonl(export / "journal.jsonl", [])
    rows = [{"change_key": "phase3:k1", "site_id": "elsewhere", "column": "site_type"}]
    lanes.write_jsonl(tmp_path / "ALL_ROWS.jsonl", rows)
    _pin_mass_plan(monkeypatch, rows)
    (tmp_path / "written_keys.txt").write_text("phase3:k1\n", encoding="utf-8")
    census = _census_list(tmp_path / "mismatches.txt", SL.B10_ROWS)
    data = _census_data(tmp_path / "data", {A: "pass", B: "pass"}, [_site(A), _site(B)])
    questions = G.read_questions(paths["questions"])
    inputs = SL.site_inputs(questions, exported=SL.Export.read(export), mass=run)
    decided = {
        A: {**inputs[A], "chosen": [_chosen("elwiki", "Ναός", 5)], "skipped": []},
        B: {**inputs[B], "chosen": [], "skipped": []},
    }
    (tmp_path / "sitelinks.json").write_text(json.dumps(decided), encoding="utf-8")
    argv = ["plan", "--mass-run", str(run), "--questions", str(paths["questions"])]
    argv += ["--export", str(export), "--rows", str(tmp_path / "ALL_ROWS.jsonl")]
    argv += ["--written-keys", str(tmp_path / "written_keys.txt"), "--country-census", str(census)]
    argv += ["--data", str(data), "--sitelinks", str(tmp_path / "sitelinks.json")]
    argv += ["--out", str(tmp_path / "PLAN.jsonl"), "--summary", str(tmp_path / "summary.json")]
    paths["argv"] = argv  # type: ignore[assignment]
    return paths


def test_plan_writes_the_lanes_batches_and_counts_the_country_the_point_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _plan_inputs(tmp_path, monkeypatch)["argv"]
    assert SL.main(list(argv)) == 0  # type: ignore[call-overload]
    plan = (tmp_path / "PLAN.jsonl").read_text(encoding="utf-8")
    (batch,) = [json.loads(line) for line in plan.splitlines()]
    assert batch["batch_id"] == "slk-0001"
    assert [site["site_id"] for site in batch["sites"]] == [A]
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert (summary["sites"], summary["fields"], summary["articles"]) == (1, 1, 1)
    assert summary["no_article"] == {"no-article": {"country": 1}}
    assert summary["country_geometry"]["counts"] == {
        "asked": 1,
        "verified_by_geometry": 1,
        "verified_by_geometry_and_in_this_plan": 0,
    }
    assert summary["sha256"] == SL.R._sha256(tmp_path / "PLAN.jsonl")


def test_plan_refuses_a_resolution_recorded_under_other_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _plan_inputs(tmp_path, monkeypatch)["argv"]
    recorded = json.loads((tmp_path / "sitelinks.json").read_text(encoding="utf-8"))
    recorded[A]["room"] -= 1
    (tmp_path / "sitelinks.json").write_text(json.dumps(recorded), encoding="utf-8")
    with pytest.raises(SystemExit, match="resolved under other inputs"):
        SL.main(list(argv))  # type: ignore[call-overload]
    assert not (tmp_path / "PLAN.jsonl").exists()
