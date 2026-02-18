"""Phase 6: YouTube Distributor — uploads rendered video via YouTube Data API v3.

Handles resumable upload, metadata, chapters, and thumbnail.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# YouTube API scopes needed:
# - https://www.googleapis.com/auth/youtube.upload
# - https://www.googleapis.com/auth/youtube


def _build_description(script: dict, timeline: dict) -> str:
    """Build YouTube video description with chapters and source links."""
    lines: list[str] = []

    # Chapter timestamps from timeline segments
    lines.append("CHAPTERS:")
    fps = timeline.get("fps", 30)
    for seg in timeline.get("segments", []):
        start_frame = seg.get("startFrame", 0)
        start_seconds = start_frame // fps
        minutes, seconds = divmod(start_seconds, 60)
        timestamp = f"{minutes}:{seconds:02d}"

        if seg["type"] == "intro":
            lines.append(f"{timestamp} Introduction")
        elif seg["type"] == "story":
            heading = seg.get("sectionHeading") or seg.get("lowerThird", {}).get("siteName", "Story")
            lines.append(f"{timestamp} {heading}")
        elif seg["type"] == "outro":
            lines.append(f"{timestamp} Credits & Sources")

    lines.append("")
    lines.append("SOURCES:")

    # Source links
    for src in script.get("sources", []):
        vid = src.get("video_id", "")
        ts = src.get("timestamp_seconds")
        ts_param = f"?t={ts}" if ts else ""
        url = f"https://youtu.be/{vid}{ts_param}"
        channel = src.get("channel_name", "")
        title = src.get("video_title", "")
        lines.append(f"[{src['citation']}] {channel} — {title}")
        lines.append(f"    {url}")

    lines.append("")
    lines.append("CREDITS:")
    for credit in script.get("credits", []):
        lines.append(f"• {credit['channel']} ({credit['clips_used']} clips)")

    lines.append("")
    lines.append("---")
    lines.append("Ancient Nerds — Archaeological news, visualized.")
    lines.append("https://ancientnerds.com")
    lines.append("")
    lines.append("All clips used under fair use for commentary and criticism.")
    lines.append("If you are a creator and want your content removed, please contact us.")

    return "\n".join(lines)


def _build_title(script: dict) -> str:
    """Build YouTube video title."""
    article_title = script.get("article_title", "")
    date_range = script.get("date_range", "")

    if article_title and date_range:
        return f"Archaeology News: {article_title} | {date_range}"
    elif article_title:
        return f"Archaeology News: {article_title}"
    return script.get("title", "This Week in Archaeology")


def _build_tags(script: dict) -> list[str]:
    """Build YouTube video tags."""
    base_tags = [
        "archaeology",
        "archaeological news",
        "archaeology news",
        "this week in archaeology",
        "ancient history",
        "excavation",
        "archaeological discoveries",
        "ancient nerds",
    ]

    # Add site names from segments
    for seg in script.get("segments", []):
        visuals = seg.get("visuals", {})
        site_name = visuals.get("site_name")
        if site_name:
            base_tags.append(site_name.lower())
        country = visuals.get("site_country")
        if country:
            base_tags.append(f"archaeology {country.lower()}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_tags: list[str] = []
    for tag in base_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags[:30]  # YouTube limit: 30 tags


def upload_to_youtube(
    video_path: Path,
    script: dict,
    timeline: dict,
    thumbnail_path: Path | None = None,
    privacy: str = "private",
) -> str:
    """Upload a video to YouTube via the Data API v3.

    Args:
        video_path: Path to the rendered MP4.
        script: Video script JSON (for metadata).
        timeline: Timeline JSON (for chapter timestamps).
        thumbnail_path: Optional custom thumbnail image.
        privacy: "private", "unlisted", or "public".

    Returns:
        The YouTube video URL.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    # Load OAuth token from environment or file
    token_path = os.getenv("YOUTUBE_TOKEN_PATH", "youtube_token.json")

    if not Path(token_path).exists():
        raise FileNotFoundError(
            f"YouTube OAuth token not found at {token_path}. "
            "Run the OAuth flow first to generate credentials."
        )

    creds = Credentials.from_authorized_user_file(token_path)
    youtube = build("youtube", "v3", credentials=creds)

    title = _build_title(script)
    description = _build_description(script, timeline)
    tags = _build_tags(script)

    body = {
        "snippet": {
            "title": title[:100],  # YouTube title limit
            "description": description[:5000],  # YouTube description limit
            "tags": tags,
            "categoryId": "27",  # Education
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    logger.info(f"Uploading video: {title}")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"Upload complete: {video_url}")

    # Upload custom thumbnail if provided
    if thumbnail_path and thumbnail_path.exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
        ).execute()
        logger.info("Custom thumbnail uploaded")

    return video_url
