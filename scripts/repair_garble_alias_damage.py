"""One-off repair for the `caption_garble` alias incident (2026-09-14).

site_identifier wrote the unverified contribution name onto whichever site a
0.35-threshold trigram search had picked, as a `caption_garble` row in
unified_site_names. site_matcher._find_site_by_name treats every row in that
table as authoritative, so the guess became an exact match forever, and
_correct_text_fields then rewrote the published story text with the wrong
site's name.

This script undoes the damage. The writer and the unconditional rewrite are
already removed in code; run this once against prod afterwards.

    dry run:  ssh ancientnerds "docker exec -i ancient_nerds_api python -u -" < scripts/repair_garble_alias_damage.py
    apply:    ssh ancientnerds "docker exec -e APPLY=1 -i ancient_nerds_api python -u -" < scripts/repair_garble_alias_damage.py
"""

import os
import re

from sqlalchemy import text

from pipeline.database import NewsItem, UnifiedSiteName, get_session
from pipeline.lyra.site_matcher import _is_same_name, recount_mentions
from pipeline.utils.text import clean_llm_name

APPLY = os.environ.get("APPLY") == "1"
MODE = "APPLY" if APPLY else "DRY RUN"


def reverse_rewrite(value: str | None, wrong: str, original: str) -> str | None:
    """Put the source's own wording back: canonical name -> extracted name."""
    if not value:
        return value
    return re.compile(re.escape(wrong), re.IGNORECASE).sub(original, value)


with get_session() as session:
    print(f"=== {MODE} ===\n")

    # ── 1. News items linked through a caption_garble alias ────────────────
    linked = session.execute(
        text("""
        SELECT ni.id, ni.site_name_extracted, us.name AS site_name
        FROM news_items ni
        JOIN unified_sites us ON us.id = ni.site_id
        WHERE EXISTS (
            SELECT 1 FROM unified_site_names usn
            WHERE usn.site_id = ni.site_id
              AND usn.name_type = 'caption_garble'
              AND lower(usn.name) = lower(ni.site_name_extracted)
        )
    """)
    ).fetchall()
    print(f"news_items linked via a caption_garble alias: {len(linked)}")

    wrong = [r for r in linked if not _is_same_name(r.site_name_extracted, r.site_name)]
    print(f"  of those, linked to a DIFFERENT place: {len(wrong)}")

    text_fixed = 0
    samples: list[str] = []
    for row in wrong:
        item = session.get(NewsItem, row.id)
        if item is None:
            continue
        before = item.headline
        item.headline = reverse_rewrite(item.headline, row.site_name, row.site_name_extracted)
        item.post_text = reverse_rewrite(item.post_text, row.site_name, row.site_name_extracted)
        item.summary = reverse_rewrite(item.summary, row.site_name, row.site_name_extracted)
        if item.facts:
            item.facts = [
                reverse_rewrite(f, row.site_name, row.site_name_extracted) or f for f in item.facts
            ]
        if before != item.headline:
            text_fixed += 1
            if len(samples) < 15:
                samples.append(f"    - {before}\n    + {item.headline}")
        # Unlink and requeue: the match was a memoized guess, not a decision.
        item.site_id = None
        item.site_match_tried = False

    print(f"  headlines restored: {text_fixed}")
    for s in samples:
        print(s)

    # ── 2. Drop the aliases themselves ─────────────────────────────────────
    garble = session.query(UnifiedSiteName).filter(
        UnifiedSiteName.name_type == "caption_garble"
    )
    garble_count = garble.count()
    on_an = session.execute(
        text("""SELECT COUNT(*) FROM unified_site_names usn
                JOIN unified_sites us ON us.id = usn.site_id
                WHERE usn.name_type='caption_garble' AND us.source_id='ancient_nerds'""")
    ).scalar()
    print(f"\ncaption_garble aliases to delete: {garble_count} ({on_an} of them on curated sites)")
    if APPLY:
        garble.delete(synchronize_session=False)

    # ── 3. Placeholder corrected_name values ───────────────────────────────
    rows = session.execute(
        text("""SELECT id::text, name, corrected_name FROM user_contributions
                WHERE source IN ('lyra','user') AND corrected_name IS NOT NULL""")
    ).fetchall()
    bad = [r for r in rows if clean_llm_name(r.corrected_name) is None]
    print(f"\ncorrected_name placeholders to clear: {len(bad)}")
    for r in bad[:10]:
        print(f"    '{r.name}' had corrected_name={r.corrected_name!r}")
    if bad:
        session.execute(
            text(
                "UPDATE user_contributions SET corrected_name = NULL "
                "WHERE id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": [r.id for r in bad]},
        )
        # Raw UPDATE bypasses the identity map; recount_mentions below reads
        # corrected_name off ORM objects and would otherwise still see 'null'.
        session.expire_all()

    # ── 4. Rebuild mention_count from the real news items ──────────────────
    before_total = session.execute(
        text("SELECT COALESCE(SUM(mention_count),0) FROM user_contributions WHERE source='lyra'")
    ).scalar()
    changed = recount_mentions(session)
    session.flush()  # without this the SUM below re-reads the pre-change rows
    after_total = session.execute(
        text("SELECT COALESCE(SUM(mention_count),0) FROM user_contributions WHERE source='lyra'")
    ).scalar()
    print(f"\nmention_count rows corrected: {changed} (sum {before_total} -> {after_total})")
    zeroed = session.execute(
        text("SELECT COUNT(*) FROM user_contributions WHERE source='lyra' AND mention_count = 0")
    ).scalar()
    print(f"  contributions now at 0 mentions: {zeroed} (visible — min_mentions defaults to 0)")

    # ── 5. Sites left with no name at all after the alias delete ───────────
    orphans = session.execute(
        text("""SELECT COUNT(*) FROM unified_sites us
                WHERE NOT EXISTS (SELECT 1 FROM unified_site_names usn WHERE usn.site_id = us.id)
                  AND us.source_id = 'ancient_nerds'""")
    ).scalar()
    print(f"curated sites with no unified_site_names row: {orphans}")

    if APPLY:
        session.commit()
        print("\nCOMMITTED")
    else:
        session.rollback()
        print("\nrolled back — re-run with APPLY=1 to write")

    print(f"\n=== {MODE} complete ===")
