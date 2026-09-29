"""Studio captures (spec 2026-09-26 section 4.5; plan C contract C7).

Four entry points, each ``(episode_dir: Path, spec: dict) -> dict``. ``spec`` is the
script's capture entry ``{"id", "kind", ...}``; each function writes its media as
``captures/<id>.<ext>`` in the episode workspace and returns the manifest
(manifest.py), which ``pipeline.studio.captures`` validates and stores as
``captures/<id>.json``:

* record_platform  kind "platform"        real site take (Playwright CDP screencast)
* record_globe     kind "globe"           our vector globe or a Mapbox take (Puppeteer recorder)
* capture_source   kind "source"          a source page, or our paper page, with the quote highlighted
* mapbox_topdown   kind "mapbox_topdown"  Mapbox Static top-down frame with projected pins

Local-only: Playwright, Chrome, Node and ffmpeg live on the workstation and are
imported or started inside the functions. Nothing in api/ or pipeline/lyra imports
this package.
"""

from pipeline.studio.capture.globe import record_globe
from pipeline.studio.capture.mapbox import mapbox_topdown
from pipeline.studio.capture.platform import record_platform
from pipeline.studio.capture.sources import capture_source

__all__ = ["capture_source", "mapbox_topdown", "record_globe", "record_platform"]
