"""`paper correct` with the small kinds of owner decision D60 (2026-10-24).

The studio sends them in the theo_publish --correct envelope, alone or with a --report-file
text, dry run first; it checks what only the workstation can (the card's house rule, the
added evidence quotes against the workspace's dossier) and leaves the rest to the server's
gates on the stored row.
"""

from __future__ import annotations

import json

import pytest

from pipeline.studio import remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import bundle, gates, numbering, publish
from pipeline.studio.paper.workspace import read_json
from tests.pipeline.studio import fixtures as fx

ENTRIES = [{"date": "2026-10-24", "text": "Corrected the paper."}]
PICTURE = f"/data/research-images/{fx.REQ}/p1_quarry.jpg"


@pytest.fixture
def checked(tmp_path):
    ws = fx.complete_workspace(tmp_path)
    assert gates.run_check(ws)["passed"]
    return ws


class FakeRemote:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls: list[tuple] = []

    def run_module(self, module, args, *, stdin=None, timeout):
        self.calls.append((module, args, stdin))
        code, outcome = self.answers.pop(0)
        return remote.RemoteResult(code, json.dumps(outcome).encode("utf-8"), "")


@pytest.fixture
def fake(monkeypatch):
    fake = FakeRemote([(0, {"ok": True}), (0, {"ok": True, "journal_id": 7})])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(
        remote,
        "upload_research_images",
        lambda *a, **k: pytest.fail("a small kind uploads nothing"),
    )
    return fake


def _sent(fake) -> dict:
    """The apply's payload; the dry run sent the same bytes."""
    assert [call[1] for call in fake.calls] == [["--correct", "--dry-run"], ["--correct"]]
    assert fake.calls[0][2] == fake.calls[1][2]
    return json.loads(fake.calls[1][2])


def test_pictures_hero_and_card_travel_in_one_correction(fake, checked):
    record = publish.correct(
        checked,
        ENTRIES,
        image_changes={"verify": [PICTURE], "drop": []},
        hero=PICTURE,
        card="The Baalbek blocks were cut and moved by Roman engineers.",
    )
    assert record["apply"]["journal_id"] == 7
    assert _sent(fake) == {
        "version": 1,
        "request_id": fx.REQ,
        "writer": bundle.WRITER,  # the envelope writer; the stored writer stays (owner 2026-10-20)
        "corrections_append": ENTRIES,
        "probative_image_changes": {"verify": [PICTURE], "drop": []},
        "hero_image": {"web_path": PICTURE},
        "card_description": "The Baalbek blocks were cut and moved by Roman engineers.",
    }


def test_a_small_kind_goes_with_a_report_file(fake, tmp_path):
    ws = fx.make_workspace(tmp_path)
    report = numbering.build_paper(ws).markdown
    publish.correct(ws, ENTRIES, report=report, card="A corrected card for the paper.")
    sent = _sent(fake)
    assert sent["report"] == report
    assert sent["card_description"] == "A corrected card for the paper."


@pytest.mark.parametrize(
    "card",
    ["x" * 401, "One. Two. Three. Four.", "A card with a citation [1]."],
    ids=["too-long", "four-sentences", "markup"],
)
def test_a_corrected_card_keeps_the_house_rule(fake, checked, card):
    with pytest.raises(StudioError, match="--card-file refused"):
        publish.correct(checked, ENTRIES, card=card)
    assert fake.calls == []


@pytest.mark.parametrize("mode", [{"with_report": True}, {"republish": True}])
@pytest.mark.parametrize(
    "kind",
    [
        {"image_changes": {"drop": [PICTURE]}},
        {"hero": PICTURE},
        {"card": "A corrected card."},
        {"evidence_changes": {"retire": ["ev-01"]}},
    ],
)
def test_the_small_kinds_exclude_with_report_and_republish(fake, checked, mode, kind):
    with pytest.raises(StudioError, match="go alone or with --report-file"):
        publish.correct(checked, ENTRIES, **mode, **kind)
    assert fake.calls == []


def test_evidence_changes_exclude_a_rewrite(fake, checked):
    report = numbering.build_paper(checked).markdown
    with pytest.raises(StudioError, match="--evidence-changes excludes --rewrite"):
        publish.correct(
            checked, ENTRIES, report=report, rewrite=True, evidence_changes={"retire": ["ev-01"]}
        )
    assert fake.calls == []


def _added(checked, **overrides) -> dict:
    """A re-anchored copy of the workspace's first evidence entry under a new id."""
    entry = read_json(checked.evidence, "")[0]
    return {**entry, "id": "ev-90", **overrides}


def test_a_reanchored_entry_whose_quote_is_in_its_source_goes_out(fake, checked):
    entries = [{**ENTRIES[0], "evidence_id": "ev-01"}]
    changes = {"retire": ["ev-01"], "add": [_added(checked)]}
    publish.correct(checked, entries, evidence_changes=changes)
    sent = _sent(fake)
    assert sent["evidence_changes"] == changes
    assert sent["corrections_append"] == entries


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"quote": "The stone weighs exactly 2000 tons."}, "quote does not occur verbatim"),
        (
            {"source_ids": ["f6f6f6f6f6f6"], "quote_source_id": "f6f6f6f6f6f6"},
            "source ids the paper does not cite",
        ),
        (
            {"source_ids": ["0123456789ab"], "quote_source_id": "0123456789ab"},
            "source ids not in the dossier",
        ),
        ({"verdict": "partly"}, "only 'supported' may be published"),
        ({"claim": ""}, "claim must be a non-empty string"),
    ],
    ids=["quote-not-in-source", "uncited-source", "unknown-source", "partly", "no-claim"],
)
def test_a_reanchored_entry_is_checked_against_the_dossier_before_any_call(
    fake, checked, overrides, problem
):
    changes = {"retire": ["ev-01"], "add": [_added(checked, **overrides)]}
    with pytest.raises(StudioError, match="--evidence-changes refused") as refused:
        publish.correct(checked, [{**ENTRIES[0], "evidence_id": "ev-01"}], evidence_changes=changes)
    assert problem in str(refused.value)
    assert fake.calls == []


def test_a_retirement_alone_needs_no_dossier(fake, tmp_path):
    """A legacy-style workspace without a dossier may still retire an id; adding needs one."""
    ws = fx.make_workspace(tmp_path)
    ws.dossier_gz.unlink()
    publish.correct(
        ws, [{**ENTRIES[0], "evidence_id": "ev-01"}], evidence_changes={"retire": ["ev-01"]}
    )
    assert _sent(fake)["evidence_changes"] == {"retire": ["ev-01"]}
    with pytest.raises(StudioError, match="dossier.json.gz does not exist"):
        publish.correct(ws, ENTRIES, evidence_changes={"add": [{"id": "ev-90"}]})
