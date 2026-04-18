"""Title image generation for Theo research papers.

Generates a single cover illustration using MiniMax image-01, downloads
it to local storage, and returns the URL for embedding above the abstract.

Storage: public/data/research-images/{paper_id}/cover.png
Served at: /data/research-images/{paper_id}/cover.png

Usage:
    from pipeline.lyra.theo_images import generate_cover_image
    url = await generate_cover_image(paper_id, paper_title, emit)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

MINIMAX_BASE_URL = "https://api.minimax.io"
MINIMAX_IMAGE_PATH = "/v1/image_generation"
MINIMAX_REMAINS_PATH = "/v1/api/openplatform/coding_plan/remains"

# Images stored here, served by Nginx/Vite at /data/research-images/
IMAGES_DIR = Path(__file__).parent.parent.parent / "public" / "data" / "research-images"

# Style suffix for archaeological illustrations
STYLE_SUFFIX = (
    ", digital painting, thick painterly brushstrokes, impasto texture, "
    "semi-realistic stylized rendering, strong chiaroscuro, saturated "
    "complementary colors, cinematic color grading, atmospheric haze, "
    "concept art quality, matte painting aesthetic, high contrast"
)

# Minimum remaining image quota to proceed
_MIN_QUOTA = 3


def _get_api_key() -> str:
    return os.getenv("LYRA_MINIMAX_API_KEY", "")


async def check_image_quota() -> int:
    """Check remaining MiniMax image-01 daily quota.

    Returns the number of images remaining, or -1 if check fails.
    """
    api_key = _get_api_key()
    if not api_key:
        return -1

    def _check() -> int:
        try:
            client = httpx.Client(timeout=10.0)
            resp = client.get(
                f"{MINIMAX_BASE_URL}{MINIMAX_REMAINS_PATH}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            client.close()
            if resp.status_code != 200:
                logger.warning("MiniMax quota check failed: %s", resp.status_code)
                return -1
            data = resp.json()
            for item in data.get("model_remains", []):
                if item.get("model_name") == "image-01":
                    used = item.get("current_interval_usage_count", 0)
                    total = item.get("current_interval_total_count", 0)
                    return max(0, total - used)
            return -1
        except Exception as exc:
            logger.warning("MiniMax quota check error: %s", exc)
            return -1

    return await asyncio.to_thread(_check)


def _extract_title(paper_text: str) -> str:
    """Extract the # title from paper markdown."""
    for line in paper_text.split("\n"):
        match = re.match(r"^#\s+(.+)$", line)
        if match:
            return match.group(1).strip()
    return ""


def _build_cover_prompt(title: str) -> str:
    """Build an image generation prompt from the paper title."""
    return (
        f"Archaeological illustration: {title}. "
        f"Ancient ruins, artifacts, or landscape relevant to this topic. "
        f"No text, no labels, no watermarks"
        f"{STYLE_SUFFIX}"
    )


async def generate_cover_image(
    paper_id: str,
    paper_text: str,
    emit: callable,
) -> str:
    """Generate a single cover image for a research paper.

    Returns the relative URL of the image, or empty string on failure/skip.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.info("[THEO] No MiniMax API key — skipping cover image")
        return ""

    title = _extract_title(paper_text)
    if not title:
        return ""

    # Check quota
    remaining = await check_image_quota()
    if remaining != -1 and remaining < _MIN_QUOTA:
        logger.warning(
            "[THEO] MiniMax image quota too low (%d remaining), skipping cover",
            remaining,
        )
        emit(
            {
                "type": "status",
                "content": f"Image quota low ({remaining} remaining), skipping cover image.",
            }
        )
        return ""

    emit({"type": "status", "content": "Generating cover illustration..."})

    prompt = _build_cover_prompt(title)

    try:
        image_url = await _generate_one(api_key, prompt)
        if not image_url:
            return ""

        # Download and save
        paper_dir = IMAGES_DIR / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        local_path = paper_dir / "cover.png"
        await _download_image(image_url, local_path)

        relative_url = f"/data/research-images/{paper_id}/cover.png"
        logger.info("[THEO] Generated cover image: %s", relative_url)
        emit({"type": "status", "content": "Cover illustration ready."})
        return relative_url

    except Exception as exc:
        logger.warning("[THEO] Cover image generation failed: %s", exc)
        return ""


async def _generate_one(api_key: str, prompt: str) -> str | None:
    """Generate a single image via MiniMax image-01. Returns URL or None."""

    def _call() -> str | None:
        client = httpx.Client(
            base_url=MINIMAX_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
        try:
            resp = client.post(
                MINIMAX_IMAGE_PATH,
                json={
                    "model": "image-01",
                    "prompt": prompt,
                    "aspect_ratio": "16:9",
                    "response_format": "url",
                    "n": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            status_code = data.get("base_resp", {}).get("status_code", -1)
            if status_code != 0:
                logger.warning(
                    "MiniMax image-01 error: %s",
                    data.get("base_resp", {}).get("status_msg", "unknown"),
                )
                return None

            urls = data.get("data", {}).get("image_urls", [])
            return urls[0] if urls else None
        finally:
            client.close()

    return await asyncio.to_thread(_call)


async def _download_image(url: str, output_path: Path) -> None:
    """Download an image from URL to local file."""

    def _dl() -> None:
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    await asyncio.to_thread(_dl)


def insert_cover_image(paper_text: str, cover_url: str) -> str:
    """Insert cover image after the # title, before ## Abstract."""
    if not cover_url:
        return paper_text

    lines = paper_text.split("\n")
    result: list[str] = []

    for line in lines:
        result.append(line)
        # Insert after the # title line
        if re.match(r"^#\s+.+$", line) and not line.startswith("##"):
            result.append("")
            result.append(f"![Cover]({cover_url})")
            result.append("")

    return "\n".join(result)


def delete_paper_images(paper_id: str) -> None:
    """Delete all generated images for a paper."""
    paper_dir = IMAGES_DIR / paper_id
    if paper_dir.exists():
        import shutil

        shutil.rmtree(paper_dir)
        logger.info("Deleted images for paper %s", paper_id)
