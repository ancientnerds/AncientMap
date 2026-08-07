#!/usr/bin/env python3
"""Report what Theo's research runs REALLY cost on the MiniMax plan.

Compares two numbers per run:
  reported  — research_requests.total_tokens (the API `usage` field)
  measured  — plan balance drop (probe `weekly_remains_time` start vs end)

The gap is the billed adaptive-reasoning tokens that `usage` never shows;
measured at ~7.7x on 2026-08-07, which is why quota planning must never use
the reported number. Runs that crossed the Monday reset are skipped (their
balance refilled mid-run, so the subtraction is meaningless).

Usage (on the VPS):
    docker exec ancient_nerds_api python scripts/theo_plan_cost.py
    docker exec ancient_nerds_api python scripts/theo_plan_cost.py --limit 20
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from pipeline.database import get_session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="how many recent runs")
    args = parser.parse_args()

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT left(question, 44) AS q,
                       status,
                       is_batch,
                       total_tokens,
                       plan_weekly_remains_start AS s,
                       plan_weekly_remains_end   AS e,
                       ROUND(duration_ms / 3600000.0, 1) AS hours,
                       completed_at::date AS day
                FROM research_requests
                WHERE plan_weekly_remains_start IS NOT NULL
                  AND plan_weekly_remains_end IS NOT NULL
                ORDER BY completed_at DESC NULLS LAST
                LIMIT :lim
            """),
            {"lim": args.limit},
        ).fetchall()

    if not rows:
        print("No measured runs yet — the measurement starts with the next research run.")
        print("(Columns added by migration 0013 on 2026-08-07.)")
        return

    print(f"{'day':<11} {'h':>5} {'reported':>10} {'measured':>10} {'gap':>6}  question")
    print("-" * 92)
    ratios: list[float] = []
    for r in rows:
        measured = (r.s or 0) - (r.e or 0)
        if measured <= 0:
            # Negative/zero = the run crossed the weekly reset (balance refilled).
            print(f"{str(r.day):<11} {r.hours or 0:>5} {'—':>10} {'reset':>10} {'—':>6}  {r.q}")
            continue
        reported = r.total_tokens or 0
        ratio = measured / reported if reported else 0.0
        if ratio:
            ratios.append(ratio)
        print(
            f"{str(r.day):<11} {r.hours or 0:>5} {reported / 1e6:>9.1f}M "
            f"{measured / 1e6:>9.1f}M {ratio:>5.1f}x  {r.q}"
        )

    if ratios:
        avg_ratio = sum(ratios) / len(ratios)
        print("-" * 92)
        print(f"Average accounting gap: {avg_ratio:.1f}x  (n={len(ratios)})")
        print("Note: measured includes parallel Lyra/curator traffic — treat as an upper bound.")


if __name__ == "__main__":
    main()
