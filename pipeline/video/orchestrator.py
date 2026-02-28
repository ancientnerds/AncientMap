"""Phase 7: Video Pipeline Orchestrator — end-to-end runner.

Ties together all phases: script → voiceover → assets → timeline → render → upload.

Usage:
  python -m pipeline.video.orchestrator --article-id=42
  python -m pipeline.video.orchestrator --article-id=42 --dry-run
  python -m pipeline.video.orchestrator --article-id=42 --skip-upload
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from pipeline.lyra.config import LyraSettings

logger = logging.getLogger(__name__)

# Base output directory for video pipeline artifacts
OUTPUT_BASE = Path("pipeline/video/output")

# Path to the Remotion project
REMOTION_PROJECT = Path("video")


def _render_video(timeline_path: Path, output_path: Path) -> bool:
    """Render the video using Remotion CLI.

    Args:
        timeline_path: Path to timeline.json (Remotion inputProps).
        output_path: Where to write the final MP4.

    Returns:
        True if render succeeded.
    """
    cmd = [
        "npx",
        "remotion",
        "render",
        "WeeklyVideo",
        "--props",
        str(timeline_path),
        "--output",
        str(output_path),
        "--codec",
        "h264",
        "--image-format",
        "jpeg",
        "--log",
        "warn",
    ]

    logger.info(f"Starting Remotion render: {' '.join(cmd)}")
    try:
        subprocess.run(
            cmd,
            cwd=str(REMOTION_PROJECT),
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout
        )
        logger.info(f"Render complete: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Remotion render failed:\n{e.stderr[:500]}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Remotion render timed out (30 min)")
        return False


async def generate_weekly_video(
    article_id: int,
    dry_run: bool = False,
    skip_upload: bool = False,
    skip_render: bool = False,
    api_base_url: str = "https://ancientnerds.com",
) -> dict:
    """Run the full video pipeline for an article.

    Args:
        article_id: ID of the NewsArticle to turn into a video.
        dry_run: If True, only generate the script and print it.
        skip_upload: If True, render but don't upload to YouTube.
        skip_render: If True, generate assets but don't render.
        api_base_url: Base URL for the API (for screenshot downloads).

    Returns:
        Dict with paths to all generated artifacts.
    """
    settings = LyraSettings()
    output_dir = OUTPUT_BASE / f"article_{article_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {"article_id": article_id, "output_dir": str(output_dir)}
    t0 = time.time()

    # Phase 1: Script Adapter
    logger.info(f"=== Phase 1: Generating script for article {article_id} ===")
    from pipeline.video.script_adapter import generate_script

    script = generate_script(article_id, settings)

    script_path = output_dir / "video_script.json"
    script_path.write_text(json.dumps(script, indent=2), encoding="utf-8")
    result["script_path"] = str(script_path)
    logger.info(f"Script: {len(script['segments'])} segments, {len(script['sources'])} sources")

    if dry_run:
        logger.info("Dry run — stopping after script generation")
        result["dry_run"] = True
        print(json.dumps(script, indent=2))
        return result

    # Phase 2: Voiceover
    logger.info("=== Phase 2: Generating voiceover ===")
    from pipeline.video.voiceover import ElevenLabsSettings, generate_voiceover

    elevenlabs_settings = ElevenLabsSettings()
    audio_result = generate_voiceover(script, output_dir, elevenlabs_settings)
    result["audio_files"] = audio_result["audio_files"]

    # Phase 3: Asset Collection
    logger.info("=== Phase 3: Collecting assets ===")
    from pipeline.video.asset_collector import collect_assets

    manifest = collect_assets(script, output_dir, api_base_url)
    result["manifest"] = manifest

    # Phase 4: Timeline Builder
    logger.info("=== Phase 4: Building timeline ===")
    from pipeline.video.timeline_builder import build_timeline

    timeline_path = output_dir / "timeline.json"
    timeline = build_timeline(script, audio_result, manifest, timeline_path)
    result["timeline_path"] = str(timeline_path)
    total_seconds = timeline.get("totalDurationSeconds", 0)
    logger.info(f"Timeline: {total_seconds:.1f}s total duration")

    if skip_render:
        logger.info("Skipping render (--skip-render)")
        result["skip_render"] = True
        return result

    # Phase 5: Remotion Render
    logger.info("=== Phase 5: Rendering video ===")
    video_path = output_dir / "final.mp4"
    render_ok = _render_video(timeline_path, video_path)
    if not render_ok:
        result["render_failed"] = True
        return result
    result["video_path"] = str(video_path)

    if skip_upload:
        logger.info("Skipping upload (--skip-upload)")
        result["skip_upload"] = True
        elapsed = time.time() - t0
        logger.info(f"Pipeline complete in {elapsed:.1f}s (upload skipped)")
        return result

    # Phase 6: YouTube Upload
    logger.info("=== Phase 6: Uploading to YouTube ===")
    from pipeline.video.distributor import upload_to_youtube

    thumbnail_path = output_dir / "thumbnail.png"
    youtube_url = upload_to_youtube(
        video_path,
        script,
        timeline,
        thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
        privacy="private",
    )
    result["youtube_url"] = youtube_url

    elapsed = time.time() - t0
    logger.info(f"=== Video pipeline complete in {elapsed:.1f}s ===")
    logger.info(f"YouTube URL: {youtube_url}")

    return result


def main() -> None:
    """CLI entry point for the video pipeline."""
    parser = argparse.ArgumentParser(description="Weekly video pipeline orchestrator")
    parser.add_argument("--article-id", type=int, required=True, help="NewsArticle ID to process")
    parser.add_argument(
        "--dry-run", action="store_true", help="Only generate script JSON, don't render"
    )
    parser.add_argument(
        "--skip-upload", action="store_true", help="Render but don't upload to YouTube"
    )
    parser.add_argument(
        "--skip-render", action="store_true", help="Generate assets but don't render"
    )
    parser.add_argument(
        "--api-base-url", default="https://ancientnerds.com", help="API base URL for screenshots"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    import asyncio

    result = asyncio.run(
        generate_weekly_video(
            article_id=args.article_id,
            dry_run=args.dry_run,
            skip_upload=args.skip_upload,
            skip_render=args.skip_render,
            api_base_url=args.api_base_url,
        )
    )

    if result.get("dry_run"):
        return

    # Print summary
    print("\n=== Video Pipeline Result ===")
    for key, value in result.items():
        if key != "manifest":
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
