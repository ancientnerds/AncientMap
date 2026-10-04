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
from pipeline.studio import remote
from pipeline.studio.capture import platform as platform_take
from pipeline.studio.spoken import spelling_mismatch

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


def accepted_number_forms(text: str, start: str) -> list[tuple[str, str]]:
    """Every `spoken` / `display` pair between `start` and the "Anything else" that ends the list.

    Whitespace is collapsed first: STUDIO.md wraps its list mid-pair."""
    flat = re.sub(r"\s+", " ", text)
    region = flat[flat.index(start) + len(start) :]
    region = region[: region.index("Anything else")]
    return re.findall(r"`([^`]+)` / `([^`]+)`", region)


NUMBER_FORMS = [
    ("the studio-video skill", VIDEO_SKILL, "Spoken, then display, as the check accepts them:"),
    ("STUDIO.md", STUDIO_MD, "The check accepts, spoken then display:"),
]


@pytest.mark.parametrize(("where", "doc", "start"), NUMBER_FORMS, ids=lambda v: str(v)[:24])
def test_every_number_form_the_docs_accept_passes_the_caption_check(where, doc, start):
    # the skill once listed `the hundredth` / `100th`: the check reads the article as a spoken
    # word the display lacks and refuses it, so a script author copying it got an `episode check`
    # error
    pairs = accepted_number_forms(doc.read_text(encoding="utf-8"), start)
    assert len(pairs) >= 20, f"{where}: only {len(pairs)} pairs found, the list moved"
    refused = {
        (spoken, display): mismatch
        for spoken, display in pairs
        if (mismatch := spelling_mismatch(spoken, display)) is not None
    }
    assert not refused, f"{where} lists pairs the caption check refuses: {refused}"


# as the skill writes them after "Anything else": `about` against `around`, and so on
REFUSED_NUMBER_FORMS = [
    ("about", "around"),
    ("12–16 m", "twelve to fifteen metres"),
    ("2 cm", "2 mm"),
    ("World War III", "World War Two"),
]


@pytest.mark.parametrize(("one", "other"), REFUSED_NUMBER_FORMS)
def test_the_refused_number_forms_the_skill_names_are_refused(one, other):
    skill = " ".join(VIDEO_SKILL.read_text(encoding="utf-8").split())
    refusals = skill[skill.index("Anything else") :]
    refusals = refusals[: refusals.index("Where the words allow")]
    assert one in refusals
    assert other in refusals
    # either side may be the spoken one: the error names the first differing token either way
    assert spelling_mismatch(one, other) is not None
    assert spelling_mismatch(other, one) is not None


# Wording that is true only on the unmerged branch. The release deploy applies migrations 0025/0026
# and ships the three production modules, so a runbook that says production lacks them is false from
# the first green deploy: a session reading it would stop, or report the migrations as missing.
BRANCH_ONLY_WORDING = [
    "not released",
    "feat/studio",
    "until the release",
    "before the release",
    "neither migrations",
    "cannot run",
]


def runbook_section(heading: str, next_heading: str) -> str:
    text = STUDIO_MD.read_text(encoding="utf-8")
    start = text.index(heading)
    return text[start : text.index(next_heading, start)]


@pytest.mark.parametrize("phrase", BRANCH_ONLY_WORDING)
def test_the_runbook_does_not_state_the_unreleased_branch_as_the_present(phrase):
    flat = " ".join(STUDIO_MD.read_text(encoding="utf-8").split()).lower()
    assert phrase not in flat, f"STUDIO.md still says {phrase!r}: it must hold after the release"


def test_the_runbook_tells_how_to_read_the_release_state_from_production():
    section = " ".join(runbook_section("## 0. State on", "## 1. Setup").split())
    # migrations 0025 and 0026 and the three modules are what the release ships; the session reads
    # whether they are there, it does not assume
    assert "applied_migrations" in section
    assert "0025" in section
    assert "0026" in section
    assert "`commit`" in section
    for module in sorted(remote.ALLOWED_MODULES):
        assert f"`{module}`" in section, f"section 0 does not name {module}"
