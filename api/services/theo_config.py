"""Configuration for Theodore Furcade — async archaeological research agent.

NOTE: Backend not yet configured. Phase 2 will wire MiniMax M2.7.
"""

THEO_PARALLEL_SLOTS = 1
THEO_MAX_TOKENS = 12288

EFFORT_CONFIG = {
    "quick": {"thinking": False, "max_rounds": 1},
    "deep": {"thinking": True, "max_rounds": 5},
    "full": {"thinking": True, "max_rounds": 15},
    "auto": {"thinking": True, "max_rounds": 10},
}

RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 5
