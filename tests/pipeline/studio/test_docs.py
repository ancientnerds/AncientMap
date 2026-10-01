"""The studio's runbook, skills and CLAUDE.md name what the code defines.

Plan D's cross-stream requests 3 and 9 hand the platform action vocabulary to STUDIO.md and the
studio-video skill, and the integration reviews found both lists stale more than once (a
`toggle_layer` without `empire`, a command list one entry short). These tests hold the two
enumerations that are cheap to pin; the rest of the prose is checked by reading it against the
code (docs/procedures/STUDIO.md, "Where this file and the code disagree, the code is right").
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from pipeline.studio import __main__ as studio_cli
from pipeline.studio.capture import platform as platform_take

ROOT = Path(__file__).resolve().parents[3]
STUDIO_MD = ROOT / "docs" / "procedures" / "STUDIO.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
VIDEO_SKILL = ROOT / ".claude" / "skills" / "studio-video" / "SKILL.md"


def subcommands(area: str) -> list[str]:
    parser = studio_cli.build_parser()
    (areas,) = (a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    (commands,) = (
        a for a in areas.choices[area]._actions if isinstance(a, argparse._SubParsersAction)
    )
    return list(commands.choices)


def listed(text: str, area: str) -> list[str]:
    """The `{a,b,c}` list that follows `pipeline.studio <area>` in a command block."""
    found = re.findall(rf"pipeline\.studio {area}\s+\{{([a-z,\-]+)\}}", text)
    assert len(found) == 1, f"{area}: {len(found)} command lists"
    return found[0].split(",")


@pytest.mark.parametrize("doc", [STUDIO_MD, CLAUDE_MD], ids=lambda p: p.name)
@pytest.mark.parametrize("area", ["paper", "episode"])
def test_the_docs_list_every_studio_subcommand(doc, area):
    assert sorted(listed(doc.read_text(encoding="utf-8"), area)) == sorted(subcommands(area))


def test_the_skill_and_the_runbook_name_every_platform_action():
    skill = VIDEO_SKILL.read_text(encoding="utf-8")
    row = next(line for line in skill.splitlines() if line.startswith('| `kind: "platform"`'))
    runbook = STUDIO_MD.read_text(encoding="utf-8")
    vocabulary = runbook[runbook.index("### 9.5 Platform takes") :]
    vocabulary = vocabulary[: vocabulary.index("## 10.")]
    for action, keys in platform_take.ACTIONS.items():
        optional = platform_take.OPTIONAL.get(action, frozenset())
        # written as `search {q}`, `measure {a, b}`, `toggle_layer {label, empire?}`, and
        # without braces when the action takes no key
        wanted = {*keys, *(f"{key}?" for key in optional)}
        for where, text in (
            ("the studio-video skill's platform row", row),
            ("STUDIO.md 9.5", vocabulary),
        ):
            found = re.search(rf"`{action}(?: \{{([^}}]*)\}})?`", text)
            assert found is not None, f"{where} does not name the action {action}"
            written = {k.strip() for k in (found.group(1) or "").split(",") if k.strip()}
            assert written == wanted, (
                f"{where}: {action} takes {sorted(wanted)}, it says {sorted(written)}"
            )
