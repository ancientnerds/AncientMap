"""The studio runs without a display (owner requirement 2026-10-02): the screen may be
asleep or locked while a capture runs. Nothing in it may need the desktop session."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SOURCES = [
    *(REPO / "pipeline" / "studio").rglob("*.py"),
    *(REPO / "ancient-nerds-map" / "video").rglob("*.ts"),
    *(REPO / "video").rglob("*.ts"),
]
SOURCES = [p for p in SOURCES if "node_modules" not in p.parts]
HEADED = re.compile(
    r"headless\s*[:=]\s*(False|false)|--headless=false|headless:\s*'shell'\s*\?\s*false"
)
KEEP_AWAKE = re.compile(r"SetThreadExecutionState|ES_DISPLAY_REQUIRED|display_awake")


def test_the_scan_sees_the_capture_sources():
    names = {p.name for p in SOURCES}
    assert {"platform.py", "gpu.py", "record.ts"} <= names


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_source_launches_a_headed_browser_or_holds_a_display(path):
    if path == Path(__file__):
        return
    text = path.read_text(encoding="utf-8")
    assert not HEADED.search(text), f"{path} launches a headed browser"
    assert not KEEP_AWAKE.search(text), f"{path} holds the display awake"
