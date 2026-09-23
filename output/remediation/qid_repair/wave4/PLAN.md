# Source-url split, wave 4 (2026-09-23) - planned, not applied

48 row changes (run stamp `2026-09-23_source-url-split-wave4`): 20 `unified_sites.source_url` values keep their first URL, 28 `site_external_ids` rows are new and 0 corrected; 6 value(s) are left, each with its reason. The input is `wave4/RESOLUTION.json`: production read 2026-09-23T11:38:12Z (every `unified_sites` row whose `source_url` carries a control character: 20), English Wikipedia resolved 2026-09-23T11:38:14Z through `pipeline.lyra.prospector.wiki.resolve_titles`. The rules are in the module docstring of `output/remediation/tools/qid_repair.py`.

| site | column / kind | old | new |
| --- | --- | --- | --- |
| Acanceh (`e3a400b7-f8cd-4c4d-a2b0-b79ac18d2258`) | source_url | `https://www.megalithic.co.uk/article.php?sid=22756`<br>`https://en.wikipedia.org/wiki/Acanceh` | `https://www.megalithic.co.uk/article.php?sid=22756` |
| Acatitlan (`3f686b4b-2d03-45c0-b7f9-6c45ab044d7b`) | source_url | `https://www.megalithic.co.uk/article.php?sid=16598`<br>`https://en.wikipedia.org/wiki/Santa_Cecilia_Acatitlan` | `https://www.megalithic.co.uk/article.php?sid=16598` |
| Acatitlan (`3f686b4b-2d03-45c0-b7f9-6c45ab044d7b`) | enwiki_title | (no row) | `Santa Cecilia Acatitlan` |
| Acatitlan (`3f686b4b-2d03-45c0-b7f9-6c45ab044d7b`) | wikidata_qid | (no row) | `Q2725918` |
| Atzompa (`5699564f-61e7-481d-99dc-d23edc32207b`) | source_url | `https://www.megalithic.co.uk/article.php?sid=24013`<br>`https://en.wikipedia.org/wiki/Santa_Mar%C3%ADa_Atzompa` | `https://www.megalithic.co.uk/article.php?sid=24013` |
| Balamkú (`b2b1beee-00c6-4dfa-a616-89f7be1b86b7`) | source_url | `https://www.megalithic.co.uk/article.php?sid=22752`<br>`https://en.wikipedia.org/wiki/Balamku` | `https://www.megalithic.co.uk/article.php?sid=22752` |
| Balamkú (`b2b1beee-00c6-4dfa-a616-89f7be1b86b7`) | enwiki_title | (no row) | `Balamku` |
| Balamkú (`b2b1beee-00c6-4dfa-a616-89f7be1b86b7`) | wikidata_qid | (no row) | `Q804617` |
| Balankanche Cave (`1a9242d4-250f-4ffb-8dad-dae849c10798`) | source_url | `https://www.megalithic.co.uk/article.php?sid=22783`<br>`https://en.wikipedia.org/wiki/Balankanche` | `https://www.megalithic.co.uk/article.php?sid=22783` |
| Balankanche Cave (`1a9242d4-250f-4ffb-8dad-dae849c10798`) | enwiki_title | (no row) | `Balankanche` |
| Balankanche Cave (`1a9242d4-250f-4ffb-8dad-dae849c10798`) | wikidata_qid | (no row) | `Q1156198` |
| Balcon de Montezuma (`c4d2251b-b64a-4615-a6f9-5a71ff6f3955`) | source_url | `https://www.megalithic.co.uk/article.php?sid=27653`<br>`https://en.wikipedia.org/wiki/Balc%C3%B3n_de_Montezuma` | `https://www.megalithic.co.uk/article.php?sid=27653` |
| Balcon de Montezuma (`c4d2251b-b64a-4615-a6f9-5a71ff6f3955`) | enwiki_title | (no row) | `Balcón de Montezuma` |
| Balcon de Montezuma (`c4d2251b-b64a-4615-a6f9-5a71ff6f3955`) | wikidata_qid | (no row) | `Q4850276` |
| Becan (`ad61addd-d62b-4c88-972c-18ebf465a900`) | source_url | `https://www.megalithic.co.uk/article.php?sid=20199`<br>`https://en.wikipedia.org/wiki/Becan` | `https://www.megalithic.co.uk/article.php?sid=20199` |
| Becan (`ad61addd-d62b-4c88-972c-18ebf465a900`) | enwiki_title | (no row) | `Becan` |
| Becan (`ad61addd-d62b-4c88-972c-18ebf465a900`) | wikidata_qid | (no row) | `Q813784` |
| Boca de Potrerillos (`69fb9773-3709-4e8e-8682-96c75f57dfc6`) | source_url | `https://www.megalithic.co.uk/article.php?sid=51375`<br>`https://en.wikipedia.org/wiki/Boca_de_Potrerillos` | `https://www.megalithic.co.uk/article.php?sid=51375` |
| Boca de Potrerillos (`69fb9773-3709-4e8e-8682-96c75f57dfc6`) | enwiki_title | (no row) | `Boca de Potrerillos` |
| Boca de Potrerillos (`69fb9773-3709-4e8e-8682-96c75f57dfc6`) | wikidata_qid | (no row) | `Q4936130` |
| Bonampak (`08508ff0-053d-4b8e-b2a3-6382818c6735`) | source_url | `https://www.megalithic.co.uk/article.php?sid=16557`<br>`https://en.wikipedia.org/wiki/Bonampak` | `https://www.megalithic.co.uk/article.php?sid=16557` |
| Bonampak (`08508ff0-053d-4b8e-b2a3-6382818c6735`) | enwiki_title | (no row) | `Bonampak` |
| Bonampak (`08508ff0-053d-4b8e-b2a3-6382818c6735`) | wikidata_qid | (no row) | `Q605455` |
| Cacaxtla (`2bc26dce-7797-40a5-8a39-589e5dee1453`) | source_url | `https://www.megalithic.co.uk/article.php?sid=28978`<br>`https://en.wikipedia.org/wiki/Cacaxtla` | `https://www.megalithic.co.uk/article.php?sid=28978` |
| Cacaxtla (`2bc26dce-7797-40a5-8a39-589e5dee1453`) | enwiki_title | (no row) | `Cacaxtla` |
| Cacaxtla (`2bc26dce-7797-40a5-8a39-589e5dee1453`) | wikidata_qid | (no row) | `Q1024995` |
| Cantil de las animas (`885bbbdb-2583-4bc7-8be9-91b978cedcf3`) | source_url | `https://www.megalithic.co.uk/article.php?sid=33354`<br>`https://rockartblog.blogspot.com/2013/05/cantil-de-las-animas-tepic-mexico.html` | `https://www.megalithic.co.uk/article.php?sid=33354` |
| Cascajal Block (`08f54fa9-0ca0-490c-82af-47fdd0a40e6b`) | source_url | `https://www.megalithic.co.uk/article.php?sid=16211`<br>`https://en.wikipedia.org/wiki/Cascajal_Block` | `https://www.megalithic.co.uk/article.php?sid=16211` |
| Cascajal Block (`08f54fa9-0ca0-490c-82af-47fdd0a40e6b`) | enwiki_title | (no row) | `Cascajal Block` |
| Cascajal Block (`08f54fa9-0ca0-490c-82af-47fdd0a40e6b`) | wikidata_qid | (no row) | `Q1046912` |
| Cañada de la Virgen (`bf81babd-58bf-4bac-b5e9-fac36c10c95c`) | source_url | `https://www.megalithic.co.uk/article.php?sid=51362`<br>`https://en.wikipedia.org/wiki/Ca%C3%B1ada_de_la_Virgen` | `https://www.megalithic.co.uk/article.php?sid=51362` |
| Cañada de la Virgen (`bf81babd-58bf-4bac-b5e9-fac36c10c95c`) | enwiki_title | (no row) | `Cañada de la Virgen` |
| Cañada de la Virgen (`bf81babd-58bf-4bac-b5e9-fac36c10c95c`) | wikidata_qid | (no row) | `Q5055568` |
| Cerro De Trincheras (`d4671d52-1421-4853-a186-6f3b4516368d`) | source_url | `https://www.megalithic.co.uk/article.php?sid=33431`<br>`https://en.wikipedia.org/wiki/Trincheras` | `https://www.megalithic.co.uk/article.php?sid=33431` |
| Chacchoben (`5b9393ea-f867-4553-b497-7079cebbff61`) | source_url | `https://www.megalithic.co.uk/article.php?sid=22796`<br>`https://en.wikipedia.org/wiki/Chacchoben` | `https://www.megalithic.co.uk/article.php?sid=22796` |
| Chacchoben (`5b9393ea-f867-4553-b497-7079cebbff61`) | enwiki_title | (no row) | `Chacchoben` |
| Chacchoben (`5b9393ea-f867-4553-b497-7079cebbff61`) | wikidata_qid | (no row) | `Q928886` |
| Chacmultun (`ad605739-5499-4bbd-8a9f-448225caff56`) | source_url | `https://www.megalithic.co.uk/article.php?sid=16564`<br>`https://en.wikipedia.org/wiki/Chacmultun` | `https://www.megalithic.co.uk/article.php?sid=16564` |
| Chacmultun (`ad605739-5499-4bbd-8a9f-448225caff56`) | enwiki_title | (no row) | `Chacmultun` |
| Chacmultun (`ad605739-5499-4bbd-8a9f-448225caff56`) | wikidata_qid | (no row) | `Q1058412` |
| Chactún (`8e625e19-eeb1-4813-8244-14ec448d7440`) | source_url | `https://www.megalithic.co.uk/article.php?sid=34244`<br>`https://en.wikipedia.org/wiki/Chact%C3%BAn` | `https://www.megalithic.co.uk/article.php?sid=34244` |
| Chactún (`8e625e19-eeb1-4813-8244-14ec448d7440`) | enwiki_title | (no row) | `Chactún` |
| Chactún (`8e625e19-eeb1-4813-8244-14ec448d7440`) | wikidata_qid | (no row) | `Q13518345` |
| Chalcatzingo (`b7020e91-a80b-46cc-8624-878be1713336`) | source_url | `https://www.megalithic.co.uk/article.php?sid=29909`<br>`https://en.wikipedia.org/wiki/Chalcatzingo` | `https://www.megalithic.co.uk/article.php?sid=29909` |
| Chalcatzingo (`b7020e91-a80b-46cc-8624-878be1713336`) | enwiki_title | (no row) | `Chalcatzingo` |
| Chalcatzingo (`b7020e91-a80b-46cc-8624-878be1713336`) | wikidata_qid | (no row) | `Q1059465` |
| Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) | source_url | `https://www.megalithic.co.uk/article.php?sid=26242`<br>`https://en.wikipedia.org/wiki/Chiapa_de_Corzo_(Mesoamerican_site)` | `https://www.megalithic.co.uk/article.php?sid=26242` |
| Petra (`a06a95d0-35b4-44bb-a0c1-716cbf972b19`) | source_url | `https://en.wikipedia.org/wiki/Petra`<br>`https://www.khanacademy.org/humanities/ap-art-history/west-and-central-asia-apahh/west-asia/a/petra-rock-cut-facades` | `https://en.wikipedia.org/wiki/Petra` |

