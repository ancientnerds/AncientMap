"""Script check for story text (headline, facts, post).

2026-10-01: 6 of 3,489 stories carried text in a script the site does not
write — a Serbian-Cyrillic site name through headline, summary, post and facts
(8351), Chinese characters inside English sentences (8359, 6342, 5733, 5797),
and one story entirely in Chinese (6266). Nothing in the story steps looked at
the script; the detector for exactly this ("language bleed", MiniMax drift)
lived in theo_citations and was only called for Theo papers and image
captions. This module applies it to the stories, using that same detector.

A story that fails is not published and not repaired: the caller drops the
topic, the post or the rewrite and logs what was found.
"""

from __future__ import annotations

from collections.abc import Iterable

from pipeline.lyra.theo_citations import contains_non_latin_script, detect_language_bleed


def story_script_bleed(headline: str | None = None, texts: Iterable[str] = ()) -> list[str]:
    """Foreign-script fragments in a story's text; empty means clean.

    A headline is checked strictly: it is English by the summary prompt and has
    no room for a gloss. The other texts (facts, post, site name) may carry a
    term gloss — `the term "shakoki" (遮光器, "light-blocker")` is scholarship —
    which detect_language_bleed exempts; a whole foreign clause is still drift.
    Greek is allowed in both (quoted ancient terms, π, φ).
    """
    found: list[str] = []
    if headline and contains_non_latin_script(headline):
        found.append(headline)
    for text in texts:
        if text:
            found.extend(detect_language_bleed(text))
    return found
