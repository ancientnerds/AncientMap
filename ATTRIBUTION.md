# Data Attribution and Licenses

This project aggregates archaeological and historical data from numerous sources.
We are grateful to all the organizations and individuals who make their data
openly available for research and education.

## Required Attribution

When using or displaying data from this platform, please include appropriate
attribution to the original data sources as specified below.

---

## Archaeological Gazetteers

### Pleiades
- **Website**: https://pleiades.stoa.org/
- **License**: CC-BY 3.0
- **Citation**: Pleiades: A Gazetteer of Past Places. https://pleiades.stoa.org/
- **Data**: ~38,000 ancient Mediterranean places

### Digital Atlas of the Roman Empire (DARE)
- **Website**: https://imperium.ahlfeldt.se/
- **License**: CC-BY 4.0
- **Citation**: Johan Åhlfeldt, Digital Atlas of the Roman Empire
- **Data**: Roman settlements, roads, and boundaries

### ToposText
- **Website**: https://topostext.org/
- **License**: Contact for terms
- **Citation**: ToposText - Ancient Places and Texts
- **Data**: 8,137 historic places with literary references

### EAMENA (Endangered Archaeology in the Middle East and North Africa)
- **Website**: https://eamena.org/
- **License**: Open (check specific datasets)
- **Citation**: EAMENA Database
- **Data**: Middle East and North Africa archaeological sites

---

## Cultural Heritage Organizations

### UNESCO World Heritage Sites
- **Website**: https://whc.unesco.org/
- **License**: Open with attribution
- **Citation**: UNESCO World Heritage List
- **Data**: World Heritage Sites with archaeological significance

### Europeana
- **Website**: https://www.europeana.eu/
- **License**: Various (per item)
- **Citation**: Europeana Foundation
- **Data**: European cultural heritage collections

### Historic England
- **Website**: https://historicengland.org.uk/
- **License**: Open Government Licence
- **Citation**: Historic England
- **Data**: Listed buildings, scheduled monuments, registered parks

### Irish National Museum
- **Website**: https://www.museum.ie/
- **License**: Contact for terms
- **Data**: Irish archaeological artifacts and sites

### Met Museum (Metropolitan Museum of Art)
- **Website**: https://www.metmuseum.org/
- **License**: CC0 for open access images
- **Data**: Archaeological collection metadata

---

## Linked Open Data Sources

### Wikidata
- **Website**: https://www.wikidata.org/
- **License**: CC0 (Public Domain)
- **Citation**: Wikidata contributors
- **Data**: Archaeological sites, historical places

### OpenStreetMap (Historic Features)
- **Website**: https://www.openstreetmap.org/
- **License**: ODbL (Open Database License)
- **Citation**: © OpenStreetMap contributors
- **Data**: Historic and archaeological features

### GeoNames
- **Website**: https://www.geonames.org/
- **License**: CC-BY 4.0
- **Citation**: GeoNames geographical database
- **Data**: Geographic names and coordinates

---

## Academic Databases

### Arachne (German Archaeological Institute)
- **Website**: https://arachne.dainst.org/
- **License**: Contact for terms
- **Citation**: Arachne - Central Object Database of the DAI
- **Data**: Archaeological objects and contexts

### DINAA (Digital Index of North American Archaeology)
- **Website**: https://www.dinaa.net/
- **License**: Contact for terms
- **Data**: North American archaeological sites

### Open Context
- **Website**: https://opencontext.org/
- **License**: Various (per dataset, mostly CC)
- **Citation**: Open Context
- **Data**: Archaeological research data

### Epigraphic Database Heidelberg (EDH)
- **Website**: https://edh.ub.uni-heidelberg.de/
- **License**: CC-BY-SA
- **Citation**: Epigraphic Database Heidelberg
- **Data**: Latin inscriptions

---

## Specialized Databases

### Oxford Roman Economy Project (OXREP)
- **Website**: https://oxrep.classics.ox.ac.uk/
- **License**: Free use with citation
- **Data**:
  - Shipwrecks Database
  - Mines Database

### Nomisma.org
- **Website**: http://nomisma.org/
- **License**: CC-BY
- **Citation**: Nomisma.org
- **Data**: Ancient numismatics (coins, mints, hoards)

### Sketchfab (3D Models)
- **Website**: https://sketchfab.com/
- **License**: Various (per model)
- **Data**: 3D models of archaeological sites and artifacts

### Sacred Sites
- **License**: Various
- **Data**: Religious and sacred archaeological sites

### Rock Art Database
- **Website**: https://rockartdatabase.com/
- **License**: Contact for terms
- **Data**: Global rock art sites

---

## Environmental and Geological Data

### Smithsonian Global Volcanism Program
- **Website**: https://volcano.si.edu/
- **License**: Free use with citation
- **Citation**: Global Volcanism Program, Smithsonian Institution
- **Data**: Holocene volcanoes and eruptions

### NCEI (National Centers for Environmental Information)
- **Website**: https://www.ncei.noaa.gov/
- **License**: Public Domain (US Government)
- **Data**:
  - Significant Earthquakes Database
  - Tsunami Events Database
  - Significant Volcanic Eruptions Database

### Earth Impact Database
- **Website**: http://www.passc.net/EarthImpactDatabase/
- **License**: Free use with citation
- **Data**: Confirmed meteor impact craters

### Holocene Volcanoes Database
- **License**: Academic use
- **Data**: Volcanic activity during human history

---

## Cartographic Data

