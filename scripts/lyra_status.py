"""Quick status dashboard for the Lyra pipeline.

Shows pipeline state at a glance: heartbeat, discovery counts, recent processing, news/video stats.

Usage:
    python scripts/lyra_status.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from sqlalchemy import text

from pipeline.database import engine


def format_ago(dt: datetime) -> str:
    """Format a datetime as 'X min ago' or 'X hours ago'."""
    now = datetime.now(timezone.utc)
    delta = now - dt
    minutes = int(delta.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m ago"


def _query(conn, sql: str):
    """Run a query, returning None if the table doesn't exist yet."""
    try:
        return conn.execute(text(sql))
    except Exception:
        conn.rollback()
        return None


def main() -> None:
    with engine.connect() as conn:
        print("\n=== Lyra Pipeline Status ===\n")

        # --- Heartbeat ---
        result = _query(conn,
            "SELECT last_heartbeat, status, last_error FROM pipeline_heartbeats WHERE pipeline_name = 'lyra'"
        )
        row = result.fetchone() if result else None
        if row:
            hb_time, hb_status, hb_error = row
            ago = format_ago(hb_time)
            status_label = "OK" if hb_status == "ok" else f"ERROR: {hb_error}"
            print(f"Heartbeat: {hb_time.strftime('%Y-%m-%d %H:%M:%S')} ({ago}) -- {status_label}")
        else:
            print("Heartbeat: no data (pipeline has never run)")

        # --- Discovery counts ---
        result = _query(conn,
            "SELECT enrichment_status, COUNT(*) FROM user_contributions "
            "WHERE source='lyra' GROUP BY enrichment_status ORDER BY enrichment_status"
        )
        rows = result.fetchall() if result else []
        counts = {r[0]: r[1] for r in rows}
        total = sum(counts.values())

        print(f"\nDiscovery counts:")
        if total:
            for status in ["matched", "enriched", "promoted", "pending", "rejected", "failed"]:
                if status in counts:
                    print(f"  {status:<12} {counts[status]:>4}")
            print(f"  {'total':<12} {total:>4}")
        else:
            print("  (none)")

        # --- Recent processing ---
        result = _query(conn, """
            SELECT uc.name, uc.enrichment_status,
                   uc.enrichment_data->>'matched_site_name' AS matched_name,
                   uc.enrichment_data->>'matched_source' AS matched_source,
                   uc.wikidata_id, uc.lat, uc.lon, uc.thumbnail_url, uc.score
            FROM user_contributions uc
            WHERE uc.source = 'lyra'
            ORDER BY uc.created_at DESC
            LIMIT 10
        """)
        recent = result.fetchall() if result else []

        if recent:
            print(f"\nRecent processing (last {len(recent)}):")
            for r in recent:
                name = r[0][:20].ljust(20)
                status = r[1]
                matched = f"-> {r[2]} ({r[3]})" if r[2] else f"(score={r[8] or 0})"
                wiki = "wiki=Y" if r[4] else "wiki=N"
                coords = "coords=Y" if (r[5] is not None and r[6] is not None) else "coords=N"
                thumb = "thumb=Y" if r[7] else "thumb=N"
                print(f"  {name} {status:<10} {matched:<35} {wiki} {coords} {thumb}")

        # --- News feed ---
        result = _query(conn,
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'published'), "
            "COUNT(*) FILTER (WHERE status = 'pending') FROM news_items"
        )
        news_row = result.fetchone() if result else None
        if news_row:
            print(f"\nNews feed: {news_row[0]} posts ({news_row[1]} published, {news_row[2]} pending)")

        # --- Videos ---
        result = _query(conn,
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE description IS NULL OR description = '') FROM news_videos"
        )
        vid_row = result.fetchone() if result else None
        if vid_row:
            print(f"Videos: {vid_row[0]} total ({vid_row[1]} missing descriptions)")

        print()


if __name__ == "__main__":
    main()
