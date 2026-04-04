"""Image generation for Theo research papers.

Generates section illustrations using MiniMax image-01, downloads
them to local storage, and returns markdown image tags for embedding.

Storage: public/data/research-images/{paper_id}/section-{index}.png
Served at: /data/research-images/{paper_id}/section-{index}.png

Usage:
    from pipeline.lyra.theo_images import generate_paper_images
    images = await generate_paper_images(paper_id, sections, emit)
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

# Sections that don't get images
_SKIP_SECTIONS = frozenset({
    "abstract",
    "introduction",
    "methodology",
    "conclusion",
    "references",
    "appendix: specialist debate summary",
})

# Minimum remaining image quota to proceed with generation
_MIN_QUOTA = 5


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
            # Find image-01 in the remains response
            for item in data.get("data", {}).get("detail", []):
                if item.get("model") == "image-01":
                    return item.get("remains", 0)
            return -1
        except Exception as exc:
            logger.warning("MiniMax quota check error: %s", exc)
            return -1

    return await asyncio.to_thread(_check)


def _extract_topic_sections(paper_text: str) -> list[dict]:
    """Extract topic section titles from paper markdown.

    Returns [{title, index}] for sections that should get images.
    """
    sections: list[dict] = []
    index = 0
    for line in paper_text.split("\n"):
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            title = heading.group(1).strip()
            if title.lower() not in _SKIP_SECTIONS:
                sections.append({"title": title, "index": index})
                index += 1
    return sections


def _build_image_prompt(section_title: str) -> str:
    """Build an image generation prompt from a section title."""
    return (
        f"Archaeological illustration: {section_title}. "
        f"Ancient ruins, artifacts, or landscape relevant to this topic. "
        f"No text, no labels, no watermarks"
        f"{STYLE_SUFFIX}"
    )


async def generate_paper_images(
    paper_id: str,
    paper_text: str,
    emit: callable,
) -> dict[str, str]:
    """Generate images for each topic section of a paper.

    Returns a dict mapping section title -> local image path (relative URL).
    Skips if API key missing, quota too low, or generation fails.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.info("[THEO] No MiniMax API key — skipping image generation")
        return {}

    sections = _extract_topic_sections(paper_text)
    if not sections:
        return {}

    # Check quota
    remaining = await check_image_quota()
    if remaining != -1 and remaining < _MIN_QUOTA:
        logger.warning(
            "[THEO] MiniMax image quota too low (%d remaining), skipping images",
            remaining,
        )
        emit({
            "type": "status",
            "content": f"Image quota low ({remaining} remaining), skipping illustrations.",
        })
        return {}

    if remaining != -1 and remaining < len(sections) + _MIN_QUOTA:
        # Limit to what we can afford while keeping a buffer
        sections = sections[: max(remaining - _MIN_QUOTA, 1)]

    emit({
        "type": "status",
        "content": f"Generating {len(sections)} section illustrations...",
    })

    # Create output directory
    paper_dir = IMAGES_DIR / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)

    images: dict[str, str] = {}

    for section in sections:
        title = section["title"]
        idx = section["index"]
        prompt = _build_image_prompt(title)

        emit({
            "type": "status",
            "content": f"Generating image for: {title}...",
        })

        try:
            image_url = await _generate_one(api_key, prompt)
            if not image_url:
                continue

            # Download and save
            local_path = paper_dir / f"section-{idx}.png"
            await _download_image(image_url, local_path)

            # Return relative URL for markdown embedding
            relative_url = f"/data/research-images/{paper_id}/section-{idx}.png"
            images[title] = relative_url
            logger.info("[THEO] Generated image for '%s': %s", title, relative_url)

        except Exception as exc:
            logger.warning("[THEO] Image generation failed for '%s': %s", title, exc)
            continue

    emit({
        "type": "status",
        "content": f"Generated {len(images)}/{len(sections)} illustrations.",
    })
    return images


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


def insert_images_into_paper(paper_text: str, images: dict[str, str]) -> str:
    """Insert image markdown tags after each matching ## section heading.

    Args:
        paper_text: The paper markdown
        images: {section_title: relative_url}

    Returns modified paper text with images embedded.
    """
    if not images:
        return paper_text

    lines = paper_text.split("\n")
    result: list[str] = []

    for line in lines:
        result.append(line)
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            title = heading.group(1).strip()
            if title in images:
                result.append("")
                result.append(f"![{title}]({images[title]})")
                result.append("")

    return "\n".join(result)


def delete_paper_images(paper_id: str) -> None:
    """Delete all generated images for a paper."""
    paper_dir = IMAGES_DIR / paper_id
    if paper_dir.exists():
        import shutil

        shutil.rmtree(paper_dir)
        logger.info("Deleted images for paper %s", paper_id)
