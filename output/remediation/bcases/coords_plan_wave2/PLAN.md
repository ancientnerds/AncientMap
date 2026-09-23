# Owner-case coordinates, wave 2 (a third witness from the web) - planned, not applied

7 curated sites, 21 journalled changes (geom, lat, lon each), run stamp `2026-09-23_owner-case-coordinates-wave2`. Rendered by `scripts/remediation/bcases/coord_plan.py` from the `move` verdicts of `coords3/VERDICTS.jsonl` (`web_witness.py reweigh`: the first wave's review cases weighed again with the web witnesses proven from the live page): two independent witnesses agree within the tolerance and the stored point lies outside it. **Not applied**: FIELD_CONTRACT section 4.6 reserves coordinate changes for the owner (HUMAN_ONLY B1/B2).

Independent means: neither says it was imported from the other, neither is the other rounded or truncated to the grid its digits are written on (decimals, whole arcseconds or arcminutes), and the two points lie further apart than one arcsecond, one step of either grid and the Wikidata precision (`scripts/remediation/bcases/classify.py`, `independent`).

A web witness is a page outside Wikipedia, Wikidata and their mirrors whose coordinates `scripts/remediation/bcases/web_witness.py` read from the live page: the quoted text occurs in the page, parses to exactly the stated numbers, and stands within 1,500 characters of a distinctive word of the site's name. Pages of one publisher (a registered domain) are one witness; two web witnesses pair only across publishers, under the same independence rule. Where a web witness takes part, two witnesses that are each one with a third are one with each other (`copy_groups`), and a P625 whose references name the page's publisher is that page (`cited_publishers`). A move into another country than the stored one is not in this plan (it is read first).

| site | stored | new | moved | witnesses | reason |
| --- | --- | --- | --- | --- | --- |
| Teanum Apulum (`ce4058e7-7631-40ad-beb1-188e3cd27232`) | 41.80021, 14.91662 | 41.76370, 15.24169 | 27.26 km | [wikidata](https://www.wikidata.org/wiki/Q3017180) P625 = 41.763700, 15.241690 (precision 1e-05)<br>[web:ahlfeldt.se](http://imperium.ahlfeldt.se/places/23226.html) 41.77125, 15.23548 | wikidata and web:ahlfeldt.se agree within 985 m (independent), the stored point is 27.26 km away |
| Aziz Dheri (`b8ddb28d-b0b8-4d6e-bdec-c5346a0de1a1`) | 34.11680, 72.46656 | 34.24546, 72.39341 | 15.81 km | [wikidata](https://www.wikidata.org/wiki/Q88078046) P625 = 34.245464, 72.393405 (precision 1e-07)<br>[web:doam.gov.pk](https://doam.gov.pk/public/sites/2330) Latitude: 34.241666667 Longitude: 72.402333333 | wikidata and web:doam.gov.pk agree within 923 m (independent), the stored point is 15.81 km away |
| Kephala, Kea (`294968f3-036b-44ff-b704-91593648927d`) | 37.64433, 24.33814 | 37.68090, 24.32862 | 4.15 km | [wikidata](https://www.wikidata.org/wiki/Q1739125) P625 = 37.680899, 24.328623 (precision 2.77777777778e-06)<br>[web:topostext.org](https://topostext.org/place/377243XKef) Latitude: 37.681700 Longitude: 24.328600 | wikidata and web:topostext.org agree within 89 m (independent), the stored point is 4.15 km away |
| Jordbro Grave Field (`cbc93ea2-6ae5-4be6-a320-254960a60ab7`) | 59.16675, 18.13339 | 59.13194, 18.12269 | 3.92 km | [wikidata](https://www.wikidata.org/wiki/Q10540828) P625 = 59.131944, 18.122694 (precision 2.777777777778e-05)<br>[web:guidebook-sweden.com](https://www.guidebook-sweden.com/en/guidebook/destination/jordbro-gravfaelt-grave-field-jordbro) 59°7′53.7″N 18°7′29.0″E | wikidata and web:guidebook-sweden.com agree within 122 m (independent), the stored point is 3.92 km away |
| Dalj (`62b23da1-7a44-4827-8bdd-bd03ac3157a5`) | 45.48323, 18.95288 | 45.48436, 18.98739 | 2.69 km | [wikidata](https://www.wikidata.org/wiki/Q912341) P625 = 45.484361, 18.987394 (precision 2.77777777778e-06)<br>[web:geonames.org](https://www.geonames.org/3202215/dalj.html) 45.48438, 18.98610 | wikidata and web:geonames.org agree within 101 m (independent), the stored point is 2.69 km away |
| Great Dolmen of Dwasieden (`d3d33b4f-7d75-4ce6-962d-386834c72cab`) | 54.51241, 13.62123 | 54.50210, 13.60910 | 1.39 km | [wikidata](https://www.wikidata.org/wiki/Q575698) P625 = 54.502100, 13.609100 (precision 0.0001)<br>[web:paganplaces.com](https://paganplaces.com/places/great-dolmen-of-dwasieden/) 54.5020817, 13.6069502 | wikidata and web:paganplaces.com agree within 139 m (independent), the stored point is 1.39 km away |
| Karnak Temple Complex (`14c0c237-0ece-4124-ada8-8ec56b431b08`) | 25.71291, 32.64862 | 25.71833, 32.65833 | 1.14 km | [wikidata](https://www.wikidata.org/wiki/Q522862) P625 = 25.718333, 32.658333 (precision 0.0002777777777777778) imported from English Wikipedia<br>[web:ahlfeldt.se](http://imperium.ahlfeldt.se/places/21108.html) 25.7191736, 32.6566111 | wikidata and web:ahlfeldt.se agree within 196 m (independent), the stored point is 1.14 km away |

## How to run it (the orchestrator's job, in this order, after the owner's go)

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/bcases/run.py plan --wave 2     # REHEARSAL.sql is not versioned
$PY scripts/remediation/bcases/run.py check --wave 2    # read-only: every old value still holds
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/bcases/coords_plan_wave2/REHEARSAL.sql
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/bcases/coords_plan_wave2/APPLY.sql
$PY scripts/remediation/bcases/run.py verify --wave 2   # read-only: new values and the journal
```
