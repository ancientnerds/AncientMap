"""Phase 2: Voiceover — generates TTS audio with word-level timing via ElevenLabs.

Calls the ElevenLabs /text-to-speech/{voice_id}/with-timestamps endpoint for each
narration segment, producing MP3 files and a word_timings JSON manifest.
"""

import json
import logging
from pathlib import Path

import httpx

from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

# ElevenLabs API base
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsSettings:
    """ElevenLabs-specific settings loaded from environment."""

    def __init__(self) -> None:
        import os

        self.api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")
        self.model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")


def _characters_to_words(characters: list[dict], text: str) -> list[dict]:
    """Convert character-level timing from ElevenLabs into word-level timing.

    ElevenLabs returns:
      {"characters": ["H","e","l","l","o"," ","w","o","r","l","d"],
       "character_start_times_seconds": [0.0, 0.05, ...],
       "character_end_times_seconds": [0.05, 0.1, ...]}

    We aggregate into words split by whitespace.
    """
    char_starts = characters[0] if characters else []
    char_ends = characters[1] if len(characters) > 1 else []

    words = []
    current_word = ""
    word_start = None

    for i, char in enumerate(text):
        if char in (" ", "\n", "\t"):
            if current_word and word_start is not None:
                word_end = char_ends[i - 1] if i - 1 < len(char_ends) else word_start + 0.1
                words.append(
                    {
                        "word": current_word,
                        "start": word_start,
                        "end": word_end,
                    }
                )
            current_word = ""
            word_start = None
        else:
            if word_start is None and i < len(char_starts):
                word_start = char_starts[i]
            current_word += char

    # Last word
    if current_word and word_start is not None:
        word_end = char_ends[-1] if char_ends else word_start + 0.1
        words.append(
            {
                "word": current_word,
                "start": word_start,
                "end": word_end,
            }
        )

    return words


def generate_voiceover(
    script: dict,
    output_dir: Path,
    settings: ElevenLabsSettings | None = None,
) -> dict:
    """Generate TTS audio for each segment in the script.

    Args:
        script: Video script JSON from script_adapter.
        output_dir: Directory to write audio files and timing JSON.
        settings: ElevenLabs API configuration.

    Returns:
        Dict with "audio_files" (list of paths) and "word_timings" (per-segment timing).
    """
    if settings is None:
        settings = ElevenLabsSettings()

    if not settings.api_key:
        raise ValueError("ELEVENLABS_API_KEY not set")
    if not settings.voice_id:
        raise ValueError("ELEVENLABS_VOICE_ID not set")

    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    audio_files: list[str] = []
    all_timings: list[dict] = []

    headers = {
        "xi-api-key": settings.api_key,
        "Content-Type": "application/json",
    }

    for i, segment in enumerate(script.get("segments", [])):
        narration = segment.get("narration", "")
        if not narration.strip():
            audio_files.append("")
            all_timings.append({"segment_index": i, "words": [], "duration": 0})
            continue

        logger.info(f"Generating voiceover for segment {i} ({len(narration)} chars)")

        url = f"{ELEVENLABS_API_URL}/text-to-speech/{settings.voice_id}/with-timestamps"
        payload = {
            "text": narration,
            "model_id": settings.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.3,
            },
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Extract audio bytes (base64 encoded in response)
        import base64

        audio_b64 = data.get("audio_base64", "")
        audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""

        audio_path = audio_dir / f"segment_{i:02d}.mp3"
        audio_path.write_bytes(audio_bytes)
        audio_files.append(str(audio_path))

        # Extract character-level timing and convert to word-level
        alignment = data.get("alignment", {})
        char_starts = alignment.get("character_start_times_seconds", [])
        char_ends = alignment.get("character_end_times_seconds", [])

        word_timings = _characters_to_words([char_starts, char_ends], narration)

        duration = word_timings[-1]["end"] if word_timings else 0
        all_timings.append(
            {
                "segment_index": i,
                "words": word_timings,
                "duration": duration,
            }
        )

        logger.info(f"  Segment {i}: {duration:.1f}s audio, {len(word_timings)} words")

    # Write timing manifest
    timing_path = output_dir / "word_timings.json"
    timing_path.write_text(json.dumps(all_timings, indent=2), encoding="utf-8")

    return {
        "audio_files": audio_files,
        "word_timings": all_timings,
        "timing_path": str(timing_path),
    }