## Left as they are, and why

| site | what | reason |
| --- | --- | --- |
| Acanceh (`e3a400b7-f8cd-4c4d-a2b0-b79ac18d2258`) | external ids | https://en.wikipedia.org/wiki/Acanceh: Q8186545 is a place, not the site (P31: locality of Mexico) |
| Atzompa (`5699564f-61e7-481d-99dc-d23edc32207b`) | external ids | https://en.wikipedia.org/wiki/Santa_Mar%C3%ADa_Atzompa: Q3846612 is a place, not the site (P31: municipality of Mexico) |
| Cantil de las animas (`885bbbdb-2583-4bc7-8be9-91b978cedcf3`) | external ids | neither URL is an English Wikipedia article |
| Cerro De Trincheras (`d4671d52-1421-4853-a186-6f3b4516368d`) | external ids | https://en.wikipedia.org/wiki/Trincheras: Q1434929 is a place, not the site (P31: locality of Mexico) |
| Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) | external ids | https://en.wikipedia.org/wiki/Chiapa_de_Corzo_(Mesoamerican_site): Q4384315 is already carried by the curated site Zoque Culture Archaeological Zone (ed186ea9-9ed1-415d-828b-97d9f21401d2) |
| Petra (`a06a95d0-35b4-44bb-a0c1-716cbf972b19`) | external ids | https://en.wikipedia.org/wiki/Petra: Q5788 is a place, not the site (P31: ancient city, city, archaeological site) |

