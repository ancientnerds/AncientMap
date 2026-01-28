# Comprehensive List of Historical Empires and Civilizations (5000 BC - 1500 AD)

## Research Summary

This document provides a comprehensive catalog of major historical empires and civilizations across all world regions from 5000 BC to 1500 AD, including available GeoJSON data sources for historical boundary mapping.

---

## Part 1: GeoJSON Data Sources for Historical Boundaries

### Primary Open-Source Datasets

#### 1. Cliopatria (Seshat Global History Databank) - BEST OVERALL
- **URL**: https://github.com/Seshat-Global-History-Databank/cliopatria
- **Coverage**: 3400 BCE to 2024 CE
- **Records**: ~15,000 polity records worldwide
- **Format**: GeoJSON (cliopatria.geojson)
- **Attributes**: Entity name, FromYear, ToYear, polygons, area (km2), Wikipedia references
- **Quality**: Comprehensive, academically backed, regularly updated
- **License**: Open source

#### 2. Historical Basemaps (aourednik)
- **URL**: https://github.com/aourednik/historical-basemaps
- **Coverage**: Ancient history through modern era
- **Format**: GeoJSON files organized by year
- **Features**: NAME, SUBJECTO (colonial power), PARTOF, BORDERPRECISION
- **Notes**: Work in progress; includes places.geojson for historical cities
- **Includes**: World countries and cultural regions

#### 3. Ancient World Mapping Center (AWMC) Geodata
- **URL**: https://github.com/AWMC/geodata
- **Coverage**: Greek and Roman world primarily
- **Format**: GeoJSON and ESRI Shapefiles
- **Content**: Aqueducts, roads, regional names, coastlines, provinces
- **Source**: Derived from Barrington Atlas of the Greek and Roman World

#### 4. Roman Empire Vector Map (Klokantech)
- **URL**: https://github.com/klokantech/roman-empire
- **Coverage**: Roman Empire provinces and infrastructure
- **Format**: GeoJSON
- **Content**: Places, roads, fortifications, provinces from DARE database

#### 5. Europe Historical GeoJSON
- **URL**: https://github.com/ioggstream/europe-historical-geojson
- **Coverage**: Congress of Vienna to WWI (European focus)
- **Format**: GeoJSON
- **Source**: GISCO dataset of European Union

#### 6. Thenmap
- **URL**: https://www.thenmap.net/
- **Coverage**: World borders from 1945 onwards; regional datasets for various countries
- **Format**: GeoJSON, TopoJSON, SVG via REST API
- **API Example**: api.thenmap.net/v1/world/geo/1956
- **Limitation**: Modern era only (post-1865 for most datasets)

#### 7. CShapes Dataset
- **URL**: https://demo.ldproxy.net/cshapes/collections
- **Coverage**: 1886-2019
- **Format**: GeoJSON, Shapefile
- **License**: CC BY-NC-SA 4.0

#### 8. Project MERCURY
- **URL**: https://projectmercury.eu/datasets/
- **Coverage**: Roman provinces, various ancient kingdoms
- **Source**: Ancient World Mapping Centre data

### Data Availability Assessment Key
- **Excellent**: Multiple high-quality GeoJSON sources available
- **Good**: At least one reliable GeoJSON source
- **Moderate**: Shapefile or limited GeoJSON available
- **Limited**: Scattered or incomplete data
- **Sparse**: Little to no publicly available boundary data

---

## Part 2: Comprehensive Empire and Civilization Catalog

---

