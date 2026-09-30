"""The episode workspace `<STUDIO_ASSETS>/episodes/<slug>/` (spec 4.1) and episode.json.

episode.json   {version, slug, paper: {request_id, slug} | null, topic_type, format,
                voice: {id, speed}, music: {file, credit, gainDb, duck} | null,
                title_candidates: [...], tags: [...], allow_ai_imagery}
casefile.json  script.json  review.html
voice/         <beat>.mp3, manifest.json, words.json
captures/      <id>.mp4|.png + <id>.json (manifest)
media/         stills the case file references
markers_check/ the marker crop checks (markers.py)
timeline.json
render/        public/ (per-render public dir), bundle/ (transient, node scripts), raw.mp4,
               <slug>.mp4, audit.json, thumbnails
package/       the upload package

`load_all` validates everything together: episode.json, the case file (icons from the
renderer's registry), the script against the case file, words and the current captures, a
Mapbox take's `country` against the site export (`country_problems`), the marker crop checks,
and the paper link: casefile.paper equals episode.json's paper (both null, or the same
{request_id, slug}), every paper_anchor is an evidence id of that paper's workspace
(<STUDIO_ASSETS>/papers/<id>/), and episode.json's paper slug is the slug the publish returned.

Every JSON file is read with the paper workspace's `read_json` (a missing file names its hint,
a syntax error is a StudioError naming the file), imported here as `load_json`, the name
render, package and cli_episode import from this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.studio import config, markers
from pipeline.studio.blocks import claim_icons, load_registry
from pipeline.studio.casefile import TOPIC_TYPES, CaseFile, load_casefile
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import published_slug
from pipeline.studio.paper.workspace import read_json as load_json
from pipeline.studio.script import (
    FORMATS,
    GLOBE_SCENES_OF,
    ScriptReport,
    is_number,
    place_at,
    validate_script,
)
from pipeline.studio.sites import resolve_capture_spec, site_country
from pipeline.utils.card_provenance import text_sha256

DEFAULT_VOICE = {"id": "English_expressive_narrator", "speed": 1.0}
DEFAULT_DUCK = {"underNarrationDb": -12, "attackFrames": 6, "releaseFrames": 24}
MUSIC_GAIN_DB = -8
DUCK_KEYS = frozenset(DEFAULT_DUCK)
EPISODE_KEYS = frozenset(
    {
        "version",
        "slug",
        "paper",
        "topic_type",
        "format",
        "voice",
        "music",
        "title_candidates",
        "tags",
        "allow_ai_imagery",
    }
)


@dataclass(frozen=True)
class EpisodeWorkspace:
    root: Path
    slug: str

    @property
    def config(self) -> Path:
        return self.root / "episode.json"

    @property
    def casefile(self) -> Path:
        return self.root / "casefile.json"

    @property
    def script(self) -> Path:
        return self.root / "script.json"

    @property
    def review(self) -> Path:
        return self.root / "review.html"

    @property
    def voice_dir(self) -> Path:
        return self.root / "voice"

    @property
    def words(self) -> Path:
        return self.voice_dir / "words.json"

    @property
    def captures_dir(self) -> Path:
        return self.root / "captures"

    @property
    def media_dir(self) -> Path:
        return self.root / "media"

    @property
    def timeline(self) -> Path:
        return self.root / "timeline.json"

    @property
    def render_dir(self) -> Path:
        return self.root / "render"

    @property
    def public_dir(self) -> Path:
        return self.render_dir / "public"

    @property
    def package_dir(self) -> Path:
        return self.root / "package"

    def paper_dir(self, request_id: str) -> Path:
        """The paper workspace beside the episodes: <STUDIO_ASSETS>/papers/<request_id>/."""
        return self.root.parent.parent / "papers" / request_id


def episode_workspace(slug: str) -> EpisodeWorkspace:
    return EpisodeWorkspace(config.episode_dir(slug), slug)


def init_episode(
    ws: EpisodeWorkspace,
    *,
    paper: dict[str, str] | None,
    topic_type: str,
    fmt: str,
    music: dict[str, Any] | None,
) -> dict[str, Any]:
    if ws.config.exists():
        raise StudioError(f"{ws.config} exists already; edit it instead of re-initialising")
    data = {
        "version": 1,
        "slug": ws.slug,
        "paper": paper,
        "topic_type": topic_type,
        "format": fmt,
        "voice": dict(DEFAULT_VOICE),
        "music": music,
        "title_candidates": [],
        "tags": [],
        "allow_ai_imagery": False,
    }
    problems = episode_problems(data, ws.slug)
    if problems:
        raise StudioError("; ".join(problems))
    for d in (ws.voice_dir, ws.captures_dir, ws.media_dir, ws.render_dir, ws.package_dir):
        d.mkdir(parents=True, exist_ok=True)
    ws.config.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def music_config(file: str, credit: str) -> dict[str, Any]:
    if not credit.strip():
        raise StudioError("the music bed needs its credit line (it goes into the description)")
    return {"file": file, "credit": credit, "gainDb": MUSIC_GAIN_DB, "duck": dict(DEFAULT_DUCK)}


def episode_problems(data: Any, slug: str) -> list[str]:
    if not isinstance(data, dict) or set(data) != EPISODE_KEYS:
        return [f"episode.json keys must be exactly {sorted(EPISODE_KEYS)}"]
    problems: list[str] = []
    if data["version"] != 1 or data["slug"] != slug:
        problems.append("episode.json version must be 1 and slug must match the directory")
    if data["topic_type"] not in TOPIC_TYPES:
        problems.append(f"topic_type must be one of {list(TOPIC_TYPES)}")
    if data["format"] not in FORMATS:
        problems.append(f"format must be one of {list(FORMATS)}")
    voice = data["voice"]
    if not isinstance(voice, dict) or set(voice) != {"id", "speed"}:
        problems.append("voice must be {id, speed}")
    paper = data["paper"]
    if paper is not None and (not isinstance(paper, dict) or set(paper) != {"request_id", "slug"}):
        problems.append("paper must be {request_id, slug} or null")
    elif paper is not None:
        config.check_request_id(paper["request_id"])
        config.check_slug(paper["slug"])
    if data["music"] is not None:
        problems.extend(music_problems(data["music"]))
    for key in ("title_candidates", "tags"):
        if not isinstance(data[key], list) or not all(isinstance(x, str) for x in data[key]):
            problems.append(f"{key} must be a list of strings")
    if not isinstance(data["allow_ai_imagery"], bool):
        problems.append("allow_ai_imagery must be a boolean")
    return problems


def music_problems(music: Any) -> list[str]:
    """The music bed as the renderer plays it: gainDb (<= 0) in pauses, gainDb +
    underNarrationDb (<= 0, relative) under each narration span, integer frame ramps."""
    if not isinstance(music, dict) or set(music) != {"file", "credit", "gainDb", "duck"}:
        return ["music must be {file, credit, gainDb, duck} or null"]
    problems: list[str] = []
    file = music["file"]
    if (
        not isinstance(file, str)
        or not file
        or file in (".", "..")
        or any(c in file for c in "/\\:")
    ):
        problems.append("music.file must be a bare file name (in video-assets/music/)")
    if not isinstance(music["credit"], str) or not music["credit"].strip():
        problems.append("music.credit must name the track (it goes into the description)")
    if not is_number(music["gainDb"]) or music["gainDb"] > 0:
        problems.append("music.gainDb must be a number <= 0")
    duck = music["duck"]
    if not isinstance(duck, dict) or set(duck) != DUCK_KEYS:
        problems.append(f"music.duck keys must be exactly {sorted(DUCK_KEYS)}")
        return problems
    if not is_number(duck["underNarrationDb"]) or duck["underNarrationDb"] > 0:
        problems.append("music.duck.underNarrationDb must be a number <= 0 (relative to gainDb)")
    for key in ("attackFrames", "releaseFrames"):
        value = duck[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"music.duck.{key} must be an integer >= 0")
    return problems


def load_episode(ws: EpisodeWorkspace) -> dict[str, Any]:
    data = load_json(ws.config, f"run `episode init {ws.slug}`")
    problems = episode_problems(data, ws.slug)
    if problems:
        raise StudioError("; ".join(problems))
    return data


def load_words(ws: EpisodeWorkspace) -> dict[str, Any] | None:
    return load_json(ws.words, "") if ws.words.exists() else None


def capture_spec_sha256(spec: dict[str, Any]) -> str:
    """The hash `episode capture` stores with a manifest: which spec recorded it (the
    resolved spec: sites.resolve_capture_spec)."""
    return text_sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False))


def load_captures(ws: EpisodeWorkspace, script: Any) -> dict[str, dict[str, Any]] | None:
    """{id: manifest} of the captures recorded from the script's current specs, or None.

    A manifest whose spec_sha256 differs from the current spec with its id (the spec was
    edited after recording, or a distribution's site export changed: the hash is of the
    resolved spec, sites.resolve_capture_spec), or whose id is no longer declared, is left
    out: that capture counts as not recorded, so its checks wait and `timeline` refuses it.
    """
    captures = script.get("captures") if isinstance(script, dict) else None
    specs = {
        c["id"]: c for c in captures or [] if isinstance(c, dict) and isinstance(c.get("id"), str)
    }
    paths = sorted(ws.captures_dir.glob("*.json")) if ws.captures_dir.exists() else []
    out = {}
    for path in paths:
        manifest = load_json(path, "")
        spec = specs.get(manifest["id"])
        if spec is None:
            continue
        if manifest.get("spec_sha256") == capture_spec_sha256(resolve_capture_spec(spec)):
            out[manifest["id"]] = manifest
    return out or None


def country_problems(script: Any, cf: CaseFile) -> list[str]:
    """C7: the `country` a Mapbox fly-in or orbit highlights is the site export's country of
    the case-file place the take centres on. script.py requires that place and its site_id
    (and reports a malformed spec); only such takes read the export (sites.site_country)."""
    captures = script.get("captures") if isinstance(script, dict) else None
    problems: list[str] = []
    for spec in captures or []:
        if not (
            isinstance(spec, dict)
            and spec.get("kind") == "globe"
            and spec.get("scene") in GLOBE_SCENES_OF["MapboxFlyover"]
            and isinstance(spec.get("country"), str)
        ):
            continue
        place = place_at(cf, spec)
        if place is None or place.site_id is None:
            continue
        if site_country(spec["id"], place.site_id) != spec["country"]:
            problems.append(
                f"capture {spec['id']}: country {spec['country']} is not the site export's "
                f"country of place {place.id}"
            )
    return problems


def paper_problems(ws: EpisodeWorkspace, episode: dict[str, Any], cf: CaseFile) -> list[str]:
    """The case file's paper and paper anchors against episode.json and the paper workspace."""
    paper = episode["paper"]
    problems: list[str] = []
    # Either side may be the one that names no paper: a paper episode's case file must name
    # it, and a paper-less episode's case file must not.
    linked = (
        None if cf.paper is None else {"request_id": cf.paper.request_id, "slug": cf.paper.slug}
    )
    if linked != paper:
        problems.append("casefile.json paper differs from episode.json paper")
    anchored = [e for e in cf.evidence if e.paper_anchor is not None]
    if paper is None:
        problems.extend(
            f"{e.id}: paper_anchor {e.paper_anchor} needs the paper in episode.json"
            for e in anchored
        )
        return problems
    root = ws.paper_dir(paper["request_id"])
    published = published_slug(root / "publish_outcome.json")
    if published is not None and published != paper["slug"]:
        problems.append(
            f"episode.json paper slug {paper['slug']!r} is not the published slug {published!r}"
        )
    if not anchored:
        return problems
    evidence_file = root / "evidence.json"
    if not evidence_file.exists():
        problems.extend(
            f"{e.id}: paper_anchor cannot be verified (no paper workspace)" for e in anchored
        )
        return problems
    entries = load_json(evidence_file, "")
    # Claude's working file in the paper workspace: mid-edit it can have any shape.
    if not isinstance(entries, list) or not all(
        isinstance(x, dict) and isinstance(x.get("id"), str) for x in entries
    ):
        problems.extend(
            f"{e.id}: paper_anchor cannot be verified: papers/{paper['request_id']}/evidence.json "
            "is not a list of evidence entries {id, ...}"
            for e in anchored
        )
        return problems
    ids = {x["id"] for x in entries}
    problems.extend(
        f"{e.id}: paper_anchor {e.paper_anchor} is not an evidence id of paper "
        f"{paper['request_id']}"
        for e in anchored
        if e.paper_anchor not in ids
    )
    return problems


