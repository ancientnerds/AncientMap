"""
Museum collection connectors.

Connectors for major museum APIs:
- Metropolitan Museum of Art (REST, CC0)
- Louvre (JSON, terms of use)
- Getty Museum (bulk, CC0)
- Europeana (REST + IIIF, varies)
- Portable Antiquities Scheme (REST, CC-BY-NC-SA)
"""

from pipeline.connectors.museums.europeana import EuropeanaConnector
from pipeline.connectors.museums.getty import GettyMuseumConnector
from pipeline.connectors.museums.louvre import LouvreConnector
from pipeline.connectors.museums.met_museum import MetMuseumConnector
from pipeline.connectors.museums.pas import PASConnector

__all__ = [
    "MetMuseumConnector",
    "LouvreConnector",
    "GettyMuseumConnector",
    "EuropeanaConnector",
    "PASConnector",
]
