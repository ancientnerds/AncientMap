"""The committed renderer registry (stream D's video/src/blocks/registry.json, contract C5),
glyph set (DRAWABLE of video/src/theme/glyphs.ts) and hook caption line budget
(video/src/captions.ts) against this plan's mirrors of them: the local cue table, the fixture
entries, the icons, the code points the brand font files map, HOOK_LINE_MAX_CHARS."""

from __future__ import annotations

import re

from pipeline.studio import blocks, casefile, config, glyphs, script
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf


def test_the_cue_table_covers_exactly_the_registry():
    assert set(script.LOCAL_CUES) == set(blocks.load_registry())


def test_the_fixture_entries_and_icons_are_the_committed_ones():
    registry = blocks.load_registry()
    assert {name: registry[name] for name in sf.REGISTRY} == sf.REGISTRY
    assert blocks.claim_icons(registry) == ef.ICONS


def test_the_fixture_script_passes_against_the_committed_registry():
    data = sf.script()
    report = script.validate_script(
        data,
        casefile.from_dict(ef.casefile()),
        blocks.load_registry(),
        slug="baalbek-c5",
        fmt="full",
        words=sf.words_for(data),
        captures=sf.manifests(),
    )
    assert report.errors == [] and report.deferred == []


def test_the_brand_glyph_set_is_the_renderers():
    source = (config.REPO / "video" / "src" / "theme" / "glyphs.ts").read_text(encoding="utf-8")
    found = re.findall(r"export const DRAWABLE =\s*'([^']*)'", source)
    assert found == [glyphs.DRAWABLE]


def test_the_hook_line_budget_is_the_renderers():
    source = (config.REPO / "video" / "src" / "captions.ts").read_text(encoding="utf-8")
    found = re.findall(r"^export const HOOK_LINE_MAX_CHARS = (\d+)\b", source, re.MULTILINE)
    assert found == [str(script.HOOK_LINE_MAX_CHARS)]
