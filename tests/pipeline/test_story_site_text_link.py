"""site_matcher: where the hourly match step lets the story-text matcher decide."""

import uuid
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_
from sqlalchemy.orm.evaluator import _EvaluatorCompiler

from pipeline.database import NewsItem
from pipeline.lyra import site_matcher as sm

CURATED = str(uuid.UUID(int=1))


class _Matcher:
    def __init__(self, reason="headline"):
        self.reason = reason
        self.calls = 0

    def match_item(self, item):
        self.calls += 1
        return SimpleNamespace(site_id=CURATED, site_name="Giza", reason=self.reason, via="Giza")


def _item(created_at=sm.TEXT_MATCH_SINCE, site_id=None):
    return SimpleNamespace(
        id=1, created_at=created_at, site_id=site_id, site_name_extracted="Wadi Cemetery"
    )


def test_a_story_before_the_cutoff_is_left_to_the_reviewed_proposals():
    """The stock gets a checked list; the live step must not link it unreviewed."""
    item, matcher = _item(created_at=sm.TEXT_MATCH_SINCE - timedelta(seconds=1)), _Matcher()
    assert sm._link_by_text(item, None, matcher) is None
    assert (item.site_id, matcher.calls) == (None, 0)


def test_a_new_story_without_a_site_takes_the_text_match():
    item = _item()
    assert sm._link_by_text(item, None, _Matcher()).site_id == CURATED
    assert item.site_id == uuid.UUID(CURATED)


def test_a_curated_exact_key_hit_is_never_second_guessed():
    item, matcher = _item(), _Matcher(reason="extracted_name")
    site = SimpleNamespace(source_id="ancient_nerds")
    assert sm._link_by_text(item, site, matcher) is None
    assert matcher.calls == 0


def test_a_bulk_imported_hit_gives_way_only_to_the_extracted_name():
    site = SimpleNamespace(source_id="wikidata")
    item = _item()
    assert sm._link_by_text(item, site, _Matcher(reason="headline")) is None
    assert item.site_id is None
    assert sm._link_by_text(item, site, _Matcher(reason="extracted_name")).site_id == CURATED
    assert item.site_id == uuid.UUID(CURATED)


def test_no_text_match_changes_nothing():
    class Nothing:
        def match_item(self, item):
            return None

    item = _item()
    assert sm._link_by_text(item, None, Nothing()) is None
    assert item.site_id is None


# --- match_sites_for_pending_items: the queries and the loop around _link_by_text ---
#
# The fake session evaluates the step's own filter criteria on transient NewsItem
# rows with SQLAlchemy's in-Python evaluator (the one synchronize_session='evaluate'
# uses), so the cutoff and the post_text gate are tested as written, without a
# Postgres: news_items carries JSONB and joins unified_sites, which has PostGIS.

BULK = uuid.UUID(int=3)
NEW = sm.TEXT_MATCH_SINCE + timedelta(hours=1)
OLD = sm.TEXT_MATCH_SINCE - timedelta(days=1)


