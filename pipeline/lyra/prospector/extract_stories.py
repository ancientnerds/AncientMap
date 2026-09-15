"""Stage 1b: named places in stories (news items) — the durable pump.

Stories arrive at ~90 a week (papers: none since August), so this is what
the weekly run actually reads. Six items go into one window separated by
blank lines; the same grounding as papers runs over the window, and each
grounded mention is mapped back to ITS item's reconstructed text so the
stored offsets index that text alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.prospector.corpus import StoryUnit
from pipeline.lyra.prospector.extract_papers import (
    ABORT_REJECT_RATE,
    MAX_OUTPUT_TOKENS,
    THINKING_OFF,
    Budget,
)
from pipeline.lyra.prospector.mentions import (
    MENTION_SCHEMA,
    GroundingStats,
    Mention,
    ground_mentions,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "prospector_mentions.txt"
EXTRACTOR_TAG = "prospector_stories_v1"
ITEMS_PER_CALL = 6
MAX_WINDOW_CHARS = 9000
SEPARATOR = "\n\n"


@dataclass
class StoryExtraction:
    mentions: list[tuple[StoryUnit, Mention]]
    stats: GroundingStats = field(default_factory=GroundingStats)
    calls: int = 0


def batches(units: list[StoryUnit]) -> list[list[StoryUnit]]:
    out: list[list[StoryUnit]] = []
    cur: list[StoryUnit] = []
    size = 0
    for u in units:
        if cur and (len(cur) >= ITEMS_PER_CALL or size + len(u.text) > MAX_WINDOW_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += len(u.text) + len(SEPARATOR)
    if cur:
        out.append(cur)
    return out


def remap_to_units(
    window_mentions: list[Mention], units: list[StoryUnit], starts: list[int]
) -> list[tuple[StoryUnit, Mention]]:
    """Window offsets -> per-unit offsets. A mention belongs to the unit whose
    span contains its start; the quote never crosses a blank line, so it is
    inside that unit by construction."""
    out: list[tuple[StoryUnit, Mention]] = []
    for m in window_mentions:
        for unit, start in zip(units, starts, strict=True):
            if start <= m.char_start < start + len(unit.text):
                out.append(
                    (
                        unit,
                        Mention(
                            name=m.name,
                            place_class=m.place_class,
                            char_start=m.char_start - start,
                            char_end=m.char_end - start,
                            quote=m.quote,
                            quote_start=m.quote_start - start,
                            footnotes=[],
                            country_in_text=m.country_in_text,
                            period_phrase=m.period_phrase,
                        ),
                    )
                )
                break
    return out


def extract_stories(
    units: list[StoryUnit], *, budget: Budget, temperature: float
) -> StoryExtraction:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    stats = GroundingStats()
    result: list[tuple[StoryUnit, Mention]] = []
    calls = 0
    for batch in batches(units):
        budget.check()
        starts: list[int] = []
        pos = 0
        for u in batch:
            starts.append(pos)
            pos += len(u.text) + len(SEPARATOR)
        window = SEPARATOR.join(u.text for u in batch)
        usage: dict = {}
        parsed = structured_llm_call(
            system,
            window,
            MENTION_SCHEMA,
            MAX_OUTPUT_TOKENS,
            temperature=temperature,
            thinking=THINKING_OFF,
            usage=usage,
        )
        budget.charge(usage)
        calls += 1
        raw = parsed.get("mentions") if isinstance(parsed, dict) else None
        grounded = ground_mentions(raw or [], window, 0, window, stats)
        result.extend(remap_to_units(grounded, batch, starts))

    if stats.emitted and stats.reject_rate > ABORT_REJECT_RATE:
        raise RuntimeError(
            f"[stories] grounding reject rate {stats.reject_rate:.0%} "
            f"({stats.rejected}/{stats.emitted}) exceeds {ABORT_REJECT_RATE:.0%} — aborting"
        )
    logger.info(
        "[PROSPECTOR] stories: %d items, %d calls, %d emitted, %d grounded, %d rejected",
        len(units),
        calls,
        stats.emitted,
        len(result),
        stats.rejected,
    )
    return StoryExtraction(result, stats, calls)
