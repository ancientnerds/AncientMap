"""`episode timeline`: script + words + captures + case file -> timeline.json (spec 4.7).

    {"version": 1, "fps": 60, "width": 1920, "height": 1080, "durationInFrames": N,
     "audio": {"narration": [{"src": "voice/b01.mp3", "from": 21}],
               "music": {"src": "music/<file>", "gainDb": -8,
                         "duck": {"underNarrationDb": -12, "attackFrames": 6,
                                  "releaseFrames": 24}} | null},
     "scenes": [{"id": "b01", "from": 0, "durationInFrames": 357, "block": "PhotoPlate",
                 "props": {...resolved...}, "cues": [{"frame": 212, "do": "show", "target": "mk1"}]}],
     "captions": [{"text": "THIS", "from": 21, "to": 45}],   (display token uppercased,
                                                              punctuation kept: "TONNES.")
     "ticker": {"evidence": [{"frame": 0, "n": 1}]},
     "chapters": [{"title": "...", "frame": 0}],
     "credits": [{"sceneId": "b03", "text": "© Mapbox © Maxar"}],
     "thumbnails": [{"frame": 214, "text": "Who moved it?"}, ... exactly 3]}

Every frame is counted at script.FPS. A scene lasts `script.scene_frames` frames,
ceil(max(min_s, lead + speech + tail) * fps), the count `episode script` checks a clip against;
its narration starts after the lead (script.narration_start); cues and captions are placed on
the word timings of the display text (script.word_start; a cue on the word
`script.cue_word_index` finds, script.cue_frame: whole display words, never a match inside a
longer word). A cue is exactly {frame, do, target} plus `value` for status and meter, and lies
inside its scene.
Captions exist only for hook beats. Every path is relative to the per-render public dir.
The word timings must belong to the current display text and voice/<beat>.mp3 to the current
spoken text, voice and speed (voice.stale_beats); anything else is `episode voice` again.
The three thumbnail candidates (owner decisions 24, 25; still.ts renders each with its teaser)
land at `scene.from + floor(at * durationInFrames)` of their beat, never where they could show
the answer (thumbnail_problem).
"""

from __future__ import annotations

import json
import math
from typing import Any

from pipeline.studio.casefile import CaseFile, capture_ids_in, refs_in, resolve_refs, resolved
from pipeline.studio.episode import EpisodeWorkspace, load_all, require_valid
from pipeline.studio.errors import StudioError
from pipeline.studio.script import (
    FPS,
    ROLES,
    VALUE_VERBS,
    cue_frame,
    is_verdict_cue,
    narration_start,
    scene_frames,
    word_start,
    word_timings_match,
)
from pipeline.studio.voice import stale_beats

WIDTH = 1920
HEIGHT = 1080


def verdict_frame(timeline: dict[str, Any]) -> int | None:
    """The first frame that shows an answer (script.is_verdict_cue: a claim status other than
    pending, a meter move)."""
    frames = [
        cue["frame"] for scene in timeline["scenes"] for cue in scene["cues"] if is_verdict_cue(cue)
    ]
    return min(frames) if frames else None


def thumbnail_problem(timeline: dict[str, Any], roles: dict[str, str], frame: int) -> str | None:
    """Why a thumbnail at `frame` could show the answer (owner decision 24), or None. `roles`
    maps beat ids to their script role."""
    total = timeline["durationInFrames"]
    if isinstance(frame, bool) or not isinstance(frame, int) or not 0 <= frame < total:
        return f"frame {frame} is not a frame of the episode (0 to {total - 1})"
    scene = next(
        s for s in timeline["scenes"] if s["from"] <= frame < s["from"] + s["durationInFrames"]
    )
    role = roles.get(scene["id"])
    if role in ROLES:
        return (
            f"frame {frame} lies in beat {scene['id']} ({role}): a thumbnail never shows the answer"
        )
    first = verdict_frame(timeline)
    if first is not None and frame >= first:
        return (
            f"frame {frame} is at or after the first verdict cue (frame {first}): a thumbnail "
            "never shows the answer"
        )
    return None


