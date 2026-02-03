"""
Archaeological site database connectors.

Connectors for site databases:
- Pleiades (gazetteer of ancient places)
- Open Context (archaeological data platform)
- ARIADNE Portal (European archaeological infrastructure)
- EAMENA (Middle East/North Africa heritage)
- Historic England (listed buildings, monuments)
- Ireland SMR (Sites and Monuments Record)
- tDAR (Digital Archaeological Record)
"""

from pipeline.connectors.sites.ariadne import ARIADNEConnector
from pipeline.connectors.sites.eamena import EAMENAConnector
from pipeline.connectors.sites.historic_england import HistoricEnglandConnector
from pipeline.connectors.sites.ireland_smr import IrelandSMRConnector
from pipeline.connectors.sites.open_context import OpenContextConnector
from pipeline.connectors.sites.pleiades import PleiadesConnector
from pipeline.connectors.sites.tdar import TDARConnector

__all__ = [
    "PleiadesConnector",
    "OpenContextConnector",
    "ARIADNEConnector",
    "EAMENAConnector",
    "HistoricEnglandConnector",
    "IrelandSMRConnector",
    "TDARConnector",
]
