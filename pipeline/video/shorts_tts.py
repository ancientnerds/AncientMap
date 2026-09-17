"""Narrate a site's card text with MiniMax TTS.

Reuses the paper narrator's HTTP path (`call_minimax_tts`) and its AI-generated
ID3 marker; only the voice and pace differ.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline.lyra.tts_generator import call_minimax_tts, tag_mp3_ai_generated
from pipeline.video.media import probe_duration

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "English_expressive_narrator"  # user pick 2026-09-16 (paper narrator)
DEFAULT_SPEED = 0.92


def spoken_name(name: str, country: str | None) -> str:
    """Closing line the narrator speaks: "Machu Picchu, Peru." A country stored
    as "Chile, Easter Island" contributes its most specific part; a country
    already contained in the name is not repeated."""
    place = (country or "").split(",")[-1].strip()
    if not place or place.lower() in name.lower():
        return f"{name}."
    return f"{name}, {place}."


def narrate(
    text: str, out_path: Path, voice_id: str = DEFAULT_VOICE, speed: float = DEFAULT_SPEED
) -> float:
    """Synthesize `text` to `out_path` (MP3) and return its duration in seconds."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(call_minimax_tts(text, speed=speed, voice_id=voice_id))
    tag_mp3_ai_generated(out_path)
    duration = probe_duration(out_path)
    logger.info("narration %s: %.2fs (%s @ %.2f)", out_path.name, duration, voice_id, speed)
    return duration