### Category 1: Ancient Near East / Mesopotamia

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Sumerian City-States | c. 4500 BCE | c. 2000 BCE | Southern Mesopotamia (Iraq) | Moderate (Cliopatria) |
| Akkadian Empire | c. 2334 BCE | c. 2100 BCE | Mesopotamia, Syria, Anatolia | Good (Cliopatria) |
| Third Dynasty of Ur (Neo-Sumerian) | c. 2112 BCE | c. 2004 BCE | Mesopotamia | Moderate (Cliopatria) |
| Old Babylonian Empire | c. 1894 BCE | c. 1595 BCE | Mesopotamia | Good (Cliopatria) |
| Old Assyrian Kingdom | c. 2000 BCE | c. 1750 BCE | Northern Mesopotamia | Limited |
| Kassite Babylonia | c. 1595 BCE | c. 1155 BCE | Mesopotamia | Limited |
| Middle Assyrian Empire | c. 1392 BCE | c. 1056 BCE | Northern Mesopotamia | Moderate |
| Neo-Assyrian Empire | c. 911 BCE | 612 BCE | Mesopotamia, Levant, Egypt | Good (Cliopatria, AWMC) |
| Neo-Babylonian Empire | c. 626 BCE | 539 BCE | Mesopotamia, Levant | Good (Cliopatria) |
| Hittite Empire | c. 1650 BCE | c. 1178 BCE | Anatolia, Northern Levant | Good (Cliopatria) |
| Neo-Hittite States | c. 1180 BCE | c. 700 BCE | Syria, SE Anatolia | Limited |
| Phoenician City-States | c. 1500 BCE | 332 BCE | Levantine Coast | Moderate (AWMC) |
| Mitanni Kingdom | c. 1500 BCE | c. 1300 BCE | Northern Mesopotamia | Limited |
| Elamite Civilization | c. 2700 BCE | 539 BCE | SW Iran | Limited |
| Kingdom of Urartu | c. 860 BCE | c. 590 BCE | Armenian Highlands | Moderate |

---

### Category 2: Mediterranean World

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Minoan Civilization | c. 2700 BCE | c. 1450 BCE | Crete, Aegean | Limited |
| Mycenaean Greece | c. 1600 BCE | c. 1100 BCE | Greek Peninsula, Aegean | Limited |
| Greek City-States (Archaic/Classical) | c. 800 BCE | 338 BCE | Greece, Aegean, Anatolia | Moderate (AWMC) |
| Macedonian Kingdom | c. 808 BCE | 168 BCE | Northern Greece, Balkans | Good (Cliopatria) |
| Macedonian Empire (Alexander) | 336 BCE | 323 BCE | Greece to India | Good (Cliopatria) |
| Seleucid Empire | 312 BCE | 63 BCE | Near East, Persia | Good (Cliopatria) |
| Ptolemaic Kingdom | 305 BCE | 30 BCE | Egypt, Cyrenaica | Good (Cliopatria) |
| Antigonid Kingdom | 306 BCE | 168 BCE | Macedonia, Greece | Moderate |
| Attalid Kingdom (Pergamon) | 282 BCE | 133 BCE | Western Anatolia | Moderate |
| Roman Republic | 509 BCE | 27 BCE | Italy to Mediterranean | Excellent (AWMC, Roman Empire dataset) |
| Roman Empire (Principate) | 27 BCE | 284 CE | Mediterranean, Europe | Excellent (Multiple sources) |
| Roman Empire (Dominate) | 284 CE | 476/480 CE | Mediterranean, Europe | Excellent |
| Byzantine Empire (Eastern Roman) | 330/395 CE | 1453 CE | Eastern Mediterranean, Balkans, Anatolia | Good (Cliopatria) |
| Carthaginian Empire | c. 650 BCE | 146 BCE | North Africa, Western Mediterranean | Good (AWMC, Cliopatria) |

---

