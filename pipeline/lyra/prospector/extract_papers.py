"""Stage 1a: named places in published research papers, grounded.

One MiniMax M3 call per ~8,000-char window with thinking DISABLED (the
shared helper would otherwise default to adaptive reasoning, ~7x the visible
tokens). Every string the model returns is located in the window by the code
before it becomes a mention; see pipeline.lyra.prospector.mentions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.prospector.corpus import PaperUnit, harvest_wiki_urls, mask_paper, windows
from pipeline.lyra.prospector.mentions import (
    MENTION_SCHEMA,
    GroundingStats,
    Mention,
    ground_mentions,
)
from pipeline.lyra.prospector.wiki import enwiki_title_from_url

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "prospector_mentions.txt"
THINKING_OFF = {"type": "disabled"}
MAX_OUTPUT_TOKENS = 3000
# Above this share of ungroundable strings the model (or the prompt) has
# drifted; ship nothing rather than degraded cards.
ABORT_REJECT_RATE = 0.15

EXTRACTOR_TAG = "prospector_mentions_v1"


class BudgetExhausted(RuntimeError):
    """The run's token or call budget is spent; commit what exists and stop."""


@dataclass
class Budget:
    """Hard stops, as code. Decremented from real response usage."""

    max_tokens: int
    max_calls: int
    tokens_used: int = 0
    calls: int = 0

    def charge(self, usage: dict) -> None:
        self.calls += 1
        self.tokens_used += sum(int(v or 0) for v in usage.values())

    def check(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExhausted(f"call cap reached ({self.max_calls})")
        if self.tokens_used >= self.max_tokens:
            raise BudgetExhausted(f"token budget spent ({self.tokens_used}/{self.max_tokens})")


@dataclass
class PaperExtraction:
    unit: PaperUnit
    mentions: list[Mention]
    cited_titles: list[str]  # enwiki titles from the reference list, free hard keys
    stats: GroundingStats = field(default_factory=GroundingStats)
    windows: int = 0


def extract_paper(unit: PaperUnit, *, budget: Budget, temperature: float) -> PaperExtraction:
    """Extract grounded mentions from one paper.

    Raises BudgetExhausted mid-paper; the caller commits nothing for a paper
    it did not finish (evidence must be complete per unit or absent).
    Raises RuntimeError when the grounding reject rate exceeds the abort
    threshold — that is a drift alarm, not a data condition.
    """
    masked, refs = mask_paper(unit.text)
    cited = [t for t in (enwiki_title_from_url(u) for u in harvest_wiki_urls(refs)) if t]
    system = PROMPT_PATH.read_text(encoding="utf-8")
    stats = GroundingStats()
    mentions: list[Mention] = []
    wins = windows(masked)

    for w in wins:
        budget.check()
        usage: dict = {}
        parsed = structured_llm_call(
            system,
            w.text,
            MENTION_SCHEMA,
            MAX_OUTPUT_TOKENS,
            temperature=temperature,
            thinking=THINKING_OFF,
            usage=usage,
        )
        budget.charge(usage)
        raw = parsed.get("mentions") if isinstance(parsed, dict) else None
        mentions.extend(ground_mentions(raw or [], w.text, w.abs_start, unit.text, stats))

    if stats.emitted and stats.reject_rate > ABORT_REJECT_RATE:
        raise RuntimeError(
            f"[{unit.slug}] grounding reject rate {stats.reject_rate:.0%} "
            f"({stats.rejected}/{stats.emitted}) exceeds {ABORT_REJECT_RATE:.0%} — aborting"
        )
    logger.info(
        "[PROSPECTOR] %s: %d windows, %d emitted, %d grounded, %d rejected, %d cited titles",
        unit.slug,
        len(wins),
        stats.emitted,
        len(mentions),
        stats.rejected,
        len(cited),
    )
    return PaperExtraction(unit, mentions, cited, stats, len(wins))
