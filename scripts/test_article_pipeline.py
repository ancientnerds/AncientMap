"""
Seed 4 test news items and generate a weekly article from them.

Usage (run inside the api container):
    docker exec ancient_nerds_api python scripts/test_article_pipeline.py
    docker exec ancient_nerds_api python scripts/test_article_pipeline.py --cleanup

--cleanup  Remove all TEST_ channels/videos/items and test articles, then exit.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_article_pipeline")

# ---------------------------------------------------------------------------
# Test data — 4 items across 4 categories
# ---------------------------------------------------------------------------

TEST_CHANNEL_ID = "TEST_CHANNEL_ANCIENT_NERDS"
TEST_CHANNEL_NAME = "Ancient Nerds Test Channel"

TEST_VIDEOS = [
    {
        "id": "TEST_VID_EXCAVATION01",
        "title": "New Excavations at Jericho Reveal 10,000-Year-Old Ritual Complex",
        "category": "excavation",
    },
    {
        "id": "TEST_VID_ARTIFACT01",
        "title": "Bronze Age Sword Hoard Discovered in Danish Bog — 37 Weapons Perfectly Preserved",
        "category": "artifact",
    },
    {
        "id": "TEST_VID_DATING01",
        "title": "Radiocarbon Dates Rewrite Stonehenge Timeline — Bluestones Older Than Thought",
        "category": "dating",
    },
    {
        "id": "TEST_VID_ARCHITECTURE01",
        "title": "LiDAR Survey Uncovers Lost Mayan City Beneath Guatemalan Jungle",
        "category": "architecture",
    },
]

TEST_ITEMS = [
    {
        "video_id": "TEST_VID_EXCAVATION01",
        "headline": "10,000-Year-Old Ritual Complex Found at Jericho",
        "summary": (
            "Archaeologists excavating at Tell es-Sultan (ancient Jericho) have uncovered "
            "a large communal structure dating to approximately 8,500 BCE, featuring plastered "
            "floors, a central hearth, and dozens of animal skulls arranged in a deliberate "
            "pattern along the walls. The complex predates the famous Neolithic tower by "
            "several centuries and suggests organised ritual activity far earlier than "
            "previously documented at the site."
        ),
        "facts": [
            "Structure dated to ~8,500 BCE via AMS radiocarbon on charcoal from hearth",
            "Plastered skull arrangement similar to PPNB ancestor veneration practices at 'Ain Ghazal",
            "Complex measures 18×12 metres — largest pre-pottery Neolithic structure found at Jericho",
        ],
        "news_category": "excavation",
        "significance": 9,
        "timestamp_seconds": 312,
        "site_name_extracted": "Tell es-Sultan",
    },
    {
        "video_id": "TEST_VID_ARTIFACT01",
        "headline": "37 Bronze Age Swords Pulled from Danish Bog in Pristine Condition",
        "summary": (
            "A peat-cutting operation in Jutland, Denmark, has yielded a hoard of 37 bronze "
            "swords dating to approximately 900–700 BCE, still wrapped in what appear to be "
            "organic sheaths. The weapons show no battle damage and were clearly deposited "
            "intentionally, likely as a votive offering. This is the largest Bronze Age weapon "
            "deposit ever found in Scandinavia and will significantly advance understanding of "
            "Late Bronze Age exchange networks."
        ),
        "facts": [
            "37 swords, 12 spearheads, and 4 shields — total 53 objects",
            "Peat environment preserved organic handles and leather sheaths",
            "Lead isotope analysis indicates Iberian copper sources — evidence of long-distance trade",
            "Dated 900–700 BCE via dendrochronology of wooden hafts",
        ],
        "news_category": "artifact",
        "significance": 9,
        "timestamp_seconds": 540,
        "site_name_extracted": "Jutland bog, Denmark",
    },
    {
        "video_id": "TEST_VID_DATING01",
        "headline": "New Dates Push Stonehenge Bluestones Back 500 Years",
        "summary": (
            "A reanalysis of sediment cores and charred bone fragments from beneath the "
            "Stonehenge bluestone sockets has produced radiocarbon dates clustering around "
            "3,400–3,200 BCE — pushing the first erection of the Welsh bluestones back by "
            "roughly 500 years compared to previous estimates. The findings suggest the "
            "monument's construction history is significantly more complex than the accepted "
            "narrative and that Preseli Hills quarrying began during the Neolithic rather "
            "than the Chalcolithic."
        ),
        "facts": [
            "14 new AMS dates from charred hazelnut shells in bluestone socket fills",
            "Earliest dates: 3,410–3,210 BCE (95% confidence)",
            "Previous consensus date for bluestone erection: ~2,900–2,600 BCE",
            "Implies bluestone transport predates Salisbury Plain's cursus monuments",
        ],
        "news_category": "dating",
        "significance": 8,
        "timestamp_seconds": 720,
        "site_name_extracted": "Stonehenge",
    },
    {
        "video_id": "TEST_VID_ARCHITECTURE01",
        "headline": "LiDAR Reveals 40km² Lost Maya City Hidden in Guatemalan Forest",
        "summary": (
            "A high-resolution airborne LiDAR survey of the Petén Basin in Guatemala has "
            "revealed a previously unknown Maya urban centre covering at least 40 square "
            "kilometres, featuring a central acropolis, three ball courts, and an extensive "
            "causeway network connecting it to the known site of El Mirador 18 km to the "
            "north. Ceramic surface scatters suggest occupation from roughly 350 BCE to "
            "900 CE, spanning the entire Classic period. The city — provisionally named "
            "Cuauhtémoc — may have been a key node in the Mirador Basin political network."
        ),
        "facts": [
            "LiDAR point density: 25 returns/m² — highest resolution survey of Petén to date",
            "Acropolis platform: 380m × 240m, estimated 45m height",
            "Three ball courts, two reservoirs, 12 stelae identified from laser returns",
            "18km causeway (sacbé) connects site directly to El Mirador",
        ],
        "news_category": "architecture",
        "significance": 10,
        "timestamp_seconds": 187,
        "site_name_extracted": "Cuauhtémoc (provisional)",
    },
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def seed_test_data(session) -> None:
    from pipeline.database import NewsChannel, NewsItem, NewsVideo

    # Channel
    if not session.get(NewsChannel, TEST_CHANNEL_ID):
        session.add(NewsChannel(id=TEST_CHANNEL_ID, name=TEST_CHANNEL_NAME, enabled=True))
        logger.info(f"Created channel: {TEST_CHANNEL_NAME}")

    # Videos
    for v in TEST_VIDEOS:
        if not session.get(NewsVideo, v["id"]):
            session.add(
                NewsVideo(
                    id=v["id"],
                    channel_id=TEST_CHANNEL_ID,
                    title=v["title"],
                    status="summarized",
                    published_at=datetime.now(UTC),
                    duration_minutes=30.0,
                )
            )
            logger.info(f"Created video: {v['title'][:60]}")

    session.flush()

    # News items
    now = datetime.now(UTC)
    for item in TEST_ITEMS:
        ni = NewsItem(
            video_id=item["video_id"],
            headline=item["headline"],
            summary=item["summary"],
            facts=item["facts"],
            news_category=item["news_category"],
            significance=item["significance"],
            timestamp_seconds=item["timestamp_seconds"],
            site_name_extracted=item["site_name_extracted"],
            created_at=now,
        )
        session.add(ni)
        logger.info(f"Created news item: {item['headline'][:60]}")


def cleanup_test_data(session) -> None:
    from pipeline.database import NewsArticle, NewsChannel, NewsItem, NewsVideo

    video_ids = [v["id"] for v in TEST_VIDEOS]

    deleted_items = (
        session.query(NewsItem).filter(NewsItem.video_id.in_(video_ids)).delete(synchronize_session=False)
    )
    deleted_videos = (
        session.query(NewsVideo).filter(NewsVideo.id.in_(video_ids)).delete(synchronize_session=False)
    )
    deleted_channels = (
        session.query(NewsChannel)
        .filter(NewsChannel.id == TEST_CHANNEL_ID)
        .delete(synchronize_session=False)
    )

    # Remove test articles (identified by video_ids in their video_ids JSONB field)
    # Simpler: remove articles that reference any test video ID
    articles = session.query(NewsArticle).all()
    deleted_articles = 0
    for a in articles:
        if a.video_ids and any(vid in (a.video_ids or []) for vid in video_ids):
            session.delete(a)
            deleted_articles += 1

    logger.info(
        f"Cleaned up: {deleted_items} news items, {deleted_videos} videos, "
        f"{deleted_channels} channels, {deleted_articles} articles"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="Remove test data and exit")
    args = parser.parse_args()

    from pipeline.database import get_session
    from pipeline.lyra.article_generator import generate_weekly_article
    from pipeline.lyra.config import LyraSettings

    settings = LyraSettings()

    if args.cleanup:
        with get_session() as session:
            cleanup_test_data(session)
        print("Cleanup complete.")
        return

    if not settings.anthropic_api_key:
        print("ERROR: LYRA_ANTHROPIC_API_KEY not set — cannot generate article.")
        sys.exit(1)

    # Seed
    with get_session() as session:
        seed_test_data(session)

    logger.info("Test data seeded. Generating article...")

    # Generate
    created = generate_weekly_article(settings)

    if not created:
        print("\nArticle generation returned False — check logs above.")
        print("(An article for this week may already exist; run --cleanup first.)")
        sys.exit(1)

    # Print result
    from pipeline.database import NewsArticle, get_session as gs

    with gs() as session:
        from pipeline.lyra.article_generator import _get_week_range
        week_start, _ = _get_week_range()
        article = session.query(NewsArticle).filter(NewsArticle.week_start == week_start).first()
        if article:
            print("\n" + "=" * 70)
            print(f"TITLE: {article.title}")
            print("=" * 70)
            print(f"SUMMARY: {article.summary}")
            print("-" * 70)
            print(article.content)
            print("=" * 70)
            print(f"Article ID: {article.id}  |  week_start: {article.week_start.date()}")


if __name__ == "__main__":
    main()
