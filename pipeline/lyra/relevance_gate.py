"""Relevancy gate for Theo research requests.

A fast M3 classification that rejects questions unrelated to the ancient
or historical world. Called standalone by the /theo/check-relevance route
before a user spends credits on a full research run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from pipeline.lyra.config import thinking_for_effort
from pipeline.lyra.minimax_shared import MiniMaxTerminalError, minimax_chat_anthropic

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a relevancy filter for an archaeological research platform. "
    "Decide whether the user's question is related to ANY of these topics:\n"
    "- Archaeology, excavations, archaeological sites\n"
    "- Ancient history, prehistory, historical civilizations\n"
    "- Mythology, ancient religions, ancient texts\n"
    "- Geology and earth sciences related to human history\n"
    "- Anthropology, ancient cultures, migration\n"
    "- Paleontology, human evolution\n"
    "- Ancient technology, architecture, engineering\n"
    "- Heritage, conservation, museums\n"
    "- Numismatics, epigraphy, ancient languages\n"
    "- Alternative/fringe theories about ancient history "
    "(Ancient Astronauts, lost civilizations, Atlantis, Nibiru, etc.)\n\n"
    "Be VERY inclusive — if there is ANY plausible connection to the "
    "ancient or historical world, it is relevant. Only reject questions "
    "that have absolutely nothing to do with history or archaeology.\n\n"
    'Output ONLY: {"relevant": true} or {"relevant": false, "reason": "brief explanation"}'
)


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        result = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Relevancy gate: failed to parse JSON: %s", cleaned[:200])
        return {}
    return result if isinstance(result, dict) else {}


async def check_relevance(question: str) -> str | None:
    """Return None if the question is on-topic, or a rejection message if not."""
    # A binary relevance check needs almost no reasoning — cap M3 thinking to a
    # small budget so it can't eat the tiny output budget (the old failure mode).
    try:
        raw = await asyncio.to_thread(
            minimax_chat_anthropic,
            _SYSTEM_PROMPT,
            question,
            256,
            thinking=thinking_for_effort("instant"),
        )
    except MiniMaxTerminalError as exc:
        # EXPLICIT fail-open, same policy as the unparseable-verdict branch
        # below: a dead classifier backend must not 500 the public
        # check-relevance endpoint or block a user's request — but it must
        # be visible (fail-loud conversion P2-10, 2026-08-06).
        logger.warning("[relevance_gate] classifier backend down — failing OPEN: %s", exc)
        return None
    # Strip any residual <think> tags the SDK path may have missed
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    parsed = _parse_json(raw)

    if not parsed:
        # EXPLICIT fail-open: an unparseable classifier verdict must not
        # block a user's request, but it has to be visible — a silently
        # permissive gate looks identical to a working one in the logs.
        logger.warning(
            "[relevance_gate] unparseable LLM output — failing OPEN "
            "(treating question as relevant). raw=%r",
            raw[:200],
        )
        return None

    if parsed.get("relevant", True):
        return None

    reason = parsed.get("reason", "Question is not related to archaeology or ancient history")
    logger.info("[relevance_gate] rejected: %s — %s", question[:80], reason)
    return (
        f"This question doesn't appear to be related to archaeology, "
        f"ancient history, or the ancient world. {reason}"
    )
