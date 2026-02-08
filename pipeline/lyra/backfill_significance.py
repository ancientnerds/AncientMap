"""One-off heuristic backfill: assign significance + news_category to existing news items.

Usage:
    python -m pipeline.lyra.backfill_significance          # dry-run (prints stats)
    python -m pipeline.lyra.backfill_significance --apply  # write to DB
"""

import argparse
import logging
import re
from collections import Counter

from sqlalchemy import text

from pipeline.database import engine

logger = logging.getLogger(__name__)

# ---- Significance keywords (checked against post_text + headline) ----

HIGH_KEYWORDS = {
    10: [r"rewrit(?:es?|ing) history", r"paradigm.shift", r"lost.civ", r"unknown.civilization"],
    9: [r"new(?:ly)?.(?:found|discover)", r"first.(?:ever|of.its.kind)", r"unknown.chamber",
        r"never.before.seen", r"first.time.ever", r"brand.new.site"],
    8: [r"dna.(?:results?|analysis|reveal)", r"major.dat(?:e|ing).revision", r"breakthrough",
        r"isotop(?:e|ic).analysis", r"radiocarbon.(?:dates?|results?)"],
    7: [r"(?:important|major|remarkable).(?:artifact|find|discovery|tomb|structure)",
        r"intact.tomb", r"royal.burial", r"treasure", r"golden"],
}

MEDIUM_KEYWORDS = {
    6: [r"(?:new|recent|published).(?:study|research|paper)", r"peer.review",
        r"reinterpret", r"new.interpretation"],
    5: [r"excavation.progress", r"restoration.complet", r"significant.update",
        r"ongoing.excavation"],
}

LOW_KEYWORDS = {
    2: [r"overview", r"methodology", r"background", r"context", r"introduction"],
    1: [r"subscribe", r"patreon", r"merch", r"sponsor", r"giveaway"],
}

# ---- Category keywords ----

CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
    ("bioarchaeology", [r"dna", r"isotop", r"skeleton", r"burial", r"remains", r"ancient.human", r"diet.analys"]),
    ("dating", [r"radiocarbon", r"carbon.14", r"c-?14", r"dendrochronol", r"dating.(?:results?|revision)", r"thermoluminesc"]),
    ("remote_sensing", [r"lidar", r"satellite", r"drone", r"gpr", r"ground.penetrat", r"aerial.survey", r"magnetometr"]),
    ("underwater", [r"underwater", r"shipwreck", r"submerged", r"marine.archaeol", r"diving"]),
    ("epigraphy", [r"inscription", r"decipher", r"hieroglyph", r"cuneiform", r"script", r"text.analys"]),
    ("conservation", [r"conservat", r"restorat", r"preserv", r"site.protect"]),
    ("heritage", [r"museum", r"repatriat", r"loot(?:ing|ed)", r"cultural.policy", r"heritage"]),
    ("theory", [r"reinterpret", r"alternative.hypothes", r"debate", r"theor(?:y|ies)", r"controver"]),
    ("technology", [r"3d.scan", r"3d.print", r"photogrammetr", r"lab.technique", r"new.method"]),
    ("artifact", [r"potter(?:y|ies)", r"tool(?:s|kit)", r"statue", r"jewel", r"coin(?:s|age)", r"ceramic", r"figurine"]),
    ("architecture", [r"building", r"pyramid", r"temple", r"monument", r"fortress", r"wall(?:s|ed)", r"colum(?:n|ns)", r"mosaic"]),
    ("survey", [r"landscape.survey", r"mapping", r"prospection", r"field.survey"]),
    ("art", [r"painting", r"rock.art", r"petroglyph", r"sculpture", r"fresco"]),
    ("excavation", [r"excavat", r"trench", r"dig(?:ging|s)", r"fieldwork", r"stratigraph"]),
]


def _score_text(text_str: str) -> int:
    """Heuristic significance score from text content."""
    lower = text_str.lower()

    for level, patterns in sorted(HIGH_KEYWORDS.items(), reverse=True):
        for pat in patterns:
            if re.search(pat, lower):
                return level

    for level, patterns in sorted(MEDIUM_KEYWORDS.items(), reverse=True):
        for pat in patterns:
            if re.search(pat, lower):
                return level

    for level, patterns in sorted(LOW_KEYWORDS.items()):
        for pat in patterns:
            if re.search(pat, lower):
                return level

    return 3  # default: routine update


def _categorize_text(text_str: str) -> str:
    """Heuristic category from text content."""
    lower = text_str.lower()

    for category, patterns in CATEGORY_PATTERNS:
        for pat in patterns:
            if re.search(pat, lower):
                return category

    return "general"


def backfill(apply: bool = False) -> None:
    """Scan all news items and assign significance + news_category."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, headline, COALESCE(post_text, '') AS post_text "
            "FROM news_items "
            "WHERE significance IS NULL OR news_category IS NULL"
        )).fetchall()

        logger.info(f"Found {len(rows)} items to backfill")

        sig_counter: Counter[int] = Counter()
        cat_counter: Counter[str] = Counter()

        for row in rows:
            combined = f"{row.headline} {row.post_text}"
            sig = _score_text(combined)
            cat = _categorize_text(combined)
            sig_counter[sig] += 1
            cat_counter[cat] += 1

            if apply:
                conn.execute(text(
                    "UPDATE news_items SET significance = :sig, news_category = :cat WHERE id = :id"
                ), {"sig": sig, "cat": cat, "id": row.id})

        if apply:
            conn.commit()
            logger.info("Backfill applied to database")
        else:
            logger.info("DRY RUN — no changes written")

        logger.info("Significance distribution:")
        for level in range(10, 0, -1):
            if sig_counter[level]:
                logger.info(f"  {level:2d}: {sig_counter[level]}")

        logger.info("Category distribution:")
        for cat, count in cat_counter.most_common():
            logger.info(f"  {cat}: {count}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to DB")
    args = parser.parse_args()
    backfill(apply=args.apply)
