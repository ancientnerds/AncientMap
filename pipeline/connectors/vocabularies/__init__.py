"""
Controlled vocabulary connectors.

Connectors for vocabulary/thesaurus sources:
- Getty AAT (Art & Architecture Thesaurus)
- Getty TGN (Thesaurus of Geographic Names)
- Getty ULAN (Union List of Artist Names)
- PeriodO (historical period definitions)
- GeoNames (geographic place names)
"""

from pipeline.connectors.vocabularies.geonames import GeoNamesConnector
from pipeline.connectors.vocabularies.getty_aat import GettyAATConnector
from pipeline.connectors.vocabularies.getty_tgn import GettyTGNConnector
from pipeline.connectors.vocabularies.getty_ulan import GettyULANConnector
from pipeline.connectors.vocabularies.periodo import PeriodOConnector

__all__ = [
    "GettyAATConnector",
    "GettyTGNConnector",
    "GettyULANConnector",
    "PeriodOConnector",
    "GeoNamesConnector",
]
