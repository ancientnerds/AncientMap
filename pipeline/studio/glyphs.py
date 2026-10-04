"""The brand fonts' glyphs: the renderer's rule that every drawn string uses only them.

DRAWABLE is a verbatim copy of the constant of stream D's video/src/theme/glyphs.ts: the code
points the latin and latin-ext font files the renderer loads really map (their cmap, within each
face's unicode-range, common to the heading, body and serif stacks; D generates it from the files
and its test recomputes it), plus tab, line feed and carriage return. Task 27 checks the copy
against that file. The declared unicode-range is not enough: Google's subsets leave gaps (no Ḫ,
Ḥ, Ṣ, Ṭ, ʾ, ʿ, U+2011 or ‰ in the loaded JetBrains Mono files). Any other character (Greek,
Cyrillic, an arrow, an emoji, a gap) would render in a Windows system font, so the renderer's
checkBlocks refuses every drawn timeline string that holds one, and so does a character whose
CSS upper case falls outside DRAWABLE (ƒ -> Ƒ; the renderer's `unsupportedChar` applies the
same rule). Owner decision 32: the rule covers only the strings
that are actually drawn as text: a block's registry `drawn` paths (`drawn_strings`) and a
capture's credits and place and pin labels (`capture_strings`); ids, paths, URLs, a captured
page's own <title> (kept in its `page` event as a record, never drawn: SourceViewer's address
bar draws only the page's ASCII hostname) and an original quote inside a captured source page
are not checked. script.py applies the rule before voice and capture, and captures.py to what a
capture manifest brings.
"""

from __future__ import annotations

import re
from typing import Any

DRAWABLE = (
    "U+0009-000A, U+000D, U+0020-007E, U+00A0-00B4, U+00B6-0131, U+0134-017F, U+018F, U+0192, "
    "U+01A0-01A1, U+01AF-01B0, U+01CD-01CE, U+01E6-01E7, U+01EA-01EB, U+01FC-01FF, U+0218-021B, "
    "U+0232-0233, U+0237, U+0259, U+02BC, U+02C6-02C7, U+02DA, U+02DC-02DD, U+0304, U+0308, "
    "U+1E80-1E85, U+1E9E, U+1EF2-1EF9, U+2013-2014, U+2018-201A, U+201C-201E, U+2020, U+2022, "
    "U+2026, U+2032-2033, U+2039-203A, U+2044, U+20AB-20AC, U+20AE, U+20BD, U+2113, U+2122, "
    "U+2191, U+2193, U+2212, U+FEFF"
)
_ENTRY_RE = re.compile(r"U\+([0-9A-F]+)(?:-([0-9A-F]+))?", re.IGNORECASE)


def parse_unicode_range(css: str) -> list[tuple[int, int]]:
    """A CSS unicode-range ("U+0000-00FF, U+0131") as inclusive (first, last) code points."""
    pairs: list[tuple[int, int]] = []
    for part in css.split(","):
        match = _ENTRY_RE.fullmatch(part.strip())
        if match is None:
            raise ValueError(f"not a unicode-range entry: {part.strip()!r}")
        first = int(match.group(1), 16)
        pairs.append((first, int(match.group(2), 16) if match.group(2) else first))
    return pairs


COVERED = tuple(parse_unicode_range(DRAWABLE))
NO_GLYPH = "has no glyph in the brand fonts (latin and latin-ext only)"


def _covered(ch: str) -> bool:
    return any(first <= ord(ch) <= last for first, last in COVERED)


def unsupported_char(text: str) -> str | None:
    """The first character of `text` the brand fonts cannot draw, or None when they draw all.

    The renderer sets most drawn strings in upper case by CSS (heading() and hud():
    textTransform 'uppercase'), which applies the full Unicode mapping, so a character is
    drawable only if it and every code point of its uppercase mapping have a glyph. One
    character of DRAWABLE fails that: ƒ (-> Ƒ). µ, ǰ and ẖ are refused as written (no loaded
    file maps them); `micrometre` is the drawable spelling."""
    for ch in text:
        if not (_covered(ch) and all(_covered(u) for u in ch.upper())):
            return ch
    return None


def glyph_problem(where: str, text: str) -> str | None:
    """The renderer's message for the first character of `text` it cannot draw, or None."""
    ch = unsupported_char(text)
    if ch is None:
        return None
    if _covered(ch):
        upper = ch.upper()
        points = " ".join(f"U+{ord(u):04X}" for u in upper)
        return (
            f'{where}: "{ch}" (U+{ord(ch):04X}) draws as "{upper}" ({points}) in upper case, '
            f"which {NO_GLYPH}"
        )
    return f'{where}: "{ch}" (U+{ord(ch):04X}) {NO_GLYPH}'


def drawn_strings(value: Any, patterns: list[str], at: str) -> list[tuple[str, str]]:
    """The strings a block draws: every string `value` holds at one of `patterns` (its registry
    `drawn` paths: keys joined by ".", `key[]` for every array element), each with its path
    below `at` ("props.claims[0].label"). An optional prop that is absent draws nothing."""
    found: list[tuple[str, str]] = []
    for pattern in patterns:
        nodes: list[tuple[str, Any]] = [(at, value)]
        for segment in pattern.split("."):
            key = segment.removesuffix("[]")
            step: list[tuple[str, Any]] = []
            for path, node in nodes:
                if not isinstance(node, dict) or key not in node:
                    continue
                child = node[key]
                if not segment.endswith("[]"):
                    step.append((f"{path}.{key}", child))
                elif isinstance(child, list):
                    step.extend((f"{path}.{key}[{i}]", item) for i, item in enumerate(child))
            nodes = step
        found.extend((path, node) for path, node in nodes if isinstance(node, str))
    return found


#: The capture event field a block draws, by event name: a globe place's or a top-down pin's
#: label. Nothing else of an event is drawn as text: not its name or target, not a url
#: (SourceViewer's address bar and the source credit draw only its ASCII hostname), not a
#: `page` event's title (a record of the captured page, never drawn), not the `gpu` event's
#: renderer label.
DRAWN_EVENT_FIELDS = {"place": "label", "pin": "label"}


def capture_strings(manifest: dict[str, Any], at: str) -> list[tuple[str, str]]:
    """The strings a capture brings that the renderer draws: its credits and the drawn event
    fields, with their paths below `at` ("manifest.events[0].label")."""
    found = [(f"{at}.credits[{i}]", credit) for i, credit in enumerate(manifest["credits"])]
    for i, event in enumerate(manifest["events"]):
        key = DRAWN_EVENT_FIELDS.get(event["name"])
        if key is not None and isinstance(event.get(key), str):
            found.append((f"{at}.events[{i}].{key}", event[key]))
    return found
