"""
Protocol handlers for different API types.

Each protocol handler provides a consistent interface for communicating
with external services that use that protocol.

Protocols:
- REST: Standard REST/JSON APIs (most common)
- SPARQL: SPARQL endpoints (British Museum, Getty, CDLI, Wikidata)
- ArcGIS: ArcGIS Feature Services (Historic England, Ireland SMR)
- OAI-PMH: OAI-PMH harvesting (arXiv, Europeana metadata)
- IIIF: IIIF Image/Presentation API (museums with high-res images)
- CTS: Canonical Text Services (Perseus Digital Library)
- MediaWiki: MediaWiki API (Wikimedia Commons)
"""

from pipeline.connectors.protocols.arcgis import ArcGISProtocol
from pipeline.connectors.protocols.cts import (
    CTS_ENDPOINTS,
    HOMER_URNS,
    CTSError,
    CTSPassage,
    CTSProtocol,
    CTSReference,
    CTSWork,
)
from pipeline.connectors.protocols.iiif import IIIFProtocol
from pipeline.connectors.protocols.mediawiki import MediaWikiProtocol
from pipeline.connectors.protocols.oai_pmh import OAIError, OAIListResult, OAIPMHProtocol, OAIRecord
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.protocols.sparql import COMMON_PREFIXES, SparqlProtocol, with_prefixes

__all__ = [
    # REST
    "RestProtocol",
    # SPARQL
    "SparqlProtocol",
    "COMMON_PREFIXES",
    "with_prefixes",
    # ArcGIS
    "ArcGISProtocol",
    # IIIF
    "IIIFProtocol",
    # MediaWiki
    "MediaWikiProtocol",
    # OAI-PMH
    "OAIPMHProtocol",
    "OAIRecord",
    "OAIListResult",
    "OAIError",
    # CTS
    "CTSProtocol",
    "CTSWork",
    "CTSPassage",
    "CTSReference",
    "CTSError",
    "CTS_ENDPOINTS",
    "HOMER_URNS",
]