### Category 3: Persian and Central Asian Empires

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Median Empire | c. 678 BCE | 549 BCE | Iran, Near East | Moderate |
| Achaemenid Empire | c. 550 BCE | 330 BCE | Persia to Egypt to India | Good (Cliopatria) |
| Parthian Empire (Arsacid) | 247 BCE | 224 CE | Iran, Mesopotamia | Good (Cliopatria) |
| Sassanid Empire | 224 CE | 651 CE | Iran, Mesopotamia, Central Asia | Good (Cliopatria) |
| Greco-Bactrian Kingdom | c. 256 BCE | c. 125 BCE | Afghanistan, Central Asia | Limited |
| Indo-Greek Kingdom | c. 180 BCE | c. 10 CE | NW India, Afghanistan | Limited |
| Kushan Empire | c. 30 CE | c. 375 CE | Central Asia, N India, Afghanistan | Moderate (Cliopatria) |
| Xiongnu Confederation | c. 209 BCE | c. 93 CE | Mongolia, Central Asia | Limited |
| Hephthalite Empire | c. 440 CE | c. 560 CE | Central Asia, N India | Limited |
| Gokturk Khaganate | 552 CE | 744 CE | Central Asia, Mongolia | Limited |
| Uyghur Khaganate | 744 CE | 840 CE | Mongolia, Central Asia | Limited |
| Khazar Khaganate | c. 650 CE | c. 969 CE | Caucasus, Southern Russia | Limited |
| Samanid Empire | 819 CE | 999 CE | Central Asia, Iran | Moderate |
| Ghaznavid Empire | 977 CE | 1186 CE | Afghanistan, Iran, N India | Moderate |
| Seljuk Empire | 1037 CE | 1194 CE | Persia, Anatolia, Levant | Moderate (Cliopatria) |
| Khwarazmian Empire | c. 1077 CE | 1231 CE | Central Asia, Iran | Moderate |
| Mongol Empire | 1206 CE | 1368 CE | Eurasia (largest land empire) | Good (Cliopatria) |
| Chagatai Khanate | 1227 CE | 1363 CE | Central Asia | Moderate |
| Golden Horde | c. 1240s CE | 1502 CE | Russia, Kazakhstan | Moderate |
| Ilkhanate | 1256 CE | 1335 CE | Persia, Mesopotamia | Moderate |
| Timurid Empire | 1370 CE | 1507 CE | Central Asia, Persia | Moderate |

---

### Category 4: East Asian Civilizations

#### Chinese Dynasties

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Xia Dynasty | c. 2070 BCE | c. 1600 BCE | Yellow River Valley | Limited (legendary) |
| Shang Dynasty | c. 1600 BCE | c. 1046 BCE | North China | Moderate (Cliopatria) |
| Western Zhou Dynasty | c. 1046 BCE | 771 BCE | North/Central China | Moderate |
| Eastern Zhou Dynasty | 770 BCE | 256 BCE | Central China | Moderate |
| Warring States Period | 475 BCE | 221 BCE | China (multiple states) | Moderate |
| Qin Dynasty | 221 BCE | 206 BCE | China (first unified) | Good (Cliopatria) |
| Western Han Dynasty | 206 BCE | 9 CE | China, Central Asia | Good (Cliopatria) |
| Xin Dynasty | 9 CE | 23 CE | China | Limited |
| Eastern Han Dynasty | 25 CE | 220 CE | China | Good |
| Three Kingdoms (Wei, Shu, Wu) | 220 CE | 280 CE | China | Moderate |
| Western Jin Dynasty | 266 CE | 316 CE | China | Moderate |
| Eastern Jin Dynasty | 317 CE | 420 CE | South China | Moderate |
| Northern and Southern Dynasties | 420 CE | 589 CE | China (divided) | Limited |
| Sui Dynasty | 581 CE | 618 CE | China | Good |
| Tang Dynasty | 618 CE | 907 CE | China, Central Asia | Good (Cliopatria) |
| Five Dynasties and Ten Kingdoms | 907 CE | 960 CE | China (divided) | Limited |
| Northern Song Dynasty | 960 CE | 1127 CE | China (most) | Good (Cliopatria) |
| Southern Song Dynasty | 1127 CE | 1279 CE | South China | Good |
| Liao Dynasty (Khitan) | 916 CE | 1125 CE | North China, Mongolia | Moderate |
| Jin Dynasty (Jurchen) | 1115 CE | 1234 CE | North China | Moderate |
| Western Xia (Tangut) | 1038 CE | 1227 CE | NW China | Moderate |
| Yuan Dynasty (Mongol) | 1271 CE | 1368 CE | China, Mongolia | Good (Cliopatria) |
| Ming Dynasty | 1368 CE | 1644 CE | China | Good (Cliopatria) |