class _Query:
    """NewsItem rows filtered by the step's criteria; any other entity (the
    promoted radar ids) has no rows."""

    def __init__(self, rows):
        self.rows = rows

    def filter(self, *criteria):
        if not self.rows:
            return self
        keep = _EvaluatorCompiler(NewsItem).process(and_(*criteria))
        return _Query([r for r in self.rows if keep(r)])

    def all(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class _StepSession:
    def __init__(self, items):
        self.items = items

    def query(self, entity):
        return _Query(self.items if entity is NewsItem else [])

    def flush(self):
        pass


def _news(item_id, created_at, name=None, post_text="Text.", site_id=None):
    return NewsItem(
        id=item_id,
        created_at=created_at,
        site_name_extracted=name,
        post_text=post_text,
        site_id=site_id,
        site_match_tried=False,
        headline=f"Story {item_id}",
        summary="",
    )


@pytest.fixture
def step(monkeypatch):
    from pipeline.lyra import story_site_matcher as ssm

    state = SimpleNamespace(session=None, radar=[], built=0, read=[], exact={}, text={})

    @contextmanager
    def fake_session():
        yield state.session

    class Matcher:
        def __init__(self, _session):
            state.built += 1

        def match_item(self, item):
            state.read.append(item.id)
            reason = state.text.get(item.id)
            if reason is None:
                return None
            return SimpleNamespace(site_id=CURATED, site_name="Giza", reason=reason, via="Giza")

    monkeypatch.setattr(sm, "get_session", fake_session)
    monkeypatch.setattr(sm, "_load_source_priority", lambda s: {"ancient_nerds": 0, "wikidata": 5})
    monkeypatch.setattr(sm, "_find_site_by_name", lambda s, name, *a: state.exact.get(name))
    monkeypatch.setattr(
        sm,
        "_upsert_lyra_suggestion",
        lambda s, item, matched_site=None: state.radar.append((item.id, matched_site)),
    )
    monkeypatch.setattr(sm, "recount_mentions", lambda s: 0)
    monkeypatch.setattr(ssm, "StorySiteMatcher", Matcher)
    return state


def test_a_new_story_waits_for_its_post_text(step):
    """'match' runs before 'posts': a story without post_text stays untried, so
    the text matcher reads it with its full text the cycle after."""
    unnamed = _news(1, NEW, post_text=None)
    named = _news(2, NEW, name="Giza Plateau", post_text=None)
    step.session = _StepSession([unnamed, named])
    assert sm.match_sites_for_pending_items() == 0
    assert (unnamed.site_match_tried, named.site_match_tried) == (False, False)
    assert step.read == [] and step.radar == []

    unnamed.post_text = named.post_text = "The full text."
    step.text = {1: "headline", 2: "headline"}
    assert sm.match_sites_for_pending_items() == 2
    assert step.read == [1, 2]
    assert (unnamed.site_id, named.site_id) == (uuid.UUID(CURATED), uuid.UUID(CURATED))
    assert (unnamed.site_match_tried, named.site_match_tried) == (True, True)


def test_the_stock_is_left_to_the_reviewed_proposals(step):
    """An unnamed story before the cutoff is not read; only old items pending
    means no lexicon is loaded at all."""
    old_unnamed = _news(1, OLD)
    old_named = _news(2, OLD, name="Hawara", post_text=None)
    step.exact = {"Hawara": SimpleNamespace(id=BULK, name="Hawara", source_id="wikidata")}
    step.session = _StepSession([old_unnamed, old_named])
    assert sm.match_sites_for_pending_items() == 1
    assert step.built == 0
    assert (old_unnamed.site_id, old_unnamed.site_match_tried) == (None, False)
    assert (old_named.site_id, old_named.site_match_tried) == (BULK, True)
    assert step.radar == [(2, step.exact["Hawara"])]


def test_new_stories_take_the_text_match_and_the_radar_hears_the_named_place(step):
    unnamed = _news(1, NEW)
    by_name = _news(2, NEW, name="Great Pyramid of Giza")
    by_headline = _news(3, NEW, name="Wadi Cemetery")
    bulk = SimpleNamespace(id=BULK, name="Great Pyramid of Giza", source_id="wikidata")
    step.exact = {"Great Pyramid of Giza": bulk}
    step.text = {1: "headline", 2: "extracted_name", 3: "headline"}
    step.session = _StepSession([unnamed, by_name, by_headline])
    assert sm.match_sites_for_pending_items() == 3
    assert step.built == 1
    for item in (unnamed, by_name, by_headline):
        assert (item.site_id, item.site_match_tried) == (uuid.UUID(CURATED), True)
    # The extracted name is the curated site: no radar card. A headline match
    # puts the story at the site, the name it extracted still goes to the radar.
    assert step.radar == [(3, None)]
