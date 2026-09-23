"""T04 - every `site_type` is a canonical value that survives a container restart.

Two questions, both answerable from the snapshot alone:

1. Is `unified_sites.site_type` a value the system actually understands - i.e. a member
   of `pipeline/normalizers/site_type.py::CANONICAL_TYPES`, or the audit's own
   `suspect_modern` flag?
2. Would the value survive the producer that rewrites it on every restart?

Point 2 is not theoretical. `pipeline/lyra/orchestrator.py::_run_migrations` runs on EVERY
orchestrator boot and executes, globally:

    UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw

for every distinct raw value whose `normalize_site_type(raw) != raw`. So a correction
written as a synonym is reverted by the next container restart - and the March-2026
Wave-0 run looked like a no-op for exactly this reason (the plan's §3.2: all 70 distinct
production values already pass through unchanged). We therefore assert a hard invariant:
a proposed `site_type` must be a FIXED POINT of `normalize_site_type`, verified by calling
it, not by trusting the list.

The third question is cross-system: the frontend colours dots by `site_type` via
`ancient-nerds-map/src/constants/colors.ts::CATEGORY_COLORS`. A canonical type with no
colour there renders as a fallback, which is a real (if cosmetic) defect - anti-pattern 15
in ENRICHMENT_AUDIT.md. Both lists are read from source, never from a copy.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from census.model import Confidence, Evidence, Finding, Proposal, Severity

if TYPE_CHECKING:
    from census.run import Context

TEST_ID = "T04"
NAME = "site_type canonical and restart-safe"
DIMENSION = "classification / site_type"

#: written by the audit, understood by the pipeline, deliberately not in CANONICAL_TYPES
SUSPECT_MODERN = "suspect_modern"

REPO = Path(__file__).resolve().parents[4]
COLORS_TS = REPO / "ancient-nerds-map" / "src" / "constants" / "colors.ts"

_KEY_RE = re.compile(r"""^\s*(?:'([^']+)'|"([^"]+)")\s*:""", re.M)


def _canonical() -> tuple[list[str], Any]:
    """The canonical list and the normalizer itself, imported from the real module."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type

    return list(CANONICAL_TYPES), normalize_site_type


def _frontend_categories() -> set[str]:
    """Keys of the CATEGORY_COLORS map only - colors.ts holds several unrelated maps."""
    text = COLORS_TS.read_text(encoding="utf-8")
    m = re.search(r"CATEGORY_COLORS[^=]*=\s*\{(.*?)\n\}", text, re.S)
    if not m:
        raise RuntimeError(f"cannot locate CATEGORY_COLORS in {COLORS_TS}")
    return {a or b for a, b in _KEY_RE.findall(m.group(1))}


def run(ctx: Context) -> list[Finding]:
    canonical, normalize = _canonical()
    canonical_set = set(canonical)

    # The invariant this module's advice depends on. If it ever fails the advice is unsafe
    # and that must surface as a crash, not as findings we cannot stand behind.
    not_fixed = [c for c in canonical if normalize(c) != c]
    if not_fixed:
        raise AssertionError(
            "CANONICAL_TYPES contains values that normalize_site_type() would rewrite: "
            f"{not_fixed[:10]} - proposing them would be reverted on restart"
        )

    frontend = _frontend_categories()
    missing_color = [c for c in canonical if c not in frontend]

    findings: list[Finding] = []
    for site in ctx.sites:
        sid = str(site["id"])
        raw = site.get("site_type")
        value = (raw or "").strip()

        if value in canonical_set:
            # Known-good, but check the other half of anti-pattern 15: a canonical value
            # the frontend cannot colour renders as a fallback on the globe.
            if value in missing_color:
                findings.append(
                    Finding(
                        site_id=sid,
                        test_id=f"{TEST_ID}/no-frontend-colour",
                        field="site_type",
                        severity=Severity.COSMETIC,
                        dimension=DIMENSION,
                        current_value=value,
                        proposal=Proposal.REVIEW,
                        confidence=Confidence.AUTHORITATIVE,
                        note=f"{value!r} has no entry in CATEGORY_COLORS - dot uses the default colour",
                        evidence=[
                            Evidence(
                                source="pipeline/normalizers/site_type.py:CANONICAL_TYPES",
                                quote=f"{value!r} is canonical",
                            ),
                            Evidence(
                                source="ancient-nerds-map/src/constants/colors.ts:CATEGORY_COLORS",
                                quote=f"{value!r} is absent",
                            ),
                        ],
                    )
                )
            continue

        if value == SUSPECT_MODERN:
            continue  # the audit's own flag; intentional, not a defect

        if not value:
            # normalize_site_type("") == "Unknown" - upstream's own answer, so proposing it
            # is quoting the pipeline rather than guessing a category.
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/empty",
                    field="site_type",
                    severity=Severity.MODERATE,
                    dimension=DIMENSION,
                    current_value=raw,
                    proposal=Proposal.SET,
                    proposed_value="Unknown",
                    confidence=Confidence.AUTHORITATIVE,
                    note="empty site_type; normalize_site_type() maps it to 'Unknown'",
                    evidence=[
                        Evidence(
                            source="pipeline/normalizers/site_type.py:186-188",
                            quote="if not site_type or not site_type.strip(): return 'Unknown'",
                        )
                    ],
                )
            )
            continue

        mapped = normalize(value)
        if mapped != value and mapped in canonical_set:
            # A synonym the pipeline already knows. Prove the proposal is a fixed point so
            # the restart cannot undo it, then propose the canonical form.
            if normalize(mapped) != mapped:
                raise AssertionError(f"{mapped!r} is not a fixed point; refusing to propose it")
            findings.append(
                Finding(
                    site_id=sid,
                    test_id=f"{TEST_ID}/synonym",
                    field="site_type",
                    severity=Severity.COSMETIC
                    if value.lower() == mapped.lower()
                    else Severity.MODERATE,
                    dimension=DIMENSION,
                    current_value=value,
                    proposal=Proposal.SET,
                    proposed_value=mapped,
                    confidence=Confidence.AUTHORITATIVE,
                    note=f"synonym of {mapped!r} according to normalize_site_type()",
                    evidence=[
                        Evidence(
                            source="pipeline/normalizers/site_type.py:_SYNONYM_LOOKUP",
                            quote=f"normalize_site_type({value!r}) == {mapped!r}",
                        ),
                        Evidence(
                            source="pipeline/normalizers/site_type.py:CANONICAL_TYPES",
                            quote=f"CANONICAL_TYPES contains {mapped!r}",
                        ),
                    ],
                )
            )
            continue

        # Unknown to the pipeline. Do NOT guess a category: classification is a judgement
        # about the site, and a wrong category is worse than an odd one
        # (ENRICHMENT_AUDIT.md: an empty field beats a wrong one).
        findings.append(
            Finding(
                site_id=sid,
                test_id=f"{TEST_ID}/unknown",
                field="site_type",
                severity=Severity.MODERATE,
                dimension=DIMENSION,
                current_value=value,
                proposal=Proposal.REVIEW,
                confidence=Confidence.UNVERIFIABLE,
                note=f"{value!r} is neither canonical nor a known synonym; "
                "normalize_site_type() passes it through unchanged",
                evidence=[
                    Evidence(
                        source="pipeline/normalizers/site_type.py:213",
                        quote="return cleaned  # pass-through for unknown values",
                    )
                ],
            )
        )

    return findings