#### Korean Kingdoms

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Gojoseon | c. 2333 BCE | 108 BCE | Korean Peninsula | Limited (legendary early) |
| Goguryeo | 37 BCE | 668 CE | N Korea, Manchuria | Moderate (Cliopatria) |
| Baekje | 18 BCE | 660 CE | SW Korea | Moderate |
| Silla | 57 BCE | 935 CE | SE Korea | Moderate |
| Unified Silla | 668 CE | 935 CE | Korean Peninsula | Moderate |
| Gaya Confederacy | c. 42 CE | 562 CE | S Korea | Limited |
| Balhae | 698 CE | 926 CE | Manchuria, N Korea | Limited |
| Later Three Kingdoms | c. 892 CE | 936 CE | Korean Peninsula | Limited |
| Goryeo | 918 CE | 1392 CE | Korean Peninsula | Moderate (Cliopatria) |

#### Japanese Periods

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Jomon Period | c. 14000 BCE | c. 300 BCE | Japanese Archipelago | Limited (no states) |
| Yayoi Period | c. 300 BCE | c. 300 CE | Japan | Limited |
| Kofun Period | c. 300 CE | 538 CE | Japan | Limited |
| Asuka Period | 538 CE | 710 CE | Japan | Limited |
| Nara Period | 710 CE | 794 CE | Japan | Moderate |
| Heian Period | 794 CE | 1185 CE | Japan | Moderate |
| Kamakura Period | 1185 CE | 1333 CE | Japan | Moderate |
| Muromachi Period | 1336 CE | 1573 CE | Japan | Moderate |

---

### Category 5: South Asian Empires

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Indus Valley Civilization | c. 3300 BCE | c. 1300 BCE | Pakistan, NW India | Limited |
| Vedic Kingdoms | c. 1500 BCE | c. 500 BCE | North India | Limited |
| Mahajanapadas (16 kingdoms) | c. 600 BCE | c. 345 BCE | North India | Limited |
| Magadha Kingdom | c. 684 BCE | c. 320 BCE | Bihar, India | Limited |
| Nanda Empire | c. 345 BCE | c. 322 BCE | North India | Limited |
| Maurya Empire | c. 322 BCE | c. 185 BCE | Indian Subcontinent | Good (Cliopatria) |
| Shunga Empire | c. 185 BCE | c. 73 BCE | North/Central India | Limited |
| Satavahana Dynasty | c. 230 BCE | c. 220 CE | Deccan, Central India | Limited |
| Kushan Empire | c. 30 CE | c. 375 CE | NW India, Central Asia | Moderate |
| Gupta Empire | c. 320 CE | c. 550 CE | North India | Good (Cliopatria) |
| Harsha's Empire | 606 CE | 647 CE | North India | Limited |
| Pala Empire | c. 750 CE | c. 1161 CE | Bengal, Bihar | Limited |
| Rashtrakuta Dynasty | 753 CE | 982 CE | Deccan, Central India | Limited |
| Chola Empire | c. 300 BCE | 1279 CE | South India, SE Asia | Good (Cliopatria) |
| Chera Dynasty | c. 300 BCE | c. 1102 CE | Kerala, S India | Limited |
| Pandya Dynasty | c. 600 BCE | 1345 CE | Tamil Nadu | Limited |
| Pallava Dynasty | c. 275 CE | 897 CE | South India | Limited |
| Chalukya Dynasty (Badami) | 543 CE | 753 CE | Deccan | Limited |
| Chalukya Dynasty (Western) | 973 CE | 1189 CE | Deccan | Limited |
| Hoysala Empire | 1026 CE | 1343 CE | Karnataka | Limited |
| Kakatiya Dynasty | 1083 CE | 1323 CE | Andhra Pradesh | Limited |
| Delhi Sultanate | 1206 CE | 1526 CE | North India | Good (Cliopatria) |
| - Mamluk/Slave Dynasty | 1206 CE | 1290 CE | North India | Moderate |
| - Khalji Dynasty | 1290 CE | 1320 CE | North India | Moderate |
| - Tughlaq Dynasty | 1320 CE | 1413 CE | India | Moderate |
| - Sayyid Dynasty | 1414 CE | 1451 CE | North India | Moderate |
| - Lodi Dynasty | 1451 CE | 1526 CE | North India | Moderate |
| Vijayanagara Empire | 1336 CE | 1646 CE | South India | Moderate |
| Bahmani Sultanate | 1347 CE | 1527 CE | Deccan | Moderate |