### Ancient World Mapping Center (AWMC)
- **Website**: https://awmc.unc.edu/
- **License**: CC-BY 4.0 / ODC ODbL (Open Database License)
- **Citation**: Ancient World Mapping Center, UNC Chapel Hill
- **Data**: Ancient coastlines, rivers, roads, boundaries
- **Historical Maps**: Classroom maps, wall maps, and "Romans from Village to Empire" series hosted on Wikimedia Commons

### David Rumsey Map Collection
- **Website**: https://www.davidrumsey.com/
- **License**: Various (per map)
- **Data**: Historical maps for georeferencing

---

## Media Sources

### Wikimedia Commons
- **Website**: https://commons.wikimedia.org/
- **License**: Various (mostly CC)
- **Data**: Images and media files

---

## Boundary Data

### Cliopatria Historical Boundaries Dataset
- **Website**: https://github.com/Seshat-Global-History-Databank/cliopatria
- **License**: CC BY (Creative Commons Attribution)
- **Citation**: Cliopatria Dataset, Seshat Global History Databank
- **Publication**: Peer-reviewed data published in Nature Scientific Data
- **Data**: Historical polity boundary GeoJSON (1,800+ political entities, 15,000+ records, 3400 BCE - 2024 CE)
- **Note**: Empire boundaries are matched using SeshatID field from the dataset for reliable linking

### SESHAT Global History Databank
- **Website**: http://seshatdatabank.info/
- **License**: CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike)
- **Citation**: Turchin, P., et al. (2018). Quantitative historical analysis uncovers a single dimension of complexity that structures global variation in human social organization. PNAS.
- **Data**: Historical polity data including social complexity variables, warfare technology, and economy data

### Natural Earth
- **Website**: https://www.naturalearthdata.com/
- **License**: Public Domain
- **Data**: Modern political boundaries for reference

---

## Software Dependencies

This project uses open source software. Key dependencies include:

### Backend (Python)
- FastAPI (MIT)
- SQLAlchemy (MIT)
- Pydantic (MIT)
- httpx (BSD-3-Clause)
- rapidfuzz (MIT) - *Replaced python-Levenshtein (GPL-2.0)*
- anyascii (ISC) - *Replaced unidecode (GPL-2.0)*

### Frontend (JavaScript/TypeScript)
- React (MIT)
- Vite (MIT)
- Mapbox GL JS (Proprietary - requires Mapbox account and ToS compliance)
- Three.js (MIT)

### Databases & Infrastructure
- PostgreSQL (PostgreSQL License - BSD-like)
- PostGIS (GPL-2.0 - usage as database backend permitted)
- Redis 7.2.4 (BSD-3-Clause) - *Pinned version; 7.4+ uses RSALv2/SSPLv1*
- Qdrant (Apache 2.0)
- SearXNG (AGPL-3.0 - self-hosted)

---

## AI/ML Components

### Language Models (via Ollama)
- **Mistral 7B** (Apache 2.0) - Default chat model, commercial use permitted
- **Llama 3.1** (Meta Community License) - Research mode, requires attribution
- **Phi-3** (MIT) - Alternative option, fully permissive

**Note:** Qwen models require commercial license from Alibaba Cloud for business use.

### Embedding Models
- **BAAI/bge-small-en-v1.5** (MIT) - Recommended for commercial use
- *all-MiniLM-L6-v2 has training data restrictions (MS MARCO non-commercial)*

### AI Frameworks
- Ollama (MIT)
- PyTorch (BSD-3-Clause)
- Sentence-Transformers (Apache 2.0)
- Hugging Face Transformers (Apache 2.0)
- Qdrant Vector Database (Apache 2.0)

### Required Attribution (Llama 3.1)
```
Llama 3.1 is licensed under the Llama 3.1 Community License,
Copyright (c) Meta Platforms, Inc. All Rights Reserved.
```

---

## Map Services

### Mapbox GL JS
- **License**: Proprietary (Mapbox Terms of Service)
- **Requirements**: Active Mapbox account, visible attribution
- **Attribution**: © Mapbox, © OpenStreetMap contributors

### OpenStreetMap
- **License**: ODbL (Open Database License)
- **Attribution**: © OpenStreetMap contributors

### Natural Earth
- **License**: Public Domain
- No attribution required

---

## How to Cite This Project

If you use this platform in your research, please cite:

```
Ancient Nerds Map - Archaeological Research Platform
https://github.com/AncientNerds/AncientMap
```

And include appropriate citations for any specific data sources you use.

---

## Reporting Attribution Issues

If you believe your data is being used incorrectly or without proper attribution,
please open an issue on our GitHub repository or contact us directly.

---

---

## Licensing Compliance Notes

### Non-Commercial Data Sources
The following sources have **non-commercial use restrictions**:

| Source | License | Restriction |
|--------|---------|-------------|
| Seshat Global History Databank | CC-BY-NC-SA 4.0 | Non-commercial only |
| CyArk | CC-BY-NC 4.0 | Non-commercial only |
| MorphoSource | Varies (mostly CC-BY-NC) | Check per item |
| Packard Humanities Institute | Personal/Fair Use | Academic use only |

### Commercial Deployment Checklist
For commercial use of this platform:
- [ ] Replace Qwen models with Mistral/Phi-3 (done in defaults)
- [ ] Use BAAI/bge-small-en-v1.5 embedding model (done in defaults)
- [ ] Maintain active Mapbox account
- [ ] Ensure Mapbox attribution is visible
- [ ] Exclude or obtain licenses for NC-restricted data sources
- [ ] Verify Sketchfab model licenses before display

---

*Last updated: February 2026*
