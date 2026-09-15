"""Prospector: site candidates mined from our own content, for human review.

    python -m pipeline.lyra.prospector papers [--slug S] [--max-calls N] [--dry-run]
    python -m pipeline.lyra.prospector external-ids [--all]
    python -m pipeline.lyra.prospector review --id <uuid>

Design: docs/superpowers/specs/2026-09-14-site-proposer-design.md
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict

from pipeline.database import get_session
from pipeline.lyra.config import _get_settings
from pipeline.lyra.minimax_shared import probe_minimax_quota
from pipeline.lyra.prospector.corpus import PaperUnit, load_public_papers
from pipeline.lyra.prospector.dedup import Candidate, adjudicate
from pipeline.lyra.prospector.extract_papers import (
    EXTRACTOR_TAG,
    Budget,
    BudgetExhausted,
    PaperExtraction,
    extract_paper,
)
from pipeline.lyra.prospector.mentions import Mention
from pipeline.lyra.prospector.propose import add_evidence, paper_locator, upsert_proposal
from pipeline.lyra.prospector.resolve import ResolverBudget, resolve_names
from pipeline.utils.text import normalize_name

logger = logging.getLogger(__name__)

TOKEN_BUDGET = int(os.environ.get("PROSPECTOR_TOKEN_BUDGET", "3000000"))
MAX_CALLS_PER_RUN = 200
MAX_TIEBREAK_CALLS = 40
# Stricter than the Theo watchdog's own freeze points, so the prospector
# always yields first.
QUOTA_WEEKLY_FLOOR_PCT = 25
QUOTA_FIVE_HOUR_FLOOR_PCT = 20
RESOLVER_ABORT_RATE = 0.20


class QuotaFloor(RuntimeError):
    pass


def check_quota() -> None:
    q = probe_minimax_quota()
    if q.get("ok") is False:
        logger.warning("[PROSPECTOR] quota probe failed (%s) — proceeding", q.get("error"))
        return
    weekly = q.get("weekly_remaining_percent")
    five = q.get("five_hour_remaining_percent")
    if weekly is not None and weekly <= QUOTA_WEEKLY_FLOOR_PCT:
        raise QuotaFloor(f"weekly quota at {weekly}% — below {QUOTA_WEEKLY_FLOOR_PCT}% floor")
    if five is not None and five <= QUOTA_FIVE_HOUR_FLOOR_PCT:
        raise QuotaFloor(f"5h quota at {five}% — below {QUOTA_FIVE_HOUR_FLOOR_PCT}% floor")


def _already_extracted(session, unit: PaperUnit) -> bool:
    from sqlalchemy import text as sql

    return bool(
        session.execute(
            sql("""SELECT 1 FROM site_proposal_evidence
                   WHERE source_table = 'research_requests' AND source_pk = :pk
                     AND extracted_by = :by LIMIT 1"""),
            {"pk": unit.request_id, "by": EXTRACTOR_TAG},
        ).fetchone()
    )


def process_paper(session, extraction: PaperExtraction, *, resolver: ResolverBudget) -> dict:
    """Resolve, adjudicate and write one paper's grounded mentions."""
    unit = extraction.unit
    groups: dict[str, list[Mention]] = defaultdict(list)
    for m in extraction.mentions:
        groups[normalize_name(m.name)].append(m)

    # Representative surface form per group: the most frequent spelling.
    reps: dict[str, Mention] = {}
    for key, ms in groups.items():
        counts: dict[str, int] = defaultdict(int)
        for m in ms:
            counts[m.name] += 1
        best = max(counts, key=counts.get)
        reps[key] = next(m for m in ms if m.name == best)

    site_keys = [k for k, m in reps.items() if m.place_class == "site"]
    resolutions = resolve_names(
        [reps[k].name for k in site_keys], cited_titles=extraction.cited_titles, budget=resolver
    )
    if resolver.attempted and resolver.failures / resolver.attempted > RESOLVER_ABORT_RATE:
        raise RuntimeError(
            f"[{unit.slug}] resolver failure rate {resolver.failures}/{resolver.attempted} "
            f"exceeds {RESOLVER_ABORT_RATE:.0%} — Wikidata degraded? Nothing written."
        )

    cands: list[Candidate] = []
    for i, key in enumerate(site_keys):
        rep = reps[key]
        res = resolutions.get(rep.name)
        country = (res.country if res else None) or _first(
            m.country_in_text for m in groups[key] if m.country_in_text
        )
        cands.append(
            Candidate(
                idx=i,
                name=rep.name,
                qid=res.qid if res and res.verdict == "resolved" else None,
                enwiki_title=res.canonical_title if res and res.verdict == "resolved" else None,
                country=country,
                lat=res.lat if res and res.verdict == "resolved" else None,
                lon=res.lon if res and res.verdict == "resolved" else None,
            )
        )
    verdicts = adjudicate(session, cands)

    counts: dict[str, int] = defaultdict(int)
    for i, key in enumerate(site_keys):
        rep, ms = reps[key], groups[key]
        res = resolutions.get(rep.name)
        pid = upsert_proposal(
            session,
            name=rep.name,
            place_class="site",
            res=res,
            verdict=verdicts.get(i),
            country_in_text=_first(m.country_in_text for m in ms if m.country_in_text),
            period_phrase=_first(m.period_phrase for m in ms if m.period_phrase),
        )
        add_evidence(
            session,
            pid,
            ms,
            corpus="paper",
            source_table="research_requests",
            source_pk=unit.request_id,
            locator_for=lambda m: paper_locator(unit.slug, m.quote),
            extracted_by=EXTRACTOR_TAG,
        )
        counts[verdicts[i].verdict if i in verdicts else "new"] += 1

    # Non-site classes: recorded for the audit trail, never queued for review.
    for key, rep in reps.items():
        if rep.place_class == "site":
            continue
        pid = upsert_proposal(
            session,
            name=rep.name,
            place_class=rep.place_class,
            res=None,
            verdict=None,
            country_in_text=_first(m.country_in_text for m in groups[key] if m.country_in_text),
            period_phrase=None,
        )
        add_evidence(
            session,
            pid,
            groups[key],
            corpus="paper",
            source_table="research_requests",
            source_pk=unit.request_id,
            locator_for=lambda m: paper_locator(unit.slug, m.quote),
            extracted_by=EXTRACTOR_TAG,
        )
        counts["not_a_place"] += 1
    return dict(counts)