---

### Category 6: Southeast Asian Empires

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Funan Kingdom | c. 1st c. CE | c. 550 CE | Cambodia, S Vietnam | Limited |
| Champa | c. 192 CE | 1832 CE | Central/S Vietnam | Limited |
| Chenla | c. 550 CE | c. 802 CE | Cambodia | Limited |
| Srivijaya Empire | c. 650 CE | c. 1377 CE | Sumatra, Malay Peninsula | Moderate (Cliopatria) |
| Sailendra Dynasty | c. 750 CE | c. 850 CE | Java | Limited |
| Khmer Empire | 802 CE | 1431 CE | Cambodia, Thailand, Laos | Good (Cliopatria) |
| Pagan Kingdom | 849 CE | 1287 CE | Myanmar/Burma | Moderate |
| Dai Viet (Ly Dynasty) | 1009 CE | 1225 CE | Vietnam | Moderate |
| Dai Viet (Tran Dynasty) | 1225 CE | 1400 CE | Vietnam | Moderate |
| Singhasari Kingdom | 1222 CE | 1292 CE | Java | Limited |
| Majapahit Empire | 1293 CE | c. 1527 CE | Indonesia | Moderate (Cliopatria) |
| Sukhothai Kingdom | c. 1238 CE | 1438 CE | Thailand | Moderate |
| Ayutthaya Kingdom | 1351 CE | 1767 CE | Thailand | Moderate |
| Lan Xang | 1353 CE | 1707 CE | Laos | Limited |
| Malacca Sultanate | 1400 CE | 1511 CE | Malaysia | Moderate |

---

### Category 7: African Empires and Kingdoms

#### North Africa and Egypt

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Pre-Dynastic Egypt | c. 5500 BCE | c. 3100 BCE | Nile Valley | Limited |
| Early Dynastic Egypt | c. 3100 BCE | c. 2686 BCE | Egypt | Moderate |
| Old Kingdom Egypt | c. 2686 BCE | c. 2181 BCE | Egypt | Good (Cliopatria) |
| First Intermediate Period | c. 2181 BCE | c. 2055 BCE | Egypt (divided) | Limited |
| Middle Kingdom Egypt | c. 2055 BCE | c. 1650 BCE | Egypt, Nubia | Good |
| Second Intermediate Period | c. 1650 BCE | c. 1550 BCE | Egypt (Hyksos) | Limited |
| New Kingdom Egypt | c. 1550 BCE | c. 1070 BCE | Egypt, Nubia, Levant | Good (Cliopatria) |
| Third Intermediate Period | c. 1070 BCE | c. 664 BCE | Egypt | Limited |
| Late Period Egypt | 664 BCE | 332 BCE | Egypt | Moderate |
| Ptolemaic Egypt | 305 BCE | 30 BCE | Egypt, Cyrenaica | Good |
| Carthaginian Empire | c. 814 BCE | 146 BCE | North Africa, W Mediterranean | Good (AWMC) |
| Numidia | c. 202 BCE | 46 BCE | Algeria, Tunisia | Moderate |
| Mauretania | c. 285 BCE | 40 CE | Morocco, W Algeria | Moderate |

