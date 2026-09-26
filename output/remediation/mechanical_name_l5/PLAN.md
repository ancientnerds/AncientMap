# L5 name lane (`name-l5`) - planned, not applied

Built 2026-09-26T14:34:05+00:00 by `scripts/remediation/l5/plan.py`: 2 site(s), 4 cell(s) (`name` and its match key, the key computed by Postgres from the new name; a key that does not move is not written). Run stamp `2026-09-26_mechanical-name-l5`, journal test id `B1/name-l5`.

| site | old name | new name | new key |
| --- | --- | --- | --- |
| `1d7cca0c-fb61-4b09-8692-52781474ed3e` | Dhank Buddhist Archaeological Site | Dhank Caves | `dhank caves` |
| `3199f739-6eaf-4065-8a07-4e44ec4695f7` | Augustòs Arch | Arch of Augustus | `arch of augustus` |

## Evidence

* **Dhank Caves** (`1d7cca0c-fb61-4b09-8692-52781474ed3e`): L5 reading (r1, r1-b02 (2026-09-26T09:25:58+00:00)): The site's own item and article call it 'Dhank Caves'; 'Dhank Buddhist Archaeological Site' is not a name attested for it and misdescribes it as only Buddhist, while the article says the caves are both Buddhist and Jain. No other curated site carries Q16924514.
  * https://en.wikipedia.org/wiki/Dhank_Caves: The Dhank Caves are located near Dhank village near Upleta, Rajkot district, Gujarat, India.
  * https://en.wikipedia.org/wiki/Dhank_Caves: The caves are influenced by Buddhist and Jain cultures.
* **Arch of Augustus** (`3199f739-6eaf-4065-8a07-4e44ec4695f7`): L5 reading (r1, r1-b03 (2026-09-26T09:26:07+00:00)): The site's own item and article name it 'Arch of Augustus' (Italian Arco di Augusto). The stored 'Augustòs Arch' is not a name of the monument in any language, nor a transliteration: it is a misspelt label found only on map-POI aggregator listings. Renamed to the item's English label, which is also the article title without the '(Susa)' qualifier.
  * https://en.wikipedia.org/wiki/Arch_of_Augustus_(Susa): The Arch of Augustus is an Ancient Roman arch constructed in the city of Susa
  * https://www.wikidata.org/wiki/Special:EntityData/Q1892101.json: Arch of Augustus

Run: `apply.py --lane name-l5 --emit`, `--rehearse`, `--probe-guards`, `--apply`, `--verify`, `--rehearse-rollback` (docs/procedures/SITES_DB_REMEDIATION_2026-09.md, WE lanes). On its next boot Lyra adds each new name to `unified_site_names` as a 'label' row (`_run_migrations`, the backfill); the old name stays there, so an exact search finds both.
