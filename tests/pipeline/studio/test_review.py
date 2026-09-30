"""review.html, the owner's script table: timings, per-beat findings and the summary."""

from __future__ import annotations

import pytest

from pipeline.studio import casefile, review, script
from pipeline.studio.errors import StudioError
from tests.pipeline.studio import episode_fixtures as ef
from tests.pipeline.studio import script_fixtures as sf


@pytest.mark.parametrize(
    ("seconds", "shown"),
    [
        (0.0, "0:00.0"),
        (59.97, "1:00.0"),
        (119.96, "2:00.0"),
        (61.24, "1:01.2"),
        (600.04, "10:00.0"),
    ],
)
def test_the_clock_never_shows_sixty_seconds(seconds, shown):
    assert review._clock(seconds) == shown


def test_the_summary_keeps_every_error_no_row_shows():
    """A general finding that merely starts with a beat id (beat `c`, finding `capture ...`)
    belongs in the summary: rows and summary use the same attribution."""
    cf = casefile.from_dict(ef.casefile())
    data = sf.mutated_script(lambda d: d["beats"][0].update(id="c"))
    report = script.ScriptReport(
        errors=["capture g4: kind must be one of the capture kinds", "c: a row finding"]
    )
    page = review.render_review(data, cf, None, report)
    summary = page[page.index("<ul>") : page.index("</ul>")]
    assert "capture g4: kind must be one of the capture kinds" in summary
    assert "c: a row finding" not in summary
    assert page.count("capture g4: kind must be one of the capture kinds") == 1


@pytest.mark.parametrize(
    "breaks",
    [
        lambda d: d["beats"][2].pop("display"),
        lambda d: d["beats"][2].update(visual="PhotoCard"),
        lambda d: d["beats"][2].update(evidence=[{"$ref": "e1"}]),
        lambda d: d["beats"].insert(1, "not a beat"),
        lambda d: d.pop("beats"),
    ],
)
def test_a_script_the_table_cannot_lay_out_is_a_studio_error(breaks):
    cf = casefile.from_dict(ef.casefile())
    data = sf.mutated_script(breaks)
    report = script.validate_script(data, cf, sf.REGISTRY, slug="baalbek-c5", fmt="full")
    assert report.errors
    with pytest.raises(StudioError, match="review.html needs a well-formed script"):
        review.render_review(data, cf, None, report)
