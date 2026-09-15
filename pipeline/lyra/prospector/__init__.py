"""Prospector: site candidates mined from our own content, for human review.

    python -m pipeline.lyra.prospector papers [--slug S] [--max-calls N] [--dry-run]
    python -m pipeline.lyra.prospector stories [--items N] [--max-calls N] [--dry-run]
    python -m pipeline.lyra.prospector radar-backlog
    python -m pipeline.lyra.prospector entities-legacy
    python -m pipeline.lyra.prospector external-ids [--all]
    python -m pipeline.lyra.prospector review --id <uuid>

Design: docs/superpowers/specs/2026-09-14-site-proposer-design.md
"""

from __future__ import annotations

import argparse
import logging
import os

from pipeline.database import get_session
from pipeline.lyra.config import _get_settings
from pipeline.lyra.minimax_shared import probe_minimax_quota
from pipeline.lyra.prospector.corpus import (
    PaperUnit,
    load_public_papers,
    load_stories,
    mark_prospected,
)
from pipeline.lyra.prospector.dedup import gate_country  # noqa: F401 — re-exported for tests
from pipeline.lyra.prospector.extract_papers import (
    EXTRACTOR_TAG,
    Budget,
    BudgetExhausted,
    PaperExtraction,
    extract_paper,
)
from pipeline.lyra.prospector.pipeline import EvidenceRef, process_mentions
from pipeline.lyra.prospector.propose import paper_locator
from pipeline.lyra.prospector.resolve import ResolverBudget

logger = logging.getLogger(__name__)

TOKEN_BUDGET = int(os.environ.get("PROSPECTOR_TOKEN_BUDGET", "3000000"))
MAX_CALLS_PER_RUN = 200
MAX_TIEBREAK_CALLS = 40
# Stricter than the Theo watchdog's own freeze points, so the prospector
# always yields first.
QUOTA_WEEKLY_FLOOR_PCT = 25
QUOTA_FIVE_HOUR_FLOOR_PCT = 20
DAILY_STORY_ITEMS = 60  # ~10 calls; new items arrive at ~13/day


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


# ── papers ──────────────────────────────────────────────────────────────────


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
    unit = extraction.unit
    pairs = [
        (
            m,
            EvidenceRef(
                "paper",
                "research_requests",
                unit.request_id,
                paper_locator(unit.slug, m.quote),
                EXTRACTOR_TAG,
            ),
        )
        for m in extraction.mentions
    ]
    return process_mentions(
        session, pairs, resolver=resolver, cited_titles=extraction.cited_titles, label=unit.slug
    )


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


# ── stories ─────────────────────────────────────────────────────────────────


def run_stories(*, items: int | None, max_calls: int, dry_run: bool) -> dict:
    from pipeline.lyra.prospector.extract_stories import EXTRACTOR_TAG as STORY_TAG
    from pipeline.lyra.prospector.extract_stories import extract_stories

    settings = _get_settings()
    check_quota()
    budget = Budget(max_tokens=TOKEN_BUDGET, max_calls=max_calls)
    resolver = ResolverBudget(MAX_TIEBREAK_CALLS)
    with get_session() as session:
        units = load_stories(session, unprospected_only=True, limit=items)
        if not units:
            return {"items": 0, "calls": 0, "tokens": 0}
        try:
            extraction = extract_stories(
                units, budget=budget, temperature=settings.temperature_verification
            )
        except BudgetExhausted as exc:
            logger.warning("[PROSPECTOR] stopping: %s", exc)
            return {"items": 0, "calls": budget.calls, "tokens": budget.tokens_used}
        pairs = [
            (m, EvidenceRef("story", "news_items", str(u.item_id), u.locator, STORY_TAG))
            for u, m in extraction.mentions
        ]
        counts = process_mentions(session, pairs, resolver=resolver, label="stories")
        # Every unit the model READ is marked, mentions or not — an item that
        # names no place must not be re-read next week.
        mark_prospected(session, [u.item_id for u in units])
        if dry_run:
            session.rollback()
        else:
            session.commit()
    logger.info(
        "[PROSPECTOR] stories done: %d items, %d calls, %d tokens, %d grounded, %s",
        len(units),
        budget.calls,
        budget.tokens_used,
        len(extraction.mentions),
        dict(counts),
    )
    return {"items": len(units), "calls": budget.calls, "tokens": budget.tokens_used, **counts}


