"""pipeline.lyra.story_site_link: checked proposals written with a journal and a rollback."""

import json
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from pipeline.database import NewsItem, UnifiedSite
from pipeline.lyra import story_site_link as sl

CURATED = uuid.UUID(int=1)
RETIRED_SITE = uuid.UUID(int=2)
BULK = uuid.UUID(int=3)
OTHER = uuid.UUID(int=4)
NO_COUNTRY = uuid.UUID(int=5)


class _Session:
    def __init__(self, items, sites, commit_error=None):
        self.objects = {NewsItem: {i.id: i for i in items}, UnifiedSite: {s.id: s for s in sites}}
        self.commits = self.rollbacks = 0
        self.commit_error = commit_error

    def get(self, model, key):
        return self.objects[model].get(key)

    def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _sites():
    return [
        SimpleNamespace(id=CURATED, source_id="ancient_nerds", country="Egypt", scope_status=None),
        SimpleNamespace(
            id=RETIRED_SITE, source_id="ancient_nerds", country="Egypt", scope_status="retired"
        ),
        SimpleNamespace(id=BULK, source_id="wikidata", country="Egypt", scope_status=None),
        SimpleNamespace(
            id=OTHER, source_id="ancient_nerds", country="Egypt", scope_status="in_scope"
        ),
        # Curated but without a country: no /sites page (public_sites.curated_page).
        SimpleNamespace(id=NO_COUNTRY, source_id="ancient_nerds", country=None, scope_status=None),
    ]


def _story(item_id=7650, site_id=None):
    return SimpleNamespace(id=item_id, site_id=site_id, headline="Hawara project")


def _proposal(item_id=7650, site=CURATED, current=None, approved=True):
    return {
        "story_id": item_id,
        "site_id": str(site),
        "site_name": "Pyramid of Amenemhat III at Hawara",
        "current_site_id": str(current) if current else None,
        "match_reason": "headline: Hawara (wikidata_alias)",
        "evidence_snippet": "[headline] ... the Hawara project",
        "approved": approved,
    }


@pytest.fixture
def env(monkeypatch, tmp_path):
    state = SimpleNamespace(session=None, announced=[])

    @contextmanager
    def fake_session():
        yield state.session

    monkeypatch.setattr(sl, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(sl, "get_session", fake_session)
    monkeypatch.setattr(sl, "submit", lambda urls: state.announced.append(list(urls)))
    state.journal = tmp_path / "journal.jsonl"
    state.dry = tmp_path / "dry_run.jsonl"
    return state


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_an_approved_proposal_is_written_journalled_and_announced(env):
    story = _story()
    env.session = _Session([story], _sites())
    assert sl.apply([_proposal()], dry_run=False) == {"linked": 1}
    assert story.site_id == CURATED
    assert env.session.commits == 1
    (line,) = _lines(env.journal)
    assert line["outcome"] == "linked"
    assert line["before"] == {"site_id": None}
    assert line["after"] == {"site_id": str(CURATED)}
    assert line["evidence_snippet"].startswith("[headline]")
    assert any(u.endswith("/news-archive/hawara-project-7650") for u in env.announced[0])


def test_only_a_proposal_marked_approved_is_written(env):
    story = _story()
    env.session = _Session([story], _sites())
    outcomes = sl.apply([_proposal(approved=None), _proposal(approved=False)], dry_run=False)
    assert outcomes == {"not_approved": 2}
    assert story.site_id is None
    assert env.session.commits == 0


def test_a_story_linked_since_the_proposal_is_left_alone(env):
    story = _story(site_id=OTHER)
    env.session = _Session([story], _sites())
    assert sl.apply([_proposal()], dry_run=False) == {"changed_since_proposal": 1}
    assert story.site_id == OTHER


def test_a_relink_from_a_bulk_imported_site_names_it(env):
    story = _story(site_id=BULK)
    env.session = _Session([story], _sites())
    assert sl.apply([_proposal(current=BULK)], dry_run=False) == {"linked": 1}
    assert _lines(env.journal)[0]["before"] == {"site_id": str(BULK)}


@pytest.mark.parametrize("site", [RETIRED_SITE, BULK, NO_COUNTRY, uuid.UUID(int=99)])
def test_only_a_curated_site_with_a_page_is_a_target(env, site):
    story = _story()
    env.session = _Session([story], _sites())
    assert sl.apply([_proposal(site=site)], dry_run=False) == {"not_curated": 1}
    assert story.site_id is None


def test_a_failed_commit_journals_no_link(env):
    """The journal tells what committed: --rollback trusts its 'linked' entries."""
    story = _story()
    env.session = _Session([story], _sites(), commit_error=RuntimeError("connection lost"))
    with pytest.raises(RuntimeError, match="connection lost"):
        sl.apply([_proposal(), _proposal(item_id=7651)], dry_run=False)
    (line,) = _lines(env.journal)
    assert line["outcome"] == "commit_failed"
    assert line["after"] == {}
    assert env.announced == []
    with pytest.raises(SystemExit, match="no link of story 7650"):
        sl.rollback(7650)


def test_a_dry_run_changes_nothing_and_journals_apart(env):
    story = _story()
    env.session = _Session([story], _sites())
    assert sl.apply([_proposal()], dry_run=True) == {"linked": 1}
    assert env.session.commits == 0 and env.session.rollbacks == 1
    assert not env.journal.exists()
    assert _lines(env.dry)[0]["dry_run"] is True
    assert env.announced == []


def test_a_rollback_puts_the_site_before_back(env):
    story = _story(site_id=BULK)
    env.session = _Session([story], _sites())
    sl.apply([_proposal(current=BULK)], dry_run=False)
    assert sl.rollback(7650) == {"site_id": str(BULK)}
    assert story.site_id == BULK
    assert _lines(env.journal)[-1]["outcome"] == "rolled_back"


def test_a_rollback_refuses_a_story_changed_since_the_link(env):
    story = _story()
    env.session = _Session([story], _sites())
    sl.apply([_proposal()], dry_run=False)
    story.site_id = OTHER
    with pytest.raises(SystemExit, match="nothing rolled back"):
        sl.rollback(7650)
    assert story.site_id == OTHER


def test_proposals_are_read_one_json_object_per_line():
    lines = ['{"story_id": 1, "approved": true}\n', "\n", '{"story_id": 2}\n']
    assert [p["story_id"] for p in sl.read_proposals(lines)] == [1, 2]
