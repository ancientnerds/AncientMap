"""The dossier's shape (spec 2.2): cited sources, the manifest, the result_json summary.

Pure functions over plain data (dicts and duck-typed state), so the
DossierHandler, the worker, the run close-out and the export CLI share one
definition. Imports nothing from pipeline.lyra, so training_corpus may import it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

DOSSIER_VERSION = 1

#: research_artifacts kinds the DossierHandler writes before the manifest.
DOSSIER_KINDS: tuple[str, ...] = (
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "specialist_analyses",
    "citation_registry",
    "image_candidate_pool",
)

#: The claim lists of state.moderated_result that the paper may cite.
#: dropped_claims are out: the moderator rejected them.
MODERATED_CLAIM_LISTS: tuple[str, ...] = ("final_claims", "revised_claims", "speculative_claims")

#: The archive counters result_json["dossier"] carries (the failures stay in the manifest).
ARCHIVE_COUNT_KEYS: tuple[str, ...] = (
    "cited_sources",
    "full_text",
    "abstract_only",
    "missing",
    "tdm_reserved",
)


def moderated_source_ids(moderated: dict) -> list[str]:
    """Every source id a final, revised or speculative claim cites; first-seen order, no duplicates."""
    seen: dict[str, None] = {}
    for key in MODERATED_CLAIM_LISTS:
        for claim in moderated.get(key) or []:
            for source_id in claim.get("source_ids") or []:
                seen.setdefault(source_id, None)
    return list(seen)


def cited_source_ids(moderated: dict, angles: list[dict]) -> list[str]:
    """Sources whose text the default export ships (`--texts cited`, spec 2.8).

    The moderated claims' sources, plus every source of an angle finding that
    shares at least one source with them: those findings are the evidence behind
    the moderated claims (the moderator carries no quotes of its own).
    """
    core = moderated_source_ids(moderated)
    core_set = set(core)
    seen: dict[str, None] = dict.fromkeys(core)
    for angle in angles:
        for finding in angle.get("findings") or []:
            source_ids = finding.get("source_ids") or []
            if core_set.intersection(source_ids):
                for source_id in source_ids:
                    seen.setdefault(source_id, None)
    return list(seen)


def build_manifest(state: Any, archive: dict, *, created_at: datetime) -> dict:
    """The 'dossier' artifact (contract C1). Written last: its presence means the dossier is complete."""
    moderated = state.moderated_result
    return {
        "version": DOSSIER_VERSION,
        "request_id": state.request_id,
        "question": state.question,
        "created_at": created_at.isoformat(),
        "angle_ids": [angle.id for angle in state.angles],
        "counts": {
            "angles": len(state.angles),
            "findings": sum(len(angle.findings) for angle in state.angles),
            "sources": len(state.registry.sources),
            "final_claims": len(moderated.get("final_claims") or []),
            "revised_claims": len(moderated.get("revised_claims") or []),
            "speculative_claims": len(moderated.get("speculative_claims") or []),
            "images": sum(len(pool) for pool in state.image_candidate_pool.values()),
        },
        "kinds": list(DOSSIER_KINDS),
        "archive": archive,
        "research": {
            "llm_calls": state.llm_call_count,
            "total_tokens": state.total_tokens,
            "duration_s": round((created_at - state.started_at).total_seconds(), 1),
        },
    }


def manifest_summary(manifest: dict, artifact_id: int) -> dict:
    """What research_requests.result_json["dossier"] carries (contract C2)."""
    return {
        "artifact_id": artifact_id,
        "version": manifest["version"],
        "created_at": manifest["created_at"],
        "counts": dict(manifest["counts"]),
        "archive": {key: manifest["archive"][key] for key in ARCHIVE_COUNT_KEYS},
    }
