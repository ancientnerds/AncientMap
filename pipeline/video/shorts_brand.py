"""The website's fonts for the shorts (--font-heading Orbitron, --font-body
JetBrains Mono).

The site hosts latin-only woff2 subsets, so the static instances are cut from
the full variable fonts of the google/fonts repo (`ensure_fonts`: download
once into FONT_DIR/src, instantiate the weights). Orbitron has no Latin
Extended-A at all, so a name or card text with s-cedilla, g-breve, dotted I
or macron vowels switches the heading font to JetBrains Mono 700, the next
font in the site's own font stack.
"""

from __future__ import annotations

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[2] / "video-assets" / "fonts"
FONT_SOURCES: dict[str, str] = {
    "Orbitron[wght].ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf",
    "JetBrainsMono[wght].ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
FONTS: dict[str, tuple[str, int]] = {
    "orbitron-700.ttf": ("Orbitron[wght].ttf", 700),
    "jetbrains-mono-400.ttf": ("JetBrainsMono[wght].ttf", 400),
    "jetbrains-mono-700.ttf": ("JetBrainsMono[wght].ttf", 700),
}
FONT_HEADING = FONT_DIR / "orbitron-700.ttf"  # the site's hero title weight
FONT_HEADING_EXT = FONT_DIR / "jetbrains-mono-700.ttf"  # Orbitron has no Latin Extended-A
FONT_BODY = FONT_DIR / "jetbrains-mono-400.ttf"


def ensure_fonts() -> None:
    """Fetch the variable source fonts once and cut the static instances in
    FONTS when they are missing."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    src_dir = FONT_DIR / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    for ttf_name, (source, weight) in FONTS.items():
        out = FONT_DIR / ttf_name
        if out.exists():
            continue
        src = src_dir / source
        if not src.exists():
            import httpx

            response = httpx.get(FONT_SOURCES[source], follow_redirects=True, timeout=60)
            src.write_bytes(response.raise_for_status().content)
        font = instantiateVariableFont(TTFont(src), {"wght": weight})
        font.flavor = None
        font.save(out)


_CMAPS: dict[Path, set[int]] = {}


def font_cmap(font: Path) -> set[int]:
    from fontTools.ttLib import TTFont

    if font not in _CMAPS:
        ensure_fonts()
        _CMAPS[font] = set(TTFont(font).getBestCmap())
    return _CMAPS[font]


def missing_glyphs(text: str, cmap: set[int]) -> list[str]:
    """Characters of `text` the font cannot draw (drawtext would show boxes)."""
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap})


def heading_font(text: str) -> Path:
    """Orbitron 700 when it can draw every character of `text`, else JetBrains
    Mono 700, the next font in the site's --font-heading stack."""
    if missing_glyphs(text, font_cmap(FONT_HEADING)):
        return FONT_HEADING_EXT
    return FONT_HEADING
