"""
Data ingesters for various archaeological data sources.

Each ingester is responsible for fetching, parsing, and normalizing data
from a specific source into our standard schema.
"""

# PRIMARY source - Ancient Nerds Original (manually curated)
from pipeline.ingesters.ancient_nerds_original import AncientNerdsOriginalIngester
from pipeline.ingesters.arachne import ArachneIngester
from pipeline.ingesters.base import BaseIngester, IngesterResult, ParsedSite
from pipeline.ingesters.boundaries_seshat import SeshatIngester
from pipeline.ingesters.coins_nomisma import NomismaIngester
from pipeline.ingesters.dare import DAREIngester
from pipeline.ingesters.david_rumsey import DavidRumseyIngester

# Regional ingesters - North America
from pipeline.ingesters.dinaa import DINAAIngester

# Regional ingesters - Middle East / Africa
from pipeline.ingesters.eamena import EAMENAIngester
from pipeline.ingesters.earth_impacts import EarthImpactsIngester
from pipeline.ingesters.europeana import EuropeanaIngester
from pipeline.ingesters.geonames import GeoNamesIngester

# Regional ingesters - Europe
from pipeline.ingesters.historic_england import HistoricEnglandIngester
from pipeline.ingesters.inscriptions_edh import EDHInscriptionsIngester
from pipeline.ingesters.ireland_nms import IrelandNMSIngester
from pipeline.ingesters.megalithic_portal import MegalithicPortalIngester

# Museum collections & Texts
from pipeline.ingesters.met_museum import MetMuseumIngester
from pipeline.ingesters.models_sketchfab import SketchfabIngester

# NCEI Hazards
from pipeline.ingesters.ncei_earthquakes import NCEIEarthquakesIngester
from pipeline.ingesters.ncei_tsunami_observations import NCEITsunamiObservationsIngester
from pipeline.ingesters.ncei_tsunamis import NCEITsunamisIngester
from pipeline.ingesters.ncei_volcanoes import NCEIVolcanoesIngester
from pipeline.ingesters.open_context import OpenContextIngester

# Specialized
from pipeline.ingesters.osm_historic import OSMHistoricIngester

# Core ingesters
from pipeline.ingesters.pleiades import PleiadesIngester
from pipeline.ingesters.rock_art import RockArtIngester

# Sacred & Rock Art
from pipeline.ingesters.sacred_sites import SacredSitesIngester
from pipeline.ingesters.shipwrecks_oxrep import OXREPShipwrecksIngester
from pipeline.ingesters.topostext import ToposTextIngester
from pipeline.ingesters.unesco import UNESCOIngester
from pipeline.ingesters.volcanic_holvol import HolVolIngester
from pipeline.ingesters.wikidata import WikidataIngester

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
