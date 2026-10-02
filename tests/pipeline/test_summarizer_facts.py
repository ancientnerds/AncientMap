# SPDX-License-Identifier: AGPL-3.0-only
"""Regression: facts boundary validation in the news summarizer.

On 2026-06-09 MiniMax returned `facts` for video sNLcU9wdsvg as nested
{"item": {...}, "$text": "..."} dicts (its backend converts stray <item>
XML tags in the tool call into BadgerFish-style JSON) instead of the
array-of-strings the schema declares. summarize_video() stored the dicts
verbatim into news_items.facts, and /api/news/feed then crashed with a
Pydantic ValidationError — HTTP 500 on news.html (items 7197/7198).

summarize_video must apply the same _coerce_to_schema boundary that
structured_llm_call applies for Theo handlers, and drop topics whose
facts are unusable.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

# Shortened copy of the actual facts payload stored for news_item 7198.
NESTED_ITEM_FACTS = [
    {
        "item": {
            "item": {
                "item": (
                    "The Ethiopian Orthodox Church considers 1 Enoch "
                    "canonical scripture to this day.</item>"
                ),
                "$text": "The Epistle of Jude quotes 1 Enoch directly.</item>",
            },
            "$text": "The Qumran library contained multiple copies of 1 Enoch.</item>",
        },
        "$text": "The Book of Enoch emerged from the Second Temple period.</item>",
    }
]

GOOD_TOPIC = {
    "headline": "Good topic",
    "timestamp_range": "0:10",
    "facts": ["A real string fact.", "Another fact."],
    "primary_site": None,
}

GARBAGE_TOPIC = {
    "headline": "Garbage topic",
    "timestamp_range": "0:20",
    "facts": NESTED_ITEM_FACTS,
    "primary_site": None,
}


def test_nested_item_dicts_are_dropped_from_facts() -> None:
    from pipeline.lyra.minimax_shared import _coerce_to_schema
    from pipeline.lyra.summarizer import _FACTS_SCHEMA

    assert _coerce_to_schema(NESTED_ITEM_FACTS, _FACTS_SCHEMA) == []


def _run_summarize(monkeypatch, topics: list) -> tuple:
    from pipeline.lyra import summarizer

    monkeypatch.setattr(summarizer, "_check_relevance", lambda *a, **kw: True)
    monkeypatch.setattr(summarizer, "_calculate_topic_limit", lambda *a, **kw: 5)
    response = SimpleNamespace(text=json.dumps({"key_topics": topics}))
    monkeypatch.setattr(summarizer, "call_api", lambda *a, **kw: response)

    session = MagicMock()
    session.get.return_value = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = session
    cm.__exit__.return_value = False
    monkeypatch.setattr(summarizer, "get_session", lambda: cm)

    video = SimpleNamespace(
        id="vid123",
        title="Test video",
        description="A description",
        tags=None,
        transcript_text="0:00 some transcript text long enough to matter",
        duration_minutes=10.0,
    )
    settings = MagicMock()
    settings.anthropic_api_key = "key"

    result = summarizer.summarize_video(video, settings)
    return result, session


def test_all_garbage_topics_fails_video(monkeypatch) -> None:
    # Every topic mangled -> no usable content; the video must NOT be marked
    # summarized (returns False so the next cycle retries the stochastic LLM).
    result, session = _run_summarize(monkeypatch, [GARBAGE_TOPIC])
    assert result is False
    session.add.assert_not_called()


def test_good_topic_kept_garbage_topic_dropped(monkeypatch) -> None:
    result, session = _run_summarize(monkeypatch, [GOOD_TOPIC, GARBAGE_TOPIC])
    assert result is True
    assert session.add.call_count == 1
    item = session.add.call_args[0][0]
    assert item.facts == GOOD_TOPIC["facts"]
    assert all(isinstance(f, str) for f in item.facts)


# -- foreign script (2026-10-01) ---------------------------------------------
# The summarizer writes headline and facts, and builds the summary from them.
# Story 8351's headline carried a Serbian-Cyrillic site name through all four
# text fields; 6342/8359/5733 carried Chinese characters inside English
# sentences. A topic with foreign script is dropped like a topic without usable
# facts: logged, not published.

BLEED_HEADLINE_TOPIC = {
    "headline": (
        "Локалитет Беловоде код Петровца на Млави furnaces: earliest secure copper smelting evidence"
    ),
    "timestamp_range": "0:30",
    "facts": ["Copper slag was found in Vinča-period layers."],
    "primary_site": None,
}

BLEED_FACT_TOPIC = {
    "headline": "Fourth Mallorca talayot found",
    "timestamp_range": "0:40",
    "facts": ["Researchers科尔 Chromemer and Regillo evidence suggest an earlier date."],
    "primary_site": None,
}

BLEED_SITE_TOPIC = {
    "headline": "Copper smelting at Belovode",
    "timestamp_range": "0:50",
    "facts": ["Copper slag was found."],
    "primary_site": {"name": "Беловоде", "confidence": "high"},
}


def test_topic_with_foreign_script_in_the_headline_is_dropped(monkeypatch, caplog) -> None:
    with caplog.at_level("WARNING"):
        result, session = _run_summarize(monkeypatch, [GOOD_TOPIC, BLEED_HEADLINE_TOPIC])
    assert result is True
    assert session.add.call_count == 1
    assert session.add.call_args[0][0].facts == GOOD_TOPIC["facts"]
    assert "foreign script" in caplog.text


def test_topic_with_foreign_script_in_a_fact_is_dropped(monkeypatch) -> None:
    result, session = _run_summarize(monkeypatch, [GOOD_TOPIC, BLEED_FACT_TOPIC])
    assert result is True
    assert session.add.call_count == 1


def test_topic_with_foreign_script_in_the_site_name_is_dropped(monkeypatch) -> None:
    result, session = _run_summarize(monkeypatch, [GOOD_TOPIC, BLEED_SITE_TOPIC])
    assert result is True
    assert session.add.call_count == 1


def test_video_whose_topics_all_carry_foreign_script_stays_retryable(monkeypatch) -> None:
    # Same terminal rule as all-garbage topics: nothing usable -> False, nothing
    # added, the video is not marked summarized and the next cycle asks the
    # (stochastic) model again.
    result, session = _run_summarize(monkeypatch, [BLEED_HEADLINE_TOPIC, BLEED_FACT_TOPIC])
    assert result is False
    session.add.assert_not_called()
