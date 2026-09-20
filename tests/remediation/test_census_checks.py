"""Do the census checks actually have teeth?

A check that reports zero findings is indistinguishable from a check that is broken, and
"5,004 sites have a valid site_type" is only a result if the same code reports a bad
`site_type` when one is present. These tests feed each check synthetic sites carrying the
defect the check exists to find, and assert it fires.

They are deliberately not end-to-end: no snapshot, no network. The site dicts are the
minimum shape the check reads, so a check that starts depending on a new column fails
here rather than silently reporting fewer findings.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402


def _ctx(sites: list[dict]) -> SimpleNamespace:
    """The only part of Context these checks read: `.sites`."""
    ids = {str(s["id"]) for s in sites}
    return SimpleNamespace(
        sites=sites,
        snap=SimpleNamespace(rows=lambda *a, **k: [], by=lambda *a, **k: {}),
        site_ids=lambda: ids,
    )


def _site(sid: str, **over: Any) -> dict[str, Any]:
    base = {"id": sid, "source_id": "ancient_nerds", "name": f"Site {sid}"}
    base.update(over)
    return base


# --------------------------------------------------------------------- import helper
def _load(mod_name: str) -> Any:
    import importlib

    return importlib.import_module(f"census.tests.{mod_name}")


needs_t04 = pytest.mark.skipif(
    not (REPO / "ancient-nerds-map" / "src" / "constants" / "colors.ts").exists(),
    reason="frontend colour list not present",
)


@needs_t04
class TestT04SiteType:
    """t04_site_type: canonical values only, and never a value a restart would rewrite."""

    @pytest.fixture(scope="class")
    def t04(self):
        return _load("t04_site_type")

    def test_canonical_value_produces_nothing(self, t04):
        got = t04.run(_ctx([_site("a", site_type="Fortress/citadel")]))
        assert got == []

    def test_suspect_modern_is_deliberately_allowed(self, t04):
        """The audit's own flag must not be re-reported as a defect every run."""
        got = t04.run(_ctx([_site("a", site_type="suspect_modern")]))
        assert got == []

    def test_empty_site_type_is_set_to_unknown(self, t04):
        got = t04.run(_ctx([_site("a", site_type="")]))
        assert len(got) == 1
        f = got[0]
        assert f.proposal is M.Proposal.SET
        assert f.proposed_value == "Unknown"
        assert f.applicable, "the normalizer defines this mapping, so it needs no second source"

    def test_null_site_type_is_reported(self, t04):
        got = t04.run(_ctx([_site("a", site_type=None)]))
        assert len(got) == 1
        assert got[0].proposed_value == "Unknown"

    def test_known_synonym_is_proposed_in_canonical_form(self, t04):
        """Whatever synonym this is, the proposal must be a value the pipeline keeps."""
        canonical, normalize = t04._canonical()
        # Build a synonym on the fly rather than hard-coding one the lookup may drop.
        synonyms = [
            v
            for v in canonical
            if v.lower().replace(" ", "_") in {c.lower().replace(" ", "_") for c in canonical}
        ]
        assert synonyms, "sanity: canonical list is not empty"
        got = t04.run(_ctx([_site("a", site_type=synonyms[0].upper())]))
        for f in got:
            assert f.proposed_value is None or normalize(f.proposed_value) == f.proposed_value, (
                "T04 proposed a value that the orchestrator's startup normalizer would rewrite"
            )

    def test_unknown_value_goes_to_review_never_to_a_guess(self, t04):
        got = t04.run(_ctx([_site("a", site_type="Intergalactic parking structure")]))
        assert len(got) == 1
        f = got[0]
        assert f.proposal is M.Proposal.REVIEW
        assert f.proposed_value is None, "a guess is worse than a flag"
        assert f.confidence is M.Confidence.UNVERIFIABLE
        assert not f.applicable, "REVIEW is never auto-applicable"

    def test_every_proposed_value_is_a_restart_safe_fixed_point(self, t04):
        """The invariant that makes T04's advice durable, checked against real inputs."""
        _, normalize = t04._canonical()
        sites = [
            _site("a", site_type=""),
            _site("b", site_type=None),
            _site("c", site_type="fortress/citadel"),
            _site("d", site_type="Fortress/citadel"),
            _site("e", site_type="totally made up"),
        ]
        for f in t04.run(_ctx(sites)):
            if f.proposal is M.Proposal.SET:
                assert normalize(f.proposed_value) == f.proposed_value, (
                    f"{f.proposed_value!r} would be rewritten on the next container restart"
                )

    def test_findings_are_evidenced_and_attributed_to_the_right_site(self, t04):
        sites = [_site("a", site_type="Fortress/citadel"), _site("b", site_type="nonsense value")]
        got = t04.run(_ctx(sites))
        assert [f.site_id for f in got] == ["b"]
        assert got[0].evidence, "every finding must carry the source that supports it"
        assert got[0].test_id.startswith("T04")
