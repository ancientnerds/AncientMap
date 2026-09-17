"""Word-level captions for a short: one word on screen at a time, timed to the voice.

MiniMax's TTS only reports sentence spans, so the words are timed by running
faster-whisper (word timestamps) over the narration and mapping what it heard
onto the card text we know. Recognised words are matched with difflib; words
whisper merged, split or misheard get their time interpolated from the
neighbours, so every display word has a start and an end.

`align_words` is pure and unit tested; `transcribe_words` needs the model.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

WHISPER_MODEL = "base.en"  # ~150 MB, 1 s per 15 s of speech on CPU
MIN_WORD_S = 0.12  # a word never flashes shorter than this (unless the next word starts sooner)
MIN_GAP_S = 0.05  # consecutive starts are at least this far apart


@dataclass(frozen=True)
class Word:
    text: str  # as displayed (from the card text)
    start: float
    end: float


def _key(token: str) -> str:
    """Comparison key: lowercase, digits and letters only ("2,430" → "2430")."""
    return re.sub(r"[^a-z0-9]+", "", token.lower())


def align_words(display_tokens: list[str], heard: list[tuple[str, float, float]]) -> list[Word]:
    """Give each display token a time from the recognised words.

    `heard` is [(word, start, end)] from the recogniser. Matching tokens take
    the heard times; unmatched runs of display tokens share the span between
    their matched neighbours proportionally to their length.
    """
    if not display_tokens:
        return []
    if not heard:
        raise ValueError("no recognised words to align to")
    a = [_key(t) for t in display_tokens]
    b = [_key(w) for w, _, _ in heard]
    times: list[tuple[float, float] | None] = [None] * len(a)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k][1], heard[j1 + k][2])
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # same count, different spelling ("metres," vs "meters") — pair them up
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k][1], heard[j1 + k][2])
    # interpolate the rest between the nearest timed neighbours
    total_end = heard[-1][2]
    i = 0
    while i < len(a):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(a) and times[j] is None:
            j += 1
        span_start = times[i - 1][1] if i > 0 else 0.0
        span_end = times[j][0] if j < len(a) else total_end
        weights = [max(len(a[k]), 1) for k in range(i, j)]
        total_w = sum(weights)
        cursor = span_start
        for k, w in zip(range(i, j), weights, strict=True):
            step = (span_end - span_start) * w / total_w
            times[k] = (cursor, cursor + step)
            cursor += step
        i = j
    # Strictly ordered spans: starts climb by at least MIN_GAP_S (whisper hands
    # out identical starts now and then), and a word ends no later than the
    # next one starts — two words on screen at once looked like a double
    # exposure at the same spot (user, 17.09.). MIN_WORD_S applies where the
    # next word leaves room.
    starts = [start for start, _ in times]
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1] + MIN_GAP_S)
    words: list[Word] = []
    for i, (token, (_, end)) in enumerate(zip(display_tokens, times, strict=True)):
        start = starts[i]
        end = max(end, start + MIN_WORD_S)
        if i + 1 < len(starts):
            end = min(end, starts[i + 1])
        words.append(Word(token, round(start, 3), round(end, 3)))
    return words


EDGE_PUNCT = ".,;:!?\"'()[]\u2026\u2014\u2013-\u201c\u201d\u2018\u2019"


def display_text(token: str) -> str:
    """The word as shown: punctuation at the edges is dropped ("mortar." →
    "mortar", "metres," → "metres"); inner marks stay ("2,430", "15th-century").
    A single word with a trailing comma looks wrong on its own (user, 17.09.)."""
    return token.strip(EDGE_PUNCT)


def spoken_at(card_text: str, phrase: str, words: list[Word]) -> float | None:
    """When `phrase` (a stretch of the card text, as the VLM quotes it) starts
    being spoken: the start of the word at the phrase's first character. None
    when the phrase is empty or not in the text. `words` is aligned with
    `card_text.split()`."""
    needle = phrase.strip().lower()
    if not needle:
        return None
    at = card_text.lower().find(needle)
    if at < 0:
        return None
    index = len(card_text[:at].split())
    if at > 0 and not card_text[at - 1].isspace():
        index -= 1  # the phrase starts inside a token
    return words[index].start if index < len(words) else None


SRT_MAX_WORDS = 6


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt_text(words: list[Word]) -> str:
    """SubRip captions for the upload: short cues (at most SRT_MAX_WORDS words,
    broken at sentence ends) with the original punctuation."""
    cues: list[list[Word]] = []
    for word in words:
        if (
            cues
            and len(cues[-1]) < SRT_MAX_WORDS
            and not cues[-1][-1].text.endswith((".", "!", "?"))
        ):
            cues[-1].append(word)
        else:
            cues.append([word])
    blocks = [
        f"{i}\n{_srt_time(cue[0].start)} --> {_srt_time(cue[-1].end)}\n"
        + " ".join(w.text for w in cue)
        for i, cue in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def transcribe_words(audio: Path) -> list[tuple[str, float, float]]:
    """Recognised words with timestamps from faster-whisper."""
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), word_timestamps=True, language="en", beam_size=5)
    heard = [(w.word.strip(), float(w.start), float(w.end)) for seg in segments for w in seg.words]
    logger.info("whisper heard %d words in %s", len(heard), audio.name)
    return heard


def caption_words(card_text: str, narration: Path) -> list[Word]:
    return align_words(card_text.split(), transcribe_words(narration))
