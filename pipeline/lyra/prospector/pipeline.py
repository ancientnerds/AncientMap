"""The one path from grounded mentions to written proposals.

Every corpus (papers, stories, the radar backlog, the legacy entities vein)
produces `(Mention, EvidenceRef)` pairs and hands them here. Grouping by
name, resolution, the dedup ladder and the write happen exactly once, in
this module — four extractors, one adjudication.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from pipeline.lyra.prospector.dedup import Candidate, adjudicate, gate_country
from pipeline.lyra.prospector.mentions import Mention
from pipeline.lyra.prospector.propose import add_evidence, upsert_proposal
from pipeline.lyra.prospector.resolve import Resolution, ResolverBudget, resolve_names
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)

RESOLVER_ABORT_RATE = 0.20
RESOLVER_MIN_SAMPLE = 10


@dataclass(frozen=True)
class EvidenceRef:
    """Where a mention was seen: enough to store it and to deep-link to it."""

    corpus: str  # paper | story | radar | entities_legacy
    source_table: str
    source_pk: str
    locator: str
    extracted_by: str


@dataclass
class Prefill:
    """What a corpus already knows about a name, so resolution is skipped."""

    resolution: Resolution | None = None
    contribution_id: str | None = None
    prior_verdict: str | None = None


def _first(it):
    for x in it:
        return x
    return None


def process_mentions(
    session,
    pairs: list[tuple[Mention, EvidenceRef]],
    *,
    resolver: ResolverBudget,
    cited_titles: list[str] | None = None,
    prefill: dict[str, Prefill] | None = None,
    label: str = "",
) -> dict[str, int]:
    """Group, resolve, adjudicate and write. Returns verdict counts.

    `prefill` is keyed by normalize_name(name); a key with a Resolution
    bypasses the Wikipedia/Wikidata resolver (the radar already knows the
    QID and coordinates it enriched).
    """
    prefill = prefill or {}
    groups: dict[str, list[tuple[Mention, EvidenceRef]]] = defaultdict(list)
    for m, ref in pairs:
        groups[normalize_name(m.name)].append((m, ref))
    if not groups:
        return {}

    reps: dict[str, Mention] = {}
    for key, items in groups.items():
        counts: dict[str, int] = defaultdict(int)
        for m, _ in items:
            counts[m.name] += 1
        best = max(counts, key=counts.get)
        reps[key] = next(m for m, _ in items if m.name == best)

    site_keys = [k for k, m in reps.items() if m.place_class == "site"]
    to_resolve = [reps[k].name for k in site_keys if prefill.get(k, Prefill()).resolution is None]
    resolutions = resolve_names(to_resolve, cited_titles=cited_titles or [], budget=resolver)
    for k in site_keys:
        pre = prefill.get(k)
        if pre and pre.resolution is not None:
            resolutions[reps[k].name] = pre.resolution

    if (
        resolver.attempted >= RESOLVER_MIN_SAMPLE
        and resolver.failures / resolver.attempted > RESOLVER_ABORT_RATE
    ):
        raise RuntimeError(
            f"[{label}] resolver failure rate {resolver.failures}/{resolver.attempted} "
            f"exceeds {RESOLVER_ABORT_RATE:.0%} — Wikidata degraded? Nothing written."
        )

    cands: list[Candidate] = []
    for i, key in enumerate(site_keys):
        rep = reps[key]
        res = resolutions.get(rep.name)
        ok = res is not None and res.verdict == "resolved"
        cands.append(
            Candidate(
                idx=i,
                name=rep.name,
                qid=res.qid if ok else None,
                enwiki_title=res.canonical_title if ok else None,
                country=gate_country(
                    res.country if res else None,
                    _first(m.country_in_text for m, _ in groups[key] if m.country_in_text),
                ),
                lat=res.lat if ok else None,
                lon=res.lon if ok else None,
            )
        )
    verdicts = adjudicate(session, cands)

    counts: dict[str, int] = defaultdict(int)
    for i, key in enumerate(site_keys):
        rep, items = reps[key], groups[key]
        pre = prefill.get(key, Prefill())
        pid = upsert_proposal(
            session,
            name=rep.name,
            place_class="site",
            res=resolutions.get(rep.name),
            verdict=verdicts.get(i),
            country_in_text=_first(m.country_in_text for m, _ in items if m.country_in_text),
            period_phrase=_first(m.period_phrase for m, _ in items if m.period_phrase),
            contribution_id=pre.contribution_id,
            prior_verdict=pre.prior_verdict,
        )
        add_evidence(session, pid, items)
        counts[verdicts[i].verdict if i in verdicts else "new"] += 1

    for key, rep in reps.items():
        if rep.place_class == "site":
            continue
        pid = upsert_proposal(
            session,
            name=rep.name,
            place_class=rep.place_class,
            res=None,
            verdict=None,
            country_in_text=_first(m.country_in_text for m, _ in groups[key] if m.country_in_text),
            period_phrase=None,
        )
        add_evidence(session, pid, groups[key])
        counts["not_a_place"] += 1
    return dict(counts)
