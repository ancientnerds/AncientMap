"""`episode package`: the upload package (spec 4.9). Upload itself stays off.

package/
    <slug>.mp4              the audited render
    <slug>.srt              display words, cues of at most 6 words broken at sentence ends,
                            never overlapping
    description.txt         <= 5,000 UTF-8 bytes, no < or >: hook sentence, chapters, evidence
                            timestamps with paper anchor links, image/map/music credits, the AI
                            disclosure
    titles.txt              the title candidates from episode.json (the owner picks)
    thumbnail_<K>.jpg       K = 1, 2, 3: the thumbnail candidates for YouTube's A/B test
                            (owner decisions 24, 25), 1280x720, under 2 MB; one of them is
                            also the paper page's video poster (`episode register-youtube
                            --poster K`, owner decision 13)
    thumbnail_<K>_3840.png  their 3840x2160 masters
    youtube.json            {title, description, tags, categoryId: 27, containsSyntheticMedia,
                             madeForKids: false, chapters: [{title, start_s}], captions,
                             thumbnails: ["thumbnail_1.jpg", "thumbnail_2.jpg",
                             "thumbnail_3.jpg"]}
    evidence_timestamps.json {ev-NN: seconds} for `episode register-youtube`
A failed or missing render audit writes package/FAILED.json with the reasons and stops. The
package is built only from the audited render and the files it was rendered from:
render/ledger.json's `timeline_sha256` and `words_sha256` must be timeline.json's and
voice/words.json's, its row's `script_sha256`, `casefile_sha256` and `video_sha256`
script.json's, casefile.json's and render/<slug>.mp4's, and episode.json's music file the one
the timeline mixed. A script, case file, voice or music edited after the render (the SRT, the
hook sentence, the evidence lines and the credits would describe another video), a recompiled
timeline or another video means `episode render` again; titles, tags and the wording of the
music credit may change after it.
"""

from __future__ import annotations

import json
from typing import Any

from pipeline.lyra.text_sentences import split_sentences
from pipeline.research_html_renderer import video_clock
from pipeline.studio.casefile import CaseFile, refs_in
from pipeline.studio.episode import EpisodeWorkspace, load_all, load_json, require_valid
from pipeline.studio.errors import StudioError
from pipeline.studio.render import CANDIDATES, link_or_copy, thumbnail_files
from pipeline.studio.script import CHAPTER_MIN_S as SCRIPT_CHAPTER_MIN_S
from pipeline.studio.script import CHAPTERS_MIN_FULL
from pipeline.utils.slugs import BASE_URL

UTM = "utm_source=youtube&utm_medium=longform"
DISCLOSURE = (
    "Narration: AI-generated voice (MiniMax speech-2.8-hd). Research: Theo (AI). "
    "Script: Claude (AI)."
)
DESCRIPTION_MAX_BYTES = 5000
TITLE_MAX_CHARS = 100
TAGS_MAX_CHARS = 500
THUMB_JPEG_MAX_BYTES = 2 * 1024 * 1024
CATEGORY_ID = 27
#: YouTube's chapter rule, the one `episode check` applies (script._chapters).
CHAPTER_MIN_S = SCRIPT_CHAPTER_MIN_S
CHAPTERS_MIN = CHAPTERS_MIN_FULL


def global_words(
    script: dict[str, Any], words: dict[str, Any], timeline: dict[str, Any]
) -> list[Any]:
    from pipeline.video.shorts_captions import Word

    fps = timeline["fps"]
    starts = {n["src"]: n["from"] for n in timeline["audio"]["narration"]}
    out = []
    for beat in script["beats"]:
        offset = starts[f"voice/{beat['id']}.mp3"] / fps
        out.extend(
            Word(w["w"], round(offset + w["s"], 3), round(offset + w["e"], 3))
            for w in words[beat["id"]]["words"]
        )
    return out


def srt(script: dict[str, Any], words: dict[str, Any], timeline: dict[str, Any]) -> str:
    from pipeline.video.shorts_captions import srt_text

    all_words = global_words(script, words, timeline)
    for a, b in zip(all_words, all_words[1:], strict=False):
        if b.start < a.end:
            raise StudioError(
                f"word timings overlap at {a.text!r}/{b.text!r} ({a.end} > {b.start})"
            )
    return srt_text(all_words)


