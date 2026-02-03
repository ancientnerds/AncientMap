"""
Academic paper connectors.

Connectors for academic paper sources:
- CORE (open access papers)
- JSTOR/Constellate (academic journals)
- Internet Archaeology (archaeological papers)
- arXiv (preprints)
- Europe PMC (life science papers)
- Semantic Scholar (AI-powered research tool)
- OpenAlex (open catalog of scholarly works)
"""

from pipeline.connectors.papers.arxiv import ArXivConnector
from pipeline.connectors.papers.core import COREConnector
from pipeline.connectors.papers.europe_pmc import EuropePMCConnector
from pipeline.connectors.papers.internet_archaeology import InternetArchaeologyConnector
from pipeline.connectors.papers.jstor import JSTORConnector
from pipeline.connectors.papers.openalex import OpenAlexConnector
from pipeline.connectors.papers.semantic_scholar import SemanticScholarConnector

__all__ = [
    "COREConnector",
    "JSTORConnector",
    "InternetArchaeologyConnector",
    "ArXivConnector",
    "EuropePMCConnector",
    "SemanticScholarConnector",
    "OpenAlexConnector",
]