#### Sub-Saharan Africa

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Kingdom of Kush/Nubia | c. 1070 BCE | c. 350 CE | Sudan | Moderate (Cliopatria) |
| Kingdom of Meroe | c. 800 BCE | c. 350 CE | Sudan | Moderate |
| Kingdom of Aksum/Axum | c. 100 CE | c. 940 CE | Ethiopia, Eritrea | Moderate (Cliopatria) |
| Kingdom of D'mt | c. 980 BCE | c. 400 BCE | Ethiopia, Eritrea | Limited |
| Ghana Empire | c. 300 CE | c. 1240 CE | Mali, Mauritania | Moderate (Cliopatria) |
| Kanem Empire | c. 700 CE | 1387 CE | Chad, Nigeria | Limited |
| Bornu Empire | 1387 CE | 1893 CE | Nigeria, Chad | Limited |
| Mali Empire | c. 1235 CE | c. 1600 CE | West Africa | Good (Cliopatria) |
| Songhai Empire | c. 1464 CE | 1591 CE | West Africa | Good (Cliopatria) |
| Kingdom of Mapungubwe | c. 1075 CE | c. 1220 CE | S Africa, Zimbabwe | Limited |
| Kingdom of Great Zimbabwe | c. 1220 CE | c. 1450 CE | Zimbabwe | Moderate |
| Mutapa Kingdom | c. 1430 CE | 1760 CE | Zimbabwe, Mozambique | Limited |
| Swahili City-States | c. 800 CE | 16th c. CE | East African Coast | Limited |
| Kilwa Sultanate | c. 957 CE | 1513 CE | Tanzania | Limited |
| Kingdom of Kongo | c. 1390 CE | 1914 CE | Congo, Angola | Moderate |
| Ethiopian Empire (Zagwe) | c. 900 CE | 1270 CE | Ethiopia | Limited |
| Ethiopian Empire (Solomonic) | 1270 CE | 1974 CE | Ethiopia | Moderate |

---

### Category 8: Americas

#### Mesoamerica

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Olmec Civilization | c. 1500 BCE | c. 400 BCE | Gulf Coast Mexico | Limited |
| Zapotec Civilization | c. 700 BCE | c. 1521 CE | Oaxaca, Mexico | Limited |
| Teotihuacan | c. 100 BCE | c. 650 CE | Central Mexico | Limited |
| Maya Civilization (Classic) | c. 250 CE | c. 900 CE | Yucatan, Guatemala, Belize | Moderate |
| Maya Civilization (Postclassic) | c. 900 CE | 1697 CE | Yucatan, Guatemala | Moderate |
| Toltec Empire | c. 900 CE | c. 1168 CE | Central Mexico | Limited |
| Aztec Empire (Triple Alliance) | 1428 CE | 1521 CE | Central Mexico | Moderate (Cliopatria) |
| Tarascan Empire (Purepecha) | c. 1300 CE | 1530 CE | Michoacan, Mexico | Limited |
| Mixtec Kingdoms | c. 700 CE | 1523 CE | Oaxaca, Mexico | Limited |

#### South America

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Norte Chico/Caral Civilization | c. 3000 BCE | c. 1800 BCE | Peru | Limited |
| Chavin Culture | c. 900 BCE | c. 200 BCE | Peru | Limited |
| Moche Civilization | c. 100 CE | c. 700 CE | Peru | Limited |
| Nazca Culture | c. 100 BCE | c. 800 CE | Peru | Limited |
| Tiwanaku Empire | c. 300 CE | c. 1150 CE | Bolivia, Peru | Limited |
| Wari Empire | c. 500 CE | c. 1000 CE | Peru | Limited |
| Chimu Kingdom | c. 900 CE | 1470 CE | Peru | Limited |
| Inca Empire | c. 1438 CE | 1533 CE | Peru, Ecuador, Bolivia, Chile | Moderate (Cliopatria) |
| Muisca Confederation | c. 1000 CE | 1541 CE | Colombia | Limited |

#### North America

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Poverty Point Culture | c. 1700 BCE | c. 1100 BCE | Louisiana | Limited |
| Adena Culture | c. 500 BCE | c. 100 CE | Ohio Valley | Limited |
| Hopewell Culture | c. 100 BCE | c. 500 CE | Ohio Valley, Midwest | Limited |
| Ancestral Puebloans (Anasazi) | c. 100 CE | c. 1600 CE | Four Corners Region | Limited |
| Hohokam Culture | c. 300 CE | c. 1450 CE | Arizona | Limited |
| Mississippian Culture | c. 800 CE | c. 1600 CE | Mississippi Valley, Southeast | Limited |
| Cahokia | c. 600 CE | c. 1400 CE | Illinois (St. Louis area) | Limited |

---

