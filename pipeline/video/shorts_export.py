"""Export one site's short-video inputs to `video-assets/shorts/<slug>/site.json`.

Reads the card text and rarity from `card_stats`, the site row from
`unified_sites`, and every non-excluded Commons image with its attribution from
`wiki_images`. Raw SQL on purpose: `card_stats` is an api-side model and the
import-linter forbids pipeline -> api imports.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.article_html_renderer import slugify
from pipeline.sites_html_renderer import site_path

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "video-assets" / "shorts"

# Orbit zoom for the 3D flyover by site type: a stone circle needs z16 to be
# visible, a city or a geoglyph field needs z13.5 to fit. Unlisted types get
# ORBIT_ZOOM_DEFAULT (tuned on Machu Picchu).
ORBIT_ZOOM_DEFAULT = 14.2
ORBIT_ZOOM_BY_TYPE: dict[str, float] = {
    **dict.fromkeys(
        [
            "Megalithic structures",
            "Megalithic stones",
            "Megalithic statues",
            "Megalithic walls",
            "Megalithic",
            "Stone circle",
            "Dolmen",
            "Henge",
            "Timber circle",
            "Monument",
            "Sculptured stone",
            "Rock art",
            "Petroglyphs",
            "Rock relief/carving",
            "Mound/tumulus",
            "Barrow",
            "Cairn",
            "Gate/archway/bridge",
            "Minaret/tower",
            "Theatre",
            "Well",
            "Tomb",
            "Church/cathedral",
            "Mosque",
            "Temple",
            "Inscription",
            "Bath",
            "Sanctuary",
            "Polygonal masonry",
            "Sacred site",
        ],
        16.0,
    ),
    **dict.fromkeys(
        [
            "Temple complex",
            "Pyramid complex",
            "Necropolis/tombs complex",
            "Castle/palace",
            "Palace",
            "Fortress/citadel",
            "Fortress",
            "Fortification",
            "Wall",
            "Earthwork",
            "Museum",
            "Residence/villa/farmhouse",
            "Forum",
            "Cemetery",
            "Archaeological site",
            "Port",
            "Quarry",
            "Mine/quarry",
            "Reservoir/aqueduct/canal",
            "Cave Structures",
        ],
        15.0,
    ),
    **dict.fromkeys(
        [
            "City/town/settlement",
            "City",
            "Settlement",
            "Geoglyphs",
            "Road/avenue/trackway",
            "Underwater structures",
            "Geological interest",
            "Natural feature",
            "Magnetic anomaly",
            "Infrastructure",
        ],
        13.5,
    ),
}


def orbit_zoom_for(site_type: str | None) -> float:
    return ORBIT_ZOOM_BY_TYPE.get(site_type or "", ORBIT_ZOOM_DEFAULT)


# Tier names mirror api/cardgame/constants.RARITY_TIERS (pipeline may not import api).
RARITY_NAMES: dict[int, str] = {5: "Legendary", 4: "Epic", 3: "Rare", 2: "Uncommon", 1: "Common"}

_SITE_SQL = text(
    """
    SELECT s.id::text AS id, s.name, s.country, s.lat, s.lon, s.site_type, s.period_name,
           s.description,
           c.card_description, c.rarity_tier, c.rarity_score, c.total_power,
           c.antiquity, c.fortification, c.cultural_influence, c.mystery, c.legacy,
           c.civilization
    FROM unified_sites s
    JOIN card_stats c ON c.site_id = s.id
    WHERE s.id = CAST(:site_id AS uuid)
    """
)

_IMAGES_SQL = text(
    """
    SELECT id, filename, original_url, commons_page_url, author, author_url, license,
           license_url, title, is_hero, is_lead, sort_order, width, height
    FROM wiki_images
    WHERE site_id = CAST(:site_id AS uuid) AND NOT is_excluded
    ORDER BY is_hero DESC, is_lead DESC, sort_order, id
    """
)

_LOOKUP_SQL = text(
    """
    SELECT s.id::text AS id
    FROM unified_sites s
    JOIN card_stats c ON c.site_id = s.id
    WHERE s.name = :name
    ORDER BY c.rarity_score DESC NULLS LAST
    LIMIT 1
    """
)


def assemble_site(row: Mapping, images: list[Mapping]) -> dict:
    """Pure: shape one site row plus its image rows into the site.json record."""
    tier = int(row["rarity_tier"] or 1)
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": slugify(row["name"]),
        "country": row["country"],
        "lat": float(row["lat"]),
        "lng": float(row["lon"]),
        "site_type": row["site_type"],
        "orbit_zoom": orbit_zoom_for(row["site_type"]),
        "period_name": row["period_name"],
        "page_path": site_path(row["country"] or "", row["name"], row["id"]),
        "card_text": (row["card_description"] or "").strip(),
        "description": (row["description"] or "").strip(),
        "rarity_tier": tier,
        "rarity_name": RARITY_NAMES[tier],
        "rarity_score": row["rarity_score"],
        "total_power": row["total_power"],
        "stats": {
            k: row[k]
            for k in ("antiquity", "fortification", "cultural_influence", "mystery", "legacy")
        },
        "civilization": row["civilization"],
        "images": [
            {
                "id": img["id"],
                "filename": img["filename"],
                "original_url": img["original_url"],
                "commons_page_url": img["commons_page_url"],
                "author": img["author"],
                "author_url": img["author_url"],
                "license": img["license"],
                "license_url": img["license_url"],
                "title": img["title"],
                "is_hero": bool(img["is_hero"]),
                "width": img["width"],
                "height": img["height"],
            }
            for img in images
        ],
    }


def resolve_site_id(session: Session, name: str) -> str:
    """Site id for an exact name; the highest-rarity card wins on duplicates."""
    row = session.execute(_LOOKUP_SQL, {"name": name}).first()
    if row is None:
        raise LookupError(f"no card-bearing site named {name!r}")
    return row[0]


def export_site(session: Session, site_id: str) -> dict:
    row = session.execute(_SITE_SQL, {"site_id": site_id}).mappings().one()
    images = session.execute(_IMAGES_SQL, {"site_id": site_id}).mappings().all()
    return assemble_site(row, list(images))


def site_dir(site: dict) -> Path:
    return ASSETS_ROOT / site["slug"]


def write_site_json(site: dict) -> Path:
    out = site_dir(site) / "site.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(site, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def load_site_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
