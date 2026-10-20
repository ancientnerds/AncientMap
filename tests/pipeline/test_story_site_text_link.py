"""site_matcher._link_by_text: where the hourly match step lets the story-text matcher decide."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

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
