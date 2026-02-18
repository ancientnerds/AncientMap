"""Phase 4: Timeline Builder — merges voiceover timing + assets into Remotion inputProps.

Produces a timeline.json that the Remotion renderer consumes to sequence all compositions.
"""

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

FPS = 30
WIDTH = 1920
HEIGHT = 1080

# Duration constants (in seconds)
INTRO_DURATION = 8.0
GLOBE_FLYTO_DURATION = 3.0
TRANSITION_DURATION = 1.5
OUTRO_DURATION = 10.0


def _seconds_to_frames(seconds: float) -> int:
    return round(seconds * FPS)


def _allocate_visuals(
    segment: dict,
    total_frames: int,
    manifest: dict,
    segment_index: int,
) -> list[dict]:
    """Allocate visual elements within a story segment's frame budget.

    Order: screenshot (first ~30%), clip (~40%), wiki images (remaining ~30%).
    If assets are missing, remaining types fill the gap.
    """
    visuals_list: list[dict] = []
    visuals = segment.get("visuals", {})
    if not visuals:
        return visuals_list

    frame_cursor = 0

    # Screenshot
    screen_key = f"segment_{segment_index}"
    screen_path = manifest.get("screenshots", {}).get(screen_key)
    if screen_path:
        screen_frames = min(_seconds_to_frames(5), total_frames // 3)
        visuals_list.append({
            "type": "screenshot",
            "src": screen_path,
            "startFrame": frame_cursor,
            "endFrame": frame_cursor + screen_frames,
        })
        frame_cursor += screen_frames

    # YouTube clip
    clip_info = visuals.get("clip", {})
    video_id = clip_info.get("video_id")
    if video_id:
        start = clip_info.get("start", 0) or 0
        clip_key = f"{video_id}_{start}"
        clip_path = manifest.get("clips", {}).get(clip_key)
        if clip_path:
            clip_duration = min(clip_info.get("duration", 15), 15)
            clip_frames = min(_seconds_to_frames(clip_duration), total_frames - frame_cursor)
            visuals_list.append({
                "type": "clip",
                "src": clip_path,
                "startFrame": frame_cursor,
                "endFrame": frame_cursor + clip_frames,
                "attribution": {
                    "channel": visuals.get("channel_name", ""),
                    "title": visuals.get("video_title", ""),
                },
            })
            frame_cursor += clip_frames

    # WikiImages for remaining time
    wiki_images = visuals.get("wiki_images", [])
    remaining_frames = total_frames - frame_cursor
    if wiki_images and remaining_frames > 0:
        frames_per_image = remaining_frames // len(wiki_images)
        for j, _wiki_img in enumerate(wiki_images):
            wiki_key = f"seg{segment_index}_wiki{j}"
            wiki_path = manifest.get("wiki_images", {}).get(wiki_key)
            if wiki_path:
                img_frames = frames_per_image if j < len(wiki_images) - 1 else (total_frames - frame_cursor)
                if img_frames > 0:
                    visuals_list.append({
                        "type": "wiki_image",
                        "src": wiki_path,
                        "startFrame": frame_cursor,
                        "endFrame": frame_cursor + img_frames,
                    })
                    frame_cursor += img_frames

    # Globe fly-to at the end (if we have site coordinates)
    site_lat = visuals.get("site_lat")
    site_lon = visuals.get("site_lon")
    if site_lat is not None and site_lon is not None:
        flyto_frames = _seconds_to_frames(GLOBE_FLYTO_DURATION)
        visuals_list.append({
            "type": "globe_flyto",
            "startFrame": frame_cursor,
            "endFrame": frame_cursor + flyto_frames,
            "targetLat": site_lat,
            "targetLon": site_lon,
            "siteName": visuals.get("site_name", ""),
            "country": visuals.get("site_country", ""),
        })

    return visuals_list


def build_timeline(
    script: dict,
    audio_result: dict,
    manifest: dict,
    output_path: Path | None = None,
) -> dict:
    """Build a Remotion-compatible timeline from script + audio + assets.

    Args:
        script: Video script JSON from script_adapter.
        audio_result: Output from voiceover.generate_voiceover().
        manifest: Asset manifest from asset_collector.collect_assets().
        output_path: If provided, write timeline.json here.

    Returns:
        The timeline dict (Remotion inputProps).
    """
    word_timings = audio_result.get("word_timings", [])
    audio_files = audio_result.get("audio_files", [])

    segments_out: list[dict] = []
    frame_cursor = 0

    for i, segment in enumerate(script.get("segments", [])):
        seg_type = segment.get("type", "story")

        # Get audio duration for this segment
        timing = word_timings[i] if i < len(word_timings) else {"duration": 0, "words": []}
        audio_duration = timing.get("duration", 0)
        audio_file = audio_files[i] if i < len(audio_files) else ""

        if seg_type == "intro":
            duration_frames = max(
                _seconds_to_frames(INTRO_DURATION),
                _seconds_to_frames(audio_duration),
            )
            segments_out.append({
                "type": "intro",
                "startFrame": frame_cursor,
                "durationFrames": duration_frames,
                "audio": audio_file,
                "wordTimings": timing.get("words", []),
                "titleText": script.get("title", "This Week in Archaeology"),
                "dateRange": script.get("date_range", ""),
            })
            frame_cursor += duration_frames

        elif seg_type == "transition":
            duration_frames = max(
                _seconds_to_frames(TRANSITION_DURATION),
                _seconds_to_frames(audio_duration),
            )
            segments_out.append({
                "type": "transition",
                "startFrame": frame_cursor,
                "durationFrames": duration_frames,
                "audio": audio_file,
                "wordTimings": timing.get("words", []),
                "narration": segment.get("narration", ""),
            })
            frame_cursor += duration_frames

        elif seg_type == "outro":
            duration_frames = max(
                _seconds_to_frames(OUTRO_DURATION),
                _seconds_to_frames(audio_duration),
            )
            segments_out.append({
                "type": "outro",
                "startFrame": frame_cursor,
                "durationFrames": duration_frames,
                "audio": audio_file,
                "wordTimings": timing.get("words", []),
                "credits": script.get("credits", []),
                "sources": script.get("sources", []),
            })
            frame_cursor += duration_frames

        else:
            # Story segment — audio duration determines total length
            duration_frames = max(
                _seconds_to_frames(audio_duration + GLOBE_FLYTO_DURATION),
                _seconds_to_frames(10),  # Minimum 10 seconds
            )

            visuals = _allocate_visuals(segment, duration_frames, manifest, i)
            site_visuals = segment.get("visuals", {})

            lower_third = None
            if site_visuals.get("site_name"):
                lower_third = {
                    "siteName": site_visuals.get("site_name", ""),
                    "period": site_visuals.get("site_period_name", ""),
                    "country": site_visuals.get("site_country", ""),
                    "siteType": site_visuals.get("site_type", ""),
                }

            segments_out.append({
                "type": "story",
                "startFrame": frame_cursor,
                "durationFrames": duration_frames,
                "audio": audio_file,
                "wordTimings": timing.get("words", []),
                "visuals": visuals,
                "lowerThird": lower_third,
                "sectionHeading": segment.get("section_heading", ""),
            })
            frame_cursor += duration_frames

    timeline = {
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "totalDurationFrames": frame_cursor,
        "totalDurationSeconds": round(frame_cursor / FPS, 2),
        "segments": segments_out,
        "title": script.get("title", ""),
        "articleTitle": script.get("article_title", ""),
        "dateRange": script.get("date_range", ""),
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        logger.info(f"Timeline written to {output_path} ({frame_cursor} frames, {frame_cursor / FPS:.1f}s)")

    return timeline