@dataclass(frozen=True)
class Loaded:
    episode: dict[str, Any]
    casefile: CaseFile
    script: dict[str, Any]
    words: dict[str, Any] | None
    captures: dict[str, dict[str, Any]] | None
    report: ScriptReport


def load_case(
    ws: EpisodeWorkspace, episode: dict[str, Any], registry: dict[str, dict[str, Any]]
) -> CaseFile:
    """casefile.json, validated with the renderer's icons and the episode's AI-imagery switch."""
    return load_casefile(
        ws.casefile, icons=claim_icons(registry), allow_ai_imagery=episode["allow_ai_imagery"]
    )


def load_all(ws: EpisodeWorkspace, registry: dict[str, dict[str, Any]] | None = None) -> Loaded:
    episode = load_episode(ws)
    registry = registry if registry is not None else load_registry()
    cf = load_case(ws, episode, registry)
    script = load_json(ws.script, "write script.json")
    words = load_words(ws)
    captures = load_captures(ws, script)
    report = validate_script(
        script,
        cf,
        registry,
        slug=ws.slug,
        fmt=episode["format"],
        words=words,
        captures=captures,
    )
    if isinstance(script, dict) and script.get("voice") != episode["voice"]:
        report.errors.append("script.json voice differs from episode.json voice")
    report.errors.extend(country_problems(script, cf))
    report.errors.extend(paper_problems(ws, episode, cf))
    report.errors.extend(markers.marker_problems(ws.root, cf))
    return Loaded(episode, cf, script, words, captures, report)


def require_valid(loaded: Loaded, *, final: bool) -> None:
    """Refuse on script errors; `final` also refuses deferred checks (timeline/render)."""
    if loaded.report.errors:
        raise StudioError("script.json: " + "; ".join(loaded.report.errors))
    if final and loaded.report.deferred:
        raise StudioError("not ready: " + "; ".join(loaded.report.deferred))