### Category 9: Medieval European Kingdoms

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Visigothic Kingdom | 418 CE | 721 CE | Iberia, S France | Moderate (Cliopatria) |
| Ostrogothic Kingdom | 493 CE | 553 CE | Italy | Moderate |
| Vandal Kingdom | 435 CE | 534 CE | North Africa | Moderate |
| Frankish Kingdom (Merovingian) | 481 CE | 751 CE | France, Germany | Good (Cliopatria) |
| Lombard Kingdom | 568 CE | 774 CE | Italy | Moderate |
| Carolingian Empire | 800 CE | 888 CE | Western Europe | Good (Cliopatria) |
| West Francia | 843 CE | 987 CE | France | Moderate |
| East Francia | 843 CE | 962 CE | Germany | Moderate |
| Holy Roman Empire | 962 CE | 1806 CE | Central Europe | Good (Cliopatria) |
| Kingdom of France (Capetian) | 987 CE | 1328 CE | France | Good |
| Kingdom of England | 927 CE | 1707 CE | England | Good |
| Kingdom of Scotland | 843 CE | 1707 CE | Scotland | Good |
| Kingdom of Ireland | c. 400 CE | 1541 CE | Ireland | Moderate |
| Kingdom of Denmark | c. 936 CE | Present | Denmark, Scandinavia | Good |
| Kingdom of Norway | 872 CE | 1397 CE | Norway | Moderate |
| Kingdom of Sweden | c. 970 CE | Present | Sweden | Moderate |
| Kievan Rus' | 882 CE | 1240 CE | Ukraine, Russia | Good (Cliopatria) |
| Polish Kingdom | 1025 CE | 1795 CE | Poland | Good |
| Kingdom of Hungary | 1000 CE | 1526 CE | Hungary | Good |
| Kingdom of Bohemia | c. 870 CE | 1918 CE | Czech Republic | Good |
| Papal States | 754 CE | 1870 CE | Central Italy | Moderate |
| Republic of Venice | 697 CE | 1797 CE | NE Italy, Adriatic | Moderate |
| Republic of Genoa | 1005 CE | 1797 CE | NW Italy | Moderate |
| Kingdom of Sicily | 1130 CE | 1816 CE | Sicily, S Italy | Moderate |
| Kingdom of Aragon | 1035 CE | 1707 CE | Spain | Moderate |
| Kingdom of Castile | 1065 CE | 1516 CE | Spain | Moderate |
| Kingdom of Portugal | 1139 CE | Present | Portugal | Good |
| Kingdom of Navarre | 824 CE | 1620 CE | Spain/France | Moderate |
| Crusader States | 1098 CE | 1291 CE | Levant | Moderate |
| Latin Empire | 1204 CE | 1261 CE | Greece, Anatolia | Limited |
| Bulgarian Empire (First) | 681 CE | 1018 CE | Balkans | Moderate |
| Bulgarian Empire (Second) | 1185 CE | 1396 CE | Balkans | Moderate |
| Serbian Empire | 1346 CE | 1371 CE | Balkans | Moderate |
| Principality of Moscow | 1263 CE | 1547 CE | Russia | Moderate |

---

### Category 10: Islamic World

| Name | Start Year | End Year | Region | GeoJSON Availability |
|------|------------|----------|--------|---------------------|
| Rashidun Caliphate | 632 CE | 661 CE | Arabia, Near East, N Africa | Good (Cliopatria) |
| Umayyad Caliphate | 661 CE | 750 CE | Near East, N Africa, Iberia | Good (Cliopatria) |
| Abbasid Caliphate | 750 CE | 1258 CE | Near East, N Africa | Good (Cliopatria) |
| Umayyad Emirate of Cordoba | 756 CE | 929 CE | Iberia | Moderate |
| Caliphate of Cordoba | 929 CE | 1031 CE | Iberia | Good |
| Taifa Kingdoms | 1031 CE | 1492 CE | Iberia | Limited |
| Almoravid Empire | 1040 CE | 1147 CE | N Africa, Iberia | Moderate |
| Almohad Caliphate | 1121 CE | 1269 CE | N Africa, Iberia | Moderate |
| Fatimid Caliphate | 909 CE | 1171 CE | N Africa, Egypt, Levant | Good (Cliopatria) |
| Ayyubid Dynasty | 1171 CE | 1260 CE | Egypt, Syria | Moderate |
| Mamluk Sultanate | 1250 CE | 1517 CE | Egypt, Syria | Good (Cliopatria) |
| Ghaznavid Empire | 977 CE | 1186 CE | Afghanistan, Iran, N India | Moderate |
| Ghurid Dynasty | c. 879 CE | 1215 CE | Afghanistan, N India | Limited |
| Seljuk Empire | 1037 CE | 1194 CE | Persia, Anatolia | Moderate |
| Sultanate of Rum | 1077 CE | 1307 CE | Anatolia | Moderate |
| Zengid Dynasty | 1127 CE | 1250 CE | Syria, Iraq | Limited |
| Marinid Dynasty | 1244 CE | 1465 CE | Morocco | Limited |
| Nasrid Kingdom (Granada) | 1232 CE | 1492 CE | S Spain | Moderate |
| Ottoman Empire (Early) | 1299 CE | 1922 CE | Anatolia, Balkans, Near East | Good (Cliopatria) |
| Hafsid Dynasty | 1229 CE | 1574 CE | Tunisia | Limited |

