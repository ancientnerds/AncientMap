"""
3D model connectors.

Connectors for 3D model sources:
- Sketchfab (3D models)
- CyArk (heritage site models)
- Open Heritage 3D (endangered heritage)
- MorphoSource (biological/archaeological specimens)
"""

from pipeline.connectors.models3d.cyark import CyArkConnector
from pipeline.connectors.models3d.morphosource import MorphoSourceConnector
from pipeline.connectors.models3d.open_heritage_3d import OpenHeritage3DConnector
from pipeline.connectors.models3d.sketchfab import SketchfabConnector

__all__ = [
    "SketchfabConnector",
    "CyArkConnector",
    "OpenHeritage3DConnector",
    "MorphoSourceConnector",
]
