"""
Imagery connectors.

Connectors for image sources:
- Wikimedia Commons (CC licensed images)
- Library of Congress (photos, prints)
- National Archives (documents, images)
- IIIF Consortium (high-resolution images)
"""

from pipeline.connectors.imagery.iiif_consortium import IIIFConsortiumConnector
from pipeline.connectors.imagery.library_of_congress import LibraryOfCongressConnector
from pipeline.connectors.imagery.national_archives import NationalArchivesConnector
from pipeline.connectors.imagery.wikimedia import WikimediaConnector

__all__ = [
    "WikimediaConnector",
    "LibraryOfCongressConnector",
    "NationalArchivesConnector",
    "IIIFConsortiumConnector",
]
