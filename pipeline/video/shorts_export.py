"""Export one site's short-video inputs to `video-assets/shorts/<slug>/site.json`.

Reads the card text and rarity from `card_stats`, the site row from
`unified_sites` (with the card hash its `_description_provenance` pins, for the
audit's S13 check), and every non-excluded Commons image with its attribution
from `wiki_images`. Raw SQL on purpose: `card_stats` is an api-side model and the
import-linter forbids pipeline -> api imports.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.sites_html_renderer import site_path
from pipeline.utils.public_sites import RETIRED, not_retired
from pipeline.utils.slugs import slugify

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "video-assets" / "shorts"
FLAGS_DIR = Path(__file__).resolve().parents[2] / "video-assets" / "flags"
# The frontend's country → ISO-3166 mapping (GameCard, FilterPanel, CountryFlag).
COUNTRY_CODES_TS = (
    Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "src" / "utils" / "countryFlags.ts"
)
# Same CDN the game cards use (flagcdn.com/w40); w320 is sharp enough under the name.
FLAG_URL = "https://flagcdn.com/w320/{code}.png"

_COUNTRY_CODES: dict[str, str] | None = None


def country_codes() -> dict[str, str]:
    """`COUNTRY_CODES` from countryFlags.ts, parsed once ('Name': 'CC' pairs)."""
    global _COUNTRY_CODES
    if _COUNTRY_CODES is None:
        src = COUNTRY_CODES_TS.read_text(encoding="utf-8")
        start = src.index("export const COUNTRY_CODES")
        end = src.index("\n}", start)
        pairs = re.findall(r"'([^']+)':\s*'([A-Z]{2,6})'", src[start:end])
        if not pairs:
            raise RuntimeError(f"no country codes parsed from {COUNTRY_CODES_TS}")
        _COUNTRY_CODES = dict(pairs)
    return _COUNTRY_CODES


def country_code_for(country: str | None) -> str | None:
    """Mirror of the frontend's getCountryCode: exact, case-insensitive, then the
    last comma part of a location string — plus its first part, which the
    frontend skips ("Chile, Easter Island" → CL)."""
    if not country:
        return None
    codes = country_codes()
    lower = {name.lower(): code for name, code in codes.items()}
    candidates = [country.strip()]
    if "," in country:
        parts = [p.strip() for p in country.split(",")]
        candidates += [parts[-1], parts[0]]
    for cand in candidates:
        if cand in codes:
            return codes[cand]
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def flag_path(code: str) -> Path:
    return FLAGS_DIR / f"{code.lower()}.png"


def ensure_flag(code: str) -> Path:
    """Cached 320-px flag PNG; fetched from the CDN on first use."""
    path = flag_path(code)
    if path.exists():
        return path
    import httpx

    resp = httpx.get(FLAG_URL.format(code=code.lower()), timeout=30.0, follow_redirects=True)
    if resp.status_code != 200 or not resp.content:
        raise RuntimeError(
            f"flag {code} not available from {FLAG_URL.format(code=code.lower())} "
            f"(HTTP {resp.status_code}); put a PNG at {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return path


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
        16.6,  # a stone circle is ~100 m across; at 16.0 (Stonehenge) it stayed a small ring
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
           s.description, s.scope_status, s.scope_reason,
           c.card_description, c.rarity_tier, c.rarity_score, c.total_power,
           c.antiquity, c.fortification, c.cultural_influence, c.mystery, c.legacy,
           c.civilization,
           s.raw_data -> '_description_provenance' -> 'card' ->> 'text_sha256'
               AS card_text_sha256
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

# A name never resolves to a retired site (E4), as on the site pages: the lookup takes the
# best shown card of that name.
_LOOKUP_SQL = text(
    f"""
    SELECT s.id::text AS id
    FROM unified_sites s
    JOIN card_stats c ON c.site_id = s.id
    WHERE s.name = :name AND {not_retired("s")}
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
        "country_code": country_code_for(row["country"]),
        "lat": float(row["lat"]),
        "lng": float(row["lon"]),
        "site_type": row["site_type"],
        "orbit_zoom": orbit_zoom_for(row["site_type"]),
        "period_name": row["period_name"],
        "page_path": site_path(row["country"] or "", row["name"], row["id"]),
        "card_text": (row["card_description"] or "").strip(),
        # The sha256 the card's provenance pins (Phase 5); None when the card
        # has none. The audit's S13 check compares it with the narrated text.
        "card_text_sha256": row["card_text_sha256"],
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
        raise LookupError(f"no card-bearing site named {name!r} that is not retired")
    return row[0]


class RetiredSite(LookupError):
    """The site is retired (E4, migration 0020): it gets no short."""


def export_site(session: Session, site_id: str) -> dict:
    """The site.json record of one site. A retired site raises RetiredSite: its page answers
    410, and a short would advertise it (the batch never plans one; this covers --site)."""
    row = session.execute(_SITE_SQL, {"site_id": site_id}).mappings().one()
    if row["scope_status"] == RETIRED:
        reason = f": {row['scope_reason']}" if row["scope_reason"] else ""
        raise RetiredSite(f"{row['name']} ({site_id}) is retired (E4){reason} - no short")
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