def compile_timeline(
    script: dict[str, Any],
    words: dict[str, Any],
    cf: CaseFile,
    captures: dict[str, dict[str, Any]],
    episode: dict[str, Any],
) -> dict[str, Any]:
    from pipeline.video.shorts_captions import Word, display_text

    entities = resolved(cf)
    media_ids = {m.id for m in cf.media}
    scenes: list[dict[str, Any]] = []
    narration: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    credits: list[dict[str, str]] = []
    ticker: list[dict[str, int]] = [{"frame": 0, "n": 0}]
    seen_evidence: set[str] = set()
    starts: dict[str, int] = {}
    cursor = 0
    for beat in script["beats"]:
        bid = beat["id"]
        if bid not in words:
            raise StudioError(f"{bid}: no word timings; run `episode voice` first")
        timing = words[bid]
        if not word_timings_match(beat, timing):
            raise StudioError(
                f"{bid}: words.json was aligned to another display text; run `episode voice`"
            )
        duration = scene_frames(beat, float(timing["duration_s"]))
        voice_from = cursor + narration_start(beat)
        starts[bid] = cursor
        narration.append({"src": f"voice/{bid}.mp3", "from": voice_from})
        aligned = [Word(w["w"], float(w["s"]), float(w["e"])) for w in timing["words"]]
        cues = []
        for n, cue in enumerate(beat["cues"], start=1):
            frame = cursor + cue_frame(beat, timing, cue["at_word"])
            if not cursor <= frame < cursor + duration:
                raise StudioError(
                    f"{bid} cue {n}: frame {frame} outside the scene [{cursor}, {cursor + duration})"
                )
            out = {"frame": frame, "do": cue["do"], "target": cue["target"]}
            if cue["do"] in VALUE_VERBS:
                out["value"] = cue["value"]
            cues.append(out)
        props = beat["visual"]["props"]
        scenes.append(
            {
                "id": bid,
                "from": cursor,
                "durationInFrames": duration,
                "block": beat["visual"]["block"],
                "props": resolve_refs(props, entities, captures),
                "cues": cues,
            }
        )
        if beat.get("hook", False):
            for index, w in enumerate(aligned):
                if display_text(w.text):
                    start = cursor + word_start(beat, timing, index)
                    captions.append(
                        {
                            "text": w.text.upper(),
                            "from": start,
                            "to": max(start + 1, voice_from + round(w.end * FPS)),
                        }
                    )
        new = set(beat["evidence"]) - seen_evidence
        if new:
            seen_evidence |= new
            if ticker[-1]["frame"] == cursor:
                ticker[-1]["n"] = len(seen_evidence)
            else:
                ticker.append({"frame": cursor, "n": len(seen_evidence)})
        texts: list[str] = []
        if beat["visual"].get("credit"):
            texts.append(beat["visual"]["credit"])
        for cid in capture_ids_in(props):
            texts.extend(captures[cid]["credits"])
        for ref in refs_in(props):
            if ref in media_ids:
                m = entities[ref]
                texts.append(f"Photo: {m['attribution']} ({m['license']})")
        credits.extend({"sceneId": bid, "text": t} for t in dict.fromkeys(texts))
        cursor += duration
    for a, b in zip(captions, captions[1:], strict=False):
        a["to"] = min(a["to"], b["from"])
    music = episode["music"]
    compiled = {
        "version": 1,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "durationInFrames": cursor,
        "audio": {
            "narration": narration,
            "music": None
            if music is None
            else {
                "src": f"music/{music['file']}",
                "gainDb": music["gainDb"],
                "duck": music["duck"],
            },
        },
        "scenes": scenes,
        "captions": captions,
        "ticker": {"evidence": ticker},
        "chapters": [{"title": c["title"], "frame": starts[c["beat"]]} for c in script["chapters"]],
        "credits": credits,
    }
    by_id = {s["id"]: s for s in scenes}
    roles = {b["id"]: b["role"] for b in script["beats"] if "role" in b}
    thumbnails = []
    for i, candidate in enumerate(script["thumbnails"]):
        scene = by_id[candidate["beat"]]
        frame = scene["from"] + math.floor(candidate["at"] * scene["durationInFrames"])
        problem = thumbnail_problem(compiled, roles, frame)
        if problem is not None:
            raise StudioError(f"thumbnails[{i}]: {problem}")
        thumbnails.append({"frame": frame, "text": candidate["text"]})
    compiled["thumbnails"] = thumbnails
    return compiled


def build_timeline(ws: EpisodeWorkspace) -> dict[str, Any]:
    loaded = load_all(ws)
    require_valid(loaded, final=False)
    # Before the deferred checks: load_all defers a beat whose voice is stale one by one, and
    # stale_beats says the same once (a manifest that does not exist, an mp3 that is missing).
    if loaded.words is not None:
        stale = stale_beats(ws, loaded.script)
        if stale:
            raise StudioError("; ".join(stale))
    require_valid(loaded, final=True)
    if loaded.words is None:
        raise StudioError("voice/words.json is missing: run `episode voice` first")
    captures = loaded.captures if loaded.captures is not None else {}
    timeline = compile_timeline(
        loaded.script, loaded.words, loaded.casefile, captures, loaded.episode
    )
    ws.timeline.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    return timeline
