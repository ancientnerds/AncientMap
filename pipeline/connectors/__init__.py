"""
Connectors Module - Unified External Data Sources Integration.

This module provides a unified architecture for integrating 50+ external data sources
into Ancient Nerds Map, replacing scattered frontend services with a clean backend system.

Architecture:
- BaseConnector: Abstract base class for all connectors
- Protocols: REST, SPARQL, ArcGIS, OAI-PMH, IIIF, CTS, MediaWiki handlers
- Registry: Central connector registration and discovery
- Cache: Redis/DB caching layer for responses

Categories:
- museums/: Museum collections (Met, Louvre, Getty, Smithsonian)
- sites/: Archaeological databases (Pleiades, ARIADNE, Historic England)
- papers/: Academic papers (CORE, arXiv, Europe PMC)
- texts/: Books & manuscripts (HathiTrust, Internet Archive, Perseus)
- imagery/: Image sources (Wikimedia Commons, Library of Congress)
- models3d/: 3D models (Sketchfab, Smithsonian 3D, CyArk)
- maps/: Historical maps (David Rumsey, LoC Maps)
- inscriptions/: Epigraphic data (EDH, CDLI, Trismegistos)
- numismatics/: Coin databases (Nomisma, ANS, PAS)
- vocabularies/: Controlled vocabularies (Getty AAT/TGN, PeriodO)
"""

from pipeline.connectors.base import BaseConnector

# Imagery
from pipeline.connectors.imagery import (
    iiif_consortium,
    library_of_congress,
    national_archives,
    wikimedia,
)

# Inscriptions
from pipeline.connectors.inscriptions import cdli, edh, packard, trismegistos

# Maps
from pipeline.connectors.maps import david_rumsey, loc_maps, pleiades_gis

# 3D Models
from pipeline.connectors.models3d import cyark, morphosource, open_heritage_3d, sketchfab

# Import all connectors to trigger registration via @ConnectorRegistry.register decorator
# Museums
from pipeline.connectors.museums import europeana, getty, louvre, met_museum, pas

# Numismatics
from pipeline.connectors.numismatics import ans, nomisma, pas_coins

# Papers
from pipeline.connectors.papers import (
    arxiv,
    core,
    europe_pmc,
    internet_archaeology,
    jstor,
    openalex,
    semantic_scholar,
)
from pipeline.connectors.registry import ConnectorRegistry

# Sites
from pipeline.connectors.sites import (
    ariadne,
    eamena,
    historic_england,
    ireland_smr,
    open_context,
    pleiades,
    tdar,
)

# Texts
from pipeline.connectors.texts import ctext, google_books, hathitrust, internet_archive, perseus
from pipeline.connectors.types import AuthType, ContentItem, ContentType

# Vocabularies
from pipeline.connectors.vocabularies import geonames, getty_aat, getty_tgn, getty_ulan, periodo

__all__ = [
    "BaseConnector",
    "ContentType",
    "ContentItem",
    "AuthType",
    "ConnectorRegistry",
]
