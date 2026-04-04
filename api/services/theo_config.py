"""Configuration for Theodore Furcade — async archaeological research agent."""

from __future__ import annotations

from dataclasses import dataclass

THEO_PARALLEL_SLOTS = 1
RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 5

# M2.7 token budget per individual call (not total)
THEO_MAX_TOKENS = 8192
THEO_MAX_TOKENS_SYNTHESIS = 16384  # synthesis + debate need more room


@dataclass(frozen=True)
class TierConfig:
    """Per-tier pipeline configuration."""

    specialists_count: int  # how many specialists to select
    max_search_queries: int  # Stage 2 query limit
    convergence_stage1: int  # max critic iterations in question analysis
    convergence_stage3: bool  # whether source audit retries
    convergence_stage5: int  # max critic iterations in synthesis
    debate_rounds: int  # 0 = skip debate entirely
    devils_advocate: bool  # whether Stage 7 runs devil's advocate
    simplified_moderator: bool  # True = single moderator call, False = full
    max_tokens_per_call: int  # M2.7 max_tokens for most calls
    max_tokens_synthesis: int  # M2.7 max_tokens for synthesis/debate


EFFORT_CONFIG: dict[str, TierConfig] = {
    "brief": TierConfig(
        specialists_count=1,
        max_search_queries=5,
        convergence_stage1=0,  # single-shot
        convergence_stage3=False,
        convergence_stage5=0,  # skipped
        debate_rounds=0,  # skipped
        devils_advocate=False,
        simplified_moderator=False,  # skipped entirely
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS,
    ),
    "paper": TierConfig(
        specialists_count=4,
        max_search_queries=10,
        convergence_stage1=2,
        convergence_stage3=True,
        convergence_stage5=1,
        debate_rounds=0,  # skipped
        devils_advocate=True,  # simplified devil's advocate
        simplified_moderator=True,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
    ),
    "thesis": TierConfig(
        specialists_count=6,
        max_search_queries=15,
        convergence_stage1=3,
        convergence_stage3=True,
        convergence_stage5=2,
        debate_rounds=2,
        devils_advocate=True,
        simplified_moderator=False,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
    ),
    "auto": TierConfig(
        specialists_count=4,
        max_search_queries=10,
        convergence_stage1=2,
        convergence_stage3=True,
        convergence_stage5=1,
        debate_rounds=0,
        devils_advocate=True,
        simplified_moderator=True,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
    ),
}
