"""
Open Graph Image Generator for Social Media Sharing.

Generates preview images for Twitter/X, Facebook, etc.
with site title and country overlaid on hero image.
"""

import html
import io
import json
import logging
import os
import httpx
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Response, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from PIL import Image, ImageDraw, ImageFont

from pipeline.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# Font directory - relative to project root or configurable via env
FONT_DIR = Path(os.environ.get("FONT_DIR", Path(__file__).parent.parent.parent / "fonts"))

# Logo directory
LOGO_DIR = Path(__file__).parent.parent.parent / "logo"

# OG image dimensions (smaller, optimized)
OG_WIDTH = 600
OG_HEIGHT = 315

# Colors - matching popup style
TEXT_COLOR = (255, 255, 255)
BRAND_COLOR = (255, 215, 0)  # Gold


async def fetch_wikipedia_image(site_name: str) -> Optional[Image.Image]:
    """Fetch hero image from Wikipedia for the site."""
    search_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": site_name,
        "prop": "pageimages",
        "format": "json",
        "pithumbsize": 1200,
        "pilicense": "any",
    }

    # User-Agent configured via environment or default
    user_agent = os.environ.get("OG_USER_AGENT", "AncientNerdsMap/1.0")
    headers = {"User-Agent": user_agent}

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            response = await client.get(search_url, params=params)
            if response.status_code != 200:
                return None

            data = response.json()
            pages = data.get("query", {}).get("pages", {})

            for page in pages.values():
                thumb_url = page.get("thumbnail", {}).get("source")
                if thumb_url:
                    img_response = await client.get(thumb_url, follow_redirects=True, timeout=10.0)
                    if img_response.status_code == 200:
                        return Image.open(io.BytesIO(img_response.content))

    except httpx.TimeoutException:
        logger.warning(f"Wikipedia image fetch timed out for: {site_name}")
    except httpx.HTTPError as e:
        logger.error(f"Wikipedia HTTP error for {site_name}: {e}")
    except json.JSONDecodeError:
        logger.error(f"Wikipedia returned invalid JSON for: {site_name}")
    except IOError as e:
        logger.error(f"Failed to open image for {site_name}: {e}")

    return None


