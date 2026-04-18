"""Diversity scoring for the probative-image selection.

Computed after ProbativeImagesHandler finishes embedding images. Used to surface
"are we drawing from a wide spectrum of sources?" telemetry rather than silently
accepting a paper with 8 images all from Wikimedia.

Two metrics, both in [0, 1]:
  - source_diversity       — unique connector sources / total embedded
  - license_diversity      — unique license strings / total embedded

Simple but useful. Extending to per-artifact-type diversity would require a
metadata-to-type classifier; deferred until need demonstrated.
"""

from __future__ import annotations


def score_source_diversity(embedded: list[dict]) -> float:
    """Fraction of embedded images that come from distinct source connectors.

    Example: 4 images from [wikimedia, met_museum, wikimedia, loc] → 3/4 = 0.75.
    Perfect diversity (1.0) = every image from a different source.
    Returns 0.0 for empty input.
    """
    if not embedded:
        return 0.0
    sources = [e.get("source") or "" for e in embedded]
    sources = [s for s in sources if s]
    if not sources:
        return 0.0
    return len(set(sources)) / len(sources)


def score_license_diversity(embedded: list[dict]) -> float:
    """Fraction of embedded images that carry distinct license strings."""
    if not embedded:
        return 0.0
    licenses = [e.get("license") or "" for e in embedded]
    licenses = [ln for ln in licenses if ln]
    if not licenses:
        return 0.0
    return len(set(licenses)) / len(licenses)


def compute_diversity(embedded: list[dict]) -> dict:
    """Return a full diversity summary dict for the state + SSE telemetry.

    Each embedded dict is expected to have keys: source, license (others ignored).
    """
    total = len(embedded)
    sources = {e.get("source") for e in embedded if e.get("source")}
    licenses = {e.get("license") for e in embedded if e.get("license")}
    return {
        "total_embedded": total,
        "source_count": len(sources),
        "license_count": len(licenses),
        "source_diversity": round(score_source_diversity(embedded), 3),
        "license_diversity": round(score_license_diversity(embedded), 3),
        "sources": sorted(s for s in sources if s),
    }