def _first(it):
    for x in it:
        return x
    return None


def run_papers(*, slug: str | None, max_calls: int, dry_run: bool) -> dict:
    settings = _get_settings()
    check_quota()
    budget = Budget(max_tokens=TOKEN_BUDGET, max_calls=max_calls)
    resolver = ResolverBudget(MAX_TIEBREAK_CALLS)
    summary: dict[str, dict] = {}
    with get_session() as session:
        units = load_public_papers(session, slug=slug)
        for unit in units:
            if not slug and _already_extracted(session, unit):
                continue
            try:
                extraction = extract_paper(
                    unit, budget=budget, temperature=settings.temperature_verification
                )
            except BudgetExhausted as exc:
                logger.warning("[PROSPECTOR] stopping: %s", exc)
                break
            counts = process_paper(session, extraction, resolver=resolver)
            summary[unit.slug] = {
                "windows": extraction.windows,
                "emitted": extraction.stats.emitted,
                "grounded": len(extraction.mentions),
                "rejected": extraction.stats.rejected,
                **counts,
            }
            if dry_run:
                session.rollback()
            else:
                session.commit()
            check_quota()
    logger.info(
        "[PROSPECTOR] papers done: %d papers, %d calls, %d tokens, %d tiebreaks",
        len(summary),
        budget.calls,
        budget.tokens_used,
        resolver.llm_calls,
    )
    return {"papers": summary, "calls": budget.calls, "tokens": budget.tokens_used}


def run_daily() -> int:
    """Orchestrator step (daily): key any new curated sites, refresh the
    token frequencies, and extract any paper published since the last run.

    Papers are a backlog, not a pump (none published since August), so this
    is usually a no-op costing zero tokens. Returns the number of proposals
    touched. Never raises on quota: a floor just means "not today".
    """
    from pipeline.lyra.prospector.external_ids import refresh_site_external_ids, refresh_token_df

    with get_session() as session:
        refresh_site_external_ids(session, only_missing=True)
        refresh_token_df(session)
    try:
        result = run_papers(slug=None, max_calls=MAX_CALLS_PER_RUN, dry_run=False)
    except QuotaFloor as exc:
        logger.warning("[PROSPECTOR] daily run skipped: %s", exc)
        return 0
    return sum(
        v
        for paper in result["papers"].values()
        for k, v in paper.items()
        if k in ("new", "needs_decision", "have_it", "not_a_place")
    )


def print_review(proposal_id: str) -> None:
    from sqlalchemy import text as sql

    with get_session() as session:
        p = session.execute(
            sql("SELECT * FROM site_proposals WHERE id = CAST(:id AS uuid)"), {"id": proposal_id}
        ).fetchone()
        if not p:
            print("no such proposal")
            return
        ev = session.execute(
            sql(
                "SELECT * FROM site_proposal_evidence WHERE proposal_id = CAST(:id AS uuid) ORDER BY id"
            ),
            {"id": proposal_id},
        ).fetchall()
    print(f"{p.name}  [{p.status}]  class={p.place_class}")
    print(
        f"  resolved: {p.resolved_label or '-'}  qid={p.wikidata_qid or '-'}  via {p.resolution_path or '-'}"
    )
    if p.resolution_note:
        print(f"  note: {p.resolution_note}")
    print(f"  location: {p.location_rung}  ({p.lat}, {p.lon})  precision={p.coord_precision}")
    print(
        f"  country={p.country}  type={p.site_type}  period={p.period_name}  scope={p.scope_verdict}"
    )
    print(f"  dedup: {p.dedup_verdict}  an_site={p.an_site_id}")
    for t in p.dedup_trace or []:
        print(f"    - {t}")
    print(f"  evidence ({p.evidence_count}):")
    for e in ev:
        print(f'    "{e.quote}"')
        print(f"      -> {e.locator}")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="prospector", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("papers")
    p.add_argument("--slug")
    p.add_argument("--max-calls", type=int, default=MAX_CALLS_PER_RUN)
    p.add_argument("--dry-run", action="store_true")
    e = sub.add_parser("external-ids")
    e.add_argument("--all", action="store_true")
    r = sub.add_parser("review")
    r.add_argument("--id", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "papers":
        result = run_papers(slug=args.slug, max_calls=args.max_calls, dry_run=args.dry_run)
        for slug, c in result["papers"].items():
            print(f"{slug}: {c}")
        print(f"calls={result['calls']} tokens={result['tokens']}")
    elif args.cmd == "external-ids":
        from pipeline.lyra.prospector.external_ids import (
            refresh_site_external_ids,
            refresh_token_df,
        )

        with get_session() as session:
            print(refresh_site_external_ids(session, only_missing=not args.all))
            print(f"token_df rows: {refresh_token_df(session)}")
    elif args.cmd == "review":
        print_review(args.id)


if __name__ == "__main__":
    main()
