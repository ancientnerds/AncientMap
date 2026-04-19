"""MiniMax TTS audio generation for Theo research papers.

Generates narrated MP3 audio for published research papers using MiniMax
speech-2.8-hd + English_expressive_narrator. Paragraphs are synthesized
individually with 2-second pauses, citation markers and references are
stripped, and generation stops when the daily token budget is low.

Usage:
    from pipeline.lyra.tts_generator import generate_paper_audio
    url = generate_paper_audio(paper_id, settings)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path

import httpx

from pipeline.database import TtsRequest, get_session

logger = logging.getLogger(__name__)

MINIMAX_BASE_URL = "https://api.minimax.io"
MINIMAX_REMAINS_PATH = "/v1/api/openplatform/coding_plan/remains"
MINIMAX_TTS_PATH = "/v1/t2a_v2"

# Voice and model
VOICE_ID = "English_expressive_narrator"
MODEL = "speech-2.8-hd"
PARAGRAPH_PAUSE = "<#2#>"  # 2-second pause between paragraphs
BUDGET_SAFETY_BUFFER = 2000  # stop when ~2000 chars remain in daily budget
MIN_CHARS_FOR_PARAGRAPH = 100  # skip very short fragments

# Audio output directory (served by Nginx at /data/audio/)
AUDIO_DIR = Path(__file__).parent.parent.parent / "public" / "data" / "audio"


# ---------------------------------------------------------------------------
# Token quota
# ---------------------------------------------------------------------------


def check_speech_quota() -> int:
    """Return remaining speech-hd characters for today, or -1 on error."""
    api_key = os.getenv("LYRA_MINIMAX_API_KEY", "")
    if not api_key:
        logger.warning("[TTS] No API key for speech quota check")
        return -1

    try:
        client = httpx.Client(timeout=10.0)
        resp = client.get(
            f"{MINIMAX_BASE_URL}{MINIMAX_REMAINS_PATH}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        client.close()
        if resp.status_code != 200:
            logger.warning("[TTS] Speech quota check failed: %s", resp.status_code)
            return -1
        data = resp.json()
        for item in data.get("model_remains", []):
            if item.get("model_name") == "speech-hd":
                used = item.get("current_interval_usage_count", 0)
                total = item.get("current_interval_total_count", 11000)
                remaining = max(0, total - used)
                logger.info(
                    "[TTS] Speech quota: %d / %d used, %d remaining",
                    used,
                    total,
                    remaining,
                )
                return remaining
        logger.warning("[TTS] speech-hd not found in quota response")
        return -1
    except Exception as exc:
        logger.warning("[TTS] Speech quota check error: %s", exc)
        return -1


# ---------------------------------------------------------------------------
# Text preprocessing
# ---------------------------------------------------------------------------


def strip_citations(text: str) -> str:
    """Remove citation markers, references section, and tier labels from paper text."""
    # Remove all [N] inline citation markers
    text = re.sub(r"\[\d+\]", "", text)
    # Remove [Academic] / [Reputable] tier labels
    text = re.sub(r"\[(?:Academic|Reputable)\]", "", text)
    # Remove references section and everything after
    text = re.sub(
        r"\n#{1,3}\s+References?\s*\n.*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Collapse excess whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------


def call_minimax_tts(text: str, speed: float = 1.0) -> bytes:
    """Synthesize a single text chunk via MiniMax TTS. Returns raw MP3 bytes."""
    api_key = os.getenv("LYRA_MINIMAX_API_KEY", "")
    if not api_key:
        raise RuntimeError("LYRA_MINIMAX_API_KEY not set")

    client = httpx.Client(
        base_url=MINIMAX_BASE_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60.0,
    )
    try:
        resp = client.post(
            MINIMAX_TTS_PATH,
            json={
                "model": MODEL,
                "text": text,
                "stream": False,
                "output_format": "hex",
                "language_boost": "English",
                "voice_setting": {
                    "voice_id": VOICE_ID,
                    "speed": speed,
                    "vol": 1.0,
                    "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 32000,
                    "bitrate": 128000,
                    "format": "mp3",
                    "channel": 1,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        base = data.get("base_resp", {})
        if base.get("status_code", -1) != 0:
            raise RuntimeError(f"TTS error {base.get('status_code')}: {base.get('status_msg')}")
        hex_audio = data.get("data", {}).get("audio", "")
        return bytes.fromhex(hex_audio)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# MP3 concatenation
# ---------------------------------------------------------------------------


def concatenate_mp3s(chunks: list[bytes]) -> bytes:
    """Concatenate multiple raw MP3 byte strings into a single MP3.

    Uses the ID3v2/MP3 frame concatenation approach — prepends all frames
    from subsequent chunks after the first frame of the first chunk.
    This is sufficient for concatenated speech where a small artifact at
    the boundary is imperceptible.
    """
    if len(chunks) == 1:
        return chunks[0]

    result = bytearray()

    for i, chunk in enumerate(chunks):
        if i == 0:
            result.extend(chunks[i])
        else:
            # Skip ID3v2 header if present at start of non-first chunks
            start = 0
            if chunk[:3] == b"ID3":
                # Find the size bytes in the ID3 header (bytes 4-6, syncsafe)
                size_bytes = chunk[6:10]
                id3_size = (
                    (size_bytes[0] << 21)
                    | (size_bytes[1] << 14)
                    | (size_bytes[2] << 7)
                    | size_bytes[3]
                )
                start = 10 + id3_size
            # Also skip any leading MP3 frames that are just silence (< 500 bytes of near-zero)
            # to avoid a "click" at concatenation boundaries
            result.extend(chunk[start:])

    return bytes(result)


# ---------------------------------------------------------------------------
# Paper audio generation
# ---------------------------------------------------------------------------


def generate_paper_audio(tts_request_id: str, settings) -> tuple[str, int]:
    """Generate narrated MP3 for a research paper.

    Loads the paper from DB, strips citations, synthesizes paragraph by
    paragraph (with 2-second pauses), and saves the result.

    Returns (audio_url, chars_generated). Raises on unrecoverable error.
    Returns ("", 0) if quota is exhausted.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    with get_session() as session:
        tts_req = session.query(TtsRequest).filter(TtsRequest.id == tts_request_id).first()
        if not tts_req:
            raise ValueError(f"TtsRequest {tts_request_id} not found")

        from pipeline.database import ResearchRequest

        paper = (
            session.query(ResearchRequest).filter(ResearchRequest.id == tts_req.paper_id).first()
        )
        if not paper:
            raise ValueError(f"Paper {tts_req.paper_id} not found")

        if not paper.result_json:
            raise ValueError(f"Paper {tts_req.paper_id} has no result_json")

        import json

        result = json.loads(paper.result_json)
        report = result.get("report", "")
        if not report:
            raise ValueError(f"Paper {tts_req.paper_id} has no report text")

        # Mark as generating
        tts_req.status = "generating"
        session.commit()

    # Strip citations and references
    clean_text = strip_citations(report)

    # Split into paragraphs (split on double newlines, keep non-empty)
    paragraphs = [
        p.strip()
        for p in clean_text.split("\n\n")
        if p.strip() and len(p.strip()) >= MIN_CHARS_FOR_PARAGRAPH
    ]

    if not paragraphs:
        raise ValueError(f"Paper {tts_req.paper_id} has no usable paragraphs after cleaning")

    logger.info(
        "[TTS] Generating audio for paper %s (%s): %d paragraphs",
        tts_req.paper_id,
        paper.slug or paper.id,
        len(paragraphs),
    )

    audio_chunks: list[bytes] = []
    total_chars = 0

    for i, para in enumerate(paragraphs):
        quota = check_speech_quota()
        if quota < 0:
            logger.warning("[TTS] Quota check failed, attempting anyway")
        elif quota < 500:
            logger.info("[TTS] Quota too low (%d chars), stopping", quota)
            break

        # Check if adding this paragraph would exceed budget
        if quota > 0 and total_chars + len(para) > quota - BUDGET_SAFETY_BUFFER:
            logger.info(
                "[TTS] Would exceed budget (%d + %d > %d - %d), stopping",
                total_chars,
                len(para),
                quota,
                BUDGET_SAFETY_BUFFER,
            )
            break

        para_with_pause = f"{para}{PARAGRAPH_PAUSE}"
        try:
            chunk_bytes = call_minimax_tts(para_with_pause)
            audio_chunks.append(chunk_bytes)
            total_chars += len(para)
            logger.info(
                "[TTS] Paragraph %d/%d done: %d chars, %d bytes",
                i + 1,
                len(paragraphs),
                len(para),
                len(chunk_bytes),
            )
        except Exception as exc:
            logger.warning("[TTS] Paragraph %d failed: %s — stopping generation", i + 1, exc)
            break

        # Small delay to avoid hammering the API
        time.sleep(0.5)

    if not audio_chunks:
        logger.warning("[TTS] No audio chunks generated for paper %s", tts_req.paper_id)
        return "", 0

    # Concatenate all chunks
    full_audio = concatenate_mp3s(audio_chunks)

    # Save to disk
    safe_id = str(tts_req.id)
    out_path = AUDIO_DIR / f"{safe_id}.mp3"
    out_path.write_bytes(full_audio)
    relative_url = f"/data/audio/{safe_id}.mp3"

    logger.info(
        "[TTS] Saved audio for paper %s: %d total chars, %d bytes → %s",
        tts_req.paper_id,
        total_chars,
        len(full_audio),
        relative_url,
    )

    # Update DB
    with get_session() as session:
        tts_row = session.query(TtsRequest).filter(TtsRequest.id == tts_request_id).first()
        if tts_row:
            tts_row.status = "done"
            tts_row.audio_url = relative_url
            tts_row.chars_generated = total_chars
            session.commit()

    return relative_url, total_chars


