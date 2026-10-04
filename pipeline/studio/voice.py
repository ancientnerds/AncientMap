"""`episode voice`: narrate every beat and time every display word (spec 4.4).

- MiniMax quota first (`quota_percentages`, the 'general' plan Theo shares): refuse below
  MIN_INTERVAL_PCT of the 5-hour window. Probed only when a beat actually needs narration.
- Each beat is narrated with shorts_tts.narrate (MiniMax speech-2.8-hd, AI-generated ID3
  marker) at the script's voice and speed; a beat over MAX_CHUNK_CHARS is split at sentence
  boundaries, narrated per chunk, concatenated with ffmpeg and re-marked.
- Word timings: shorts_captions.transcribe_words (faster-whisper on the NVIDIA, CUDA device
  0, float16: spec 4.11; the site Shorts keep their CPU default) aligned to the beat's DISPLAY
  tokens with align_words, so captions and SRT carry the script's spelling.
- voice/manifest.json keys every beat by the sha256 of its spoken and display text, voice and
  speed; an unchanged beat is never narrated (or paid for) twice, and `stale_beats` tells the
  timeline which mp3s no longer match the script.
Output voice/words.json: {beat_id: {duration_s, words: [{w, s, e}]}}.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipeline.lyra.text_sentences import split_sentences
from pipeline.studio.episode import (
    EpisodeWorkspace,
    load_voice_manifest,
    voice_key,
    voiced_for,
)
from pipeline.studio.errors import StudioError
from pipeline.utils.card_provenance import text_sha256

MIN_INTERVAL_PCT = 10
MAX_CHUNK_CHARS = 1000

Quota = Callable[[], tuple[int, int]]
Synth = Callable[[str, Path, str, float], float]
Transcribe = Callable[[Path], list[tuple[str, float, float]]]


def chunk_text(text: str) -> list[str]:
    """Sentences packed greedily into chunks of at most MAX_CHUNK_CHARS."""
    chunks: list[str] = []
    current = ""
    for sentence in (s.strip() for s in split_sentences(text)):
        if not sentence:
            continue
        if len(sentence) > MAX_CHUNK_CHARS:
            raise StudioError(
                f"a sentence of {len(sentence)} chars exceeds {MAX_CHUNK_CHARS}: split it"
            )
        joined = f"{current} {sentence}".strip()
        if len(joined) > MAX_CHUNK_CHARS:
            chunks.append(current)
            current = sentence
        else:
            current = joined
    if current:
        chunks.append(current)
    return chunks


def check_quota(interval_pct: int, weekly_pct: int) -> None:
    if interval_pct < MIN_INTERVAL_PCT:
        raise StudioError(
            f"MiniMax 5-hour window at {interval_pct}% (weekly {weekly_pct}%), below "
            f"{MIN_INTERVAL_PCT}%: Theo's research shares the plan; wait for the window to refill"
        )


def minimax_quota() -> tuple[int, int]:
    from pipeline.video.__main__ import quota_percentages

    return quota_percentages()


def synthesize(text: str, out: Path, voice_id: str, speed: float) -> float:
    from pipeline.lyra.tts_generator import tag_mp3_ai_generated
    from pipeline.video.media import probe_duration, run_ffmpeg
    from pipeline.video.shorts_tts import narrate

    chunks = chunk_text(text)
    if len(chunks) == 1:
        return narrate(chunks[0], out, voice_id=voice_id, speed=speed)
    parts = []
    for i, chunk in enumerate(chunks):
        part = out.with_name(f"{out.stem}.part{i}.mp3")
        narrate(chunk, part, voice_id=voice_id, speed=speed)
        parts.append(part)
    listing = out.with_name(f"{out.stem}.concat.txt")
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "libmp3lame", "-b:a", "128k"],
        out,
    )
    tag_mp3_ai_generated(out)
    for p in [*parts, listing]:
        p.unlink()
    return probe_duration(out)


def whisper_words(audio: Path) -> list[tuple[str, float, float]]:
    from pipeline.video.shorts_captions import transcribe_words

    return transcribe_words(audio, device="cuda", device_index=0, compute_type="float16")


def stale_beats(ws: EpisodeWorkspace, script: dict[str, Any]) -> list[str]:
    """Beats whose voice/<beat>.mp3 was not narrated from the current spoken text, voice
    and speed (voice/manifest.json); [] when every mp3 belongs to the script."""
    if not ws.voice_manifest.exists():
        return ["voice/manifest.json does not exist: run `episode voice`"]
    manifest = load_voice_manifest(ws)
    voice_id, speed = script["voice"]["id"], float(script["voice"]["speed"])
    stale = []
    for beat in script["beats"]:
        if not voiced_for(manifest, beat, voice_id, speed):
            stale.append(f"{beat['id']}: voice/{beat['id']}.mp3 is stale; run `episode voice`")
        elif not (ws.voice_dir / f"{beat['id']}.mp3").exists():
            stale.append(f"{beat['id']}: voice/{beat['id']}.mp3 is missing; run `episode voice`")
    return stale


def voice_episode(
    ws: EpisodeWorkspace,
    script: dict[str, Any],
    *,
    quota: Quota = minimax_quota,
    synth: Synth = synthesize,
    transcribe: Transcribe = whisper_words,
) -> dict[str, Any]:
    from pipeline.video.shorts_captions import align_words

    ws.voice_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_voice_manifest(ws)
    voice_id, speed = script["voice"]["id"], float(script["voice"]["speed"])

    def needs_audio(beat: dict[str, Any]) -> bool:
        audio = ws.voice_dir / f"{beat['id']}.mp3"
        return not audio.exists() or not voiced_for(manifest, beat, voice_id, speed)

    def save() -> None:
        ws.voice_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    todo = [b for b in script["beats"] if needs_audio(b)]
    if todo:
        check_quota(*quota())
    for beat in script["beats"]:
        bid = beat["id"]
        audio = ws.voice_dir / f"{bid}.mp3"
        if beat in todo:
            duration = synth(beat["spoken"], audio, voice_id, speed)
            manifest[bid] = {
                **voice_key(beat, voice_id, speed),
                "duration_s": round(duration, 3),
                "display_sha256": None,
            }
            # Saved before whisper runs: a failed transcription never pays for this again.
            save()
        entry = manifest[bid]
        if entry["display_sha256"] != text_sha256(beat["display"]):
            try:
                aligned = align_words(beat["display"].split(), transcribe(audio))
            except ValueError as exc:  # align_words: whisper recognised no word
                raise StudioError(
                    f"{bid}: the display words cannot be timed against voice/{bid}.mp3: {exc}"
                ) from exc
            entry["words"] = [{"w": w.text, "s": w.start, "e": w.end} for w in aligned]
            entry["display_sha256"] = text_sha256(beat["display"])
            save()
    beat_ids = {b["id"] for b in script["beats"]}
    for stale in ws.voice_dir.glob("*.mp3"):
        if stale.stem not in beat_ids:
            stale.unlink()
    words = {
        b["id"]: {
            "duration_s": manifest[b["id"]]["duration_s"],
            "words": manifest[b["id"]]["words"],
        }
        for b in script["beats"]
    }
    ws.words.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
    return words
