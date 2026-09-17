"""NERV brand elements for the shorts: the website's category/period badges.

Colours come straight from the frontend's `constants/colors.ts` (parsed, not
copied), the look from `metadata.css` (`.meta-badge`: uppercase JetBrains Mono
500, 1 px border and text in the category colour, dark translucent fill over
hero imagery). Badges are rendered with Pillow to a transparent PNG at 2× and
downscaled, then overlaid by ffmpeg with the same fade as the site name.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FRONTEND = Path(__file__).resolve().parents[2] / "ancient-nerds-map"
COLORS_TS = FRONTEND / "src" / "constants" / "colors.ts"
FONT_DIR = Path(__file__).resolve().parents[2] / "video-assets" / "fonts"
# The video's fonts are the families the website uses (--font-heading Orbitron,
# --font-body JetBrains Mono). The site hosts latin-only woff2 subsets, so the
# static instances are cut from the full variable fonts of the google/fonts
# repo (`ensure_fonts`: download once into FONT_DIR/src, instantiate weights).
FONT_SOURCES: dict[str, str] = {
    "Orbitron[wght].ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf",
    "JetBrainsMono[wght].ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
FONTS: dict[str, tuple[str, int]] = {
    "orbitron-700.ttf": ("Orbitron[wght].ttf", 700),
    "jetbrains-mono-400.ttf": ("JetBrainsMono[wght].ttf", 400),
    "jetbrains-mono-500.ttf": ("JetBrainsMono[wght].ttf", 500),
    "jetbrains-mono-700.ttf": ("JetBrainsMono[wght].ttf", 700),
}
FONT_HEADING = FONT_DIR / "orbitron-700.ttf"  # the site's hero title weight
FONT_HEADING_EXT = FONT_DIR / "jetbrains-mono-700.ttf"  # Orbitron has no Latin Extended-A
FONT_BODY = FONT_DIR / "jetbrains-mono-400.ttf"
FONT_BADGE = FONT_DIR / "jetbrains-mono-500.ttf"

# .meta-badge-lg over a hero image, scaled ×3 for the 1080-px frame
# (11 px font, 4/10 px padding, 1 px border, 6 px gap, 0.5 px letter-spacing).
BADGE_FONT_PX = 34
BADGE_PAD_X = 30
BADGE_PAD_Y = 12
BADGE_BORDER = 3
BADGE_GAP = 18
BADGE_LETTER_SPACING = 2
BADGE_FILL = (0, 10, 15, 224)  # --surface-raised-solid in satellite mode: rgba(0,10,15,0.88)
GENERIC_TYPES = {"", "site", "unknown"}  # SiteBadges shows no category badge for these

_MAPS: dict[str, dict[str, str]] = {}


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

            src.write_bytes(
                httpx.get(FONT_SOURCES[source], follow_redirects=True, timeout=60)
                .raise_for_status()
                .content
            )
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
    Mono 700 — the next font in the site's --font-heading stack."""
    return FONT_HEADING if not missing_glyphs(text, font_cmap(FONT_HEADING)) else FONT_HEADING_EXT


def _color_map(name: str) -> dict[str, str]:
    """`export const <name>` object literal from colors.ts as {key: '#hex'}."""
    if name not in _MAPS:
        src = COLORS_TS.read_text(encoding="utf-8")
        start = src.index(f"export const {name}")
        end = src.index("\n}", start)
        pairs = re.findall(r"'([^']+)':\s*'(#[0-9a-fA-F]{6})'", src[start:end])
        if not pairs:
            raise RuntimeError(f"no colours parsed for {name} from {COLORS_TS}")
        _MAPS[name] = dict(pairs)
    return _MAPS[name]


def category_color(category: str | None) -> str:
    """Mirror of the frontend's getCategoryColor: exact, then case-insensitive
    with underscores↔spaces, else the default grey."""
    colors = _color_map("CATEGORY_COLORS")
    if not category:
        return colors["default"]
    if category in colors:
        return colors[category]
    lower = {k.lower(): v for k, v in colors.items()}
    n = category.lower()
    return (
        lower.get(n)
        or lower.get(n.replace("_", " "))
        or lower.get(n.replace(" ", "_"))
        or colors["default"]
    )


def period_color(period: str | None) -> str:
    """Mirror of getPeriodColor: the canonical bucket's colour, else Unknown grey."""
    colors = _color_map("PERIOD_COLORS")
    return colors.get(period or "", colors["Unknown"])


def badge_specs(site: dict) -> list[tuple[str, str]]:
    """(label, colour) for the badges the site page would show: the category
    unless generic, the period unless unknown. Labels are uppercased like the
    CSS does."""
    specs: list[tuple[str, str]] = []
    category = (site.get("site_type") or "").strip()
    if category.lower() not in GENERIC_TYPES:
        specs.append((category.upper(), category_color(category)))
    period = (site.get("period_name") or "").strip()
    if period and period != "Unknown":
        specs.append((period.upper(), period_color(period)))
    return specs


def _hex_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def render_badges(specs: list[tuple[str, str]], out: Path, scale: int = 2) -> tuple[int, int]:
    """Draw the badges side by side into a transparent PNG; returns (w, h) in
    frame pixels. Text is spaced by hand (Pillow has no letter-spacing)."""
    if not specs:
        raise ValueError("no badges to render")
    font = ImageFont.truetype(str(FONT_BADGE), BADGE_FONT_PX * scale)
    spacing = BADGE_LETTER_SPACING * scale
    pad_x, pad_y, border, gap = (
        v * scale for v in (BADGE_PAD_X, BADGE_PAD_Y, BADGE_BORDER, BADGE_GAP)
    )
    ascent, descent = font.getmetrics()
    text_h = ascent + descent
    widths = [
        sum(font.getlength(ch) for ch in label) + spacing * (len(label) - 1) for label, _ in specs
    ]
    boxes = [int(w) + 2 * pad_x for w in widths]
    total_w = sum(boxes) + gap * (len(specs) - 1)
    total_h = text_h + 2 * pad_y
    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = 0
    for (label, color), box_w in zip(specs, boxes, strict=True):
        rgb = _hex_rgb(color)
        draw.rectangle(
            [x, 0, x + box_w - 1, total_h - 1], fill=BADGE_FILL, outline=rgb, width=border
        )
        cx = x + pad_x
        for ch in label:
            draw.text((cx, pad_y), ch, font=font, fill=rgb)
            cx += font.getlength(ch) + spacing
        x += box_w + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    final = img.resize((total_w // scale, total_h // scale), Image.LANCZOS)
    final.save(out)
    return final.size
