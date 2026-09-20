# G0 - persist the already-computed VLM verdicts (2026-09-21_gallery-verdicts-persist)

105 row(s) to write, 0 named refusal(s).

`image_kind` is written only where it is currently NULL, and only for rows whose site
belongs to `source_id = 'ancient_nerds'`. Nothing is overwritten and nothing is deleted.

## Why this set is 105 and not 280

The 16 `selection.json` files hold 280 entries in two shapes: 105 `stills` (full record,
carrying `id` = `wiki_images.id` and `verdict.kind`) and 175 `rejected` (only `filename`
and `reason`, no id and no kind). Only the `stills` are writable without inference. The
rejection reasons are mostly composition or quality judgements - `too small`, `duplicate`,
`panorama`, `text or overlay` - which are not image kinds.

## Rows to write

| image_id | slug | kind | filename |
|---|---|---|---|
| 60543 | archaeological-site-of-olympia | `site_photo` | `Greece-0585_(2215943566).webp` |
| 60545 | archaeological-site-of-olympia | `site_photo` | `Olimpia_FilipTemple.webp` |
| 60549 | archaeological-site-of-olympia | `site_photo` | `Olympia_34.webp` |
| 60550 | archaeological-site-of-olympia | `site_photo` | `Olympia_Model_1.webp` |
| 60555 | archaeological-site-of-olympia | `site_photo` | `Stadio_Olimpia_2007.webp` |
| 61951 | ishtar-gate | `site_photo` | `Babylon_processional_way.webp` |
| 61952 | ishtar-gate | `site_photo` | `Berlín,_Museo_de_Pérgamo_05.webp` |
| 61953 | ishtar-gate | `site_photo` | `Berlín_-_Pergamon_-_Porta_d'Ishtar_-_Lleons.webp` |
| 61956 | ishtar-gate | `site_photo` | `Fonds_Lucien_Golvin_(1908-2002)_-_Iraq_-_Babylone_-_Porte_d'Ishtar_(MédiHAL_4694048).webp` |
| 61958 | ishtar-gate | `site_photo` | `Ishtar-gate-بوابة-عشتار.webp` |
| 61967 | ishtar-gate | `site_photo` | `Mushkhusshu,_il_drago-serpente_raffigurato_sulla_porta_di_Ishtar_-_Pergamon_Museum,_Berlin.webp` |
| 61968 | ishtar-gate | `site_photo` | `Nebuchadnezzar_II's_Building_Inscription_plaque_of_the_Ishtar_Gate,_from_Babylon,_Iraq._6th_century_BCE._Pergamon_Museum.webp` |
| 61969 | ishtar-gate | `site_photo` | `Vorderasiatisches_Museum_Berlin_003_(cropped).webp` |
| 63779 | senegambian-stone-circles | `site_photo` | `Monolithe Sénégal 1.webp` |
| 63784 | senegambian-stone-circles | `site_photo` | `hero.webp` |
| 64269 | stonehenge | `site_photo` | `Stonehenge2007_07_30.webp` |
| 64272 | stonehenge | `site_photo` | `Stonehenge_Heel_Stone_-_panoramio_(2).webp` |
| 64276 | stonehenge | `site_photo` | `Stonehenge_from_the_air_-_Philip_Henry_Sharpe_(Royal_Engineers)_-_1906.webp` |
| 64277 | stonehenge | `site_photo` | `Stonehenge_on_27.01.08.webp` |
| 64481 | karatepe-aslantaş-open-air-museum | `site_photo` | `Karatepe (1600521540).webp` |
| 64492 | karatepe-aslantaş-open-air-museum | `site_photo` | `Karatepe Museum 5216.webp` |
| 64493 | karatepe-aslantaş-open-air-museum | `site_photo` | `KaratepeNord7.webp` |
| 64494 | karatepe-aslantaş-open-air-museum | `site_photo` | `KaratepeSüd1.webp` |
| 64499 | karatepe-aslantaş-open-air-museum | `site_photo` | `hero.webp` |
| 73055 | machu-picchu | `site_photo` | `143_Intiwatana_Machu_Picchu_Peru_2406_(14977268637).webp` |
| 73056 | machu-picchu | `site_photo` | `90_-_Machu_Picchu_-_Juin_2009_(cropped).webp` |
| 73059 | machu-picchu | `site_photo` | `An_Architectural_Triumph_Machu_Picchu.webp` |
| 73060 | machu-picchu | `site_photo` | `Andenes_at_Machu_Picchu_(cropped).webp` |
| 73062 | machu-picchu | `site_photo` | `MachuPicchu_Residential_(pixinn.net).webp` |
| 73065 | machu-picchu | `site_photo` | `Machu_Picchu.webp` |
| 73071 | machu-picchu | `site_photo` | `Partial_view_of_Machu_Picchu_in_1911.webp` |
| 73073 | machu-picchu | `site_photo` | `Room_of_the_Three_Windows_-_Machu_Picchu.webp` |
| 73420 | tomb-of-jahangir | `site_photo` | `Aerial_view_of_Jahangir_Tomb.webp` |
| 73421 | tomb-of-jahangir | `site_photo` | `Arcades_-_Jahangir’s_Tomb.webp` |
| 73422 | tomb-of-jahangir | `site_photo` | `Arches_of_Jahangir's_Tomb.webp` |
| 73423 | tomb-of-jahangir | `site_photo` | `Entrance_to_Jahangir's_Tomb_Compound_Lahore.webp` |
| 73424 | tomb-of-jahangir | `site_photo` | `Grave_of_Emperor_Jahangir_II.webp` |
| 73426 | tomb-of-jahangir | `site_photo` | `Interior_of_the_Tomb_of_Emperor_Jahangir.webp` |
| 73427 | tomb-of-jahangir | `site_photo` | `Jahangir's_tomb-4.webp` |
| 73431 | tomb-of-jahangir | `site_photo` | `Jehangir_tomb.webp` |
| 73432 | tomb-of-jahangir | `site_photo` | `Main_Entrance_of_Akbari_Sarai.webp` |
| 73433 | tomb-of-jahangir | `site_photo` | `Minaret_and_arcades_-_Tomb_of_Jahangir.webp` |
| 73434 | tomb-of-jahangir | `site_photo` | `Minaret_of_Jahangir's_Tomb,_Lahore.webp` |
| 73437 | tomb-of-jahangir | `site_photo` | `Tomb_of_Jahangir_Lahore_Pakistan.webp` |
| 73438 | tomb-of-jahangir | `site_photo` | `Tomb_of_Jahangir_and_gardens.webp` |
| 74401 | rano-raraku | `site_photo` | `Cesta od jezera na Rano Raraku - panoramio.webp` |
| 74402 | rano-raraku | `site_photo` | `Chile-03026 - Rapa Nui National Park (49073085342).webp` |
| 74403 | rano-raraku | `site_photo` | `Chile-03100 - Rano Raraku Volcano (49072387208).webp` |
| 74404 | rano-raraku | `site_photo` | `Chile-03101 - Caldera (49072386323).webp` |
| 74406 | rano-raraku | `site_photo` | `Chile-03103 - Rano Raraku Volcano & Coast Coral Tree (49073120952).webp` |
| 74408 | rano-raraku | `site_photo` | `Crater Lake at Rano Raraku - Easter Island (5956404668).webp` |
| 74413 | rano-raraku | `site_photo` | `Kneeled_moai_Easter_Island.webp` |
| 74414 | rano-raraku | `site_photo` | `Moai_Rano_raraku.webp` |
| 74415 | rano-raraku | `site_photo` | `Osterinsel_Moais_am_Berghang_im_Landesinnern.webp` |
| 74418 | rano-raraku | `site_photo` | `Rano-Raraku-from-South.webp` |
| 86861 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `20141013강화역사박물관고인돌.webp` |
| 86866 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `Example_of_a_southern-style_dolmen_at_Ganghwa_Island.webp` |
| 86867 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `GMJ 0153.webp` |
| 86868 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `GMJ 0154.webp` |
| 86871 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `Ganghwa Bugeun-ri dolmen.webp` |
| 86873 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `Gochang Dolmen Sites - 1.webp` |
| 86877 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `Korea-Hwasun_Dolmen_sites01.webp` |
| 86879 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `강화내가오상리고인돌.webp` |
| 86880 | gochang-hwasun-and-ganghwa-dolmen-sites | `site_photo` | `강화지석묘의 위용.webp` |
| 95395 | pamukkale | `site_photo` | `20071006-20 Turkije (288).webp` |
| 95402 | pamukkale | `site_photo` | `Denizli- Pamukkale.webp` |
| 95404 | pamukkale | `site_photo` | `Pamukkale_2_4_Commons.webp` |
| 95409 | pamukkale | `site_photo` | `TR_Pamukkale_Hierapolis_asv2020-02_img07.webp` |
| 95410 | pamukkale | `site_photo` | `TR_Pamukkale_Hierapolis_asv2020-02_img29.webp` |
| 95411 | pamukkale | `site_photo` | `TR_Pamukkale_Laodicea_asv2020-02_img11.webp` |
| 98168 | nazca-lines | `site_photo` | `04-Nazca_Lines-nX-54.webp` |
| 98169 | nazca-lines | `site_photo` | `04-Nazca_Lines-nX-58.webp` |
| 98170 | nazca-lines | `site_photo` | `1-1Nazca-lineas.webp` |
| 98172 | nazca-lines | `site_photo` | `Líneas_de_Nazca,_Nazca,_Perú,_2015-07-29,_DD_46.webp` |
| 98174 | nazca-lines | `site_photo` | `Líneas_de_Nazca,_Nazca,_Perú,_2015-07-29,_DD_50.webp` |
| 98177 | nazca-lines | `site_photo` | `Líneas_de_Nazca,_Nazca,_Perú,_2015-07-29,_DD_55.webp` |
| 98179 | nazca-lines | `site_photo` | `Líneas_de_Nazca,_Nazca,_Perú,_2015-07-29,_DD_58.webp` |
| 98185 | nazca-lines | `site_photo` | `Nazca_lines_fiore,_Nasca.webp` |
| 98277 | archaeological-site-puma-punku | `site_photo` | `In_the_Archaeological_site_of_Delphi,_Dlfi311.webp` |
| 98278 | archaeological-site-puma-punku | `site_photo` | `Ollanta,_Ollantaytambo,_Peru_-_Laslovarga_(27).webp` |
| 98279 | archaeological-site-puma-punku | `site_photo` | `Ollantaytambo_Monolithen.webp` |
| 98281 | archaeological-site-puma-punku | `site_photo` | `Puma_Punku12.webp` |
| 98283 | archaeological-site-puma-punku | `site_photo` | `Puma_Punku5.webp` |
| 98284 | archaeological-site-puma-punku | `site_photo` | `Puma_Punku6.webp` |
| 98285 | archaeological-site-puma-punku | `site_photo` | `Puma_Punku7.webp` |
| 98286 | archaeological-site-puma-punku | `site_photo` | `Puma_Punku9.webp` |
| 98289 | archaeological-site-puma-punku | `site_photo` | `Puma_Punku_landscape.webp` |
| 98291 | archaeological-site-puma-punku | `site_photo` | `Sluneční_brána_-_Puerta_del_Sol_-_Tiwanaku_-_panoramio.webp` |
| 100198 | tahai-ceremonial-complex | `site_photo` | `16 Velikonočni otok (20b) Tahai (6).webp` |
| 100200 | tahai-ceremonial-complex | `site_photo` | `Ahu Ko Te Riku - panoramio (1).webp` |
| 100203 | tahai-ceremonial-complex | `site_photo` | `Ahu Ko Te Riku 3.webp` |
| 100207 | tahai-ceremonial-complex | `site_photo` | `Ahu-Tahai-2014.webp` |
| 100210 | tahai-ceremonial-complex | `site_photo` | `Hangaroa Moais.webp` |
| 101056 | teotihuacan | `site_photo` | `Facade_of_the_Temple_of_the_Feathered_Serpent_(Teotihuacán).webp` |
| 101060 | teotihuacan | `site_photo` | `Piramide_de_la_Luna_072006.webp` |
| 104484 | giza-necropolis | `site_photo` | `00الأهرامات معرض الأبد هو الآن.webp` |
| 104486 | giza-necropolis | `site_photo` | `A sculpture in Pyramids of Giza.webp` |
| 104487 | giza-necropolis | `site_photo` | `All Gizah Pyramids - Cropped Version.webp` |
| 104488 | giza-necropolis | `site_photo` | `All Gizah Pyramids-3.webp` |
| 104493 | giza-necropolis | `site_photo` | `Giza-pyramids.webp` |
| 104498 | giza-necropolis | `site_photo` | `PyramidsofGiza_at_night.webp` |
| 104499 | giza-necropolis | `site_photo` | `S10.08_Gizeh,_image_9936.webp` |
| 107166 | federsee | `site_photo` | `80644 Federsee, Bad Buchau.webp` |
| 107167 | federsee | `site_photo` | `Abendstimmung am Federsee.webp` |
| 107170 | federsee | `site_photo` | `Aerials Federsee 2005.webp` |

## Named refusals

None.
## Verification

```bash
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --plan
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --rehearse
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --apply
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --verify
```

