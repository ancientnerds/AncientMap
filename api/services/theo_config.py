"""Configuration for Theodore Furcade — async archaeological research agent."""

from __future__ import annotations

import os
from dataclasses import dataclass

THEO_PARALLEL_SLOTS = 1

# Discord role ID that grants access to Theo Research Lab.
# Set THEO_RESEARCHER_ROLE_ID in .env to the role ID.
# If left empty, the researcher gate is disabled (403 for all users).
THEO_RESEARCHER_ROLE_ID = os.getenv("THEO_RESEARCHER_ROLE_ID", "")
RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 1

# M2.7 token budget per individual call (not total).
# M2.7 reasoning consumes ~2-6K tokens from this budget before output starts.
# 16384 leaves ~10-14K for actual JSON/text output after reasoning.
THEO_MAX_TOKENS = 16384
THEO_MAX_TOKENS_SYNTHESIS = 16384


@dataclass(frozen=True)
class TierConfig:
    """Per-tier pipeline configuration."""

    academic_format: str  # human-readable academic format name
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
    source_apis: str  # which API group: "minimal", "standard", "full", "exhaustive"


EFFORT_CONFIG: dict[str, TierConfig] = {
    "brief": TierConfig(
        academic_format="Research Brief",
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
        source_apis="minimal",
    ),
    "note": TierConfig(
        academic_format="Research Note",
        specialists_count=3,
        max_search_queries=8,
        convergence_stage1=1,
        convergence_stage3=True,
        convergence_stage5=1,
        debate_rounds=0,  # skipped
        devils_advocate=True,  # simplified devil's advocate
        simplified_moderator=True,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
        source_apis="standard",
    ),
    "article": TierConfig(
        academic_format="Journal Article",
        specialists_count=5,
        max_search_queries=12,
        convergence_stage1=2,
        convergence_stage3=True,
        convergence_stage5=1,
        debate_rounds=0,  # skipped
        devils_advocate=True,  # simplified devil's advocate
        simplified_moderator=True,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
        source_apis="standard",
    ),
    "review": TierConfig(
        academic_format="Literature Review",
        specialists_count=6,
        max_search_queries=15,
        convergence_stage1=2,
        convergence_stage3=True,
        convergence_stage5=1,  # 1 is safe within timeout
        debate_rounds=1,
        devils_advocate=True,
        simplified_moderator=False,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
        source_apis="full",
    ),
    "thesis": TierConfig(
        academic_format="Thesis Chapter",
        specialists_count=8,
        max_search_queries=20,
        convergence_stage1=3,
        convergence_stage3=True,
        convergence_stage5=1,  # 2 iterations + reasoning = timeout risk; 1 is safe
        debate_rounds=2,
        devils_advocate=True,
        simplified_moderator=False,
        max_tokens_per_call=THEO_MAX_TOKENS,
        max_tokens_synthesis=THEO_MAX_TOKENS_SYNTHESIS,
        source_apis="exhaustive",
    ),
}
