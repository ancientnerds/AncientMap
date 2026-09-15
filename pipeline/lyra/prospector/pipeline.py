"""The one path from grounded mentions to written proposals.

Every corpus (papers, stories, the radar backlog, the legacy entities vein)
produces `(Mention, EvidenceRef)` pairs and hands them here. Grouping by
name, resolution, the dedup ladder and the write happen exactly once, in
this module — four extractors, one adjudication.

Two phases, deliberately separate:
  prepare()  groups and RESOLVES — minutes of Wikipedia/Wikidata calls, no
             database session at all.
  write()    adjudicates and writes — seconds, inside a fresh session.
The first full run held one session across an 18-minute resolve phase and
Postgres closed it (idle_in_transaction_session_timeout is 15 min on prod):
"server closed the connection unexpectedly" on the first dedup statement.
Never hold a transaction across a network phase.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

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


@dataclass
class Prepared:
    """Output of prepare(): everything write() needs, no session inside."""

    groups: dict[str, list[tuple[Mention, EvidenceRef]]]
    reps: dict[str, Mention]
    site_keys: list[str]
    resolutions: dict[str, Resolution]
    prefill: dict[str, Prefill] = field(default_factory=dict)
    label: str = ""


def _first(it):
    for x in it:
        return x
    return None


def prepare(
    pairs: list[tuple[Mention, EvidenceRef]],
    *,
    resolver: ResolverBudget,
    cited_titles: list[str] | None = None,
    prefill: dict[str, Prefill] | None = None,
    label: str = "",
) -> Prepared:
    """Group by name and resolve the site-class names. No database work."""
    prefill = prefill or {}
    groups: dict[str, list[tuple[Mention, EvidenceRef]]] = defaultdict(list)
    for m, ref in pairs:
        groups[normalize_name(m.name)].append((m, ref))

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
    return Prepared(dict(groups), reps, site_keys, resolutions, prefill, label)


def write(session, p: Prepared) -> dict[str, int]:
    """Adjudicate against the curated set and write proposals + evidence."""
    cands: list[Candidate] = []
    for i, key in enumerate(p.site_keys):
        rep = p.reps[key]
        res = p.resolutions.get(rep.name)
        ok = res is not None and res.verdict == "resolved"
        cands.append(
            Candidate(
                idx=i,
                name=rep.name,
                qid=res.qid if ok else None,
                enwiki_title=res.canonical_title if ok else None,
                country=gate_country(
                    res.country if res else None,
                    _first(m.country_in_text for m, _ in p.groups[key] if m.country_in_text),
                ),
                lat=res.lat if ok else None,
                lon=res.lon if ok else None,
            )
        )
    verdicts = adjudicate(session, cands)

    counts: dict[str, int] = defaultdict(int)
    for i, key in enumerate(p.site_keys):
        rep, items = p.reps[key], p.groups[key]
        pre = p.prefill.get(key, Prefill())
        pid = upsert_proposal(
            session,
            name=rep.name,
            place_class="site",
            res=p.resolutions.get(rep.name),
            verdict=verdicts.get(i),
            country_in_text=_first(m.country_in_text for m, _ in items if m.country_in_text),
            period_phrase=_first(m.period_phrase for m, _ in items if m.period_phrase),
            contribution_id=pre.contribution_id,
            prior_verdict=pre.prior_verdict,
        )
        add_evidence(session, pid, items)
        counts[verdicts[i].verdict if i in verdicts else "new"] += 1

    for key, rep in p.reps.items():
        if rep.place_class == "site":
            continue
        pid = upsert_proposal(
            session,
            name=rep.name,
            place_class=rep.place_class,
            res=None,
            verdict=None,
            country_in_text=_first(
                m.country_in_text for m, _ in p.groups[key] if m.country_in_text
            ),
            period_phrase=None,
        )
        add_evidence(session, pid, p.groups[key])
        counts["not_a_place"] += 1
    return dict(counts)


def process_mentions(
    session,
    pairs: list[tuple[Mention, EvidenceRef]],
    *,
    resolver: ResolverBudget,
    cited_titles: list[str] | None = None,
    prefill: dict[str, Prefill] | None = None,
    label: str = "",
) -> dict[str, int]:
    """prepare() + write() on one session — only for callers whose session
    was opened AFTER the network phase (a fresh one), never across it."""
    return write(
        session,
        prepare(pairs, resolver=resolver, cited_titles=cited_titles, prefill=prefill, label=label),
    )
