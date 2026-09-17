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
MIN_WORD_S = 0.12  # a word never flashes shorter than this


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
    words: list[Word] = []
    for token, (start, end) in zip(display_tokens, times, strict=True):
        words.append(Word(token, round(start, 3), round(max(end, start + MIN_WORD_S), 3)))
    return words


SENTENCE_END = (".", "!", "?")
QUOTES = "\"'()\u201c\u201d\u2018\u2019"


def is_keyword(tokens: list[str], i: int) -> bool:
    """Accent-worthy word: carries a digit, or is capitalised without being the
    first word of a sentence (a proper noun such as "Inca", not "A" or "Its")."""
    token = tokens[i]
    if any(ch.isdigit() for ch in token):
        return True
    bare = token.strip(QUOTES)
    if not bare or not bare[0].isupper():
        return False
    sentence_start = i == 0 or tokens[i - 1].rstrip(QUOTES).endswith(SENTENCE_END)
    return not sentence_start


def keyword_flags(tokens: list[str]) -> list[bool]:
    return [is_keyword(tokens, i) for i in range(len(tokens))]


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
