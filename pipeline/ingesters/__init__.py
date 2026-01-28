"""
Data ingesters for various archaeological data sources.

Each ingester is responsible for fetching, parsing, and normalizing data
from a specific source into our standard schema.
"""

from pipeline.ingesters.base import BaseIngester, IngesterResult, ParsedSite

# PRIMARY source - Ancient Nerds Original (manually curated)
from pipeline.ingesters.ancient_nerds_original import AncientNerdsOriginalIngester

# Core ingesters
from pipeline.ingesters.pleiades import PleiadesIngester
from pipeline.ingesters.unesco import UNESCOIngester
from pipeline.ingesters.geonames import GeoNamesIngester
from pipeline.ingesters.open_context import OpenContextIngester
from pipeline.ingesters.wikidata import WikidataIngester

# Regional ingesters - Europe
from pipeline.ingesters.historic_england import HistoricEnglandIngester
from pipeline.ingesters.ireland_nms import IrelandNMSIngester
from pipeline.ingesters.arachne import ArachneIngester
from pipeline.ingesters.dare import DAREIngester

# Regional ingesters - Middle East / Africa
from pipeline.ingesters.eamena import EAMENAIngester

# Regional ingesters - North America
from pipeline.ingesters.dinaa import DINAAIngester

# Sacred & Rock Art
from pipeline.ingesters.sacred_sites import SacredSitesIngester
from pipeline.ingesters.rock_art import RockArtIngester

# Specialized
from pipeline.ingesters.osm_historic import OSMHistoricIngester
from pipeline.ingesters.megalithic_portal import MegalithicPortalIngester
from pipeline.ingesters.david_rumsey import DavidRumseyIngester
from pipeline.ingesters.shipwrecks_oxrep import OXREPShipwrecksIngester
from pipeline.ingesters.coins_nomisma import NomismaIngester
from pipeline.ingesters.inscriptions_edh import EDHInscriptionsIngester
from pipeline.ingesters.volcanic_holvol import HolVolIngester
from pipeline.ingesters.earth_impacts import EarthImpactsIngester
from pipeline.ingesters.models_sketchfab import SketchfabIngester
from pipeline.ingesters.boundaries_seshat import SeshatIngester

# NCEI Hazards
from pipeline.ingesters.ncei_earthquakes import NCEIEarthquakesIngester
from pipeline.ingesters.ncei_tsunamis import NCEITsunamisIngester
from pipeline.ingesters.ncei_tsunami_observations import NCEITsunamiObservationsIngester
from pipeline.ingesters.ncei_volcanoes import NCEIVolcanoesIngester

# Museum collections & Texts
from pipeline.ingesters.met_museum import MetMuseumIngester
from pipeline.ingesters.europeana import EuropeanaIngester
from pipeline.ingesters.topostext import ToposTextIngester

__all__ = [
    # Base classes
    "BaseIngester",
    "IngesterResult",
    "ParsedSite",
    # PRIMARY source
    "AncientNerdsOriginalIngester",
    # Global/Large databases
    "PleiadesIngester",
    "UNESCOIngester",
    "GeoNamesIngester",
    "OpenContextIngester",
    "WikidataIngester",
    # Europe
    "HistoricEnglandIngester",
    "IrelandNMSIngester",
    "ArachneIngester",
    "DAREIngester",
    # Middle East / Africa
    "EAMENAIngester",
    # North America
    "DINAAIngester",
    # Sacred & Rock Art
    "SacredSitesIngester",
    "RockArtIngester",
    # Specialized
    "OSMHistoricIngester",
    "MegalithicPortalIngester",
    "DavidRumseyIngester",
    "OXREPShipwrecksIngester",
    "NomismaIngester",
    "EDHInscriptionsIngester",
    "HolVolIngester",
    "EarthImpactsIngester",
    "SketchfabIngester",
    "SeshatIngester",
    # NCEI Hazards
    "NCEIEarthquakesIngester",
    "NCEITsunamisIngester",
    "NCEITsunamiObservationsIngester",
    "NCEIVolcanoesIngester",
    # Museum collections & Texts
    "MetMuseumIngester",
    "EuropeanaIngester",
    "ToposTextIngester",
]
