"""One-off repair for the `caption_garble` alias incident (2026-09-14).

site_identifier wrote the unverified contribution name onto whichever site a
0.35-threshold trigram search had picked, as a `caption_garble` row in
unified_site_names. site_matcher._find_site_by_name treats every row in that
table as authoritative, so the guess became an exact match forever, and
_correct_text_fields then rewrote the published story text with the wrong
site's name.

This script undoes the damage. The writer and the unconditional rewrite are
already removed in code. It is idempotent: every step detects its own work by
the damage that is still present, never by state an earlier step removed.

    dry run:  ssh ancientnerds "docker exec -i ancient_nerds_api python -u -" < scripts/repair_garble_alias_damage.py
    apply:    ssh ancientnerds "docker exec -e APPLY=1 -i ancient_nerds_api python -u -" < scripts/repair_garble_alias_damage.py

Lesson from the first APPLY run: it printed "headlines restored: 195" and
"COMMITTED", yet not one headline changed. Step 1 set attributes on ORM
objects; step 3's session.expire_all() then discarded every unflushed change.
Hence the flush() at the end of step 1 and the post-commit re-read from the
database — counts measured in memory are not evidence.
"""

import os
import re

from sqlalchemy import text

from pipeline.database import NewsItem, UnifiedSiteName, get_session
from pipeline.lyra.site_matcher import _is_same_name, recount_mentions
from pipeline.utils.text import clean_llm_name

APPLY = os.environ.get("APPLY") == "1"
MODE = "APPLY" if APPLY else "DRY RUN"

# A linked item whose extracted name is a DIFFERENT place from the linked site,
# yet whose text carries the site's name, can only have got that name from
# _correct_text_fields() after an exact-path match — and for two different
# names the exact path was a caption_garble alias. Items linked through
# site_identifier's LLM path were never text-rewritten and are left alone.
REWRITTEN_SQL = """
    SELECT ni.id, ni.site_name_extracted, us.name AS site_name
    FROM news_items ni
    JOIN unified_sites us ON us.id = ni.site_id
    WHERE ni.site_name_extracted IS NOT NULL
      AND (   ni.headline  ILIKE '%' || us.name || '%'
           OR ni.summary   ILIKE '%' || us.name || '%'
           OR ni.post_text ILIKE '%' || us.name || '%'
           OR ni.facts::text ILIKE '%' || us.name || '%')
"""


def reverse_rewrite(value: str | None, wrong: str, original: str) -> str | None:
    """Put the source's own wording back: canonical name -> extracted name."""
    if not value:
        return value
    return re.compile(re.escape(wrong), re.IGNORECASE).sub(original, value)


def damaged_rows(session) -> list:
    rows = session.execute(text(REWRITTEN_SQL)).fetchall()
    return [r for r in rows if not _is_same_name(r.site_name_extracted, r.site_name)]


with get_session() as session:
    print(f"=== {MODE} ===\n")

    # ── 1. Restore text and unlink the items a garble match rewrote ─────────
    wrong = damaged_rows(session)
    print(f"news_items rewritten with a different linked site's name: {len(wrong)}")

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

    session.flush()  # step 3's expire_all() would otherwise discard all of this
    print(f"  headlines changed: {text_fixed}")
    for line in samples:
        print(line)

    # ── 2. Drop the aliases themselves ─────────────────────────────────────
    garble = session.query(UnifiedSiteName).filter(UnifiedSiteName.name_type == "caption_garble")
    print(f"\ncaption_garble aliases to delete: {garble.count()}")
    garble.delete(synchronize_session=False)

    # ── 3. Placeholder corrected_name values ───────────────────────────────
    rows = session.execute(
        text("""SELECT id::text, name, corrected_name FROM user_contributions
                WHERE source IN ('lyra','user') AND corrected_name IS NOT NULL""")
    ).fetchall()
    bad = [r for r in rows if clean_llm_name(r.corrected_name) is None]
    print(f"corrected_name placeholders to clear: {len(bad)}")
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
    session.flush()
    after_total = session.execute(
        text("SELECT COALESCE(SUM(mention_count),0) FROM user_contributions WHERE source='lyra'")
    ).scalar()
    print(f"mention_count rows corrected: {changed} (sum {before_total} -> {after_total})")

    if not APPLY:
        session.rollback()
        print("\nrolled back — re-run with APPLY=1 to write")
    else:
        session.commit()
        print("\nCOMMITTED — re-reading from the database:")
        print(f"  items still rewritten with a different site's name: {len(damaged_rows(session))}")
        requeued = session.execute(
            text(
                "SELECT COUNT(*) FROM news_items WHERE site_match_tried = false AND site_name_extracted IS NOT NULL"
            )
        ).scalar()
        garble_left = session.execute(
            text("SELECT COUNT(*) FROM unified_site_names WHERE name_type = 'caption_garble'")
        ).scalar()
        placeholders_left = session.execute(
            text("""SELECT COUNT(*) FROM user_contributions
                    WHERE corrected_name IS NOT NULL AND trim(corrected_name) = ''
                       OR lower(trim(COALESCE(corrected_name,''))) IN ('null','none','unknown','n/a')""")
        ).scalar()
        print(f"  news_items requeued for matching: {requeued}")
        print(f"  caption_garble aliases left: {garble_left}")
        print(f"  corrected_name placeholders left: {placeholders_left}")

    print(f"\n=== {MODE} complete ===")
