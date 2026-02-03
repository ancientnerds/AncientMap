"""
Inscription and epigraphic connectors.

Connectors for inscription sources:
- EDH (Epigraphic Database Heidelberg - Latin inscriptions)
- CDLI (Cuneiform Digital Library Initiative)
- Trismegistos (ancient texts from Egypt/Nile Valley)
- Packard Humanities (Greek inscriptions)
"""

from pipeline.connectors.inscriptions.cdli import CDLIConnector
from pipeline.connectors.inscriptions.edh import EDHConnector
from pipeline.connectors.inscriptions.packard import PackardConnector
from pipeline.connectors.inscriptions.trismegistos import TrismegistosConnector

__all__ = [
    "EDHConnector",
    "CDLIConnector",
    "TrismegistosConnector",
    "PackardConnector",
]
