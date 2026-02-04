"""Transcript cleaning for YouTube transcripts - removes filler words and YouTube-isms."""

import re


# Filler words and phrases to remove
REMOVE_WORDS = {
    # Basic filler words
    "um", "uh", "like", "you know", "sort of", "kind of",
    "basically", "actually", "so yeah", "i mean", "really",
    "very", "quite", "just", "gonna", "wanna", "going to",
    "you see", "well", "okay", "so", "i think", "i believe",
    # YouTube specific phrases
    "hey guys", "whats up", "what's up", "welcome back",
    "welcome to", "to the channel", "make sure to",
    "dont forget to", "don't forget to", "smash that",
    "hit that", "click the", "subscribe", "like button",
    "notification bell", "check out", "links below",
    "in the description", "comment below", "let me know",
    "down below", "you guys", "absolutely", "definitely",
    # Common video transitions
    "anyway", "so basically", "at this point",
    "as you can see", "the thing is", "first off",
    "first of all", "to be honest", "honestly",
    "but yeah", "and yeah", "right now",
    "at the moment", "pretty much", "a little bit",
    "moving on", "next up", "lets talk about",
    "let's talk about", "talking about",
    # Sponsorship/Marketing phrases
    "sponsored by", "thanks to", "special thanks",
    "check them out", "learn more", "find out more",
    "click the link", "use code", "discount code",
}

# Pre-compiled regex patterns
_WORD_PATTERNS = {
    word: re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    for word in REMOVE_WORDS
}
_MULTI_SPACE = re.compile(r"\s+")
_EMPTY_BRACKETS = re.compile(r"\[\s*\]")
_REPEATED_PUNCT = re.compile(r"([!?,.])\1+")
_TIMESTAMP_LINE = re.compile(r"(\[\d{2}:\d{2}\])(.*)")


def clean_line(text: str) -> str:
    """Clean a single line of text by removing filler words."""
    for pattern in _WORD_PATTERNS.values():
        text = pattern.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _REPEATED_PUNCT.sub(r"\1", text)
    text = _EMPTY_BRACKETS.sub("", text)
    return text.strip()


def clean_transcript(text: str, preserve_timestamps: bool = True) -> str:
    """Clean transcript text, optionally preserving [MM:SS] timestamps."""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned = []

    for line in lines:
        if not line.strip():
            cleaned.append(line)
            continue

        if preserve_timestamps:
            m = _TIMESTAMP_LINE.match(line)
            if m:
                ts, content = m.groups()
                content = clean_line(content)
                if content:
                    cleaned.append(f"{ts} {content}")
                continue

        result = clean_line(line)
        if result:
            cleaned.append(result)

    return "\n".join(cleaned)


def clean_segments(segments: list[dict]) -> list[dict]:
    """Clean a list of transcript segments (dicts with 'text' key)."""
    result = []
    for seg in segments:
        if "text" in seg:
            cleaned_text = clean_line(seg["text"])
            if cleaned_text.strip():
                cleaned_seg = seg.copy()
                cleaned_seg["text"] = cleaned_text
                result.append(cleaned_seg)
    return result
