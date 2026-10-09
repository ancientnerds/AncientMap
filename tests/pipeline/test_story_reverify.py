"""pipeline.lyra.story_reverify: the current web verifier over published stories, in waves."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

from pipeline.lyra import story_reverify as sr
from pipeline.lyra.tweet_verifier import apply_web_verdict


def _story(item_id=6609, **fields):
    row = {
        "id": item_id,
        "headline": "Baalbek's megaliths predate the Romans",
        "facts": ["The stones predate the Romans by thousands of years."],
        "post_text": "Ancient mystery indeed!",
        "web_sources": [],
        "significance": 7,
        "news_category": "architecture",
    }
    row.update(fields)
    return SimpleNamespace(**row)


CORRECTED = {
    "verdict": "CORRECTED",
    "corrected_headline": "Video argues Baalbek's megaliths predate the Romans",
    "corrected_facts": ["The video argues the stones predate the Romans.", "The temple is Roman."],
    "corrected_text": "The video argues the megaliths are older; the excavators date them Roman.",
    "reason": "pre-Roman dating stated as fact",
}


def test_a_rerun_never_withdraws_a_published_story():
    """A re-run holds a REJECT for review: the story may be indexed and visited."""
    story = _story()
    assert (
        apply_web_verdict(story, {"verdict": "REJECT"}, withdraw_on_reject=False) == "reject_held"
    )
    assert (story.significance, story.news_category) == (7, "architecture")


def test_the_live_cycle_still_withdraws_a_rejected_new_story():
    story = _story()
    assert apply_web_verdict(story, {"verdict": "REJECT"}, withdraw_on_reject=True) == "rejected"
    assert (story.significance, story.news_category) == (1, "unverified")


class _Session:
    def __init__(self, items):
        self.items = {i.id: i for i in items}
        self.commits = self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def get(self, _model, item_id):
        return self.items[item_id]


def _wave(monkeypatch, tmp_path, story, verdict=CORRECTED):
    session = _Session([story])

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(sr, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(sr, "get_session", fake_session)
    monkeypatch.setattr(sr, "_get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(sr, "open_web_verifier", lambda settings: object())
    monkeypatch.setattr(
        sr, "pick", lambda s, limit, done, alt_first: [story] if story.id not in done else []
    )
    monkeypatch.setattr(
        sr, "web_verify_item", lambda item, verifier, settings: ("ok", dict(verdict))
    )
    return session


def test_a_wave_corrects_and_journals_before_and_after(monkeypatch, tmp_path):
    story = _story()
    session = _wave(monkeypatch, tmp_path, story)

    assert sr.run_wave(limit=10, dry_run=False) == {"corrected": 1}

    assert story.headline == CORRECTED["corrected_headline"]
    [line] = [
        json.loads(x) for x in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert line["item_id"] == 6609 and line["outcome"] == "corrected"
    assert line["before"]["headline"] == "Baalbek's megaliths predate the Romans"
    assert set(line["after"]) == {"headline", "facts", "post_text"}
    assert session.commits == 1
    # A journalled story is never picked again.
    assert sr.run_wave(limit=10, dry_run=False) == {}


def test_a_dry_run_changes_nothing_and_marks_nothing_done(monkeypatch, tmp_path):
    story = _story()
    session = _wave(monkeypatch, tmp_path, story)

    assert sr.run_wave(limit=10, dry_run=True) == {"corrected": 1}

    assert session.rollbacks == 1 and session.commits == 0
    assert (tmp_path / "dry_run.jsonl").exists()
    assert not (tmp_path / "journal.jsonl").exists()


def test_rollback_restores_the_before_values(monkeypatch, tmp_path):
    story = _story()
    _wave(monkeypatch, tmp_path, story)
    sr.run_wave(limit=10, dry_run=False)

    before = sr.rollback(6609)

    assert story.headline == before["headline"] == "Baalbek's megaliths predate the Romans"
    assert story.facts == ["The stones predate the Romans by thousands of years."]
