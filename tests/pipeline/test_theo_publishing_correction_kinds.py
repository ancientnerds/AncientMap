"""The small correction kinds of owner decision D60 (2026-10-24), through correct_paper.

A public paper's pictures, hero, card and evidence anchors change inside `--correct`,
only within what the paper already carries (owner 2026-10-20: no new images), with the
gates of a text correction re-run on the result and the journal row of every correction.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from pipeline.lyra import theo_publishing as tp
from pipeline.lyra.hero_picker import hero_from_entry
from pipeline.lyra.theo_citations import validate_paper_artifact
from tests.pipeline.theo_publish_fixtures import (
    DOSSIER_SUMMARY,
    EVIDENCE,
    HERO,
    IMG,
    IMG_NAME,
    REPORT,
    REQ,
    WRITER,
    PublishSession,
    capture_notices,
    make_result,
    research_row,
)

SHA = "c" * 64
SLUG = "the-baalbek-trilithon"
PUBLISHED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
DAY = "2026-09-22"

WIDE_NAME = "p2_trilithon_wide.jpg"
TALL_NAME = "p3_quarry_portrait.jpg"
SPARE_NAME = "p4_quarry_unopened.jpg"
NARROW_NAME = "p5_quarry_small.jpg"
BROKEN_NAME = "p6_not_a_picture.jpg"
WIDE, TALL, SPARE, NARROW, BROKEN = (
    f"/data/research-images/{REQ}/{name}"
    for name in (WIDE_NAME, TALL_NAME, SPARE_NAME, NARROW_NAME, BROKEN_NAME)
)
#: The size of each served file; BROKEN is bytes that are no picture.
SIZES = {
    IMG_NAME: (1200, 800),
    WIDE_NAME: (1600, 700),
    TALL_NAME: (700, 1400),
    SPARE_NAME: (1400, 800),
    NARROW_NAME: (400, 300),
}


def _entry(name: str, *, verified: bool | None) -> dict:
    """A stored probative_images record with full attribution (theo_image_gate)."""
    entry = {
        "title": name.removesuffix(".jpg").replace("_", " "),
        "web_path": f"/data/research-images/{REQ}/{name}",
        "license": "CC BY-SA 4.0",
        "source_url": f"https://commons.wikimedia.org/wiki/File:{name}",
        "source_name": "wikimedia",
        "artist": "A. Photographer",
        "description": f"The quarry, {name}",
        "rationale": "Shows the quarry.",
    }
    if verified is not None:
        entry["verified"] = verified
    return entry


def _images(*, spare_verified: bool = True) -> list[dict]:
    return [
        make_result()["probative_images"][0],
        _entry(WIDE_NAME, verified=True),
        _entry(TALL_NAME, verified=True),
        _entry(SPARE_NAME, verified=spare_verified),
        _entry(NARROW_NAME, verified=True),
        _entry(BROKEN_NAME, verified=True),
    ]


def _live_row(**result_overrides):
    stored = {
        **make_result(probative_images=_images()),
        "audit": validate_paper_artifact(REPORT),
        "writer": WRITER,
        "dossier": DOSSIER_SUMMARY,
    }
    stored.update(result_overrides)
    return research_row(
        status="completed",
        is_public=True,
        slug=SLUG,
        published_by="Theo",
        published_at=PUBLISHED_AT,
        result_json=json.dumps(stored),
    )


@pytest.fixture
def images(tmp_path) -> Path:
    """research-images/ with real pictures of known sizes (the hero gate measures them)."""
    root = tmp_path / "research-images"
    (root / REQ).mkdir(parents=True)
    for name, size in SIZES.items():
        Image.new("RGB", size, (120, 110, 90)).save(root / REQ / name, "JPEG")
    (root / REQ / BROKEN_NAME).write_bytes(b"jpeg")
    return root


@pytest.fixture
def effects(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}

    monkeypatch.setattr(tp, "run_publish_side_effects", fake)
    return calls


@pytest.fixture(autouse=True)
def notices(monkeypatch) -> dict[str, list]:
    return capture_notices(monkeypatch)


def _correction(entries: list[dict] | None = None, **parts) -> dict:
    return {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "corrections_append": entries or [{"date": DAY, "text": "Corrected the paper."}],
        **parts,
    }


def _correct(session, images, correction, *, dry_run=False):
    return tp.correct_paper(
        session,
        REQ,
        correction,
        bundle_sha256=SHA,
        dry_run=dry_run,
        images_root=images,
        served_root=images.parent,
    )


def _failing(outcome) -> dict[str, list[str]]:
    return {name: gate["issues"] for name, gate in outcome.gates.items() if not gate["passed"]}


# --- probative_image_changes ---------------------------------------------------------


def test_a_stored_unverified_picture_holds_every_correction_until_its_flag_is_flipped(
    images, effects
):
    """enuma-elish and solar-superflares: stored `verified: false` records fail the pictures
    gate on every correction, even when the text shows none of them (OPEN_ITEMS 2026-10-20)."""
    row = _live_row(probative_images=_images(spare_verified=False))
    held = _correct(PublishSession(row), images, _correction(), dry_run=True)
    assert set(_failing(held)) == {"pictures"}

    session = PublishSession(_live_row(probative_images=_images(spare_verified=False)))
    outcome = _correct(session, images, _correction(probative_image_changes={"verify": [SPARE]}))
    assert outcome.ok is True, _failing(outcome)
    assert outcome.gates["image_changes"] == {"passed": True, "issues": []}
    stored = json.loads(session.written)
    expected = _images(spare_verified=True)
    assert stored["probative_images"] == expected
    assert stored["report"] == stored["published_report"] == REPORT  # the text did not move
    assert stored["hero_image"] == stored["published_hero_image"] == HERO
    assert stored["writer"] == WRITER  # a small kind never stores a writer (owner 2026-10-20)
    (call,) = effects
    assert call["reindex"] is True


def test_a_drop_removes_one_stored_record_and_nothing_else(images, effects):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction(probative_image_changes={"drop": [TALL]}))
    assert outcome.ok is True, _failing(outcome)
    stored = json.loads(session.written)
    assert stored["probative_images"] == [e for e in _images() if e["web_path"] != TALL]
    assert stored["report"] == REPORT


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        (
            {"verify": [WIDE]},
            f"{WIDE}: its stored entry is not marked verified: false; only a false flag is flipped",
        ),
        (
            {"verify": [f"/data/research-images/{REQ}/p9_new.jpg"]},
            f"/data/research-images/{REQ}/p9_new.jpg: the stored probative_images hold 0 entries "
            "for it, not exactly one (a correction changes only pictures the paper carries)",
        ),
        (
            {"drop": [NARROW]},
            None,
        ),
    ],
    ids=["verify-a-verified-one", "a-new-picture", "drop-a-shown-one"],
)
def test_image_changes_stay_within_the_stored_set(images, effects, changes, issue):
    report = REPORT
    if issue is None:  # NARROW, shown in the text by a block of its own
        report = REPORT.replace(f"]({IMG})", f"]({NARROW})")
        issue = (
            f"{NARROW}: the text still shows this picture; remove its image block in `report` first"
        )
    session = PublishSession(_live_row(report=report, published_report=report))
    outcome = _correct(session, images, _correction(probative_image_changes=changes))
    assert outcome.ok is False
    assert _failing(outcome) == {"image_changes": [issue]}
    assert session.written is None
    assert effects == []


def test_a_record_without_a_verified_flag_is_not_flipped(images):
    """A record without the flag predates it (theo_image_gate): no claim to correct."""
    unflagged = [*_images()[:3], _entry(SPARE_NAME, verified=None), *_images()[4:]]
    outcome = _correct(
        PublishSession(_live_row(probative_images=unflagged)),
        images,
        _correction(probative_image_changes={"verify": [SPARE]}),
        dry_run=True,
    )
    assert "image_changes" in _failing(outcome)


def test_the_heros_picture_is_dropped_only_together_with_a_new_hero(images, effects):
    hero = hero_from_entry(_entry(WIDE_NAME, verified=True))
    row = _live_row(hero_image=hero, published_hero_image=hero)
    held = _correct(
        PublishSession(row), images, _correction(probative_image_changes={"drop": [WIDE]})
    )
    assert _failing(held) == {
        "image_changes": [f"{WIDE} is the hero's picture; name another hero in hero_image first"]
    }
    session = PublishSession(_live_row(hero_image=hero, published_hero_image=hero))
    outcome = _correct(
        session,
        images,
        _correction(probative_image_changes={"drop": [WIDE]}, hero_image={"web_path": SPARE}),
    )
    assert outcome.ok is True, _failing(outcome)
    stored = json.loads(session.written)
    assert stored["hero_image"]["src"] == SPARE
    assert WIDE not in [e["web_path"] for e in stored["probative_images"]]


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        ([WIDE], "probative_image_changes must be an object {verify?, drop?}"),
        ({"flip": [WIDE]}, "probative_image_changes has unknown keys ['flip']"),
        ({}, "probative_image_changes must name at least one picture to verify or drop"),
        (
            {"verify": [], "drop": []},
            "probative_image_changes must name at least one picture to verify or drop",
        ),
        ({"verify": [WIDE, WIDE]}, f"probative_image_changes.verify names {WIDE} twice"),
        ({"drop": [""]}, "probative_image_changes.drop must be a list of non-empty strings"),
        (
            {"verify": [SPARE], "drop": [SPARE]},
            f"probative_image_changes both verifies and drops {SPARE}",
        ),
    ],
)
def test_image_changes_are_shape_checked(images, changes, issue):
    outcome = _correct(
        PublishSession(_live_row()),
        images,
        _correction(probative_image_changes=changes),
        dry_run=True,
    )
    assert _failing(outcome) == {"shape": [issue]}


# --- hero_image -------------------------------------------------------------------------


def test_a_hero_from_the_papers_own_pictures_replaces_both_hero_fields(images, effects, notices):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction(hero_image={"web_path": WIDE}))
    assert outcome.ok is True, _failing(outcome)
    assert outcome.gates["hero"] == {"passed": True, "issues": [], "width": 1600, "height": 700}
    stored = json.loads(session.written)
    hero = hero_from_entry(_entry(WIDE_NAME, verified=True))
    assert stored["hero_image"] == stored["published_hero_image"] == hero
    assert hero["src"] == hero["web_path"] == WIDE
    assert stored["probative_images"] == _images()
    assert stored["report"] == REPORT
    assert notices == {"thinking": [], "discord": []}  # not a rewrite: no owner notice


@pytest.mark.parametrize(
    ("web_path", "issue"),
    [
        (TALL, f"{TALL} is portrait (700x1400): a banner is landscape"),
        (NARROW, f"{NARROW} is 400 px wide, below the banner minimum 600"),
        (IMG, f"{IMG} is already the hero"),
        (
            f"/data/research-images/{REQ}/p9_new.jpg",
            f"/data/research-images/{REQ}/p9_new.jpg: the paper's probative_images hold 0 "
            "entries for it, not exactly one (a hero is a picture the paper already carries, "
            "never a new one)",
        ),
    ],
    ids=["portrait", "narrow", "already-the-hero", "a-new-picture"],
)
def test_a_hero_must_be_a_banner_the_paper_already_carries(images, effects, web_path, issue):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction(hero_image={"web_path": web_path}))
    assert _failing(outcome) == {"hero": [issue]}
    assert session.written is None


def test_a_hero_picture_held_twice_is_not_guessed_between(images):
    """Two records of one file: which credit the banner carries would be a guess."""
    twice = [*_images(), _entry(WIDE_NAME, verified=True)]
    outcome = _correct(
        PublishSession(_live_row(probative_images=twice)),
        images,
        _correction(hero_image={"web_path": WIDE}),
        dry_run=True,
    )
    assert _failing(outcome)["hero"] == [
        f"{WIDE}: the paper's probative_images hold 2 entries for it, not exactly one (a hero "
        "is a picture the paper already carries, never a new one)"
    ]


def test_an_unreadable_hero_file_is_named_not_guessed(images):
    outcome = _correct(
        PublishSession(_live_row()),
        images,
        _correction(hero_image={"web_path": BROKEN}),
        dry_run=True,
    )
    (issue,) = _failing(outcome)["hero"]
    assert issue.startswith(f"{BROKEN}: the size of ")
    assert "cannot be read" in issue


def test_an_unverified_picture_becomes_the_hero_only_once_its_flag_is_flipped(images, effects):
    row = _live_row(probative_images=_images(spare_verified=False))
    held = _correct(PublishSession(row), images, _correction(hero_image={"web_path": SPARE}))
    assert _failing(held)["hero"] == [
        f"{SPARE} is marked verified: false: nobody has opened this picture"
    ]
    session = PublishSession(_live_row(probative_images=_images(spare_verified=False)))
    outcome = _correct(
        session,
        images,
        _correction(probative_image_changes={"verify": [SPARE]}, hero_image={"web_path": SPARE}),
    )
    assert outcome.ok is True, _failing(outcome)
    assert json.loads(session.written)["hero_image"]["src"] == SPARE


@pytest.mark.parametrize(
    "hero",
    [WIDE, {"src": WIDE}, {"web_path": WIDE, "caption": "x"}, {"web_path": ""}],
)
def test_hero_image_names_only_a_web_path(images, hero):
    outcome = _correct(
        PublishSession(_live_row()), images, _correction(hero_image=hero), dry_run=True
    )
    assert _failing(outcome) == {
        "shape": ["hero_image must be {web_path}: the path of a picture the paper already carries"]
    }


# --- card_description ------------------------------------------------------------------

NEW_CARD = "The Baalbek quarry blocks are Roman work, cut from the podium's limestone bed."


def test_a_card_correction_replaces_the_card_only(images, effects):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction(card_description=NEW_CARD))
    assert outcome.ok is True, _failing(outcome)
    assert outcome.gates["card"] == {"passed": True, "issues": []}
    stored = json.loads(session.written)
    before = json.loads(_live_row().result_json)
    assert stored["card_description"] == NEW_CARD
    changed = sorted(k for k in stored if stored[k] != before.get(k))
    assert changed == ["card_description", "corrections"]


@pytest.mark.parametrize(
    ("card", "gate", "issue"),
    [
        (make_result()["card_description"], "card", "card_description equals the stored one"),
        ("x" * 601, "shape", "card_description must be 1-600 characters"),
        (
            "Two lines.\nOf card.",
            "shape",
            "card_description must be one line without leading or trailing whitespace",
        ),
        (
            " Padded card.",
            "shape",
            "card_description must be one line without leading or trailing whitespace",
        ),
        (
            "Roman work [1].",
            "shape",
            "card_description must be plain text (no citations, no markdown)",
        ),
        (
            "**Bold** card.",
            "shape",
            "card_description must be plain text (no citations, no markdown)",
        ),
        ("", "shape", "card_description must be a non-empty string"),
        (7, "shape", "card_description must be a non-empty string"),
    ],
)
def test_a_card_is_one_plain_line_that_changes_something(images, card, gate, issue):
    outcome = _correct(
        PublishSession(_live_row()), images, _correction(card_description=card), dry_run=True
    )
    assert _failing(outcome) == {gate: [issue]}


# --- evidence_changes -----------------------------------------------------------------

OLD_OPENING = "The quarry dates to the Roman period, which the excavation layers confirm [2]."
NEW_OPENING = "Excavation layers date the quarry to the Roman period, as the survey confirms [2]."
REANCHORED_REPORT = REPORT.replace(OLD_OPENING, NEW_OPENING)
EV_03 = {
    **copy.deepcopy(EVIDENCE[1]),
    "id": "ev-03",
    "anchor_text": "Excavation layers date the quarry to the Roman period",
}
RETIRE_ENTRY = {"date": DAY, "text": "Reworded the dating paragraph.", "evidence_id": "ev-02"}


def test_an_anchored_opening_cannot_change_while_its_evidence_entry_stands(images):
    """Why the kind exists: the 25 anchor-blocked findings of the 2026-10-19 audit."""
    outcome = _correct(
        PublishSession(_live_row()), images, _correction(report=REANCHORED_REPORT), dry_run=True
    )
    assert _failing(outcome) == {
        "evidence": ["ev-02: anchor_text matches 0 paragraphs (needs exactly 1)"]
    }


def test_a_reanchored_entry_takes_a_new_id_and_the_old_one_is_retired(images, effects):
    session = PublishSession(_live_row())
    correction = _correction(
        [RETIRE_ENTRY],
        report=REANCHORED_REPORT,
        evidence_changes={"retire": ["ev-02"], "add": [EV_03]},
    )
    outcome = _correct(session, images, correction)
    assert outcome.ok is True, _failing(outcome)
    assert outcome.gates["evidence_changes"] == {"passed": True, "issues": []}
    stored = json.loads(session.written)
    assert [e["id"] for e in stored["evidence"]] == ["ev-01", "ev-03"]
    assert stored["evidence"][0] == EVIDENCE[0]  # a kept entry is byte for byte the stored one
    assert stored["evidence"][1] == EV_03
    assert stored["corrections"] == [RETIRE_ENTRY]
    assert stored["report"] == stored["published_report"] == REANCHORED_REPORT


def test_an_entry_can_be_retired_without_a_replacement(images, effects):
    session = PublishSession(_live_row())
    outcome = _correct(
        session, images, _correction([RETIRE_ENTRY], evidence_changes={"retire": ["ev-02"]})
    )
    assert outcome.ok is True, _failing(outcome)
    assert [e["id"] for e in json.loads(session.written)["evidence"]] == ["ev-01"]


@pytest.mark.parametrize(
    ("entries", "changes", "failing"),
    [
        (
            [{"date": DAY, "text": "Reworded the dating paragraph."}],
            {"retire": ["ev-02"], "add": [EV_03]},
            {"retention": ["ev-02 removed without a correction entry naming it"]},
        ),
        (
            [RETIRE_ENTRY],
            {"retire": ["ev-02"], "add": [{**EV_03, "id": "ev-01"}]},
            {
                "evidence_changes": [
                    "ev-01 is a current evidence id: a re-anchored entry takes a new id"
                ],
                "evidence": ["ev-01: duplicate id"],
                "page": ["evidence id ev-01 appears twice"],
            },
        ),
        (
            [RETIRE_ENTRY],
            {"retire": ["ev-02"], "add": [{**EV_03, "id": "ev-02"}]},
            {
                "evidence_changes": [
                    "ev-02 is a current evidence id: a re-anchored entry takes a new id"
                ]
            },
        ),
        (
            [RETIRE_ENTRY, {"date": DAY, "text": "Dropped a claim.", "evidence_id": "ev-07"}],
            {"retire": ["ev-02", "ev-07"], "add": [EV_03]},
            {
                "evidence_changes": ["ev-07 is not an evidence id of this paper"],
                "retention": ["a correction names ev-07, which this paper never had"],
            },
        ),
        (
            [RETIRE_ENTRY],
            {"retire": ["ev-02"], "add": [{**EV_03, "verdict": "partly"}]},
            {"evidence": ["ev-03: verdict is 'partly'; only 'supported' may be published"]},
        ),
        (
            [RETIRE_ENTRY],
            {
                "retire": ["ev-02"],
                "add": [{**EV_03, "anchor_text": "A paragraph nobody wrote here"}],
            },
            {"evidence": ["ev-03: anchor_text matches 0 paragraphs (needs exactly 1)"]},
        ),
    ],
    ids=[
        "unnamed-retirement",
        "reuse-a-kept-id",
        "reuse-the-retired-id",
        "unknown-id",
        "partly",
        "unanchored",
    ],
)
def test_evidence_changes_refusals(images, effects, entries, changes, failing):
    session = PublishSession(_live_row())
    outcome = _correct(
        session,
        images,
        _correction(entries, report=REANCHORED_REPORT, evidence_changes=changes),
    )
    assert _failing(outcome) == failing
    assert session.written is None


def test_an_id_retired_earlier_is_never_handed_out_again(images):
    """ev-05 was retired by a stored correction: no re-anchored entry may take it."""
    row = _live_row(corrections=[{"date": DAY, "text": "Retired ev-05.", "evidence_id": "ev-05"}])
    outcome = _correct(
        PublishSession(row),
        images,
        _correction(
            [RETIRE_ENTRY],
            report=REANCHORED_REPORT,
            evidence_changes={"retire": ["ev-02"], "add": [{**EV_03, "id": "ev-05"}]},
        ),
        dry_run=True,
    )
    assert _failing(outcome) == {"retention": ["ev-05 was retired earlier and may not be reused"]}


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        (["ev-02"], "evidence_changes must be an object {retire?, add?}"),
        ({"remove": ["ev-02"]}, "evidence_changes has unknown keys ['remove']"),
        ({}, "evidence_changes must retire or add at least one entry"),
        ({"retire": ["02"]}, "evidence_changes.retire: '02' is not an evidence id (ev-NN)"),
        ({"retire": ["ev-02", "ev-02"]}, "evidence_changes.retire names ev-02 twice"),
        ({"add": {"id": "ev-03"}}, "evidence_changes.add must be a list of evidence entries"),
    ],
)
def test_evidence_changes_are_shape_checked(images, changes, issue):
    outcome = _correct(
        PublishSession(_live_row()),
        images,
        _correction([RETIRE_ENTRY], evidence_changes=changes),
        dry_run=True,
    )
    assert _failing(outcome)["shape"] == [issue]


# --- several kinds at once, and the journal ------------------------------------------


def test_text_pictures_hero_and_card_go_out_as_one_journalled_correction(images, effects):
    """enuma-elish's case: a corrected text, its stored unverified records flipped, a new
    card, and a hero among its own pictures, in one write and one journal row."""
    session = PublishSession(_live_row(probative_images=_images(spare_verified=False)))
    correction = _correction(
        [RETIRE_ENTRY],
        report=REANCHORED_REPORT,
        evidence_changes={"retire": ["ev-02"], "add": [EV_03]},
        probative_image_changes={"verify": [SPARE], "drop": [TALL]},
        hero_image={"web_path": WIDE},
        card_description=NEW_CARD,
    )
    outcome = _correct(session, images, correction)
    assert outcome.ok is True, _failing(outcome)
    assert {"evidence_changes", "image_changes", "hero", "card"} <= set(outcome.gates)
    assert outcome.journal_id == 42
    (journal,) = session.journal
    assert journal.action == "correct"
    assert journal.bundle_sha256 == SHA
    stored = json.loads(session.written)
    assert stored["card_description"] == NEW_CARD
    assert stored["hero_image"]["src"] == WIDE
    assert [e["web_path"] for e in stored["probative_images"]] == [
        e["web_path"] for e in _images() if e["web_path"] != TALL
    ]
    assert all(e.get("verified") is not False for e in stored["probative_images"])


def test_a_small_kind_on_a_paper_that_is_not_public_is_refused(images):
    row = _live_row()
    row.is_public = False
    outcome = _correct(
        PublishSession(row), images, _correction(card_description=NEW_CARD), dry_run=True
    )
    assert set(_failing(outcome)) == {"status"}


def test_the_same_small_correction_sent_twice_writes_once(images, effects):
    session = PublishSession(_live_row())
    correction = _correction(card_description=NEW_CARD)
    first = _correct(session, images, correction)
    again = _correct(session, images, correction)
    assert first.ok is True and again.already_applied is True
    assert again.journal_id == first.journal_id
    assert len(session.journal) == 1


# --- quality: the stored title-term count (mogollon) -----------------------------------

MOGOLLON = "Mogollon Pithouse Sites Across the Upper Gila"


def _mogollon_row(report: str):
    """mogollon's stored summary: undefined_title_terms = 1 since its M3 write (prod 2026-10-24)."""
    quality = {
        "score": 98,
        "badge": "Unverified",
        "passed": True,
        "audit_gate_failures": {
            "audit_passed": False,
            "hallucination_final": 0,
            "high_contradictions": 0,
            "undefined_title_terms": 1,
            "non_numeric_markers": 2,
        },
    }
    return _live_row(
        title=MOGOLLON,
        report=report,
        published_report=report,
        quality_score=quality,
        evidence=[],
    )


MOGOLLON_REPORT = REPORT.replace("# The Baalbek Trilithon", f"# {MOGOLLON}")


def test_a_stored_title_term_count_no_longer_holds_a_text_that_carries_its_title(images):
    outcome = _correct(
        PublishSession(_mogollon_row(MOGOLLON_REPORT)), images, _correction(), dry_run=True
    )
    assert outcome.ok is True, _failing(outcome)
    assert outcome.gates["quality"]["undefined_title_terms"] == []


def test_a_text_without_its_title_terms_is_still_held(images):
    report = MOGOLLON_REPORT.replace(f"# {MOGOLLON}", "# Pithouses of the Gila")
    outcome = _correct(
        PublishSession(_mogollon_row(report)), images, _correction(report=report), dry_run=True
    )
    assert _failing(outcome)["quality"] == [
        "recompute_quality_passed rejects the paper against the fresh audit"
    ]
    assert outcome.gates["quality"]["undefined_title_terms"] == [MOGOLLON]
