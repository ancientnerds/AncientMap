"""Configuration for Theodore Furcade — async archaeological research agent."""

import os

THEO_MODEL = "qwen3.5:9b"
THEO_PARALLEL_SLOTS = 1
THEO_NUM_CTX = 32768  # Qwen3.5-9B supports 128K; 32K fits in 12G container
THEO_MAX_TOKENS = 8192  # Research reports need room (was 2048)

# Direct Ollama URL bypassing nginx proxy (no proxy_read_timeout limit).
# Falls back to LYRA_OLLAMA_BASE_URL (which goes through nginx) if not set.
THEO_OLLAMA_BASE_URL = os.getenv(
    "THEO_OLLAMA_BASE_URL",
    os.getenv("LYRA_OLLAMA_BASE_URL", ""),
)

EFFORT_CONFIG = {
    "quick": {"thinking": False, "max_rounds": 1},
    "deep": {"thinking": True, "max_rounds": 5},
    "full": {"thinking": True, "max_rounds": 15},
    "auto": {"thinking": True, "max_rounds": 10},
}

RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 5