def chapters(timeline: dict[str, Any], fmt: str) -> list[dict[str, Any]]:
    """[{title, start_s}] for YouTube; [] for a slice. Raises when the rules are broken."""
    if fmt == "slice":
        return []
    fps = timeline["fps"]
    marks = timeline["chapters"]
    if len(marks) < CHAPTERS_MIN or marks[0]["frame"] != 0:
        raise StudioError(
            f"YouTube chapters need a first entry at 0:00 and at least {CHAPTERS_MIN}"
        )
    ends = [m["frame"] for m in marks[1:]] + [timeline["durationInFrames"]]
    for mark, end in zip(marks, ends, strict=True):
        if (end - mark["frame"]) / fps < CHAPTER_MIN_S:
            raise StudioError(f"chapter {mark['title']!r} is shorter than {CHAPTER_MIN_S:g} s")
    return [{"title": m["title"], "start_s": m["frame"] // fps} for m in marks]


def evidence_timestamps(
    script: dict[str, Any], cf: CaseFile, timeline: dict[str, Any]
) -> dict[str, int]:
    """{paper anchor ev-NN: whole seconds of the first scene that shows it}."""
    anchor = {e.id: e.paper_anchor for e in cf.evidence if e.paper_anchor}
    starts = {s["id"]: s["from"] for s in timeline["scenes"]}
    out: dict[str, int] = {}
    for beat in script["beats"]:
        for eid in beat["evidence"]:
            ev = anchor.get(eid)
            if ev is not None and ev not in out:
                out[ev] = starts[beat["id"]] // timeline["fps"]
    return out


def _used_media(script: dict[str, Any], cf: CaseFile) -> list[Any]:
    ids = {r for b in script["beats"] for r in refs_in(b["visual"]["props"])}
    return [m for m in cf.media if m.id in ids]


def paper_url(paper_slug: str, anchor: str | None = None) -> str:
    url = f"{BASE_URL}/research/{paper_slug}?{UTM}"
    return f"{url}#{anchor}" if anchor else url


def description(
    script: dict[str, Any],
    cf: CaseFile,
    timeline: dict[str, Any],
    episode: dict[str, Any],
    chapter_list: list[dict[str, Any]],
    stamps: dict[str, int],
) -> str:
    hook_beats = [b for b in script["beats"] if b.get("hook", False)] or script["beats"][:1]
    lines = [split_sentences(hook_beats[0]["display"])[0].strip(), ""]
    if chapter_list:
        lines.append("Chapters")
        lines.extend(f"{video_clock(c['start_s'])} {c['title']}" for c in chapter_list)
        lines.append("")
    paper = episode["paper"]
    if paper is not None and stamps:
        by_anchor = {e.paper_anchor: e for e in cf.evidence if e.paper_anchor}
        lines.append(f"Evidence (the full paper: {paper_url(paper['slug'])})")
        for ev, sec in sorted(stamps.items(), key=lambda kv: kv[1]):
            lines.append(
                f"{video_clock(sec)} {by_anchor[ev].statement} {paper_url(paper['slug'], ev)}"
            )
        lines.append("")
    credits = [
        f"Image: {m.attribution} ({m.license}) {m.source_url}" for m in _used_media(script, cf)
    ]
    credits += [c["text"] for c in timeline["credits"] if not c["text"].startswith("Photo:")]
    lines.append("Credits")
    lines.extend(dict.fromkeys(credits))
    if episode["music"] is not None:
        lines.append(episode["music"]["credit"])
    lines.append(DISCLOSURE)
    text = "\n".join(lines).replace("<", "").replace(">", "")
    size = len(text.encode("utf-8"))
    if size > DESCRIPTION_MAX_BYTES:
        raise StudioError(
            f"description is {size} UTF-8 bytes (max {DESCRIPTION_MAX_BYTES}); shorten it"
        )
    return text


def check_title(title: str) -> str:
    """One YouTube title, measured as it is sent: not blank, at most TITLE_MAX_CHARS
    characters, no < or >. The package's candidates and register-youtube's --title share it."""
    if not title.strip() or len(title) > TITLE_MAX_CHARS or "<" in title or ">" in title:
        raise StudioError(
            f"a title must be 1-{TITLE_MAX_CHARS} characters without < or >: {title!r}"
        )
    return title


def check_titles(titles: list[str]) -> list[str]:
    if not titles:
        raise StudioError("episode.json title_candidates is empty")
    for title in titles:
        check_title(title)
    return titles


def check_tags(tags: list[str]) -> list[str]:
    total = sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)
    if total > TAGS_MAX_CHARS:
        raise StudioError(f"tags take {total} characters (max {TAGS_MAX_CHARS})")
    return tags


def package_thumbnail(candidate: int) -> str:
    """The upload file of thumbnail candidate K: package/thumbnail_<K>.jpg (1280x720)."""
    return f"thumbnail_{candidate}.jpg"


def _thumbnail_copies() -> dict[str, str]:
    """render/ name -> package/ name of every thumbnail file (the masters keep their names)."""
    copies: dict[str, str] = {}
    for k in CANDIDATES:
        master, jpeg = thumbnail_files(k)
        copies[master] = master
        copies[jpeg] = package_thumbnail(k)
    return copies


def _check_thumbnails(ws: EpisodeWorkspace) -> None:
    from PIL import Image

    for k in CANDIDATES:
        master, jpeg = thumbnail_files(k)
        for name, size in ((master, (3840, 2160)), (jpeg, (1280, 720))):
            path = ws.render_dir / name
            if not path.exists():
                raise StudioError(f"render/{name} is missing: run `episode render`")
            with Image.open(path) as img:
                if img.size != size:
                    raise StudioError(
                        f"{name} is {img.size[0]}x{img.size[1]}, needs {size[0]}x{size[1]}"
                    )
        if (ws.render_dir / jpeg).stat().st_size >= THUMB_JPEG_MAX_BYTES:
            raise StudioError(f"{jpeg} must stay under 2 MB")


def _require_audit(ws: EpisodeWorkspace) -> None:
    path = ws.render_dir / "audit.json"
    reasons: list[str] = []
    if not path.exists():
        reasons.append("render/audit.json is missing")
    else:
        report = json.loads(path.read_text(encoding="utf-8"))
        reasons = [f"{c['name']}: {c['value']}" for c in report["checks"] if not c["ok"]]
    if reasons:
        ws.package_dir.mkdir(parents=True, exist_ok=True)
        (ws.package_dir / "FAILED.json").write_text(
            json.dumps({"status": "failed", "reasons": reasons}, indent=2), encoding="utf-8"
        )
        raise StudioError(f"package failed: {reasons}")


def _require_audited_render(ws: EpisodeWorkspace) -> None:
    """timeline.json, script.json, casefile.json, voice/words.json and render/<slug>.mp4 are
    exactly what the audited render recorded in render/ledger.json."""
    from pipeline.video.shorts_ledger import sha256_file

    ledger = load_json(ws.render_dir / "ledger.json", "run `episode render` first")
    row = ledger["row"]
    inputs = (
        ("timeline.json", ws.timeline, ledger["timeline_sha256"]),
        ("script.json", ws.script, row["script_sha256"]),
        ("casefile.json", ws.casefile, row["casefile_sha256"]),
        ("voice/words.json", ws.words, ledger["words_sha256"]),
    )
    for name, path, recorded in inputs:
        if not path.exists():
            raise StudioError(f"{name} is missing since the render; run `episode render` again")
        if sha256_file(path) != recorded:
            raise StudioError(f"{name} changed since the render; run `episode render` again")
    video = ws.render_dir / f"{ws.slug}.mp4"
    if not video.exists() or sha256_file(video) != row["video_sha256"]:
        raise StudioError(
            f"render/{ws.slug}.mp4 is not the audited render; run `episode render` again"
        )


def _require_rendered_music(episode: dict[str, Any], timeline: dict[str, Any]) -> None:
    """episode.json credits the track the rendered timeline mixed (the credit's wording, the
    titles and the tags stay the owner's to change after a render)."""
    music, mixed = episode["music"], timeline["audio"]["music"]
    wanted = "none" if music is None else f"music/{music['file']}"
    rendered = "none" if mixed is None else mixed["src"]
    if wanted != rendered:
        raise StudioError(
            f"episode.json music is {wanted}, the render mixed {rendered}; "
            "run `episode render` again"
        )


def build_package(ws: EpisodeWorkspace) -> dict[str, Any]:
    _require_audit(ws)
    _require_audited_render(ws)
    # _require_audited_render refused a missing timeline.json or voice/words.json.
    loaded = load_all(ws)
    require_valid(loaded, final=True)
    timeline = load_json(ws.timeline, "")
    episode, script, cf = loaded.episode, loaded.script, loaded.casefile
    _require_rendered_music(episode, timeline)
    _check_thumbnails(ws)
    chapter_list = chapters(timeline, episode["format"])
    stamps = evidence_timestamps(script, cf, timeline)
    text = description(script, cf, timeline, episode, chapter_list, stamps)
    titles = check_titles(episode["title_candidates"])
    tags = check_tags(episode["tags"])
    pkg = ws.package_dir
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "FAILED.json").unlink(missing_ok=True)
    video = pkg / f"{ws.slug}.mp4"
    video.unlink(missing_ok=True)
    link_or_copy(ws.render_dir / f"{ws.slug}.mp4", video)
    for name, packaged in _thumbnail_copies().items():
        (pkg / packaged).unlink(missing_ok=True)
        link_or_copy(ws.render_dir / name, pkg / packaged)
    (pkg / f"{ws.slug}.srt").write_text(srt(script, loaded.words, timeline), encoding="utf-8")
    (pkg / "description.txt").write_text(text, encoding="utf-8")
    (pkg / "titles.txt").write_text("\n".join(titles) + "\n", encoding="utf-8")
    (pkg / "evidence_timestamps.json").write_text(json.dumps(stamps, indent=2), encoding="utf-8")
    youtube = {
        "title": titles[0],
        "description": text,
        "tags": tags,
        "categoryId": CATEGORY_ID,
        "containsSyntheticMedia": any(m.ai_generated for m in _used_media(script, cf)),
        "madeForKids": False,
        "chapters": chapter_list,
        "captions": f"{ws.slug}.srt",
        "thumbnails": [package_thumbnail(k) for k in CANDIDATES],
    }
    (pkg / "youtube.json").write_text(
        json.dumps(youtube, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"package": str(pkg), "description_bytes": len(text.encode("utf-8"))}