## Duplicate candidates (the owner's merge, not a link)

| site | the other curated site | shared item | evidence |
| --- | --- | --- | --- |
| Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) | Zoque Culture Archaeological Zone (`ed186ea9-9ed1-415d-828b-97d9f21401d2`) | `Q4384315` | this site's article https://en.wikipedia.org/wiki/Chiapa_de_Corzo_(Mesoamerican_site) resolves to `Q4384315`, the item the other row carries; the other row's source_url is `https://en.wikipedia.org/wiki/Chiapa_de_Corzo_(Mesoamerican_site)` - the same article |

## Order and fixed point

* After the apply the boot refresh (`refresh_site_external_ids(only_missing=True)`) reads only a site with no external-id row and an English Wikipedia `source_url`: none of these sites. The manual `--all` path reads every curated site whose `source_url` is an English Wikipedia article, and would write the ids this wave refuses for Petra - the fixed point waves 1-3 name for their own rows.
* Petra keeps its stored enwiki_title value with a control character: the wave refuses the article's resolution, so it has no replacement to write, and a removal is a `DELETE` - the owner's call.
* `migrations/0023_source_url_no_control_chars.sql` may reach the deploy only after this wave is applied and verified: it fails while any `source_url` carries a control character, and a failing migration stops the deploy. Once it is applied, the `source_url` half of `ROLLBACK.sql` cannot run (the CHECK refuses the two-URL value).

## How to run it (the orchestrator's job, in this order)

`resolve --wave 4` (read-only: production and English Wikipedia) wrote `RESOLUTION.json`, the versioned input of this plan. Run it again only to re-plan: it renews both timestamps, so every row's evidence and the plan digest change with it.

```bash
PY=./.venv/Scripts/python.exe
$PY output/remediation/tools/qid_repair.py render --wave 4   # REHEARSAL.sql is not versioned
$PY output/remediation/tools/qid_repair.py check --wave 4    # read-only
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave4/REHEARSAL.sql
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave4/APPLY.sql
$PY output/remediation/tools/qid_repair.py verify --wave 4   # read-only
```