# ---------------------------------------------------------------------------
# Orchestrator step
# ---------------------------------------------------------------------------


def process_pending_tts(settings) -> int:
    """Orchestrator step: process the FIFO TTS queue.

    Picks the oldest pending/no_quota TtsRequest, generates audio for it,
    and updates the status. Respects daily token budget.

    Returns the number of requests processed.
    """
    with get_session() as session:
        # Pick oldest request
        tts_req = (
            session.query(TtsRequest)
            .filter(TtsRequest.status.in_(["pending", "no_quota"]))
            .order_by(TtsRequest.requested_at.asc())
            .first()
        )
        if not tts_req:
            logger.debug("[TTS] No pending requests in queue")
            return 0

    logger.info(
        "[TTS] Processing TtsRequest %s (paper=%s, user=%s, status=%s, queued_at=%s)",
        tts_req.id,
        tts_req.paper_id,
        tts_req.user_id,
        tts_req.status,
        tts_req.requested_at,
    )

    try:
        url, chars = generate_paper_audio(str(tts_req.id), settings)
        if not url:
            # Quota exhausted — re-queue
            with get_session() as session:
                row = session.query(TtsRequest).filter(TtsRequest.id == tts_req.id).first()
                if row:
                    row.status = "no_quota"
                    row.error_message = "Quota exhausted, will retry next cycle"
                    session.commit()
            logger.info("[TTS] Quota exhausted for %s, set to no_quota", tts_req.id)
        else:
            logger.info(
                "[TTS] Successfully generated audio for %s: %s (%d chars)", tts_req.id, url, chars
            )
        return 1

    except Exception as exc:
        logger.warning("[TTS] Failed to generate audio for %s: %s", tts_req.id, exc)
        with get_session() as session:
            row = session.query(TtsRequest).filter(TtsRequest.id == tts_req.id).first()
            if row:
                row.status = "failed"
                row.error_message = str(exc)[:500]
                session.commit()
        return 0
