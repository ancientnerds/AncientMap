"""Shared state for the convergence-based research pipeline.

Replaces the fixed-tier model with dynamic angles that saturate
independently.  ResearchState carries everything the pipeline needs
from decomposition through final paper delivery and is compatible
with the worker contract (paper_text, audit_result, quality_score,
error, total_tokens, llm_call_count, debug_log, etc.).
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.lyra.theo_citations import CitationRegistry


class ResearchPhase(enum.Enum):
    DECOMPOSING = "decomposing"
    EXPLORING = "exploring"
    SYNTHESIZING = "synthesizing"
    DEBATING = "debating"
    WRITING = "writing"
    IMAGE_CURATION = "image_curation"
    JUDGING = "judging"
    DONE = "done"


@dataclass
class ResearchConfig:
    """Global config for the convergence pipeline."""

    max_concurrent_llm_calls: int = 100
    deadline_hours: int = 24
    # Convergence
    saturation_threshold: int = 2  # consecutive zero-claim rounds to saturate an angle
    max_search_rounds_per_angle: int = 4  # round 1 + cross-pollinated round 2 + 2 verification
    max_angles: int = 12  # cap on total angles (including spawned)
    # Specialists
    initial_specialist_count: int = 6
    min_specialists: int = 3
    max_specialists: int = 12
    prune_after_zero_rounds: int = 2  # consecutive zero-contribution rounds to prune
    # Debate
    max_debate_rounds: int = 4  # hard cap, converges earlier if no new challenges
    # Search
    source_apis: str = "standard"  # "minimal", "standard", "full", "exhaustive"
    queries_per_angle: int = 5
    # LLM — quality-max (tokens free): provision generously so M3's adaptive
    # thinking (which shares the output budget) can't truncate findings/prose.
    # Raised from 16384/32768. M3 output ceiling is 512k.
    max_tokens_per_call: int = 32768
    max_tokens_synthesis: int = 49152


@dataclass
class ResearchAngle:
    """A single research angle/sub-topic being investigated."""

    id: str  # short unique id
    topic: str  # e.g. "Mesopotamian radiant deities"
    description: str  # fuller description
    search_queries: list[str] = field(default_factory=list)
    specialist_domains: list[str] = field(default_factory=list)  # suggested domains
    assigned_specialists: list[str] = field(default_factory=list)  # specialist IDs for this angle
    source_ids: list[str] = field(default_factory=list)  # registry source IDs
    findings: list[dict] = field(default_factory=list)  # accumulated claims
    search_rounds: int = 0
    recent_claim_counts: list[int] = field(default_factory=list)  # last N rounds' new claims
    saturated: bool = False
    spawned_from: str | None = None  # parent angle ID if rabbit hole
    effective_max_rounds: int = 0  # bonus rounds from rabbit holes (0 = use config default)


@dataclass
class ActiveSpecialist:
    """A specialist in the active panel with contribution tracking."""

    specialist_id: str
    name: str
    domain: str
    contribution_score: float = 0.0
    consecutive_zero_rounds: int = 0
    interdisciplinary_hits: int = 0
    active: bool = True
    rounds_participated: int = 0


@dataclass
class ResearchState:
    """Shared state for the entire research lifecycle."""

    # Input
    question: str
    request_id: str = ""
    seed_urls: list[str] = field(default_factory=list)
    seed_video_ids: list[str] = field(default_factory=list)
    force_include: list[str] = field(default_factory=list)
    force_exclude: list[str] = field(default_factory=list)
    disabled_adapters: list[str] = field(default_factory=list)

    # Config
    config: ResearchConfig = field(default_factory=ResearchConfig)

    # Phase tracking
    phase: ResearchPhase = ResearchPhase.DECOMPOSING
    started_at: datetime = field(default_factory=datetime.utcnow)
    deadline: datetime | None = None  # set on init: started_at + deadline_hours

    # Research angles
    angles: list[ResearchAngle] = field(default_factory=list)

    # Specialist panel
    panel: list[ActiveSpecialist] = field(default_factory=list)

    # Sources & citations
    registry: CitationRegistry = field(default_factory=CitationRegistry)

    # Cross-pollination
    cross_pollinated: bool = False

    # Synthesis & debate
    synthesis: dict = field(default_factory=dict)
    cross_angle_connections: list[dict] = field(default_factory=list)
    debate_result: dict = field(default_factory=dict)
    moderated_result: dict = field(default_factory=dict)

    # Paper
    paper_text: str = ""
    paper_title: str = ""
    card_description: str = ""
    audit_result: dict = field(default_factory=dict)
    quality_score: dict = field(default_factory=dict)

    # Probative-image stage output — list of dicts, each with keys:
    # {claim_index, claim_text, image_path, source_url, title, artist,
    #  license, license_url, rationale, section_heading}
    probative_images: list[dict] = field(default_factory=list)

    # Hero banner pick from probative_images. Shape:
    # {src, title, caption, sourceUrl, web_path, source_name, rationale}.
    # Populated by the hero picker after presentation. None if no probative
    # images were embedded.
    hero_image: dict | None = None

    # Image research pool — populated by AngleImageResearchHandler in parallel
    # with angle_search. Keyed by angle.id, values are serialized ImageCandidate
    # dicts (dataclass round-trip via asdict). ProbativeImagesHandler selects
    # from this pool at embed time; if empty (feature disabled or race), PIH
    # falls back to on-demand fetch.
    image_candidate_pool: dict[str, list[dict]] = field(default_factory=dict)

    # Diversity scores computed after probative-image selection completes.
    # Keys: source_diversity (float 0-1), artifact_type_diversity (float 0-1),
    # source_count (int), license_count (int).
    probative_images_diversity: dict = field(default_factory=dict)

    # Metadata
    total_tokens: int = 0
    llm_call_count: int = 0
    debug_log: list[dict] = field(default_factory=list)
    error: str = ""
    # Set by EventBus.emit when a handler dies on a quota error. The bus
    # swallows the exception into `error` (to unblock the deadline loop),
    # so this flag is the worker's only way to route the run to 'deferred'
    # instead of 'failed'.
    quota_exhausted: bool = False

    # Backward compat -- worker uses len(ctx.specialist_analyses) for tools_used
    specialist_analyses: dict = field(default_factory=dict)

    # Cached Voyage embedding of the research question. Filled lazily by the
    # cross_pollination handler on its first round so we can drift-gate
    # enriched search queries via cosine similarity against the question.
    question_embedding: list[float] | None = None

    # SSE callback
    emit: Callable[[dict], None] | None = None

    def log(self, stage: str, msg: str, **data):
        """Append to debug log."""
        entry = {"ts": time.time(), "stage": stage, "level": "info", "msg": msg}
        if data:
            entry["data"] = data
        self.debug_log.append(entry)

    @property
    def time_remaining_hours(self) -> float:
        """Hours until deadline."""
        if not self.deadline:
            return 999.0
        delta = (self.deadline - datetime.utcnow()).total_seconds()
        return max(0, delta / 3600)

    @property
    def all_angles_saturated(self) -> bool:
        return len(self.angles) > 0 and all(a.saturated for a in self.angles)

    @property
    def active_specialists(self) -> list[ActiveSpecialist]:
        return [s for s in self.panel if s.active]
