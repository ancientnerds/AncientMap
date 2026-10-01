# WD1 fields-wd1-2026-09-26b-s004: plan

Built 2026-09-30T05:57:30+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s004`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s004:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 264 |
| sites_written | 99 |
| refused | 22 |
| cells:geom | 17 |
| cells:lat | 17 |
| cells:lon | 17 |
| cells:period_name | 63 |
| cells:period_start | 62 |
| cells:site_type | 54 |
| cells:source_url | 34 |
| refused:coordinates-unresolved | 21 |
| refused:country-changes | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Actun Tunichil Muknal | geom | `0101000020E6100000E69C5AFB6C3756C04D61FBE466213140` | `SRID=4326;POINT(-88.86242 17.11366)` | wd1-point |
| Actun Tunichil Muknal | lat | `17.13047629487237` | `17.11366` | wd1-replace |
| Actun Tunichil Muknal | lon | `-88.86602672432818` | `-88.86242` | wd1-replace |
| Alvastra Pile-Dwelling | geom | `0101000020E6100000AAE2A8ACE05D2D40C2A1602548244D40` | `SRID=4326;POINT(14.675 58.299722)` | wd1-point |
| Alvastra Pile-Dwelling | lat | `58.28345172136643` | `58.299722` | wd1-replace |
| Alvastra Pile-Dwelling | lon | `14.6833547550353` | `14.675` | wd1-replace |
| Alvastra Pile-Dwelling | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Alvastra Pile-Dwelling | period_start | `-4500` | `-3000` | wd1-replace |
| Alvastra Pile-Dwelling | site_type | `City/town/settlement` | `Religious` | wd1-replace |
| Ancient City of Armavir | geom | `0101000020E6100000DE195199C7044640B2E86C19D4134440` | `SRID=4326;POINT(44.03333 40.08194)` | wd1-point |
| Ancient City of Armavir | lat | `40.15491025750943` | `40.08194` | wd1-replace |
| Ancient City of Armavir | lon | `44.03734127483379` | `44.03333` | wd1-replace |
| Ancient City of Armavir | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Ancient City of Armavir | period_start | `-3000` | `-800` | wd1-replace |
| Ancient City of Armavir | site_type | `Megalithic stones` | `City` | wd1-replace |
| Apamea | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Apamea | period_start | `-3000` | `-300` | wd1-replace |
| Apesokari | geom | `0101000020E61000002D8C236B37F338408AA6102E28824140` | `SRID=4326;POINT(24.946611 35.004252)` | wd1-point |
| Apesokari | lat | `35.01685119450583` | `35.004252` | wd1-replace |
| Apesokari | lon | `24.95006436937199` | `24.946611` | wd1-replace |
| Apesokari | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Apesokari | period_start | `-3000` | `-3500` | wd1-replace |
| Atapuerca Mountains | geom | `0101000020E61000006514A3755B2D0CC074266463F42E4540` | `SRID=4326;POINT(-3.518333 42.3525)` | wd1-point |
| Atapuerca Mountains | lat | `42.36683313741824` | `42.3525` | wd1-replace |
| Atapuerca Mountains | lon | `-3.5221471014397587` | `-3.518333` | wd1-replace |
| Atapuerca Mountains | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Atapuerca Mountains | period_start | `-1400000` | `NULL` | wd1-clear |
| Atapuerca Mountains | site_type | `Cave Structures` | `Cave` | wd1-replace |
| Atapuerca Mountains | source_url | `https://en.wikipedia.org/wiki/Atapuerca_Mountains` | `https://en.wikipedia.org/wiki/Archaeological_site_of_Atapuer` | wd1-replace |
| Atsipades | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Atsipades | period_start | `-3000` | `NULL` | wd1-clear |
| Auquin Punta | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Auquin Punta | period_start | `1400` | `NULL` | wd1-clear |
| Ballyalton Court Cairn | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ballyalton Court Cairn | period_start | `-4000` | `NULL` | wd1-clear |
| Beacon Hill, Leicestershire | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Beacon Hill, Leicestershire | period_start | `-4500` | `NULL` | wd1-clear |
| Beacon Hill, Leicestershire | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Beacon Hill, Leicestershire | source_url | `https://en.wikipedia.org/wiki/Beacon_Hill,_Leicestershire` | `https://www.charnwood.gov.uk/listed_buildings/hill_fort_encl` | wd1-replace |
| Bishopsgate | site_type | `Gate/archway/bridge` | `Gate` | wd1-replace |
| Black Mountain (Pima County, Arizona) | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Black Mountain (Pima County, Arizona) | period_start | `1` | `NULL` | wd1-clear |
| Black Mountain (Pima County, Arizona) | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Bremetennacum | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Bribir, Šibenik-Knin County | geom | `0101000020E61000000A9E17733EB32F4007C655E459F54540` | `SRID=4326;POINT(15.84247 43.92584)` | wd1-point |
| Bribir, Šibenik-Knin County | lat | `43.91680578411256` | `43.92584` | wd1-replace |
| Bribir, Šibenik-Knin County | lon | `15.850085827477432` | `15.84247` | wd1-replace |
| Bribir, Šibenik-Knin County | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Bribir, Šibenik-Knin County | period_start | `1` | `NULL` | wd1-clear |
| Brown Clee Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Brown Clee Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Brown Clee Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Brown Clee Hill | source_url | `https://en.wikipedia.org/wiki/Brown_Clee_Hill` | `https://www.megalithic.co.uk/article.php?sid=11447` | wd1-replace |
| Cadbury Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cadbury Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Cadbury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Caer Caradoc - Chapel Lawn | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Caer Caradoc - Chapel Lawn | period_start | `-1500` | `NULL` | wd1-clear |
| Calleva Atrebatum | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Calleva Atrebatum | source_url | `https://en.wikipedia.org/wiki/Archaeology` | `https://en.wikipedia.org/wiki/Calleva_Atrebatum` | wd1-replace |
| Cape St. Athanasius Ancient Settlement | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cape St. Athanasius Ancient Settlement | period_start | `-1500` | `NULL` | wd1-clear |
| Cape St. Athanasius Ancient Settlement | source_url | `https://en.wikipedia.org/wiki/Cape_St._Athanasius_ancient_se` | `https://en.wikipedia.org/wiki/Cape_St._Athanasius` | wd1-replace |
| Cappadocia | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cappadocia | period_start | `-3000` | `NULL` | wd1-clear |
| Cappadocia | site_type | `Temple complex` | `NULL` | wd1-clear |
| Cappadocia | source_url | `https://en.wikipedia.org/wiki/Cappadocia` | `NULL` | wd1-clear |
| Carteia | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Carteia | period_start | `-3000` | `-400` | wd1-replace |
| Casma-Sechin Culture | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Castell Dinas | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Castell Dinas | period_start | `-3000` | `-800` | wd1-replace |
| Catholme Ceremonial Complex | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Catholme Ceremonial Complex | period_start | `-4500` | `-2500` | wd1-replace |
| Chanhudaro | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Chanhudaro | period_start | `-4500` | `-2600` | wd1-replace |
| Chocolá | site_type | `City/town/settlement` | `City` | wd1-replace |
| Compton Dundon | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Compton Dundon | period_start | `-1000` | `NULL` | wd1-clear |
| Compton Dundon | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Compton Dundon | source_url | `https://en.wikipedia.org/wiki/Compton_Dundon` | `https://en.wikipedia.org/wiki/Dundon_Hill_Hillfort` | wd1-replace |
| Copalita Eco-Archaeological Park | source_url | `https://www.lonelyplanet.com/mexico/oaxaca-state/bahias-de-h` | `https://lugares.inah.gob.mx/es/node/4487` | wd1-replace |
| Dalj | geom | `0101000020E6100000FFA7772FF0F332408DBC0955DABD4640` | `SRID=4326;POINT(18.988055 45.483793)` | wd1-point |
| Dalj | lat | `45.483225469354785` | `45.483793` | wd1-replace |
| Dalj | lon | `18.952883688652943` | `18.988055` | wd1-replace |
| Dalj | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Dalj | period_start | `-500` | `NULL` | wd1-clear |
| Didnauri | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Didnauri | period_start | `-3000` | `-1200` | wd1-replace |
| Din Lligwy Hut Circle | period_name | `3000 - 1500 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Din Lligwy Hut Circle | period_start | `-3000` | `201` | wd1-replace |
| Din Lligwy Hut Circle | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Dunkery Beacon - Dunkery Hill | source_url | `https://en.wikipedia.org/wiki/Dunkery_Hill` | `https://www.exmoorher.co.uk/Monument/MEM22803` | wd1-replace |
| El Cerrito | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| El Cerrito | period_start | `-3000` | `-300` | wd1-replace |
| El Oso, Ávila | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| El Oso, Ávila | period_start | `-4000` | `NULL` | wd1-clear |
| El Oso, Ávila | source_url | `https://en.wikipedia.org/wiki/El_Oso,_%C3%81vila` | `http://www.verracos.es/verraco/130` | wd1-replace |
| Eridu | geom | `0101000020E61000003BCDBFA05BFE464016479495ACCE3E40` | `SRID=4326;POINT(45.99611 30.81583)` | wd1-point |
| Eridu | lat | `30.80732092733441` | `30.81583` | wd1-replace |
| Eridu | lon | `45.98717126241032` | `45.99611` | wd1-replace |
| Estipeon | source_url | `https://en.wikipedia.org/wiki/History` | `https://mk.wikipedia.org/wiki/%D0%90%D1%81%D1%82%D0%B8%D0%B1` | wd1-replace |
| Eğil Kalesi | geom | `0101000020E610000010A6082C680A44404E78878FDC214340` | `SRID=4326;POINT(40.09293 38.25531)` | wd1-point |
| Eğil Kalesi | lat | `38.26454347719901` | `38.25531` | wd1-replace |
| Eğil Kalesi | lon | `40.0813040773611` | `40.09293` | wd1-replace |
| Eğil Kalesi | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Eğil Kalesi | period_start | `-3500` | `-800` | wd1-replace |
| Eğil Kalesi | source_url | `https://gelecekpartisi-org-tr.translate.goog/diyarbakir/tani` | `https://diyarbakir.gov.tr/egil-asur-kalesi` | wd1-replace |
| First Pylon | site_type | `Megalithic structures` | `Gate` | wd1-replace |
| First Pylon | source_url | `https://en.wikipedia.org/wiki/Precinct_of_Amun-Re` | `https://digitalkarnak.ucsc.edu/1st-pylon/` | wd1-replace |
| Foel Fenlli | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Foel Fenlli | period_start | `-3000` | `NULL` | wd1-clear |
| Foel Fenlli | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Foel Fenlli | source_url | `https://en.wikipedia.org/wiki/Foel_Fenlli` | `https://coflein.gov.uk/en/sites/96522` | wd1-replace |
| Font dels Coms | period_name | `4500 - 3000 BC` | `1500+ AD` | wd1-derive-period-name |
| Font dels Coms | period_start | `-3500` | `1866` | wd1-replace |
| Font dels Coms | site_type | `Geological interest` | `Heritage site` | wd1-replace |
| Font dels Coms | source_url | `https://visitandorra.com/en/culture/font-dels-coms-spring/` | `https://visitandorra.com/en/points-of-interest/font-dels-com` | wd1-replace |
| Fontes Tamarici | site_type | `Archaeological site` | `Sacred site` | wd1-replace |
| Fountain of the Idol | site_type | `Megalithic structures` | `Sanctuary` | wd1-replace |
| Fulfinum | geom | `0101000020E61000000AC6BAECB81B2D409D53B931269B4640` | `SRID=4326;POINT(14.545694 45.202831)` | wd1-point |
| Fulfinum | lat | `45.21210309552337` | `45.202831` | wd1-replace |
| Fulfinum | lon | `14.554145238685141` | `14.545694` | wd1-replace |
| Gilwern Hill, Powys | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Gilwern Hill, Powys | period_start | `-4000` | `NULL` | wd1-clear |
| Gilwern Hill, Powys | source_url | `https://en.wikipedia.org/wiki/Gilwern_Hill,_Powys` | `https://coflein.gov.uk/en/sites/403125` | wd1-replace |
| Goffers Knoll | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Goffers Knoll | period_start | `-4500` | `NULL` | wd1-clear |
| Grønsalen | site_type | `Necropolis/tombs complex` | `Barrow` | wd1-replace |
| Halliggye Fogou | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Halliggye Fogou | period_start | `-1500` | `-500` | wd1-replace |
| Halliggye Fogou | site_type | `Infrastructure` | `Cave Structures` | wd1-replace |
| Hamble Common Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Hamble Common Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Hamble Common Camp | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Hamble Common Camp | source_url | `https://en.wikipedia.org/wiki/Hamble_Common_Camp` | `https://en.wikipedia.org/wiki/Hamble_Common` | wd1-replace |
| Hastings Hill | site_type | `Necropolis/tombs complex` | `Barrow` | wd1-replace |
| Hastings Hill | source_url | `https://en.wikipedia.org/wiki/Hastings_Hill` | `https://sitelines.newcastle.gov.uk/SMR/113` | wd1-replace |
| Historic Site Tipasa | site_type | `Temple complex` | `City` | wd1-replace |
| Huacramarca | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Huacramarca | period_start | `1` | `1101` | wd1-replace |
| Huiñao | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Huiñao | period_start | `1` | `NULL` | wd1-clear |
| Huiñao | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Intini Uyu Pata | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Intini Uyu Pata | period_start | `1` | `NULL` | wd1-clear |
| Isla Palenque | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Isla Palenque | period_start | `1` | `900` | wd1-replace |
| Isla Palenque | source_url | `https://en.wikipedia.org/wiki/Isla_Palenque` | `https://www.archaeological.org/fieldwork/chiriqui-archaeolog` | wd1-replace |
| Kalkrieser Berg | geom | `0101000020E6100000CC308299993920403C384E18E9324A40` | `SRID=4326;POINT(8.129 52.408)` | wd1-point |
| Kalkrieser Berg | lat | `52.397738493149944` | `52.408` | wd1-replace |
| Kalkrieser Berg | lon | `8.112499997274789` | `8.129` | wd1-replace |
| Kalkrieser Berg | site_type | `Museum` | `Archaeological site` | wd1-replace |
| Kalkrieser Berg | source_url | `https://en.wikipedia.org/wiki/Kalkrieser_Berg` | `https://de.wikipedia.org/wiki/Fundregion_Kalkriese` | wd1-replace |
| Kelsey Head | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kelsey Head | period_start | `-1000` | `NULL` | wd1-clear |
| Kelsey Head | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Kelsey Head | source_url | `https://en.wikipedia.org/wiki/Kelsey_Head` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Kleczanów Forest | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Kleczanów Forest | period_start | `-3000` | `NULL` | wd1-clear |
| Kleczanów Forest | site_type | `Necropolis/tombs complex` | `Barrow` | wd1-replace |
| Kleczanów Forest | source_url | `https://en.wikipedia.org/wiki/Kleczan%C3%B3w_Forest` | `https://zabytek.pl/en/obiekty/kleczanow-cmentarzysko-kurhano` | wd1-replace |
| Knowlton Circles | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Knowlton Circles | period_start | `-4500` | `-3000` | wd1-replace |
| Kremna Antik Kent | source_url | `https://www-kulturportali-gov-tr.translate.goog/turkiye/burd` | `https://en.wikipedia.org/wiki/Cremna` | wd1-replace |
| Kłopot, Lubusz Voivodeship | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Kłopot, Lubusz Voivodeship | period_start | `1` | `1201` | wd1-replace |
| La Chapelle-aux-Saints | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| La Chapelle-aux-Saints | period_start | `-500` | `NULL` | wd1-clear |
| La Chapelle-aux-Saints | site_type | `Cave Structures` | `Cave` | wd1-replace |
| La Chapelle-aux-Saints | source_url | `https://en.wikipedia.org/wiki/La_Chapelle-aux-Saints` | `https://it.wikipedia.org/wiki/Sito_archeologico_di_La_Chapel` | wd1-replace |
| Labranda Ruins | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Labranda Ruins | period_start | `-500` | `-700` | wd1-replace |
| Labranda Ruins | site_type | `Megalithic stones` | `Sanctuary` | wd1-replace |
| Laugerie-Basse | geom | `0101000020E6100000A3016A1C0E0FE33F2396161F04494640` | `SRID=4326;POINT(0.9983 44.9497)` | wd1-point |
| Laugerie-Basse | lat | `44.57043827631812` | `44.9497` | wd1-replace |
| Laugerie-Basse | lon | `0.595587783333077` | `0.9983` | wd1-replace |
| Laugerie-Basse | site_type | `Cave Structures` | `Cave` | wd1-replace |
| Lefke Gate | site_type | `Infrastructure` | `Gate` | wd1-replace |
| Lefke Gate | source_url | `https://www.lonelyplanet.com/turkey/iznik/attractions/lefke-` | `https://tr.wikipedia.org/wiki/Lefke_Kap%C4%B1s%C4%B1` | wd1-replace |
| Lepsius No.25 Pyramid | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Lepsius No.25 Pyramid | period_start | `-3000` | `NULL` | wd1-clear |
| Lepsius No.25 Pyramid | source_url | `https://en.wikipedia.org/wiki/Lepsius_XXIV` | `https://en.wikipedia.org/wiki/Double_Pyramid` | wd1-replace |
| Machu Picchu | site_type | `Fortress/citadel` | `City/town/settlement` | wd1-replace |
| Maiden Way | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Maiden Way | period_start | `1` | `NULL` | wd1-clear |
| Matilo | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Midhowe Broch | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Midhowe Broch | period_start | `-1000` | `-200` | wd1-replace |
| Midhowe Broch | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Mount Nemrut | site_type | `Megalithic statues` | `Tomb` | wd1-replace |
| Niha, Zahlé | source_url | `https://en.wikipedia.org/wiki/Niha,_Zahl%C3%A9` | `https://www.livius.org/articles/place/nihata-niha/` | wd1-replace |
| Nipisat Island | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Nipisat Island | source_url | `https://en.wikipedia.org/wiki/Nipisat_Island` | `https://tidsskrift.dk/meddrgroenland_man_soc/article/view/14` | wd1-replace |
| Nobbin | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Nobbin | period_start | `-5000` | `-3500` | wd1-replace |
| Nobbin | source_url | `https://en.wikipedia.org/wiki/Nobbin` | `https://de.wikipedia.org/wiki/Gro%C3%9Fsteingrab_Nobbin` | wd1-replace |
| Patallacta | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Patallacta | period_start | `1000` | `NULL` | wd1-clear |
| Pen-y-crug | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Pen-y-crug | source_url | `https://en.wikipedia.org/wiki/Pen-y-crug` | `https://coflein.gov.uk/en/sites/92058` | wd1-replace |
| Pillkukayna | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pillkukayna | period_start | `1400` | `NULL` | wd1-clear |
| Pillkukayna | site_type | `City/town/settlement` | `Palace` | wd1-replace |
| Pinara | site_type | `Temple complex` | `City` | wd1-replace |
| Ptolemais (Cyrenaica) | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Ptolemais (Cyrenaica) | period_start | `-500` | `-700` | wd1-replace |
| Pyramid of Hellenikon | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Pyramid of Hellenikon | period_start | `1` | `-400` | wd1-replace |
| Pyramid of Hellenikon | site_type | `Megalithic stones` | `Fort` | wd1-replace |
| Roman Temple of Hercules | source_url | `https://en.wikipedia.org/wiki/Temple_of_Hercules_(Amman)` | `https://es.wikipedia.org/wiki/Templo_de_H%C3%A9rcules_(Am%C3` | wd1-replace |
| Rough Tor | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Rough Tor | period_start | `-4000` | `NULL` | wd1-clear |
| Rough Tor | site_type | `Earthwork` | `Settlement` | wd1-replace |
| San Lorenzo Tenochtitlán Museum | period_name | `1 - 500 AD` | `1500+ AD` | wd1-derive-period-name |
| San Lorenzo Tenochtitlán Museum | period_start | `1` | `1986` | wd1-replace |
| Sillyon | site_type | `Megalithic structures` | `City` | wd1-replace |
| Stina, Ukraine | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stina, Ukraine | period_start | `-4500` | `NULL` | wd1-clear |
| Stina, Ukraine | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Stina, Ukraine | source_url | `https://en.wikipedia.org/wiki/Stina,_Ukraine` | `NULL` | wd1-clear |
| Table des Marchand | site_type | `Necropolis/tombs complex` | `Dolmen` | wd1-replace |
| The Lost City of Heracleion | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| The Lost City of Heracleion | period_start | `-3000` | `-800` | wd1-replace |
| The Ships of De Meern | site_type | `Museum` | `Shipwreck` | wd1-replace |
| Tholos de Montelirio | geom | `0101000020E6100000767C6187844E18C0E124DCDF47B54240` | `SRID=4326;POINT(-6.059211 37.409589)` | wd1-point |
| Tholos de Montelirio | lat | `37.41625593423101` | `37.409589` | wd1-replace |
| Tholos de Montelirio | lon | `-6.076677432370266` | `-6.059211` | wd1-replace |
| Tlalpan | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tlalpan | period_start | `-3000` | `NULL` | wd1-clear |
| Tlalpan | source_url | `https://en.wikipedia.org/wiki/History` | `https://es.wikipedia.org/wiki/Centro_hist%C3%B3rico_de_Tlalp` | wd1-replace |
| Tumamoc Hill | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Tumamoc Hill | period_start | `-2100` | `-500` | wd1-replace |
| Tumamoc Hill | site_type | `Petroglyphs` | `Village` | wd1-replace |
| Turuñuelo | geom | `0101000020E61000004B3A5483525518C0835ABF5BD06C4340` | `SRID=4326;POINT(-6.064722 38.949167)` | wd1-point |
| Turuñuelo | lat | `38.850108593401295` | `38.949167` | wd1-replace |
| Turuñuelo | lon | `-6.0833225746305954` | `-6.064722` | wd1-replace |
| Turuñuelo | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Twin Column Tomb | geom | `0101000020E6100000F491554A2C5A5F401A53059F2B5E4340` | `SRID=4326;POINT(125.418705 38.863702)` | wd1-point |
| Twin Column Tomb | lat | `38.73570621261588` | `38.863702` | wd1-replace |
| Twin Column Tomb | lon | `125.40895326954325` | `125.418705` | wd1-replace |
| Twin Column Tomb | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Twin Column Tomb | period_start | `-500` | `401` | wd1-replace |
| Twin Column Tomb | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Undavalli Caves | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Undavalli Caves | period_start | `1` | `601` | wd1-replace |
| Undavalli Caves | site_type | `Temple complex` | `Cave Structures` | wd1-replace |
| Uçan ağıl | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Uçan ağıl | period_start | `-4500` | `-4850` | wd1-replace |
| Uçan ağıl | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Waddon Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Walton Common | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Walton Common | period_start | `-4500` | `NULL` | wd1-clear |
| Walton Common | site_type | `Barrow` | `Earthwork` | wd1-replace |
| Więckowy | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Więckowy | period_start | `-1500` | `NULL` | wd1-clear |
| Więckowy | source_url | `https://en.wikipedia.org/wiki/Wi%C4%99ckowy` | `https://zabytek.pl/pl/obiekty/g-290750` | wd1-replace |
| Wéris Megaliths | geom | `0101000020E61000000DBE97E6C61F16408FC0DD33C0294940` | `SRID=4326;POINT(5.52263 50.33348)` | wd1-point |
| Wéris Megaliths | lat | `50.326178057935174` | `50.33348` | wd1-replace |
| Wéris Megaliths | lon | `5.531032183658238` | `5.52263` | wd1-replace |
| Zyndram's Hill | geom | `0101000020E61000000953E9AC5F6F34401447091D7BC74840` | `SRID=4326;POINT(20.4651 49.5548)` | wd1-point |
| Zyndram's Hill | lat | `49.558444623499014` | `49.5548` | wd1-replace |
| Zyndram's Hill | lon | `20.4350536412849` | `20.4651` | wd1-replace |
| Zyndram's Hill | site_type | `City/town/settlement` | `Settlement` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| El Oso, Ávila | lat | `coordinates-unresolved` | The site is the Vettonian verraco standing in the square in front of the church of San Pedro Apóstol in El Oso; only Wik |
| Narona | lat | `country-changes` | the new point lies in ['Bosnia and Herzegovina'], the site says Croatia |
| Uçan ağıl | lat | `coordinates-unresolved` | The only published coordinates of Uçan Ağıl (north of Sirab, Babek District; 39.291, 45.508, about 17 km from the stored |
| Auquin Punta | lat | `coordinates-unresolved` | The Wikipedia/Wikidata point (-9.53925, -76.73719) coincides with the centroid of Jacas Grande District in OSM (-9.5400, |
| Stina, Ukraine | lat | `coordinates-unresolved` | The stored point 48.4559, 28.4200 lies within 0.2 km of the centre of the village of Stina (48.4558, 28.4178 on Wikipedi |
| Intini Uyu Pata | lat | `coordinates-unresolved` | MINCETUR's inventory puts the temple on the Chilliukani hill between Ollaraya and Unicachi, at km 17 of the Yunguyo-Tini |
| Cappadocia | lat | `coordinates-unresolved` | The entry names Cappadocia, a historical region of central Anatolia, not a single site; the stored point is the town of  |
| The Lost City of Heracleion | lat | `coordinates-unresolved` | The sources disagree by several kilometres: English Wikipedia gives 31.31278, 30.12889 (Pleiades copies it, noting 'Coor |
| Font dels Coms | lat | `coordinates-unresolved` | The site (per its source page) is the 1866 street fountain on carrer Doctor Palau in the centre of Sant Julià de Lòria;  |
| Casma-Sechin Culture | lat | `coordinates-unresolved` | The entry is the Casma–Sechin culture (Sechin Complex), a spread of ruins over the Casma and Sechin valleys and the coas |
| Maiden Way | lat | `coordinates-unresolved` | The Maiden Way is a 32 km Roman road from Kirkby Thore to Carvoran; the stored point (English Wikipedia's 54.6250, -2.56 |
| Huiñao | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote fetch failed: https://www.summitpost.org/cerro-hui-ao/305339 (status 403); quote no |
| Pillkukayna | lat | `coordinates-unresolved` | The stored point is the centre of Isla del Sol, about 4.8 km from the ruins; Spanish Wikipedia (16°02′55″S 69°08′39″O, - |
| First Pylon | lat | `coordinates-unresolved` | Only the Wikidata item of the First Pylon (25.7191, 32.6568) prints the pylon's point in a readable form; Vici.org's ent |
| Gilwern Hill, Powys | lat | `coordinates-unresolved` | The stored point is the summit of the hill (Wikipedia and Wikidata print 52.200, -3.333, so they are the hill's point, n |
| Hamble Common Camp | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family gives a point (Wikidata's Hamble Common Camp item 50.8515, -1.3172; the Hamble Common |
| Patallacta | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Patallacta (English Wikipedia 13°13′53″S 72°25′53″W, 0.18 km from  |
| Lefke Gate | lat | `coordinates-unresolved` | The stored point lies at the Lefke Gate: Turkish Wikipedia (40°25′44″K 29°43′45″D) and Wikidata (40.42886, 29.72907) put |
| Kleczanów Forest | lat | `coordinates-unresolved` | The barrow cemetery lies in the wood west of Kleczanów. OpenStreetMap's node for the NID-registered site (Location: 50.7 |
| Huacramarca | lat | `coordinates-unresolved` | English Wikipedia's point for the ruins (9°10'32"S 77°26'00"W) matches the stored point, and the excavator Vega-Centeno  |
| Chanhudaro | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family gives a point for Chanhu-daro (26°10'25"N, 68°19'23"E, which the stored point copies) |
| Więckowy | lat | `coordinates-unresolved` | The Wikipedia/Wikidata coordinates are the village's, not the cemetery's. The national register (zabytek.pl, NID) places |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s004-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s004 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