def create_fallback_image() -> Image.Image:
    """Create a dark gradient fallback image."""
    img = Image.new('RGB', (OG_WIDTH, OG_HEIGHT), (10, 20, 25))
    draw = ImageDraw.Draw(img)

    # Subtle gradient - darker at top
    for y in range(OG_HEIGHT):
        shade = int(10 + (y / OG_HEIGHT) * 15)
        draw.line([(0, y), (OG_WIDTH, y)], fill=(shade, shade + 8, shade + 12))

    return img


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get font - try Orbitron (futuristic) first, then fallback to system fonts."""
    import platform

    # Orbitron paths - project fonts first (cross-platform)
    orbitron_paths = [
        FONT_DIR / "Orbitron-Bold.ttf",
        FONT_DIR / "Orbitron-Regular.ttf",
        Path("data/fonts/Orbitron-Bold.ttf"),
        Path("fonts/Orbitron-Bold.ttf"),
    ]

    # Add OS-specific paths
    if platform.system() == "Windows":
        orbitron_paths.extend([
            Path("C:/Windows/Fonts/Orbitron-Bold.ttf"),
            Path("C:/Windows/Fonts/orbitron-bold.ttf"),
        ])

    # Try Orbitron first
    for font_path in orbitron_paths:
        try:
            return ImageFont.truetype(str(font_path), size)
        except (OSError, IOError):
            continue

    # Fallback to system fonts (cross-platform)
    system = platform.system()
    if bold:
        if system == "Windows":
            font_paths = [
                Path("C:/Windows/Fonts/segoeuib.ttf"),
                Path("C:/Windows/Fonts/arialbd.ttf"),
            ]
        elif system == "Darwin":  # macOS
            font_paths = [
                Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
                Path("/Library/Fonts/Arial Bold.ttf"),
            ]
        else:  # Linux
            font_paths = [
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
                Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            ]
    else:
        if system == "Windows":
            font_paths = [
                Path("C:/Windows/Fonts/segoeui.ttf"),
                Path("C:/Windows/Fonts/arial.ttf"),
            ]
        elif system == "Darwin":  # macOS
            font_paths = [
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/Library/Fonts/Arial.ttf"),
            ]
        else:  # Linux
            font_paths = [
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
                Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            ]

    for font_path in font_paths:
        try:
            return ImageFont.truetype(str(font_path), size)
        except (OSError, IOError):
            continue

    logger.warning("No suitable font found, using default")
    return ImageFont.load_default()


def draw_text_with_shadow(
    draw: ImageDraw.Draw,
    position: tuple,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple = TEXT_COLOR,
    shadow_offset: int = 3
):
    """Draw text with drop shadow for readability."""
    x, y = position
    # Shadow passes
    for offset in range(1, shadow_offset + 1):
        draw.text((x + offset, y + offset), text, font=font, fill=(0, 0, 0))
    # Main text
    draw.text((x, y), text, font=font, fill=fill)


def generate_og_image(
    title: str,
    country: Optional[str],
    hero_image: Optional[Image.Image] = None,
) -> bytes:
    """Generate OG image with title and country only."""

    # Start with hero image or fallback
    if hero_image:
        img = hero_image.convert('RGB')

        # Crop to OG dimensions (cover mode)
        img_ratio = img.width / img.height
        og_ratio = OG_WIDTH / OG_HEIGHT

        if img_ratio > og_ratio:
            new_width = int(img.height * og_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            new_height = int(img.width / og_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        img = img.resize((OG_WIDTH, OG_HEIGHT), Image.Resampling.LANCZOS)
    else:
        img = create_fallback_image()

    # Add overlays for popup-style look
    img = img.convert('RGBA')

    # 1. Add 30% background haze (popup color: rgba(0, 20, 25))
    haze = Image.new('RGBA', (OG_WIDTH, OG_HEIGHT), (0, 20, 25, 77))  # 77 = 30% of 255
    img = Image.alpha_composite(img, haze)

    # 2. Add contrast boost overlay
    from PIL import ImageEnhance
    img_rgb = img.convert('RGB')
    enhancer = ImageEnhance.Contrast(img_rgb)
    img_rgb = enhancer.enhance(1.15)  # 15% more contrast
    img = img_rgb.convert('RGBA')

    # 3. Bottom gradient for text readability
    overlay = Image.new('RGBA', (OG_WIDTH, OG_HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for y in range(OG_HEIGHT // 3, OG_HEIGHT):
        progress = (y - OG_HEIGHT // 3) / (OG_HEIGHT * 2 // 3)
        alpha = int(180 * progress)
        overlay_draw.line([(0, y), (OG_WIDTH, y)], fill=(0, 15, 20, alpha))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 4. Add logo in upper right corner
    logo_path = LOGO_DIR / "AN only.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert('RGBA')
            # Scale logo to fit nicely (about 60px height)
            logo_height = 50
            logo_ratio = logo.width / logo.height
            logo_width = int(logo_height * logo_ratio)
            logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
            # Position in upper right with padding
            logo_x = OG_WIDTH - logo_width - 15
            logo_y = 15
            # Paste with transparency
            img.paste(logo, (logo_x, logo_y), logo)
        except Exception as e:
            logger.warning(f"Failed to load logo: {e}")

    padding = 30
    bottom_y = OG_HEIGHT - padding

    # Constraints: title max 75% width, max 35% height
    max_width = int(OG_WIDTH * 0.75)
    max_height = int(OG_HEIGHT * 0.35)

    # Find font size that fits both constraints
    title_size = 60  # Start size for 600px width
    title_font = get_font(title_size, bold=True)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = bbox[2] - bbox[0]
    title_height = bbox[3] - bbox[1]

    # Scale down until it fits both constraints
    while (title_width > max_width or title_height > max_height) and title_size > 18:
        title_size -= 2
        title_font = get_font(title_size, bold=True)
        bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = bbox[2] - bbox[0]
        title_height = bbox[3] - bbox[1]

    # Country font: 39px base, scale down if too wide (max 90% width)
    country_max_width = int(OG_WIDTH * 0.90)
    country_size = 39
    country_font = get_font(country_size)

    if country:
        bbox = draw.textbbox((0, 0), country, font=country_font)
        country_width = bbox[2] - bbox[0]
        country_height = bbox[3] - bbox[1]

        while country_width > country_max_width and country_size > 16:
            country_size -= 2
            country_font = get_font(country_size)
            bbox = draw.textbbox((0, 0), country, font=country_font)
            country_width = bbox[2] - bbox[0]
            country_height = bbox[3] - bbox[1]

    # Country (bottom)
    if country:
        draw_text_with_shadow(draw, (padding, bottom_y - 48), country, country_font)
        title_y = bottom_y - 105
    else:
        title_y = bottom_y - 50

    # Draw title
    draw_text_with_shadow(draw, (padding, title_y), title, title_font)

    # Convert to JPEG
    img = img.convert('RGB')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=75, optimize=True)
    buffer.seek(0)

    return buffer.getvalue()


def format_coord(coord: float, is_lat: bool) -> str:
    """Format coordinate with direction."""
    direction = ('N' if coord >= 0 else 'S') if is_lat else ('E' if coord >= 0 else 'W')
    return f"{abs(coord):.4f}° {direction}"


@router.get("/homepage")
async def get_homepage_og_image():
    """Generate Open Graph image for the homepage - logo on dark background."""
    # Dark background
    img = Image.new('RGBA', (OG_WIDTH, OG_HEIGHT), (10, 20, 25, 255))

    # Add logo centered
    logo_path = LOGO_DIR / "without background.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert('RGBA')
            # Scale to fit with padding (80% of height)
            logo_height = int(OG_HEIGHT * 0.75)
            logo_ratio = logo.width / logo.height
            logo_width = int(logo_height * logo_ratio)
            logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
            # Center in image
            logo_x = (OG_WIDTH - logo_width) // 2
            logo_y = (OG_HEIGHT - logo_height) // 2
            img.paste(logo, (logo_x, logo_y), logo)
        except Exception as e:
            logger.warning(f"Failed to load logo for homepage: {e}")

    # Convert to JPEG
    img = img.convert('RGB')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85, optimize=True)
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/share/{site_id}")
async def get_share_page(
    site_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve HTML page with OG meta tags for social media sharing."""
    base_url = str(request.base_url).rstrip('/')

    query = text("""
        SELECT name, lat, lon, country, description, site_type
        FROM unified_sites
        WHERE id::text = :site_id
    """)

    result = db.execute(query, {"site_id": site_id})
    row = result.fetchone()

    if not row:
        title = "Site Not Found"
        description = "This archaeological site could not be found."
        country = ""
    else:
        title = row.name or "Unknown Site"
        description = row.description or f"Archaeological site: {row.site_type or 'Unknown type'}"
        if len(description) > 200:
            description = description[:197] + "..."
        country = row.country or ""

    og_image_url = f"{base_url}/api/og/{site_id}"
    app_url = f"/?site={site_id}"
    canonical_url = f"{base_url}/?site={site_id}"

    # OG description: just country
    og_desc = country if country else description

    # Escape all user-controlled data for XSS prevention
    title_escaped = html.escape(title)
    og_desc_escaped = html.escape(og_desc)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_escaped} - Ancient Nerds Map</title>

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:title" content="{title_escaped}">
    <meta property="og:description" content="{og_desc_escaped}">
    <meta property="og:image" content="{og_image_url}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title_escaped}">
    <meta name="twitter:description" content="{og_desc_escaped}">
    <meta name="twitter:image" content="{og_image_url}">

    <!-- Redirect to app -->
    <meta http-equiv="refresh" content="0;url={app_url}">

    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a1a1f;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }}
        .loading {{ text-align: center; }}
        .spinner {{
            width: 40px; height: 40px;
            border: 3px solid #333;
            border-top-color: #ffd700;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="loading">
        <div class="spinner"></div>
        <p>Loading {title_escaped}...</p>
    </div>
    <script>window.location.href = "{app_url}";</script>
</body>
</html>"""

    return HTMLResponse(content=html_content)


@router.get("/{site_id}")
async def get_og_image(
    site_id: str,
    db: Session = Depends(get_db),
):
    """Generate Open Graph image for a site."""
    query = text("""
        SELECT name, country
        FROM unified_sites
        WHERE id::text = :site_id
    """)

    result = db.execute(query, {"site_id": site_id})
    row = result.fetchone()

    if not row:
        img_bytes = generate_og_image(title="Site Not Found", country=None)
        return Response(content=img_bytes, media_type="image/jpeg")

    # Try to fetch hero image from Wikipedia
    hero_image = await fetch_wikipedia_image(row.name)

    img_bytes = generate_og_image(
        title=row.name or "Unknown Site",
        country=row.country,
        hero_image=hero_image,
    )

    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


