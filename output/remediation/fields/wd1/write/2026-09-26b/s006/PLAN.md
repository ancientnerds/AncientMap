# WD1 fields-wd1-2026-09-26b-s006: plan

Built 2026-09-30T05:59:43+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s006`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s006:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 273 |
| sites_written | 100 |
| refused | 30 |
| cells:geom | 21 |
| cells:lat | 21 |
| cells:lon | 21 |
| cells:period_name | 64 |
| cells:period_start | 64 |
| cells:site_type | 47 |
| cells:source_url | 35 |
| refused:coordinates-unresolved | 29 |
| refused:country-changes | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acci | geom | `0101000020E61000009B10131ADD9909C05182F37F13AD4240` | `SRID=4326;POINT(-3.134537 37.300275)` | wd1-point |
| Acci | lat | `37.352157586956885` | `37.300275` | wd1-replace |
| Acci | lon | `-3.2001287495678077` | `-3.134537` | wd1-replace |
| Acropolis of Tlos | period_name | `1500 - 500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Acropolis of Tlos | period_start | `-1500` | `-5000` | wd1-replace |
| Acropolis of Tlos | site_type | `Temple complex` | `Fortress/citadel` | wd1-replace |
| Albaniana (Roman Fort) | site_type | `Fortification` | `Fort` | wd1-replace |
| Anacopia Fortress | source_url | `https://en.wikipedia.org/wiki/Anacopia_Fortress` | `https://en.wikipedia.org/wiki/Anakopia_Fortress` | wd1-replace |
| Asklepieion - Pathos | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Asklepieion - Pathos | period_start | `1` | `NULL` | wd1-clear |
| Asklepieion - Pathos | source_url | `https://en.wikipedia.org/wiki/Asclepieion` | `https://www.explorepafos.org/place/asklepieion/?lang=en` | wd1-replace |
| Ayamachay | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ayamachay | period_start | `-1000` | `NULL` | wd1-clear |
| Banwolseong | site_type | `Castle/palace` | `Palace` | wd1-replace |
| Banwolseong | source_url | `https://en.wikipedia.org/wiki/Banwolseong` | `https://en.wikipedia.org/wiki/Wolseong` | wd1-replace |
| Batham Gate | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Batham Gate | period_start | `1` | `NULL` | wd1-clear |
| Batik Sehir Kekova | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Batik Sehir Kekova | period_start | `-3000` | `NULL` | wd1-clear |
| Batik Sehir Kekova | source_url | `https://en.wikipedia.org/wiki/Kekova` | `https://kulturenvanteri.com/yer/kekova/` | wd1-replace |
| Bela Reka, Šabac | source_url | `https://en.wikipedia.org/wiki/Bela_Reka_(%C5%A0abac)` | `https://chre.ashmus.ox.ac.uk/hoard/2806` | wd1-replace |
| Belintash | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Belintash | period_start | `-2000` | `-5000` | wd1-replace |
| Belintash | site_type | `Rock relief/carving` | `Sanctuary` | wd1-replace |
| Berel Kurgan | geom | `0101000020E61000005093DEAD099C55409161ADF2C8AF4840` | `SRID=4326;POINT(86.365564 49.343553)` | wd1-point |
| Berel Kurgan | lat | `49.373319945009946` | `49.343553` | wd1-replace |
| Berel Kurgan | lon | `86.43809077010997` | `86.365564` | wd1-replace |
| Besh Barmag Mountain | geom | `0101000020E6100000A13D044E2B9E4840C6061D4927774440` | `SRID=4326;POINT(49.2326 40.95752)` | wd1-point |
| Besh Barmag Mountain | lat | `40.93088640134151` | `40.95752` | wd1-replace |
| Besh Barmag Mountain | lon | `49.23569655615871` | `49.2326` | wd1-replace |
| Besh Barmag Mountain | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Besh Barmag Mountain | period_start | `1` | `NULL` | wd1-clear |
| Bidjigal Reserve | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Bidjigal Reserve | period_start | `-8000` | `NULL` | wd1-clear |
| Blackhammer Chambered Cairn | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Blackhammer Chambered Cairn | period_start | `-4500` | `NULL` | wd1-clear |
| Blennerhasset and Torpenhow | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Blennerhasset and Torpenhow | source_url | `https://en.wikipedia.org/wiki/Blennerhasset_and_Torpenhow` | `https://www.roman-britain.co.uk/places/blennerhasset/` | wd1-replace |
| Boeotian Treasury | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Boundary Stones, Ukraine | geom | `0101000020E6100000C0E435951D364040581B15DBAB434840` | `SRID=4326;POINT(32.03824 48.21267)` | wd1-point |
| Boundary Stones, Ukraine | lat | `48.52868212252241` | `48.21267` | wd1-replace |
| Boundary Stones, Ukraine | lon | `32.42277779704591` | `32.03824` | wd1-replace |
| Boundary Stones, Ukraine | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Boundary Stones, Ukraine | period_start | `-4000` | `NULL` | wd1-clear |
| Boundary Stones, Ukraine | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Bremridge Wood | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bremridge Wood | period_start | `-1000` | `NULL` | wd1-clear |
| Bremridge Wood | site_type | `Earthwork` | `Fort` | wd1-replace |
| Bülövqaya | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Caer Mote | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Caer Mote | period_start | `-1000` | `NULL` | wd1-clear |
| Caer Mote | source_url | `https://en.wikipedia.org/wiki/Caer_Mote` | `https://www.megalithic.co.uk/article.php?sid=16558` | wd1-replace |
| Calf of Eday Cairns | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Calf of Eday Cairns | period_start | `-4000` | `NULL` | wd1-clear |
| Calf of Eday Cairns | source_url | `https://en.wikipedia.org/wiki/Calf_of_Eday` | `https://de.wikipedia.org/wiki/Cairns_auf_dem_Calf_of_Eday` | wd1-replace |
| Carving depicting Animals, Kilmartin Glen | geom | `0101000020E6100000D0BBAE3D88F215C0F64322481E114C40` | `SRID=4326;POINT(-5.48717 56.11463)` | wd1-point |
| Carving depicting Animals, Kilmartin Glen | lat | `56.1337366263687` | `56.11463` | wd1-replace |
| Carving depicting Animals, Kilmartin Glen | lon | `-5.486847842969794` | `-5.48717` | wd1-replace |
| Carving depicting Animals, Kilmartin Glen | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Carving depicting Animals, Kilmartin Glen | period_start | `-4000` | `-2000` | wd1-replace |
| Carving depicting Animals, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://www.historicenvironment.scot/publications/all/public` | wd1-replace |
| Casteddu di Puzzonu | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Casteddu di Puzzonu | period_start | `-2000` | `NULL` | wd1-clear |
| Casteddu di Puzzonu | site_type | `Settlement` | `NULL` | wd1-clear |
| Chaa Creek | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Chaa Creek | period_start | `-200` | `NULL` | wd1-clear |
| Chaa Creek | source_url | `https://en.wikipedia.org/wiki/Chaa_Creek` | `https://www.megalithic.co.uk/article.php?sid=18170` | wd1-replace |
| Chactún | geom | `0101000020E6100000FD99B20CE05A56C08B0687E618973240` | `SRID=4326;POINT(-89.52733 18.72428)` | wd1-point |
| Chactún | lat | `18.590223701443886` | `18.72428` | wd1-replace |
| Chactún | lon | `-89.41992490235857` | `-89.52733` | wd1-replace |
| Chactún | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Chactún | period_start | `1` | `NULL` | wd1-clear |
| Cival | geom | `0101000020E6100000330A62E8495056C0B49D961136643140` | `SRID=4326;POINT(-89.25375 17.36439)` | wd1-point |
| Cival | lat | `17.391450022956363` | `17.36439` | wd1-replace |
| Cival | lon | `-89.25451097082332` | `-89.25375` | wd1-replace |
| Częstochowa | geom | `0101000020E6100000CCE860CAE21D3340BA0994496B664940` | `SRID=4326;POINT(19.152423 50.78729)` | wd1-point |
| Częstochowa | lat | `50.800149152073075` | `50.78729` | wd1-replace |
| Częstochowa | lon | `19.11674179902984` | `19.152423` | wd1-replace |
| Częstochowa | source_url | `https://en.wikipedia.org/wiki/Cz%C4%99stochowa` | `https://pl.wikipedia.org/wiki/Rezerwat_archeologiczny_kultur` | wd1-replace |
| Dilberjin Tepe | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dilberjin Tepe | period_start | `1` | `NULL` | wd1-clear |
| Dilberjin Tepe | site_type | `Temple complex` | `Town` | wd1-replace |
| Dougga | source_url | `www.historyhit.com/locations/dougga/` | `https://en.wikipedia.org/wiki/Dougga` | wd1-replace |
| El Brujo | period_name | `1 - 500 AD` | `< 4500 BC` | wd1-derive-period-name |
| El Brujo | period_start | `1` | `-12500` | wd1-replace |
| El Castillo de Huarmey | geom | `0101000020E6100000A84FD42A878853C0EC564C10621924C0` | `SRID=4326;POINT(-78.138111 -10.063278)` | wd1-point |
| El Castillo de Huarmey | lat | `-10.049576291388313` | `-10.063278` | wd1-replace |
| El Castillo de Huarmey | lon | `-78.13324995740425` | `-78.138111` | wd1-replace |
| El Castillo de Huarmey | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| El Castillo de Huarmey | period_start | `1` | `600` | wd1-replace |
| Ex voto of the Arcadians, Delphi | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Fanum d'Aron | geom | `0101000020E61000006046A0D20F7C03409AA7556FBE754640` | `SRID=4326;POINT(2.4214 44.9157)` | wd1-point |
| Fanum d'Aron | lat | `44.919874111960965` | `44.9157` | wd1-replace |
| Fanum d'Aron | lon | `2.435577054516031` | `2.4214` | wd1-replace |
| Fontaine-les-Bassets | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Fontaine-les-Bassets | period_start | `-4500` | `NULL` | wd1-clear |
| Fontaine-les-Bassets | site_type | `Megalithic structures` | `Dolmen` | wd1-replace |
| Fontaine-les-Bassets | source_url | `https://en.wikipedia.org/wiki/Fontaine-les-Bassets` | `https://fr.wikipedia.org/wiki/Pierre_Lev%C3%A9e_(Fontaine-le` | wd1-replace |
| Gavrinis | site_type | `Necropolis/tombs complex` | `Cairn` | wd1-replace |
| Gavrinis | source_url | `https://en.wikipedia.org/wiki/Gavrinis` | `https://fr.wikipedia.org/wiki/Cairn_de_Gavrinis` | wd1-replace |
| Gazma Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Gazma Cave | period_start | `-500` | `NULL` | wd1-clear |
| Gazma Cave | site_type | `Cave Structures` | `Cave` | wd1-replace |
| Ghazi Shah Mound | geom | `0101000020E61000007F65A0C73FE75040DEFAB5D936B13A40` | `SRID=4326;POINT(67.464135 26.454762)` | wd1-point |
| Ghazi Shah Mound | lat | `26.6922432011878` | `26.454762` | wd1-replace |
| Ghazi Shah Mound | lon | `67.61326780952184` | `67.464135` | wd1-replace |
| Ghazi Shah Mound | site_type | `Mound/tumulus` | `Settlement` | wd1-replace |
| Gray Hill, Monmouthshire | site_type | `Megalithic stones` | `Stone circle` | wd1-replace |
| Gray Hill, Monmouthshire | source_url | `https://en.wikipedia.org/wiki/Gray_Hill,_Monmouthshire` | `https://cadwpublic-api.azurewebsites.net/reports/sam/FullRep` | wd1-replace |
| Great Serpent Mound | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Great Serpent Mound | period_start | `1` | `NULL` | wd1-clear |
| Gunung Padang Megalithic Site | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Gunung Padang Megalithic Site | period_start | `100` | `-117` | wd1-replace |
| Gårdstånga | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Gårdstånga | period_start | `-4500` | `NULL` | wd1-clear |
| Gårdstånga | source_url | `https://en.wikipedia.org/wiki/G%C3%A5rdst%C3%A5nga` | `NULL` | wd1-clear |
| Għajn Tuffieħa Roman Baths | geom | `0101000020E6100000F0F09353CBB12C4013A9799A59F74140` | `SRID=4326;POINT(14.357442 35.926977)` | wd1-point |
| Għajn Tuffieħa Roman Baths | lat | `35.932421979336276` | `35.926977` | wd1-replace |
| Għajn Tuffieħa Roman Baths | lon | `14.34725438290522` | `14.357442` | wd1-replace |
| Għajn Tuffieħa Roman Baths | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Għajn Tuffieħa Roman Baths | period_start | `-500` | `1` | wd1-replace |
| Hedum castellum | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Hedum castellum | period_start | `-400` | `NULL` | wd1-clear |
| Hedum castellum | site_type | `Necropolis/tombs complex` | `Fort` | wd1-replace |
| High Street, Lake District | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| High Street, Lake District | period_start | `1` | `NULL` | wd1-clear |
| Huankarán | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Huankarán | period_start | `1200` | `NULL` | wd1-clear |
| Huankarán | site_type | `Necropolis/tombs complex` | `Archaeological site` | wd1-replace |
| Humbleton Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Humbleton Hill | period_start | `-4500` | `NULL` | wd1-clear |
| Humbleton Hill | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Innisidgen | site_type | `Cemetery` | `Tomb` | wd1-replace |
| Isla del Sol | geom | `0101000020E610000078F5F30C164A51C04C43BF443C0730C0` | `SRID=4326;POINT(-69.17639 -16.02056)` | wd1-point |
| Isla del Sol | lat | `-16.028263374991454` | `-16.02056` | wd1-replace |
| Isla del Sol | lon | `-69.15759586166484` | `-69.17639` | wd1-replace |
| Isla del Sol | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Isla del Sol | period_start | `-3000` | `-3500` | wd1-replace |
| Isla del Sol | site_type | `City/town/settlement` | `Sanctuary` | wd1-replace |
| Jabal al-ʿHayn | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Jabal al-ʿHayn | period_start | `-7000` | `NULL` | wd1-clear |
| Kamilari | geom | `0101000020E6100000E43294A03ACA38401A8D2E8A40844140` | `SRID=4326;POINT(24.786833 35.045347)` | wd1-point |
| Kamilari | lat | `35.03321959755904` | `35.045347` | wd1-replace |
| Kamilari | lon | `24.78995708101401` | `24.786833` | wd1-replace |
| Kamilari | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Kamilari | period_start | `-4000` | `-2000` | wd1-replace |
| Kamilari | site_type | `Cemetery` | `Tomb` | wd1-replace |
| Kamilari | source_url | `https://en.wikipedia.org/wiki/Kamilari` | `http://www.minoancrete.com/kamilari.htm` | wd1-replace |
| Killa Mach'ay | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Killa Mach'ay | period_start | `1` | `NULL` | wd1-clear |
| Kiuic | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Kiuic | period_start | `500` | `-800` | wd1-replace |
| Knocknarea | source_url | `https://en.wikipedia.org/wiki/Knocknarea` | `https://en.wikipedia.org/wiki/Miosg%C3%A1n_Meadhbha` | wd1-replace |
| Kvitky | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Kvitky | period_start | `-3600` | `NULL` | wd1-clear |
| Kvitky | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Kvitky | source_url | `https://en.wikipedia.org/wiki/Kvitky#` | `NULL` | wd1-clear |
| Kızlar Kalesi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kızlar Kalesi | period_start | `1` | `NULL` | wd1-clear |
| La Noce de Pierres | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| La Noce de Pierres | period_start | `-5000` | `NULL` | wd1-clear |
| La Noce de Pierres | site_type | `Monument` | `Standing stone` | wd1-replace |
| Limes Germanicus | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Little St Bernard Pass | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Little St Bernard Pass | period_start | `-1500` | `NULL` | wd1-clear |
| Little St Bernard Pass | source_url | `https://en.wikipedia.org/wiki/Little_St_Bernard_Pass` | `https://fr.wikipedia.org/wiki/Cromlech_du_Petit-Saint-Bernar` | wd1-replace |
| Lohum Jo Daro | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Lohum Jo Daro | period_start | `-4500` | `NULL` | wd1-clear |
| Lohum Jo Daro | site_type | `City/town/settlement` | `Mound/tumulus` | wd1-replace |
| Lukyanus Kitabesi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Lukyanus Kitabesi | period_start | `1` | `NULL` | wd1-clear |
| Lukyanus Kitabesi | source_url | `https://www.konyasehirturu.com/lukyanus-kitabesi-ve-atli-kay` | `https://www.kulturportali.gov.tr/turkiye/konya/gezilecekyer/` | wd1-replace |
| Mankby | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Mankby | period_start | `1` | `1201` | wd1-replace |
| Mankby | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Masada National Park | geom | `0101000020E61000001C0FCCCB12AF4140AFF56875804F3F40` | `SRID=4326;POINT(35.354872 31.312987)` | wd1-point |
| Masada National Park | lat | `31.310553873181274` | `31.312987` | wd1-replace |
| Masada National Park | lon | `35.367761110914415` | `35.354872` | wd1-replace |
| Maxta | site_type | `Necropolis/tombs complex` | `Settlement` | wd1-replace |
| Maxta | source_url | `https://en.wikipedia.org/wiki/Maxta` | `https://az.wikipedia.org/wiki/Maxta_abid%C9%99l%C9%99r_kompl` | wd1-replace |
| Milseburg | source_url | `https://en.wikipedia.org/wiki/Milseburg` | `https://de.wikipedia.org/wiki/Oppidum_Milseburg` | wd1-replace |
| Minanha | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Minanha | period_start | `-1500` | `NULL` | wd1-clear |
| Minanha | site_type | `Temple complex` | `City` | wd1-replace |
| Moel y Gest | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Moel y Gest | period_start | `-3000` | `NULL` | wd1-clear |
| Moel y Gest | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Moel y Gest | source_url | `https://en.wikipedia.org/wiki/Moel_y_Gest` | `https://coflein.gov.uk/en/sites/300956` | wd1-replace |
| Monte Pruno | geom | `0101000020E6100000731416FB2EB32E4082AE575B39334440` | `SRID=4326;POINT(15.362818 40.411831)` | wd1-point |
| Monte Pruno | lat | `40.400187890828434` | `40.411831` | wd1-replace |
| Monte Pruno | lon | `15.349967810101793` | `15.362818` | wd1-replace |
| Monte Pruno | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Monte Pruno | period_start | `-500` | `-700` | wd1-replace |
| Monte Pruno | source_url | `https://en.wikipedia.org/wiki/Monte_Pruno` | `https://books.openedition.org/pccj/455` | wd1-replace |
| Mərdangöl Necropolis | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mərdangöl Necropolis | period_start | `-1500` | `NULL` | wd1-clear |
| Ndachjian-Tehuacán | period_name | `500 - 1000 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Ndachjian-Tehuacán | period_start | `500` | `1000` | wd1-replace |
| Ndachjian-Tehuacán | source_url | `https://www.archaeology.org/issues/339-1905/trenches/7554-tr` | `https://sic.gob.mx/ficha.php?table=zona_arqueologica&table_i` | wd1-replace |
| Nether Largie North Cairn, Kilmartin Glen | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Nether Largie North Cairn, Kilmartin Glen | period_start | `-4000` | `-2000` | wd1-replace |
| Nether Largie North Cairn, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://www.historicenvironment.scot/visit/all/kilmartin-gle` | wd1-replace |
| Paphos | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Paphos | period_start | `-1000` | `-400` | wd1-replace |
| Pednelissos Antik Kenti | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Pednelissos Antik Kenti | period_start | `1` | `-400` | wd1-replace |
| Pednelissos Antik Kenti | source_url | `https://www-neredekal-com.translate.goog/pednelissos-antik-k` | `https://en.wikipedia.org/wiki/Pednelissus` | wd1-replace |
| Península de Kola | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Península de Kola | period_start | `-3000` | `NULL` | wd1-clear |
| Península de Kola | site_type | `City/town/settlement` | `Natural feature` | wd1-replace |
| Pergamon Amfitiyatrosu | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Pergamon Amfitiyatrosu | period_start | `-500` | `101` | wd1-replace |
| Pergamon Amfitiyatrosu | site_type | `Megalithic structures` | `Amphitheatre` | wd1-replace |
| Petroglyph Beach State Historic Park | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Petroglyph Beach State Historic Park | period_start | `-5000` | `NULL` | wd1-clear |
| Richat Structure | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Richat Structure | period_start | `1` | `NULL` | wd1-clear |
| Roman Odeon | site_type | `Megalithic structures` | `Theatre` | wd1-replace |
| Roman Odeon | source_url | `https://en.wikipedia.org/wiki/Paphos_Archaeological_Park#Ode` | `https://vici.org/vici/15097/` | wd1-replace |
| Roman Ruins of Tébessa | site_type | `Megalithic stones` | `City` | wd1-replace |
| Roman Ruins of Tébessa | source_url | `https://en.wikipedia.org/wiki/T%C3%A9bessa` | `https://en.wikipedia.org/wiki/Theveste` | wd1-replace |
| Romano-Gallic Baths of Entrammes | geom | `0101000020E610000087491AF51FA1E8BFF2FB433FF7024840` | `SRID=4326;POINT(-0.716957 47.999345)` | wd1-point |
| Romano-Gallic Baths of Entrammes | lat | `48.02317038363971` | `47.999345` | wd1-replace |
| Romano-Gallic Baths of Entrammes | lon | `-0.7696685588037305` | `-0.716957` | wd1-replace |
| Salou | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Salou | period_start | `-1500` | `NULL` | wd1-clear |
| Sitio Arqueológico La Blanca, Peten | period_name | `1500 - 500 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Sitio Arqueológico La Blanca, Peten | period_start | `-1500` | `250` | wd1-replace |
| St Dennis, Cornwall | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| St Dennis, Cornwall | period_start | `-1000` | `NULL` | wd1-clear |
| St Dennis, Cornwall | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| St Dennis, Cornwall | source_url | `https://en.wikipedia.org/wiki/St_Dennis,_Cornwall` | `https://www.megalithic.co.uk/article.php?sid=12144` | wd1-replace |
| Stoa Basileios | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Sítio Arqueológico da Pedra Pintada | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Sítio Arqueológico da Pedra Pintada | period_start | `-3000` | `NULL` | wd1-clear |
| Sítio Arqueológico da Pedra Pintada | site_type | `Petroglyphs` | `Rock art` | wd1-replace |
| Tambomachay | site_type | `Reservoir/aqueduct/canal` | `Bath` | wd1-replace |
| Tarragona | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Tarragona | period_start | `-1500` | `-218` | wd1-replace |
| Tatul | geom | `0101000020E6100000592AC5F5868A39400CE33A69E0C64440` | `SRID=4326;POINT(25.5456 41.5418)` | wd1-point |
| Tatul | lat | `41.55372348189675` | `41.5418` | wd1-replace |
| Tatul | lon | `25.541121826778497` | `25.5456` | wd1-replace |
| Tatul | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Tatul | source_url | `https://en.wikipedia.org/wiki/Tatul` | `https://en.wikipedia.org/wiki/Tatul_Sanctuary` | wd1-replace |
| Temple of Augustus, Pozzuoli | site_type | `Temple complex` | `Temple` | wd1-replace |
| Temple of Augustus, Pozzuoli | source_url | `https://en.wikipedia.org/wiki/Pozzuoli_Cathedral#Origins` | `https://en.wikipedia.org/wiki/Pozzuoli_Cathedral` | wd1-replace |
| Temple of Ptah - Garf Hussien | site_type | `Temple complex` | `Temple` | wd1-replace |
| Tiermes Archaeological Site | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Tiermes Archaeological Site | period_start | `-500` | `-1500` | wd1-replace |
| Tiermes Archaeological Site | site_type | `Fortress/citadel` | `City` | wd1-replace |
| Tomb of Artaxerxes III | source_url | `https://en.wikipedia.org/wiki/Tomb_of_Artaxerxes_III` | `https://fr.wikipedia.org/wiki/Mausol%C3%A9e_d%27Artaxerx%C3%` | wd1-replace |
| Turunçova | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Turunçova | period_start | `-600` | `NULL` | wd1-clear |
| Ucanal | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Ucanal | period_start | `500` | `-700` | wd1-replace |
| Vitudurum | geom | `0101000020E61000002A433FD6717721400287364604C04740` | `SRID=4326;POINT(8.755743 47.506943)` | wd1-point |
| Vitudurum | lat | `47.500130440354056` | `47.506943` | wd1-replace |
| Vitudurum | lon | `8.73329038164373` | `8.755743` | wd1-replace |
| Weetwood Moor | geom | `0101000020E61000006DCA9F8E262200C0083070C6EBC54B40` | `SRID=4326;POINT(-1.9655 55.547556)` | wd1-point |
| Weetwood Moor | lat | `55.54625778654014` | `55.547556` | wd1-replace |
| Weetwood Moor | lon | `-2.016675104381014` | `-1.9655` | wd1-replace |
| Weetwood Moor | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Weetwood Moor | period_start | `-4500` | `NULL` | wd1-clear |
| Wittenham Clumps | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Węsiory | geom | `0101000020E61000007F2FE8E8E8D731408A735A21981D4B40` | `SRID=4326;POINT(17.83985 54.21776)` | wd1-point |
| Węsiory | lat | `54.231205147901235` | `54.21776` | wd1-replace |
| Węsiory | lon | `17.843397671399995` | `17.83985` | wd1-replace |
| Węsiory | site_type | `Megalithic stones` | `Cemetery` | wd1-replace |
| Węsiory | source_url | `https://en.wikipedia.org/wiki/W%C4%99siory` | `https://pl.wikipedia.org/wiki/W%C4%99siory_(cmentarzysko)` | wd1-replace |
| Yazılıkkaya | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Yazılıkkaya | period_start | `-3000` | `-1500` | wd1-replace |
| Yazılıkkaya | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Yereruyk Archaeological Site | site_type | `Temple complex` | `Church` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| High Street, Lake District | lat | `coordinates-unresolved` | The site is the High Street Roman road, a line some 20 km long between Brougham and Ambleside; the stored point is the f |
| Península de Kola | lat | `coordinates-unresolved` | The site named here is the whole Kola Peninsula (about 100,000 km2); Wikipedia puts its point at 67.688, 35.944 and Wiki |
| Lukyanus Kitabesi | lat | `coordinates-unresolved` | The monument is a rock relief with an inscription about 100 m from the Fasıllar Hittite monument (Kültür Portalı). Only  |
| Huankarán | lat | `coordinates-unresolved` | The only published point for Huankarán is the one on Wikidata/Spanish Wikipedia (-9.382, -76.707), a single source famil |
| Blennerhasset and Torpenhow | lat | `coordinates-unresolved` | The site is Blennerhasset Roman fort (scheduled monument 1019017), which roman-britain.co.uk places at NY 190413 and the |
| Mankby | lat | `coordinates-unresolved` | The Finnish Heritage Agency register (kyppi.fi, Mankby (Mankki) 1000001861) places the deserted village site 4.5 km sout |
| Gårdstånga | lat | `coordinates-unresolved` | The site is only 'a Bronze Age burial mound' at Gårdstånga (English Wikipedia; its photo 'Bronsåldershög vid Gårdstånga' |
| Gazma Cave | lat | `coordinates-unresolved` | Only Wikidata prints a point for Gazma Cave (39.5383, 45.1793, about 3 km NNE of Tananam at about 1420 m). Wikipedia and |
| Batham Gate | lat | `coordinates-unresolved` | Batham Gate is a linear Roman road (Buxton to Brough-on-Noe, about 16 km); the stored point lies on its line near Peak D |
| Maxta | lat | `coordinates-unresolved` | The site is the Early Bronze Age tell Maxta I (Maxta Kültəpəsi I) at Maxta village. Only the 2026 PLOS ONE study prints  |
| Bela Reka, Šabac | lat | `coordinates-unresolved` | The site is the Roman villa at the locality Crkvine/Crkvina in the village of Bela Reka; Wikipedia and CHRE only give th |
| Temple of Ptah - Garf Hussien | lat | `coordinates-unresolved` | The temple stood at Gerf Hussein about 90 km south of Aswan (Wikipedia/Wikidata 23.2833, 32.9, a whole-minute point, cop |
| Limes Germanicus | lat | `coordinates-unresolved` | The Limes Germanicus is a frontier line of more than 550 km from the Rhine to the Danube, and its sources give arbitrary |
| Asklepieion - Pathos | lat | `coordinates-unresolved` | Only Wikidata (34°45'34.675"N, 32°24'26.388"E) prints a point for the Asklepieion of Nea Paphos in a quotable form; the  |
| Casteddu di Puzzonu | lat | `coordinates-unresolved` | No page gives a point for a 'Casteddu di Puzzonu' in Sartène: the Wikipedia stubs (en, fr, co) and Wikidata carry no coo |
| Ex voto of the Arcadians, Delphi | lat | `coordinates-unresolved` | No page gives a point for the Arcadian monument itself: Wikidata and the English and Greek Wikipedia articles carry no c |
| Killa Mach'ay | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family gives a point (-12.86125, -74.581472, 2.5 km SW of the stored point, which is Acobamb |
| Sitio Arqueológico La Blanca, Peten | lat | `coordinates-unresolved` | No two independent sources print a point for the site itself: Wikipedia and Wikidata give 16.90361, -89.44222, which on  |
| Ucanal | lat | `coordinates-unresolved` | The stored point (16.317, -90.100, copied from English Wikipedia) is the namesake village Ucanal in Sayaxché, about 100  |
| Hedum castellum | lat | `coordinates-unresolved` | The location of Hedum is not established: English Wikipedia puts it in the town of Breza (44.019854, 18.264582), while P |
| Chaa Creek | lat | `coordinates-unresolved` | The stored point is Cahal Pech's, about 4 km north of Chaa Creek. Only the Megalithic Portal gives a point for the Chaa  |
| Ayamachay | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Ayamachay (14°06′14″S 71°26′31″W, 1.2 km from the stored point); H |
| Mərdangöl Necropolis | lat | `coordinates-unresolved` | Wikipedia (en, az) places the Mərdangöl necropolis at Kharabagilan and the Ordubad society's page puts it near Sabirkənd |
| Kvitky | lat | `coordinates-unresolved` | No source prints a point for a Trypillia settlement at Kvitky: the only pages that mention one are copies of an English  |
| Boeotian Treasury | lat | `coordinates-unresolved` | The only published points for the Treasury of the Boeotians are Wikidata's (38.481635, 22.501244) and the OpenStreetMap  |
| Minanha | lat | `coordinates-unresolved` | Only Wikidata gives a point for Minanha (16.988, -89.075, 27.6 km north of the stored point); the English Wikipedia arti |
| Bülövqaya | lat | `coordinates-unresolved` | Wikipedia and Wikidata put Bülövqaya at 39.2834, 45.6382, about 2 km WSW of the stored point. The stored point is Göynük |
| Batik Sehir Kekova | lat | `coordinates-unresolved` | The stored point lies in Üçağız village (ancient Teimiussa) on the mainland, about 2.5 km from the sunken ruins on the n |
| Paphos | lat | `country-changes` | the new point lies in [], the site says Cyprus |
| Kızlar Kalesi | lat | `coordinates-unresolved` | Two places carry this name in Mersin: the castle at Çavuşlu, Tarsus (the linked Wikidata item, 37.1528, 34.9256, 33 km a |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s006-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s006 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
