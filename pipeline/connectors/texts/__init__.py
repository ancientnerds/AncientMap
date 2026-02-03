"""
Books and manuscript connectors.

Connectors for text sources:
- HathiTrust (digitized books)
- Internet Archive (books and documents)
- Perseus Digital Library (classical texts)
- Chinese Text Project (classical Chinese texts)
- Google Books (books)
"""

from pipeline.connectors.texts.ctext import ChineseTextProjectConnector
from pipeline.connectors.texts.google_books import GoogleBooksConnector
from pipeline.connectors.texts.hathitrust import HathiTrustConnector
from pipeline.connectors.texts.internet_archive import InternetArchiveConnector
from pipeline.connectors.texts.perseus import PerseusConnector

__all__ = [
    "HathiTrustConnector",
    "InternetArchiveConnector",
    "PerseusConnector",
    "ChineseTextProjectConnector",
    "GoogleBooksConnector",
]
