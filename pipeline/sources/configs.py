"""
Source configurations for the unified data loader.

Each source defines:
- name: Display name
- description: What data it contains
- color: Hex color for map display
- icon: Icon identifier for UI
- category: Grouping category
- file_pattern: Expected filename in data/raw/
- format: Parser format key
- license: Data license
- attribution: Attribution text
- is_primary: Whether this is a primary source (optional)
- enabled_by_default: Whether enabled by default (optional)
- priority: Display priority (lower = higher priority, optional)
"""

from typing import TypedDict


class SourceConfigType(TypedDict, total=False):
    name: str
    description: str
    color: str
    icon: str
    category: str
    file_pattern: str
    format: str
    license: str
    attribution: str
    is_primary: bool
    enabled_by_default: bool
    priority: int


SOURCE_CONFIG: dict[str, SourceConfigType] = {
    # Priority 0: PRIMARY SOURCE - Ancient Nerds Original (manually curated)
    "ancient_nerds": {
        "name": "ANCIENT NERDS Originals",
        "description": "Manually researched and curated archaeological sites",
        "color": "#FFD700",  # Gold - primary source
        "icon": "star",
        "category": "Primary",
        "file_pattern": "ancient_nerds_original.geojson",
        "format": "geojson_ancient_nerds",
        "license": "CC BY-SA 4.0",
        "attribution": "Ancient Nerds Research Team",
        "is_primary": True,
        "enabled_by_default": True,
        "priority": 0,  # Highest priority
    },

    # Priority 1: Core ancient world databases
    "pleiades": {
        "name": "Pleiades",
        "description": "Gazetteer of ancient places",
        "color": "#e74c3c",  # Red
        "icon": "landmark",
        "category": "Ancient World",
        "file_pattern": "pleiades-places.csv",
        "format": "csv",
        "license": "CC BY 3.0",
        "attribution": "Pleiades Project",
    },
    "dare": {
        "name": "DARE",
        "description": "Digital Atlas of the Roman Empire",
        "color": "#6c5ce7",  # Violet-blue (Roman purple)
        "icon": "empire",
        "category": "Ancient World",
        "file_pattern": "dare.json",
        "format": "geojson",
        "license": "CC BY-SA 3.0",
        "attribution": "DARE Project, Lund University",
    },
    "topostext": {
        "name": "ToposText",
        "description": "Ancient texts linked to places",
        "color": "#00bcd4",  # Cyan (different from teal coastlines)
        "icon": "scroll",
        "category": "Ancient World",
        "file_pattern": "topostext.json",
        "format": "json_places",
        "license": "CC BY-NC-SA 4.0",
        "attribution": "ToposText Project",
    },

    # Priority 2: Global databases
    "unesco": {
        "name": "UNESCO World Heritage",
        "description": "World Heritage cultural sites",
        "color": "#ffd700",  # Gold/Yellow (UNESCO)
        "icon": "globe",
        "category": "Global",
        "file_pattern": "unesco-whs.json",
        "format": "geojson",
        "license": "Public Domain",
        "attribution": "UNESCO World Heritage Centre",
    },
    "wikidata": {
        "name": "Wikidata",
        "description": "Archaeological sites from Wikidata",
        "color": "#9966ff",  # Purple
        "icon": "database",
        "category": "Global",
        "file_pattern": "wikidata.json",
        "format": "wikidata",
        "license": "CC0",
        "attribution": "Wikidata",
    },

    # Priority 3: Regional databases
    "osm_historic": {
        "name": "OpenStreetMap Historic",
        "description": "Historic sites from OpenStreetMap",
        "color": "#ff9800",  # Orange
        "icon": "map",
        "category": "Global",
        "file_pattern": "osm_historic.json",
        "format": "osm",
        "license": "ODbL",
        "attribution": "OpenStreetMap contributors",
    },
    "historic_england": {
        "name": "Historic England",
        "description": "Scheduled monuments of England",
        "color": "#c0392b",  # Dark red
        "icon": "castle",
        "category": "Europe",
        "file_pattern": "historic_england.json",
        "format": "geojson",
        "license": "Open Government Licence",
        "attribution": "Historic England",
    },
    "ireland_nms": {
        "name": "Ireland National Monuments",
        "description": "Archaeological sites of Ireland",
        "color": "#ff6699",  # Pink
        "icon": "celtic",
        "category": "Europe",
        "file_pattern": "ireland_nms.json",
        "format": "geojson",
        "license": "Open Data",
        "attribution": "National Monuments Service, Ireland",
    },
    "arachne": {
        "name": "Arachne",
        "description": "Archaeological objects database",
        "color": "#8e44ad",  # Dark purple
        "icon": "amphora",
        "category": "Europe",
        "file_pattern": "arachne.json",
        "format": "arachne",
        "license": "CC BY-NC-SA 3.0",
        "attribution": "DAI & CoDArchLab",
    },

    # Priority 4: Specialized databases
    "megalithic_portal": {
        "name": "Megalithic Portal",
        "description": "Megalithic and ancient sites",
        "color": "#9966cc",  # Amethyst Purple
        "icon": "stone",
        "category": "Europe",
        "file_pattern": "megalithic_portal.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Megalithic Portal",
    },
    "sacred_sites": {
        "name": "Sacred Sites",
        "description": "Sacred and spiritual sites worldwide",
        "color": "#ff69b4",  # Hot Pink
        "icon": "star",
        "category": "Global",
        "file_pattern": "sacred_sites.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Sacred Sites Project",
    },
    "rock_art": {
        "name": "Rock Art",
        "description": "Rock art and petroglyphs",
        "color": "#e67e22",  # Dark orange
        "icon": "paint",
        "category": "Global",
        "file_pattern": "rock_art.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Rock Art Database",
    },

    # Inscriptions & Texts
    "inscriptions_edh": {
        "name": "EDH Inscriptions",
        "description": "Latin inscriptions database",
        "color": "#5dade2",  # Light blue
        "icon": "inscription",
        "category": "Inscriptions",
        "file_pattern": "inscriptions_edh.json",
        "format": "edh",
        "license": "CC BY-SA 3.0",
        "attribution": "Epigraphic Database Heidelberg",
    },

    # Maritime & Shipwrecks
    "shipwrecks_oxrep": {
        "name": "OXREP Shipwrecks",
        "description": "Ancient Mediterranean shipwrecks",
        "color": "#0066ff",  # Ocean Blue
        "icon": "ship",
        "category": "Maritime",
        "file_pattern": "shipwrecks_oxrep.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "Oxford Roman Economy Project",
    },

    # Numismatics
    "coins_nomisma": {
        "name": "Nomisma Coins",
        "description": "Ancient coin mints and finds",
        "color": "#d4af37",  # Gold
        "icon": "coin",
        "category": "Numismatics",
        "file_pattern": "coins_nomisma.json",
        "format": "nomisma",
        "license": "CC BY 4.0",
        "attribution": "Nomisma.org",
    },

    # Environmental
    "volcanic_holvol": {
        "name": "HolVol Volcanic",
        "description": "Holocene volcanic eruptions",
        "color": "#ff0000",  # Bright Red
        "icon": "volcano",
        "category": "Environmental",
        "file_pattern": "volcanic_holvol.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "HolVol Database",
    },
    "earth_impacts": {
        "name": "Earth Impact Database",
        "description": "Confirmed meteorite impact craters",
        "color": "#FF6B35",  # Orange-red
        "icon": "crater",
        "category": "Geological",
        "file_pattern": "earth_impacts.geojson",
        "format": "geojson_impacts",
        "license": "Public Domain",
        "attribution": "Earth Impact Database / Planetary and Space Science Centre",
        "priority": 26,
    },

    # NCEI Natural Hazards
    "ncei_earthquakes": {
        "name": "NCEI Significant Earthquakes",
        "description": "Significant earthquakes with impact data",
        "color": "#FF6347",  # Tomato red
        "icon": "shake",
        "category": "Geological",
        "file_pattern": "ncei_earthquakes.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },
    "ncei_tsunamis": {
        "name": "NCEI Tsunami Events",
        "description": "Tsunami source events",
        "color": "#1E90FF",  # Dodger blue
        "icon": "wave",
        "category": "Geological",
        "file_pattern": "ncei_tsunamis.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },
    "ncei_tsunami_obs": {
        "name": "NCEI Tsunami Observations",
        "description": "Tsunami observation points",
        "color": "#4169E1",  # Royal blue
        "icon": "wave",
        "category": "Geological",
        "file_pattern": "ncei_tsunami_observations.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },
    "ncei_volcanoes": {
        "name": "NCEI Significant Volcanic Eruptions",
        "description": "Volcanic eruptions with impact data",
        "color": "#FF4500",  # Orange red
        "icon": "volcano",
        "category": "Geological",
        "file_pattern": "ncei_volcanoes.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },

    # 3D Models
    "models_sketchfab": {
        "name": "Sketchfab 3D Models",
        "description": "3D scans of archaeological sites",
        "color": "#1da1f2",  # Sketchfab blue
        "icon": "cube",
        "category": "3D Models",
        "file_pattern": "models_sketchfab.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Sketchfab",
    },

    # Boundaries
    "boundaries_seshat": {
        "name": "Seshat Boundaries",
        "description": "Historical polity boundaries",
        "color": "#a29bfe",  # Light purple
        "icon": "boundary",
        "category": "Boundaries",
        "file_pattern": "boundaries_seshat.json",
        "format": "json_sites",
        "license": "CC BY-NC-SA 4.0",
        "attribution": "Seshat Databank",
    },

    # Americas
    "dinaa": {
        "name": "DINAA",
        "description": "North American archaeology",
        "color": "#cd853f",  # Peru/brown
        "icon": "teepee",
        "category": "Americas",
        "file_pattern": "dinaa.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "Digital Index of North American Archaeology",
    },

    # Middle East & Africa
    "eamena": {
        "name": "EAMENA",
        "description": "Endangered archaeology MENA region",
        "color": "#d35400",  # Dark orange
        "icon": "pyramid",
        "category": "Middle East",
        "file_pattern": "eamena.json",
        "format": "eamena",
        "license": "CC BY 4.0",
        "attribution": "EAMENA Database",
    },

    # Open Context
    "open_context": {
        "name": "Open Context",
        "description": "Open archaeological data",
        "color": "#2980b9",  # Strong blue
        "icon": "dig",
        "category": "Global",
        "file_pattern": "open_context.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "Open Context",
    },

    # Museum Collections
    "europeana": {
        "name": "Europeana",
        "description": "European cultural heritage",
        "color": "#0a72cc",  # Europeana blue
        "icon": "museum",
        "category": "Museums",
        "file_pattern": "europeana.json",
        "format": "json_sites",
        "license": "CC BY-SA 4.0",
        "attribution": "Europeana",
    },

    # Historical Maps
    "david_rumsey": {
        "name": "David Rumsey Maps",
        "description": "Historical map collection",
        "color": "#8b4513",  # Saddle brown
        "icon": "map-old",
        "category": "Maps",
        "file_pattern": "david_rumsey.json",
        "format": "maps",
        "license": "CC BY-NC-SA 3.0",
        "attribution": "David Rumsey Map Collection",
    },
}


# Site types to EXCLUDE from Wikidata and OSM (mostly medieval/modern)
EXCLUDED_MODERN_TYPES = {
    # Religious buildings (mostly medieval/modern)
    "church", "cathedral", "chapel", "monastery", "abbey", "priory",
    "mosque", "synagogue",
    # Modern memorials
    "memorial", "cenotaph", "war_memorial",
    # Cemeteries (mostly modern)
    "cemetery", "grave_yard", "graveyard",
    # Industrial heritage
    "mine", "mill", "factory", "industrial",
    # Transportation
    "railway", "railway_station", "station", "bridge",
    # Misc modern
    "cannon", "tank", "aircraft", "ship",
    "milestone", "boundary_stone", "wayside_cross", "wayside_shrine",
}


# Site types that ARE ancient (whitelist for strict filtering)
ANCIENT_SITE_TYPES = {
    "archaeological_site", "ruin", "ruins", "tomb", "tumulus", "barrow",
    "dolmen", "menhir", "stone_circle", "megalith", "fort", "hillfort",
    "castle", "temple", "settlement", "city", "amphitheatre", "theatre",
    "aqueduct", "roman", "celtic", "prehistoric", "neolithic",
    "bronze_age", "iron_age", "ancient",
}
