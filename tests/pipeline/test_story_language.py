# SPDX-License-Identifier: AGPL-3.0-only
"""Story text must not carry foreign script.

2026-10-01: the story archive held 6 of 3,489 stories with text in a script the
site does not write — a Serbian-Cyrillic site name through headline, summary,
post and facts (8351), Chinese characters inside English sentences (8359,
6342, 5733, 5797) and one story entirely in Chinese (6266). The detector for
exactly this ("language bleed", MiniMax drift) already existed for Theo papers
(theo_citations.detect_language_bleed); the story steps never called it.

The strings below are the real ones from production.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipeline.lyra.story_language import story_script_bleed

# Story 8351
CYRILLIC_HEADLINE = (
    "Локалитет Беловоде код Петровца на Млави furnaces: earliest secure copper "
    "smelting evidence worldwide, dated to 4900 BC"
)
CYRILLIC_FACT = (
    "Excavations at Локалитет Беловоде код Петровца на Млави and Pločnik led by "
    "archaeometallurgist Miljana Radivojević uncovered copper slag"
)
# Story 6342 (headline), 5733 (fact), 8359 (headline)
SWITCH_HEADLINE = "Geologists debate natural volcanic formation vs人工 structure"
SWITCH_FACT = "Researchers科尔 Chromemer and Regillo evidence suggest an earlier date"
CJK_HEADLINE = "China's 大汶口遗址公园 holds oldest elongated skulls claimed at 10,000 years old"
# Story 6266: the whole story is Chinese
CHINESE_POST = "若为伪造需使用现代五轴CNC机床研磨花岗岩，成本极高。"


class TestFlagged:
    def test_serbian_site_name_in_a_headline(self):
        assert story_script_bleed(CYRILLIC_HEADLINE)

    def test_serbian_site_name_in_a_fact(self):
        assert story_script_bleed(texts=[CYRILLIC_FACT])

    @pytest.mark.parametrize("text", [SWITCH_FACT, CHINESE_POST])
    def test_chinese_inside_prose(self, text):
        assert story_script_bleed(texts=[text])

    @pytest.mark.parametrize("headline", [SWITCH_HEADLINE, CJK_HEADLINE])
    def test_chinese_inside_a_headline(self, headline):
        assert story_script_bleed(headline)

    def test_reports_what_it_found_so_a_log_line_can_name_it(self):
        assert "Локалитет" in "".join(story_script_bleed(texts=[CYRILLIC_FACT]))

    def test_any_one_bad_text_among_clean_ones_is_enough(self):
        assert story_script_bleed("Clean headline", ["A clean fact.", CYRILLIC_FACT])


class TestClean:
    @pytest.mark.parametrize(
        "text",
        [
            "Göbekli Tepe, Pločnik and Sacsayhuamán",
            "Çatalhöyük and Kʼinich Janaabʼ Pakal",
            "Ame no Ukiishi, the floating stone of heaven",
            "Radivojević dated the slag to 4900 BC",
            "The Cyclops appear in Hesiod's Theogony (Κύκλωπες) and π ≈ 22/7, φ = 1.618",
        ],
    )
    def test_latin_diacritics_and_greek_quotes(self, text):
        assert story_script_bleed(text, [text]) == []

    def test_nothing_to_check(self):
        assert story_script_bleed() == []
        assert story_script_bleed("", [""]) == []
        assert story_script_bleed(None, []) == []

    def test_a_term_gloss_in_prose_is_scholarship_not_drift(self):
        text = 'the term "shakoki" (遮光器, "light-blocker") names the goggle-eyed figurines'
        assert story_script_bleed(texts=[text]) == []

    def test_but_a_headline_has_no_room_for_one(self):
        # A headline is English by the summary prompt; there is nothing to gloss.
        assert story_script_bleed('The "shakoki" (遮光器, "light-blocker") figurines')


# -- the three steps that write story text ------------------------------------


def _cm(session):
    cm = MagicMock()
    cm.__enter__.return_value = session
    cm.__exit__.return_value = False
    return cm


def _item(item_id, headline, **fields):
    row = {
        "id": item_id,
        "headline": headline,
        "summary": f"{headline}.",
        "facts": [],
        "post_text": None,
        "timestamp_range": None,
        "timestamp_seconds": None,
        "significance": None,
        "news_category": None,
        "verified_at": None,
        "web_sources": None,
    }
    row.update(fields)
    return SimpleNamespace(**row)


class TestPostGeneration:
    """tweet_generator: a post carrying foreign script is not attached."""

    def _run(self, monkeypatch, posts, items):
        from pipeline.lyra import tweet_generator

        q = MagicMock()
        q.filter.return_value = q
        q.count.side_effect = [len(items), 0]
        q.all.return_value = items
        session = MagicMock()
        session.query.return_value = q
        session.get.return_value = SimpleNamespace(status="summarized")
        monkeypatch.setattr(tweet_generator, "get_session", lambda: _cm(session))
        response = SimpleNamespace(text=json.dumps({"posts": posts}))
        monkeypatch.setattr(tweet_generator, "call_api", lambda *a, **kw: response)

        video = SimpleNamespace(id="vid123", summary_json={"key_topics": []}, published_at=None)
        settings = SimpleNamespace(anthropic_api_key="key", model_post="m", max_tokens=100)
        return tweet_generator.generate_posts_for_video(video, settings, system_prompt="p")

    def test_clean_post_is_attached_contaminated_one_is_not(self, monkeypatch, caplog):
        good = _item(1, "Good headline")
        bad = _item(2, "Bad headline")
        posts = [
            {"headline": "Good headline", "tweet": "A clean post.", "timestamp_range": None},
            {"headline": "Bad headline", "tweet": CYRILLIC_FACT, "timestamp_range": None},
        ]
        with caplog.at_level(logging.WARNING):
            count = self._run(monkeypatch, posts, [good, bad])

        assert count == 1
        assert good.post_text == "A clean post."
        assert bad.post_text is None, "an item without a post has no public page"
        assert "foreign script" in caplog.text
        assert "Локалитет" in caplog.text


class TestVerification:
    """tweet_verifier: a rewrite that brings foreign script in is not applied."""

    def _run(self, monkeypatch, result, item):
        from pipeline.lyra import tweet_verifier

        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [item]
        q.count.return_value = 1
        session = MagicMock()
        session.query.return_value = q
        session.get.return_value = SimpleNamespace(status="posted")
        monkeypatch.setattr(tweet_verifier, "get_session", lambda: _cm(session))
        monkeypatch.setattr(tweet_verifier, "verify_single_post", lambda *a, **kw: result)

        video = SimpleNamespace(
            id="vid123", transcript_text="0:00 text", description=None, title="T", tags=None
        )
        settings = SimpleNamespace(
            anthropic_api_key="key", model_verify="m", max_tokens=100, minimax_api_key=None
        )
        return tweet_verifier.verify_video_posts(video, settings, system_prompt="p")

    @staticmethod
    def _modify(text):
        return {
            "verification_level": "MODIFY",
            "suggested_modification": {"modified_text": text, "changes_explained": "x"},
        }

    def test_clean_modification_is_applied(self, monkeypatch):
        item = _item(1, "Headline", post_text="Original post.")
        verified = self._run(monkeypatch, self._modify("Corrected post."), item)
        assert verified == 1
        assert item.post_text == "Corrected post."
        assert item.verified_at is not None

    def test_contaminated_modification_is_not_applied_and_the_item_stays_unverified(
        self, monkeypatch, caplog
    ):
        item = _item(1, "Headline", post_text="Original post.")
        with caplog.at_level(logging.WARNING):
            verified = self._run(monkeypatch, self._modify(CYRILLIC_FACT), item)
        assert verified == 0
        assert item.post_text == "Original post."
        assert item.verified_at is None, "unverified items are retried next cycle"
        assert "foreign script" in caplog.text


class TestWebVerification:
    """tweet_verifier._web_verify_items: a web-corrected text is gated the same way."""

    def _run(self, monkeypatch, corrected_text):
        from pipeline.lyra import minimax_shared, story_web_queries, tweet_verifier

        hit = SimpleNamespace(url="https://example.org/a", title="t", snippet="s")
        monkeypatch.setattr(minimax_shared, "create_minimax_client", lambda *a, **kw: object())
        monkeypatch.setattr(minimax_shared, "minimax_search", lambda *a, **kw: [hit])
        monkeypatch.setattr(
            minimax_shared,
            "minimax_chat",
            lambda *a, **kw: json.dumps({"verdict": "CORRECTED", "corrected_text": corrected_text}),
        )
        monkeypatch.setattr(story_web_queries, "generate_queries_for_item", lambda *a, **kw: ["q"])

        item = _item(1, "Headline", post_text="Original post.", significance=7)
        settings = SimpleNamespace(
            story_web_verify_min_significance=5, minimax_api_key="k", minimax_base_url="u"
        )
        tweet_verifier._web_verify_items([item], settings)
        return item

    def test_clean_correction_is_applied(self, monkeypatch):
        assert self._run(monkeypatch, "Corrected post.").post_text == "Corrected post."

    def test_contaminated_correction_is_not_applied(self, monkeypatch, caplog):
        with caplog.at_level(logging.WARNING):
            item = self._run(monkeypatch, CYRILLIC_FACT)
        assert item.post_text == "Original post."
        assert "foreign script" in caplog.text
