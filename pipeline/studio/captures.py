"""`episode capture`: run every capture the script declares and keep its manifest.

Contract with pipeline/studio/capture (stream D), importable from the package itself:

    record_platform(episode_dir: Path, spec: dict) -> dict   kind "platform"
    record_globe(episode_dir: Path, spec: dict) -> dict      kind "globe"
    capture_source(episode_dir: Path, spec: dict) -> dict    kind "source"
    mapbox_topdown(episode_dir: Path, spec: dict) -> dict    kind "mapbox_topdown"

`spec` is the script's capture entry ({"id", "kind", ...kind-specific keys}). Each function
writes its media under <episode_dir>/captures/ and returns the manifest

    {"id": spec id, "kind": spec kind, "path": "captures/<file>" (relative to episode_dir),
     "fps": number | null, "duration_s": number | null (null for stills),
     "width": int, "height": int, "events": [{"t": seconds, "name": str, ...}],
     "credits": [str, ...]}

which this step validates and stores as captures/<id>.json together with `spec_sha256`, the
hash of the spec that recorded it: `episode.load_captures` ignores a manifest whose spec was
edited since (that capture counts as not recorded). The recorder receives the resolved spec
(sites.resolve_capture_spec: a distribution's `site_ids` become unlabelled places at the site
export's coordinates, owner decision 15), and `spec_sha256` hashes that spec. A retake first
removes the capture's stored manifest, so a take that fails, is refused or is interrupted
leaves it "not recorded" instead of an old manifest beside new media; a recorder's failure is
re-raised as `capture <id>: <message>`. `path` follows the renderer's public-dir rule
(casefile.asset_path_problem) under captures/. Every string the renderer draws from a manifest
(glyphs.capture_strings: credits, place and pin labels; owner decision 32) must lie in the
brand fonts' glyphs (the renderer's checkBlocks rule): a credit the renderer cannot draw is
refused here, not after the render started, while a URL and a page's own <title> (not drawn:
SourceViewer and the source credit show only the ASCII hostname) may hold any character. Playwright and the recorder are imported only inside those functions
(local-only dependencies).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pipeline.studio.casefile import asset_path_problem
from pipeline.studio.episode import EpisodeWorkspace, capture_spec_sha256
from pipeline.studio.errors import StudioError
from pipeline.studio.glyphs import capture_strings, glyph_problem
from pipeline.studio.sites import resolve_capture_spec

Recorder = Callable[[Path, dict[str, Any]], dict[str, Any]]
KIND_FUNCTIONS = {
    "platform": "record_platform",
    "globe": "record_globe",
    "source": "capture_source",
    "mapbox_topdown": "mapbox_topdown",
}
MANIFEST_KEYS = frozenset(
    {"id", "kind", "path", "fps", "duration_s", "width", "height", "events", "credits"}
)


def default_recorders() -> dict[str, Recorder]:
    from pipeline.studio import capture

    return {kind: getattr(capture, name) for kind, name in KIND_FUNCTIONS.items()}


def _number_or_null(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def manifest_problems(manifest: Any, spec: dict[str, Any], episode_root: Path) -> list[str]:
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        return [f"manifest keys must be exactly {sorted(MANIFEST_KEYS)}"]
    problems: list[str] = []
    if manifest["id"] != spec["id"] or manifest["kind"] != spec["kind"]:
        problems.append("manifest id/kind differ from the capture spec")
    path = str(manifest["path"])
    path_problem = asset_path_problem(path)
    if path_problem is not None:
        problems.append(path_problem)
    elif not path.startswith("captures/"):
        problems.append("path must be relative under captures/")
    elif not (episode_root / path).is_file():
        problems.append(f"{path} does not exist")
    if not _number_or_null(manifest["fps"]) or not _number_or_null(manifest["duration_s"]):
        problems.append("fps and duration_s must be numbers or null")
    if (manifest["fps"] is None) != (manifest["duration_s"] is None):
        problems.append("a still has neither fps nor duration_s; a clip has both")
    for key in ("width", "height"):
        if (
            not isinstance(manifest[key], int)
            or isinstance(manifest[key], bool)
            or manifest[key] <= 0
        ):
            problems.append(f"{key} must be a positive integer")
    events = manifest["events"]
    if not isinstance(events, list) or not all(
        isinstance(e, dict)
        and _number_or_null(e.get("t"))
        and e.get("t") is not None
        and isinstance(e.get("name"), str)
        for e in events
    ):
        problems.append("events must be [{t: seconds, name: str, ...}]")
    if not isinstance(manifest["credits"], list) or not all(
        isinstance(c, str) for c in manifest["credits"]
    ):
        problems.append("credits must be a list of strings")
    if not problems:
        problems.extend(
            p
            for at, text in capture_strings(manifest, "manifest")
            if (p := glyph_problem(at, text))
        )
    return problems


def record_captures(
    ws: EpisodeWorkspace,
    script: dict[str, Any],
    *,
    only: list[str] | None = None,
    recorders: dict[str, Recorder] | None = None,
) -> dict[str, dict[str, Any]]:
    specs = script.get("captures", [])
    known = {s["id"] for s in specs}
    unknown = sorted(set(only or []) - known)
    if unknown:
        raise StudioError(f"no such captures in script.json: {unknown}")
    chosen = [s for s in specs if only is None or s["id"] in only]
    if not chosen:
        raise StudioError("script.json declares no captures to record")
    table = recorders if recorders is not None else default_recorders()
    ws.captures_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict[str, Any]] = {}
    for spec in chosen:
        resolved = resolve_capture_spec(spec)
        (ws.captures_dir / f"{spec['id']}.json").unlink(missing_ok=True)
        try:
            manifest = table[spec["kind"]](ws.root, resolved)
        except StudioError as exc:
            raise StudioError(f"capture {spec['id']}: {exc}") from exc
        problems = manifest_problems(manifest, resolved, ws.root)
        if problems:
            raise StudioError(f"capture {spec['id']}: " + "; ".join(problems))
        stored = {**manifest, "spec_sha256": capture_spec_sha256(resolved)}
        (ws.captures_dir / f"{spec['id']}.json").write_text(
            json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        out[spec["id"]] = manifest
    return out
