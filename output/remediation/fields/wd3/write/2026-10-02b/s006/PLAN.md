# WD3 fields-wd3-2026-10-02b-s006: plan

Built 2026-10-04T12:47:31+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s006`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s006:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 215 |
| sites_written | 97 |
| refused | 31 |
| cells:geom | 18 |
| cells:lat | 18 |
| cells:lon | 18 |
| cells:period_name | 67 |
| cells:period_start | 67 |
| cells:site_type | 24 |
| cells:source_url | 3 |
| refused:coordinates-unresolved | 8 |
| refused:country-changes | 3 |
| refused:field-unresolved | 20 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Adullam Grove Nature Reserve | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Asklepieion - Pathos | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Asklepieion - Pathos | period_start | `NULL` | `101` | wd3-replace |
| Ayamachay | geom | `0101000020E610000056F3782497DB51C0C43BCE47A1332CC0` | `SRID=4326;POINT(-71.44183 -14.10389)` | wd3-point |
| Ayamachay | lat | `-14.100839847493155` | `-14.10389` | wd3-replace |
| Ayamachay | lon | `-71.43110000430656` | `-71.44183` | wd3-replace |
| Banoštor | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Banoštor | period_start | `NULL` | `-279` | wd3-replace |
| Beech Bottom Dyke | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Beech Bottom Dyke | period_start | `NULL` | `5` | wd3-replace |
| Beech Bottom Dyke | site_type | `NULL` | `Earthwork` | wd3-replace |
| Beit el-Wali | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Beit el-Wali | period_start | `NULL` | `-1300` | wd3-replace |
| Bhimashankar Buddhist Caves | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Bhimashankar Buddhist Caves | period_start | `NULL` | `1` | wd3-replace |
| Bhimashankar Buddhist Caves | site_type | `NULL` | `Cave Structures` | wd3-replace |
| Bhutalinga Buddhist Caves | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Bhutalinga Buddhist Caves | period_start | `NULL` | `1` | wd3-replace |
| Bhutalinga Buddhist Caves | site_type | `NULL` | `Cave Structures` | wd3-replace |
| Bimaran | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Bimaran | period_start | `NULL` | `-100` | wd3-replace |
| Blackhammer Chambered Cairn | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Blackhammer Chambered Cairn | period_start | `NULL` | `-3000` | wd3-replace |
| Blennerhasset and Torpenhow | geom | `0101000020E6100000DA79FCB0480A0AC0BC0C67DE04604B40` | `SRID=4326;POINT(-3.26025 54.7602)` | wd3-point |
| Blennerhasset and Torpenhow | lat | `54.75014858276106` | `54.7602` | wd3-replace |
| Blennerhasset and Torpenhow | lon | `-3.2550214602517658` | `-3.26025` | wd3-replace |
| Brittenburg | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Brittenburg | period_start | `NULL` | `301` | wd3-replace |
| Bülövqaya | geom | `0101000020E61000008452E58873D44640A97BD3EF46A54340` | `SRID=4326;POINT(45.6382 39.2834)` | wd3-point |
| Bülövqaya | lat | `39.29122731996842` | `39.2834` | wd3-replace |
| Bülövqaya | lon | `45.659775840734284` | `45.6382` | wd3-replace |
| Cantalloc Aqueducts | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Cantalloc Aqueducts | period_start | `NULL` | `501` | wd3-replace |
| Cenabum | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Cenabum | period_start | `NULL` | `-200` | wd3-replace |
| Chitinamit | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Coneybury Henge | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Coneybury Henge | period_start | `NULL` | `-2917` | wd3-replace |
| Cras  Round Cairn | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Cras  Round Cairn | period_start | `NULL` | `-2300` | wd3-replace |
| Cras  Round Cairn | site_type | `NULL` | `Cairn` | wd3-replace |
| Cras  Round Cairn | source_url | `NULL` | `https://cadwpublic-api.azurewebsites.net/reports/sam/FullRep` | wd3-replace |
| Dabarkot | geom | `0101000020E61000002FB9423C004051405F3B21CB30573E40` | `SRID=4326;POINT(68.683333 30.083333)` | wd3-point |
| Dabarkot | lat | `30.3405882793553` | `30.083333` | wd3-replace |
| Dabarkot | lon | `69.00001436725573` | `68.683333` | wd3-replace |
| Danubian Limes | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Danubian Limes | period_start | `NULL` | `50` | wd3-replace |
| Dilberjin Tepe | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dilberjin Tepe | period_start | `NULL` | `-1000` | wd3-replace |
| Domus de Janas S'Incantu | geom | `0101000020E610000086A11463A03B2340594BA133BF354440` | `SRID=4326;POINT(8.429931 40.606631)` | wd3-point |
| Domus de Janas S'Incantu | lat | `40.419897512204166` | `40.606631` | wd3-replace |
| Domus de Janas S'Incantu | lon | `9.616458030956675` | `8.429931` | wd3-replace |
| Domus de Janas S'Incantu | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Domus de Janas S'Incantu | period_start | `NULL` | `-3200` | wd3-replace |
| Dosariyah | site_type | `NULL` | `Settlement` | wd3-replace |
| Dun Ardtreck | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Dun Ardtreck | period_start | `NULL` | `-115` | wd3-replace |
| Dun Ardtreck | site_type | `NULL` | `Fort` | wd3-replace |
| Early Roman House | site_type | `NULL` | `Residence/villa/farmhouse` | wd3-replace |
| Goldbusch | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Goldbusch | period_start | `NULL` | `-3500` | wd3-replace |
| Great Serpent Mound | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Great Serpent Mound | period_start | `NULL` | `-300` | wd3-replace |
| Gudit Stelae Field | site_type | `NULL` | `Necropolis` | wd3-replace |
| Hadrianapolis Antik Kenti | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Hadrianapolis Antik Kenti | period_start | `NULL` | `-100` | wd3-replace |
| Harrow Hill, West Sussex | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Harrow Hill, West Sussex | period_start | `NULL` | `-3710` | wd3-replace |
| Hatun Uchku | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Hatun Uchku | period_start | `NULL` | `-14000` | wd3-replace |
| Hatun Uchku | site_type | `NULL` | `Cave` | wd3-replace |
| Huankarán | geom | `0101000020E61000005112BFEF0B2E53C00DDB8729FBC822C0` | `SRID=4326;POINT(-76.707056 -9.382)` | wd3-point |
| Huankarán | lat | `-9.392541215738243` | `-9.382` | wd3-replace |
| Huankarán | lon | `-76.7194785467084` | `-76.707056` | wd3-replace |
| Inka Murata | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Iskanwaya | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Iskanwaya | period_start | `NULL` | `1145` | wd3-replace |
| Jajce Mithraeum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Jajce Mithraeum | period_start | `NULL` | `301` | wd3-replace |
| Kahu-Jo-Darro | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Kavousi Vronda | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Kavousi Vronda | period_start | `NULL` | `-4000` | wd3-replace |
| Kentisbury Down | site_type | `NULL` | `Fort` | wd3-replace |
| Keston Roman Villa | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Keston Roman Villa | period_start | `NULL` | `-2000` | wd3-replace |
| Kinđa | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Kinđa | period_start | `NULL` | `-300` | wd3-replace |
| Kriemhildenstuhl | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Kriemhildenstuhl | period_start | `NULL` | `200` | wd3-replace |
| Kul Farah Historical Site | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Kul Farah Historical Site | period_start | `NULL` | `-900` | wd3-replace |
| Kunturmarka, Pasco | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Kızlar Kalesi | geom | `0101000020E61000004375CB87F04C41404B3DE9F8ED7F4240` | `SRID=4326;POINT(34.92556 37.15278)` | wd3-point |
| Kızlar Kalesi | lat | `36.999449838530005` | `37.15278` | wd3-replace |
| Kızlar Kalesi | lon | `34.60109040674663` | `34.92556` | wd3-replace |
| Laqaya | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Laqaya | period_start | `NULL` | `1000` | wd3-replace |
| Leben, Crete | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Leben, Crete | period_start | `NULL` | `-4000` | wd3-replace |
| Luoyang | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Luoyang | period_start | `NULL` | `-1036` | wd3-replace |
| Mankby | geom | `0101000020E6100000D00B31FED4A73840728AE912571A4E40` | `SRID=4326;POINT(24.579136 60.192195)` | wd3-point |
| Mankby | lat | `60.205782283815` | `60.192195` | wd3-replace |
| Mankby | lon | `24.655593764280468` | `24.579136` | wd3-replace |
| Minanha | geom | `0101000020E6100000EBA43D44114356C033D224C1BFBD3040` | `SRID=4326;POINT(-89.075 16.988333)` | wd3-point |
| Minanha | lat | `16.741207190980457` | `16.988333` | wd3-replace |
| Minanha | lon | `-89.04792886753027` | `-89.075` | wd3-replace |
| Minanha | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Minanha | period_start | `NULL` | `-600` | wd3-replace |
| Moel Hiraddug | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Moel Hiraddug | period_start | `NULL` | `-600` | wd3-replace |
| Monagrillo - Archaeological Site | site_type | `NULL` | `Village` | wd3-replace |
| Mortuary Temple of Hawara | geom | `0101000020E61000009FCD59CA6DE53E4064E24A110D423D40` | `SRID=4326;POINT(30.899 29.273)` | wd3-point |
| Mortuary Temple of Hawara | lat | `29.258011894972142` | `29.273` | wd3-replace |
| Mortuary Temple of Hawara | lon | `30.896206519054996` | `30.899` | wd3-replace |
| Mortuary Temple of Hawara | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Mortuary Temple of Hawara | period_start | `NULL` | `-1800` | wd3-replace |
| Mərdangöl Necropolis | geom | `0101000020E610000087FD1F1D4804474065B7413C67734340` | `SRID=4326;POINT(45.843606 38.948318)` | wd3-point |
| Mərdangöl Necropolis | lat | `38.901587993705824` | `38.948318` | wd3-replace |
| Mərdangöl Necropolis | lon | `46.03345073759106` | `45.843606` | wd3-replace |
| Mərdangöl Necropolis | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Mərdangöl Necropolis | period_start | `NULL` | `-900` | wd3-replace |
| Nindowari | geom | `0101000020E61000005F323C2802A05040FCEDC65B3F003B40` | `SRID=4326;POINT(66.066667 26.95)` | wd3-point |
| Nindowari | lat | `27.000966774050525` | `26.95` | wd3-replace |
| Nindowari | lon | `66.50013166311827` | `66.066667` | wd3-replace |
| Obzor | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Obzor | period_start | `NULL` | `-300` | wd3-replace |
| Osmantəpə | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Osmantəpə | period_start | `NULL` | `-9500` | wd3-replace |
| Osmantəpə | site_type | `NULL` | `Settlement` | wd3-replace |
| Pacatnamu | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Pacatnamu | period_start | `NULL` | `600` | wd3-replace |
| Penycloddiau | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Penycloddiau | period_start | `NULL` | `-1200` | wd3-replace |
| Perge Sütunlu Cadde | site_type | `NULL` | `Road/avenue/trackway` | wd3-replace |
| Pichvnari | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Pichvnari | period_start | `NULL` | `-600` | wd3-replace |
| Puente Romano de la Alcantarilla | site_type | `NULL` | `Bridge` | wd3-replace |
| Pyramid G1-b | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Pyramid G1-b | period_start | `NULL` | `-2575` | wd3-replace |
| Pythagoreion | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Pythagoreion | period_start | `NULL` | `-1600` | wd3-replace |
| Qunchupata, Ayacucho | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Qunchupata, Ayacucho | period_start | `NULL` | `500` | wd3-replace |
| Qunchupata, Ayacucho | site_type | `NULL` | `City/town/settlement` | wd3-replace |
| Rhodes Footbridge | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Rhodes Footbridge | period_start | `NULL` | `-400` | wd3-replace |
| Roman Middlewich | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Middlewich | period_start | `NULL` | `70` | wd3-replace |
| Roman Walls | source_url | `NULL` | `https://it.wikipedia.org/wiki/Mura_di_Aosta` | wd3-replace |
| Rudston Roman Villa | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Rudston Roman Villa | period_start | `NULL` | `201` | wd3-replace |
| Salou | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Salou | period_start | `NULL` | `-600` | wd3-replace |
| Salzofen Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Salzofen Cave | period_start | `NULL` | `-65000` | wd3-replace |
| Selinunte Archaeological Park | geom | `0101000020E61000003FE0B90C97AC2940704C7C58CCCA4240` | `SRID=4326;POINT(12.82472 37.58361)` | wd3-point |
| Selinunte Archaeological Park | lat | `37.58436113423602` | `37.58361` | wd3-replace |
| Selinunte Archaeological Park | lon | `12.837089917840897` | `12.82472` | wd3-replace |
| Sidyma | geom | `0101000020E61000008DFBAFCFAC343D409420048168334240` | `SRID=4326;POINT(29.193333 36.408333)` | wd3-point |
| Sidyma | lat | `36.40162670804526` | `36.408333` | wd3-replace |
| Sidyma | lon | `29.205761890854365` | `29.193333` | wd3-replace |
| Sillustani | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Sillustani | period_start | `NULL` | `1201` | wd3-replace |
| Siraj-ji-Takri | geom | `0101000020E6100000C61F6266663651404B7D77D4A6593A40` | `SRID=4326;POINT(68.778672 27.364736)` | wd3-point |
| Siraj-ji-Takri | lat | `26.350201872989867` | `27.364736` | wd3-replace |
| Siraj-ji-Takri | lon | `68.84999999601777` | `68.778672` | wd3-replace |
| Siraj-ji-Takri | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Siraj-ji-Takri | period_start | `NULL` | `401` | wd3-replace |
| Sokhta Koh | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Sokhta Koh | period_start | `NULL` | `-2600` | wd3-replace |
| Sítio Arqueológico da Pedra Pintada | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Sítio Arqueológico da Pedra Pintada | period_start | `NULL` | `-2000` | wd3-replace |
| Tahtzibichen Labyrinth | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tahtzibichen Labyrinth | period_start | `NULL` | `100` | wd3-replace |
| Tahtzibichen Labyrinth | site_type | `NULL` | `Cave Structures` | wd3-replace |
| Tampukancha | site_type | `NULL` | `Religious` | wd3-replace |
| Taxila | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Taxila | period_start | `NULL` | `-1000` | wd3-replace |
| The Prison of Socrates | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| The Prison of Socrates | period_start | `NULL` | `-450` | wd3-replace |
| Thermes Romains en Ruine-Roman Baths | source_url | `NULL` | `https://en.wikipedia.org/wiki/Roman_Baths,_Beirut` | wd3-replace |
| Tonina | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Tonina | period_start | `NULL` | `-800` | wd3-replace |
| Tumshukayko | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Tumshukayko | period_start | `NULL` | `-2000` | wd3-replace |
| Turunçova | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Turunçova | period_start | `NULL` | `1956` | wd3-replace |
| Tzintzuntzan | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Tzintzuntzan | period_start | `NULL` | `600` | wd3-replace |
| Ucanal | geom | `0101000020E610000008A492DC648656C04C85467A1F513040` | `SRID=4326;POINT(-89.35 16.86667)` | wd3-point |
| Ucanal | lat | `16.316886560646978` | `16.86667` | wd3-replace |
| Ucanal | lon | `-90.09990610428224` | `-89.35` | wd3-replace |
| Umm es-Sawan Ancient Basalt Quarry | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Umm es-Sawan Ancient Basalt Quarry | period_start | `NULL` | `-2900` | wd3-replace |
| Usnu, Huánuco | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Uzerliktapa | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Uzerliktapa | period_start | `NULL` | `-1800` | wd3-replace |
| Villa of Torre de Palma | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Villa of Torre de Palma | period_start | `NULL` | `1` | wd3-replace |
| Vučedol | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Vučedol | period_start | `NULL` | `-6000` | wd3-replace |
| Wadbury Camp | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Wadbury Camp | period_start | `NULL` | `-800` | wd3-replace |
| Weetwood Moor | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Weetwood Moor | period_start | `NULL` | `-3800` | wd3-replace |
| Windmill Tump | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Windmill Tump | period_start | `NULL` | `-4000` | wd3-replace |
| Yesemek Open Air Museum | geom | `0101000020E61000000D55319D6B5F4240F914A353CA734240` | `SRID=4326;POINT(36.74444 36.89306)` | wd3-point |
| Yesemek Open Air Museum | lat | `36.90461202109322` | `36.89306` | wd3-replace |
| Yesemek Open Air Museum | lon | `36.745471619689944` | `36.74444` | wd3-replace |
| Yongin Wangsanli Jiseongmyo | geom | `0101000020E61000006F77C78B4BCF5F40C370952F77AA4240` | `SRID=4326;POINT(127.2525 37.33556)` | wd3-point |
| Yongin Wangsanli Jiseongmyo | lat | `37.33176226422213` | `37.33556` | wd3-replace |
| Yongin Wangsanli Jiseongmyo | lon | `127.23898596266893` | `127.2525` | wd3-replace |
| Zapote Bobal | site_type | `NULL` | `City` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Mersinaki | lat | `country-changes` | the new point lies in ['Northern Cyprus'], the site says Cyprus |
| Mersinaki | period_start | `field-unresolved` | Readable sources only give period words for the sanctuary (PHRC: in use from 'the archaic period'; Swedish expedition su |
| Adullam Grove Nature Reserve | period_start | `field-unresolved` | The reserve was declared in 1994 to protect woodland and contains several separate sites of different dates (Horvat Midr |
| Puente Romano de la Alcantarilla | lat | `coordinates-unresolved` | The consortium page for the Puente romano de la Alcantarilla gives only its position on the right bank of the Guadiana o |
| Kunturmarka, Pasco | lat | `coordinates-unresolved` | No readable source prints a point for Kunturmarka (Condormarca), Paucartambo District, Pasco: Wikipedia and Wikidata giv |
| Kunturmarka, Pasco | period_start | `field-unresolved` | No source found dates Kunturmarka in Pasco; Wikipedia gives no date. |
| Danubian Limes | lat | `coordinates-unresolved` | The Danubian Limes is a frontier running through seven countries; neither Wikipedia (en, de) nor its Wikidata item gives |
| Early Roman House | lat | `coordinates-unresolved` | No readable page prints a point for the Early Roman House of Nea Paphos; the Wikipedia and University of Warsaw pages na |
| Early Roman House | period_start | `field-unresolved` | The only page that dates the house is a scanned Polish Archaeology in the Mediterranean report whose text the checker ca |
| Early Roman House | source_url | `field-unresolved` | No readable page is about the Early Roman House itself; the pages found cover the whole city or an excavation season, an |
| Laqaya | site_type | `field-unresolved` | Spanish Wikipedia describes a mix of a defensive village or pucara, over 300 chullpa towers and a lower village; no read |
| Aghios Epiktitos Vrysi | lat | `country-changes` | the new point lies in [], the site says Cyprus |
| Zapote Bobal | period_start | `field-unresolved` | Sources date only the Late Classic kingdom (AD 600-900) and say the dynasty flourished about 200 years, disintegrating b |
| Huankarán | period_start | `field-unresolved` | No readable source dates the start of Huankarán itself; the Tantamayo-valley date range (10th-14th centuries) is given f |
| Sidyma | period_start | `field-unresolved` | Turkish Wikipedia puts the first settlement of Sidyma in the Iron Age, which is a period word and not a date, and it sta |
| Usnu, Huánuco | period_start | `field-unresolved` | No source gives a year, century or millennium for the start of the Ushnu of Pachitea, Umari, Huánuco. The Spanish articl |
| Tahtzibichen Labyrinth | lat | `coordinates-unresolved` | The Megalithic Portal point (20.9, -89.9) is rated accuracy 1 (nearest town) and the page itself says 'The location list |
| Chitinamit | period_start | `field-unresolved` | The English Wikipedia article says only that Chitinamit dates from the Early Classic through to the Late Postclassic per |
| Inka Murata | lat | `coordinates-unresolved` | No source prints a coordinate pair for Inka Murata itself: the English Wikipedia article has none, Wikidata has no P625, |
| Inka Murata | period_start | `field-unresolved` | No source gives a date for the start of Inka Murata: Wikipedia and Law 3833 only name the site and its adjacent chullpas |
| Umm es-Sawan Ancient Basalt Quarry | lat | `coordinates-unresolved` | No readable source prints a point for the Umm es-Sawan gypsum quarry itself: QuarryScapes, the Geological Survey of Norw |
| Tampukancha | lat | `coordinates-unresolved` | No source prints a point for Tampukancha in a readable form: the only page that carries one (Esperanto Wikipedia) writes |
| Tampukancha | period_start | `field-unresolved` | No source dates the start of Tampukancha; the articles call it an Incan religious centre without a year, and no excavati |
| Stairhaven | lat | `country-changes` | the new point lies in [], the site says Scotland |
| Stairhaven | period_start | `field-unresolved` | No source dates the Stairhaven Broch. The Megalithic Portal record calls it an 'iron age broch' and the linked pages des |
| Stairhaven | site_type | `field-unresolved` | The one source that describes the monument, the Megalithic Portal record, types it as 'Broch or Nuraghe' and calls it a  |
| Ayamachay | period_start | `field-unresolved` | No source gives a year, century or millennium for the start of Ayamachay; the rock-art survey only calls it late pre-Col |
| Perge Sütunlu Cadde | period_start | `field-unresolved` | The Turkish Wikipedia article on Perge describes the Sütunlu Cadde only in plan terms ('Akropol eteğinde çeşme(nympheum) |
| Yongin Wangsanli Jiseongmyo | period_start | `field-unresolved` | No source gives a year, century or millennium for the building of the Yongin Wangsanli dolmens. The English article, the |
| Kentisbury Down | period_start | `field-unresolved` | Wikipedia gives only 'Iron Age'; Historic England's scheduling gives the eighth to fifth centuries BC and the Exmoor HER |
| Kızlar Kalesi | period_start | `field-unresolved` | No source I can quote dates the start of this site. The Turkish Culture and Tourism Ministry's Mersin page on castles de |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s006-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s006 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