---

## Part 3: Data Quality and Recommendations

### Best Sources by Region

| Region | Recommended Primary Source | Secondary Sources |
|--------|---------------------------|-------------------|
| Global (all periods) | Cliopatria | Historical Basemaps |
| Roman/Greek World | AWMC Geodata | Roman Empire Vector Map |
| Medieval Europe | Cliopatria | Historical Basemaps |
| Ancient Near East | Cliopatria | AWMC |
| East Asia | Cliopatria | - |
| South Asia | Cliopatria | - |
| Africa | Cliopatria | - |
| Americas | Cliopatria (limited) | - |
| Southeast Asia | Cliopatria | - |

### Data Gaps and Limitations

1. **Pre-500 BCE Data**: Limited boundary precision for most civilizations before 500 BCE
2. **Americas**: Least well-documented region for GeoJSON boundaries
3. **Sub-Saharan Africa**: Many kingdoms have limited or no boundary data
4. **Southeast Asia**: Moderate coverage with gaps for smaller polities
5. **Border Concepts**: Ancient borders were often fluid zones rather than precise lines

### Recommended Approach for Implementation

1. **Start with Cliopatria**: Most comprehensive single source
2. **Supplement with AWMC**: For detailed Roman/Greek data
3. **Use Historical Basemaps**: For specific time-slice visualizations
4. **Consider Manual Digitization**: For important empires with no data

---

## Sources and References

### Primary GeoJSON Repositories
- [Cliopatria - Seshat Global History Databank](https://github.com/Seshat-Global-History-Databank/cliopatria)
- [Historical Basemaps (aourednik)](https://github.com/aourednik/historical-basemaps)
- [AWMC Geodata](https://github.com/AWMC/geodata)
- [Europe Historical GeoJSON](https://github.com/ioggstream/europe-historical-geojson)
- [Thenmap](https://www.thenmap.net/)

### Historical Reference Sources
- [World History Encyclopedia](https://www.worldhistory.org/)
- [Britannica](https://www.britannica.com/)
- [Khan Academy](https://www.khanacademy.org/)
- [Metropolitan Museum of Art - Heilbrunn Timeline](https://www.metmuseum.org/toah/)
- [HISTORY](https://www.history.com/)
- [Geography Realm - Historical GIS Data](https://www.geographyrealm.com/find-gis-data-historical-country-boundaries/)

### Regional Timelines
- [Mesopotamian Timeline - World History Encyclopedia](https://www.worldhistory.org/timeline/Mesopotamia/)
- [Dynasties of China - Wikipedia](https://en.wikipedia.org/wiki/Dynasties_of_China)
- [Timeline of Ancient Egypt - British Museum](https://www.britishmuseum.org/learn/schools/ages-7-11/ancient-egypt/timeline-ancient-egypt)
- [African Empires Timeline - HISTORY](https://www.history.com/articles/7-influential-african-empires)
- [Korean History - Three Kingdoms](https://www.britannica.com/topic/Three-Kingdoms-period)
- [Japanese Historical Periods](https://en.wikipedia.org/wiki/History_of_Japan)

---

*Document compiled: January 2026*
*Total empires/civilizations cataloged: 250+*
*GeoJSON sources identified: 8 major repositories*
