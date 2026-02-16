"""
Imagery connectors.

Connectors for image sources:
- Wikimedia Commons (CC licensed images)
- Wikidata (videos and papers via Commons)
- Library of Congress (photos, prints)
- National Archives (documents, images)
- IIIF Consortium (high-resolution images)

Shared services:
- WikimediaResolver (entity resolution + cache shared between Wiki* connectors)
"""

from pipeline.connectors.imagery.iiif_consortium import IIIFConsortiumConnector
from pipeline.connectors.imagery.library_of_congress import LibraryOfCongressConnector
from pipeline.connectors.imagery.national_archives import NationalArchivesConnector
from pipeline.connectors.imagery.wikidata import WikidataConnector
from pipeline.connectors.imagery.wikimedia import WikimediaConnector
from pipeline.connectors.imagery.wikimedia_resolver import WikimediaResolver

__all__ = [
    "WikimediaConnector",
    "WikidataConnector",
    "WikimediaResolver",
    "LibraryOfCongressConnector",
    "NationalArchivesConnector",
    "IIIFConsortiumConnector",
]
