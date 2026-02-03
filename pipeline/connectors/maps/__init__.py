"""
Historical map connectors.

Connectors for map sources:
- David Rumsey (historical maps)
- Library of Congress Maps (LoC map collection)
- Pleiades GIS (ancient place GIS data)
"""

from pipeline.connectors.maps.david_rumsey import DavidRumseyConnector
from pipeline.connectors.maps.loc_maps import LOCMapsConnector
from pipeline.connectors.maps.pleiades_gis import PleiadesGISConnector

__all__ = [
    "DavidRumseyConnector",
    "LOCMapsConnector",
    "PleiadesGISConnector",
]
