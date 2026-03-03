"""
Data ingesters for various archaeological data sources.

Each ingester is responsible for fetching, parsing, and normalizing data
from a specific source into our standard schema.
"""

from pipeline.ingesters.ancient_nerds_original import AncientNerdsOriginalIngester
from pipeline.ingesters.arachne import ArachneIngester
from pipeline.ingesters.base import BaseIngester, IngesterResult, ParsedSite
from pipeline.ingesters.boundaries_seshat import SeshatIngester
from pipeline.ingesters.canmore_scotland import CanmoreScotlandIngester
from pipeline.ingesters.coflein_wales import CofleinWalesIngester
from pipeline.ingesters.coins_nomisma import NomismaIngester
from pipeline.ingesters.dare import DAREIngester
from pipeline.ingesters.david_rumsey import DavidRumseyIngester
from pipeline.ingesters.eamena import EAMENAIngester
from pipeline.ingesters.earth_impacts import EarthImpactsIngester
from pipeline.ingesters.europeana import EuropeanaIngester
from pipeline.ingesters.geonames import GeoNamesIngester
from pipeline.ingesters.historic_england import HistoricEnglandIngester
from pipeline.ingesters.ireland_nms import IrelandNMSIngester
from pipeline.ingesters.list_inscriptions import LISTInscriptionsIngester
from pipeline.ingesters.luwian_atlas import LuwianAtlasIngester
from pipeline.ingesters.megalithic_portal import MegalithicPortalIngester
from pipeline.ingesters.met_museum import MetMuseumIngester
from pipeline.ingesters.models_sketchfab import SketchfabIngester
from pipeline.ingesters.mycenaean_atlas import MycenaeanAtlasIngester
from pipeline.ingesters.ncei_earthquakes import NCEIEarthquakesIngester
from pipeline.ingesters.ncei_tsunami_observations import NCEITsunamiObservationsIngester
from pipeline.ingesters.ncei_tsunamis import NCEITsunamisIngester
from pipeline.ingesters.ncei_volcanoes import NCEIVolcanoesIngester
from pipeline.ingesters.open_context import OpenContextIngester
from pipeline.ingesters.osm_historic import OSMHistoricIngester
from pipeline.ingesters.peru_amazon import PeruAmazonIngester
from pipeline.ingesters.pleiades import PleiadesIngester
from pipeline.ingesters.radiocarbon_paleo import RadiocarbonPaleoIngester
from pipeline.ingesters.rock_art import RockArtIngester
from pipeline.ingesters.shipwrecks_oxrep import OXREPShipwrecksIngester
from pipeline.ingesters.topostext import ToposTextIngester
from pipeline.ingesters.unesco import UNESCOIngester
from pipeline.ingesters.vici_org import ViciOrgIngester
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
    "ViciOrgIngester",
    "CanmoreScotlandIngester",
    "CofleinWalesIngester",
    "MycenaeanAtlasIngester",
    "RadiocarbonPaleoIngester",
    # Middle East / Africa
    "EAMENAIngester",
    "LuwianAtlasIngester",
    # Inscriptions
    "LISTInscriptionsIngester",
    # Rock Art
    "RockArtIngester",
    # Specialized
    "OSMHistoricIngester",
    "MegalithicPortalIngester",
    "DavidRumseyIngester",
    "OXREPShipwrecksIngester",
    "NomismaIngester",
    "HolVolIngester",
    "EarthImpactsIngester",
    "SketchfabIngester",
    "SeshatIngester",
    # Americas
    "PeruAmazonIngester",
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
