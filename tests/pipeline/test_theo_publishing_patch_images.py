"""Rule 8: a picture of a public paper changes through a patch, not a republish.

The 2026-10-04 campaign measured 7 image references in the 31 papers answered
404, all 7 in one paper, and named the fix (report class H.2):
`correct_paper` does not write `probative_images`, so a picture could only
change through a full republish -- replacing the whole stored text of a live
paper. The other two class-G defects are picture/content mismatches
(`p2_Halley_s_Comet.jpg` shows a hydrothermal vent, `p14_Manus_Island.jpg` is
North Sentinel Island), which have exactly the same problem: the fix is a new
picture, not a new paper.

These tests use the real block shape of the enuma-elish paper and the real
Halley case, and they assert the promise of a patch: the stored text outside the
replaced image blocks is byte-identical.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest

from pipeline.lyra import theo_publishing as tp
from tests.pipeline.test_theo_publishing_corrections import SLUG, _live_row
from tests.pipeline.theo_publish_fixtures import (
    IMG,
    IMG_NAME,
    REPORT,
    REQ,
    TITLE,
    WRITER,
    PublishSession,
    capture_notices,
)

SHA = "d" * 64
PUBLISHED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
NEW_NAME = "p9_cutting_floor.jpg"
NEW_PATH = f"/data/research-images/{REQ}/{NEW_NAME}"
NEW_BLOCK = (
    f"![gallery:1a2b3c4d|verified:yes|Quarry block on the cutting floor]({NEW_PATH})\n"
    "\n"
    "*Quarry block on the cutting floor. Photo: DAI / Wikimedia Commons.*"
    " [Source](https://commons.wikimedia.org/wiki/File:Baalbek_floor.jpg)\n"
)
#: The corrections log's date range is [publication day, today], so the entry is
#: dated today rather than a fixed date that would age out.
ENTRY = {
    "date": datetime.now(UTC).date().isoformat(),
    "text": "Replaced the quarry photograph with a verifiable one.",
}


def _new_image() -> dict:
    return {
        "title": "Quarry block on the cutting floor",
        "artist": "DAI",
        "keyword": "Baalbek",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "verified": True,
        "web_path": NEW_PATH,
        "image_path": f"research-images/{REQ}/{NEW_NAME}",
        "source_url": "https://commons.wikimedia.org/wiki/File:Baalbek_floor.jpg",
        "source_name": "Wikimedia Commons",
        "description": "",
        "rationale": "Shows the block in the quarry it was cut from",
        "search_query": "Baalbek quarry floor",
        "paragraph_text": "A second block nearby is heavier still.",
        "paragraph_index": 2,
        "section_heading": "The Quarry Blocks",
    }


def _patch(**overrides) -> dict:
    patch = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "probative_images": [_new_image()],
        "replacements": [{"old_web_path": IMG, "markdown": NEW_BLOCK}],
        "corrections_append": [ENTRY],
    }
    patch.update(overrides)
    return patch


@pytest.fixture
def images(tmp_path):
    (tmp_path / REQ).mkdir()
    (tmp_path / REQ / IMG_NAME).write_bytes(b"jpeg")
    (tmp_path / REQ / NEW_NAME).write_bytes(b"jpeg")
    return tmp_path


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


def _patch_images(session, images, patch=None, *, sha=SHA, dry_run=False):
    return tp.patch_images(
        session,
        REQ,
        patch if patch is not None else _patch(),
        bundle_sha256=sha,
        dry_run=dry_run,
        images_root=images,
    )


def test_a_patch_replaces_the_image_block_and_nothing_else(images, effects):
    before = _live_row()
    session = PublishSession(before)
    outcome = _patch_images(session, images)

    assert outcome.ok is True
    assert outcome.action == "patch_images"
    assert outcome.journal_id == 42
    stored = json.loads(session.written)

    # The text outside the block is byte-identical; inside it, only the block.
    old_block = (
        f"![Quarry block with a person for scale]({IMG})\n"
        "\n"
        "*Quarry block with a person for scale*"
        " [Source](https://commons.wikimedia.org/wiki/File:Baalbek.jpg)\n"
    )
    assert old_block in REPORT
    expected = REPORT.replace(old_block, NEW_BLOCK)
    assert stored["report"] == expected
    assert stored["published_report"] == expected
    assert stored["probative_images"] == [_new_image()]

    # Everything else of the paper is untouched.
    assert stored["title"] == TITLE
    assert stored["evidence"] == before_evidence(before)
    assert stored["quality_score"] == before_stored(before)["quality_score"]
    assert stored["writer"] == before_stored(before)["writer"]
    assert [entry["text"] for entry in stored["corrections"]] == [ENTRY["text"]]
    # One side effect run: the page's text changed, so it is re-indexed.
    assert len(effects) == 1
    assert effects[0]["reindex"] is True


def before_stored(row) -> dict:
    """The result_json the patch was written over."""
    return json.loads(row.result_json)


def before_evidence(row) -> list:
    return before_stored(row)["evidence"]


def test_a_patch_changes_neither_the_publisher_nor_the_publication_day(images, effects):
    row = _live_row()
    session = PublishSession(row)
    _patch_images(session, images)
    stored = json.loads(session.written)

    assert row.published_by == "Theo"
    assert row.published_at == PUBLISHED_AT
    assert row.slug == SLUG
    # slug, published_at and published_by are not in result_json; the write
    # updates that column only (_UPDATE_RESULT_SQL).
    assert "published_at" not in stored and "slug" not in stored


def test_the_report_shape_itself_still_validates_after_a_patch(images, effects):
    """The swapped block must not break validate_paper_artifact or the page."""
    session = PublishSession(_live_row())
    outcome = _patch_images(session, images)
    assert outcome.gates["artifact"]["passed"] is True
    assert outcome.gates["page"]["passed"] is True
    assert outcome.gates["images"]["passed"] is True
    assert outcome.gates["targets"]["passed"] is True


# -- refusals -----------------------------------------------------------------------


def test_a_patch_for_a_picture_the_paper_does_not_carry_is_refused(images, effects):
    ghost = f"/data/research-images/{REQ}/p0_never_published.jpg"
    session = PublishSession(_live_row())
    outcome = _patch_images(
        session, images, _patch(replacements=[{"old_web_path": ghost, "markdown": NEW_BLOCK}])
    )
    assert outcome.ok is False
    assert outcome.gates["targets"]["passed"] is False
    assert any("0 entries for" in issue for issue in outcome.gates["targets"]["issues"])
    assert not [sql for sql in session.statements() if "UPDATE" in sql]


def test_a_patch_whose_new_picture_is_not_on_the_vps_fails_the_images_gate(images, effects):
    (images / REQ / NEW_NAME).unlink()
    session = PublishSession(_live_row())
    outcome = _patch_images(session, images)
    assert outcome.ok is False
    assert outcome.gates["images"]["missing"] == [NEW_PATH]
    assert not [sql for sql in session.statements() if "UPDATE" in sql]


def test_a_patch_must_log_what_it_changed_on_the_page(images, effects):
    session = PublishSession(_live_row())
    outcome = _patch_images(session, images, _patch(corrections_append=[]))
    assert outcome.ok is False
    assert outcome.gates["shape"]["issues"] == [
        "corrections_append must be a non-empty list: every change is logged on the page"
    ]


def test_a_patch_block_must_name_a_picture_the_new_list_carries(images, effects):
    session = PublishSession(_live_row())
    outcome = _patch_images(
        session, images, _patch(probative_images=[{**_new_image(), "web_path": IMG}])
    )
    assert outcome.ok is False
    assert any("which the new probative_images does not carry" in issue
               for issue in outcome.gates["targets"]["issues"])


def test_a_markdown_block_without_an_image_line_is_refused(images, effects):
    session = PublishSession(_live_row())
    outcome = _patch_images(
        session, images, _patch(replacements=[{"old_web_path": IMG, "markdown": "just prose\n"}])
    )
    assert outcome.ok is False
    assert outcome.gates["shape"]["issues"] == [
        "replacements[0].markdown must start with an ![alt](path) line"
    ]


# -- idempotence, like every other write (rule 7) ------------------------------------


def test_a_patch_sent_twice_is_written_once(images, effects):
    session = PublishSession(_live_row())
    first = _patch_images(session, images)
    assert first.already_applied is False
    written = session.written

    second = _patch_images(session, images)
    assert second.ok is True
    assert second.already_applied is True
    assert second.journal_id == first.journal_id
    assert session.written == written
    assert len(session.journal) == 1
    assert len(effects) == 1


def test_a_dry_run_writes_nothing(images, effects):
    session = PublishSession(_live_row())
    outcome = _patch_images(session, images, dry_run=True)
    assert outcome.ok is True
    assert outcome.already_applied is False
    assert session.written is None
    assert not effects


# -- the report's real case: the picture that shows something else -------------------


def test_the_halley_picture_is_replaced_by_the_block_the_studio_wrote():
    """`p2_Halley_s_Comet.jpg` shows a hydrothermal vent (report class G).

    The patch carries the finished block; the server moves it and touches
    nothing else, so the prose that the vent was sitting under -- the Halley
    paragraph -- is not rewritten.
    """
    rid = "30dfca0b-0ce9-4ab5-b093-05a0240758bc"
    old = f"/data/research-images/{rid}/p2_Halley_s_Comet.jpg"
    new = f"/data/research-images/{rid}/p2_Halley_1910_drawing.jpg"
    paper = (
        "# Halley's Comet\n"
        "\n"
        "The comet was first recorded in 240 BC. [1]\n"
        "\n"
        f"![gallery:aa11bb22|verified:no|Halley's comet]({old})\n"
        "\n"
        "*Halley's comet. Photo: J. F. Julius Schmidt / Wikimedia Commons.*"
        " [Source](https://commons.wikimedia.org/wiki/File:Halley.jpg)\n"
        "\n"
        "Its 1910 return was photographed from every inhabited landmass. [2]\n"
    )
    block = (
        f"![gallery:aa11bb22|verified:yes|Halley's comet in 1910]({new})\n"
        "\n"
        "*Halley's comet in 1910. Photo: Max Wolf / Astrophotographische Gesellschaft.*"
        " [Source](https://commons.wikimedia.org/wiki/File:Halley_1910.jpg)\n"
    )
    patched = tp.apply_image_replacements(paper, [{"old_web_path": old, "markdown": block}])

    assert patched == paper.replace(
        f"![gallery:aa11bb22|verified:no|Halley's comet]({old})\n"
        "\n"
        "*Halley's comet. Photo: J. F. Julius Schmidt / Wikimedia Commons.*"
        " [Source](https://commons.wikimedia.org/wiki/File:Halley.jpg)\n",
        block,
    )
    # The verified:no marker is gone with the old block, and the prose is intact.
    assert "verified:no" not in patched
    assert "first recorded in 240 BC. [1]" in patched
    assert "photographed from every inhabited landmass. [2]" in patched


def test_the_patched_report_is_what_the_gate_revalidated(images, effects):
    """The stored text is the patched one, not the one the studio sent.

    The studio never sends the paper's text in a patch: it sends blocks, and
    the server is the only thing that assembles the new text.
    """
    session = PublishSession(_live_row())
    _patch_images(session, images)
    stored = json.loads(session.written)
    stored_report = stored["report"]
    assert IMG not in stored_report
    assert NEW_PATH in stored_report
    assert stored_report.count("![") == REPORT.count("![")
    assert copy.deepcopy(stored["probative_images"]) == [_new_image()]