# ── radar backlog (zero LLM) ────────────────────────────────────────────────


def run_radar_backlog() -> dict:
    from pipeline.lyra.prospector.extract_radar import (
        group_key,
        load_radar_units,
        mentions_for,
        prefill_for,
    )

    resolver = ResolverBudget(MAX_TIEBREAK_CALLS)
    with get_session() as session:
        units = load_radar_units(session)
        pairs = [pair for u in units for pair in mentions_for(u)]
        prefill = {group_key(u): prefill_for(u) for u in units}
        counts = process_mentions(session, pairs, resolver=resolver, prefill=prefill, label="radar")
        session.commit()
    logger.info("[PROSPECTOR] radar backlog: %d contributions absorbed, %s", len(units), counts)
    return {"contributions": len(units), **counts}


# ── legacy entities (zero LLM) ──────────────────────────────────────────────


def run_entities_legacy() -> dict:
    from pipeline.lyra.prospector.extract_entities_legacy import extract_legacy_entities, to_pairs

    resolver = ResolverBudget(MAX_TIEBREAK_CALLS)
    with get_session() as session:
        found, stats = extract_legacy_entities(session)
        counts = process_mentions(session, to_pairs(found), resolver=resolver, label="entities")
        session.commit()
    return {"names": stats.emitted, "grounded": stats.grounded, "dropped": stats.rejected, **counts}


# ── orchestrator step ───────────────────────────────────────────────────────


def run_daily() -> int:
    """Orchestrator step (daily): key new curated sites, refresh the token
    frequencies, extract any paper published since the last run and the
    week's new stories. Returns the number of proposals touched. A quota
    floor just means "not today" — it never raises."""
    from pipeline.lyra.prospector.external_ids import refresh_site_external_ids, refresh_token_df

    with get_session() as session:
        refresh_site_external_ids(session, only_missing=True)
        refresh_token_df(session)
    touched = 0
    try:
        papers = run_papers(slug=None, max_calls=MAX_CALLS_PER_RUN, dry_run=False)
        touched += sum(
            v
            for paper in papers["papers"].values()
            for k, v in paper.items()
            if k in ("new", "needs_decision", "have_it", "not_a_place")
        )
        stories = run_stories(items=DAILY_STORY_ITEMS, max_calls=40, dry_run=False)
        touched += sum(
            v
            for k, v in stories.items()
            if k in ("new", "needs_decision", "have_it", "not_a_place")
        )
    except QuotaFloor as exc:
        logger.warning("[PROSPECTOR] daily run stopped: %s", exc)
    return touched


# ── review / CLI ────────────────────────────────────────────────────────────


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
    print(f"{p.name}  [{p.status}]  class={p.place_class}  aliases={list(p.aliases or [])}")
    print(
        f"  resolved: {p.resolved_label or '-'}  qid={p.wikidata_qid or '-'}  via {p.resolution_path or '-'}"
    )
    if p.resolution_note:
        print(f"  note: {p.resolution_note}")
    if p.prior_verdict:
        print(f"  prior verdict: {p.prior_verdict}")
    print(f"  location: {p.location_rung}  ({p.lat}, {p.lon})  precision={p.coord_precision}")
    print(
        f"  country={p.country}  type={p.site_type}  period={p.period_name}  scope={p.scope_verdict}"
    )
    print(f"  dedup: {p.dedup_verdict}  an_site={p.an_site_id}")
    for t in p.dedup_trace or []:
        print(f"    - {t}")
    print(f"  evidence ({p.evidence_count}, {p.corpus_kinds}):")
    for e in ev:
        print(f'    [{e.corpus}] "{e.quote}"')
        print(f"      -> {e.locator}")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="prospector", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("papers")
    p.add_argument("--slug")
    p.add_argument("--max-calls", type=int, default=MAX_CALLS_PER_RUN)
    p.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("stories")
    s.add_argument("--items", type=int, default=None, help="cap on items (default: all unread)")
    s.add_argument("--max-calls", type=int, default=MAX_CALLS_PER_RUN)
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("radar-backlog")
    sub.add_parser("entities-legacy")
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
    elif args.cmd == "stories":
        print(run_stories(items=args.items, max_calls=args.max_calls, dry_run=args.dry_run))
    elif args.cmd == "radar-backlog":
        print(run_radar_backlog())
    elif args.cmd == "entities-legacy":
        print(run_entities_legacy())
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
