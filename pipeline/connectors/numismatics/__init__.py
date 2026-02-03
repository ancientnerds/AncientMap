"""
Numismatic (coins) connectors.

Connectors for coin databases:
- Nomisma.org (linked numismatic data)
- American Numismatic Society (ANS collection)
- PAS Coins (Portable Antiquities Scheme coins)
"""

from pipeline.connectors.numismatics.ans import ANSConnector
from pipeline.connectors.numismatics.nomisma import NomismaConnector
from pipeline.connectors.numismatics.pas_coins import PASCoinsConnector

__all__ = [
    "NomismaConnector",
    "ANSConnector",
    "PASCoinsConnector",
]
