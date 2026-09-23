# Owner-case coordinates - planned, not applied

9 curated sites, 27 journalled changes (geom, lat, lon each), run stamp `2026-09-23_owner-case-coordinates`. Rendered by `scripts/remediation/bcases/coord_plan.py` from the classifier's `move` verdicts: two independent witnesses agree within the tolerance and the stored point lies outside it. **Not applied**: FIELD_CONTRACT section 4.6 reserves coordinate changes for the owner (HUMAN_ONLY B1/B2).

Independent means: neither says it was imported from the other, neither is the other rounded or truncated to the grid its digits are written on (decimals, whole arcseconds or arcminutes), and the two points lie further apart than one arcsecond, one step of either grid and the Wikidata precision (`scripts/remediation/bcases/classify.py`, `independent`).

| site | stored | new | moved | witnesses | reason |
| --- | --- | --- | --- | --- | --- |
| Calakmul (`bc28c81f-db22-46a5-bc4e-18cb8c2ecbec`) | 19.24322, -98.34002 | 18.10500, -89.81056 | 907.27 km | [wikidata](https://www.wikidata.org/wiki/Q272771) P625 = 18.105000, -89.810556 (precision 0.0002777777777777778)<br>[enwiki](https://en.wikipedia.org/wiki/Calakmul) enwiki 'Calakmul' coordinates = 18.10539167, -89.81082778 (given to 8 decimals) | wikidata and enwiki agree within 52 m (independent), the stored point is 907.27 km away |
| Yenikale Ruins (`d6d44645-a99b-4826-85b3-eb0123faadd2`) | 37.95028, 38.65352 | 45.34945, 36.60455 | 840.10 km | [wikidata](https://www.wikidata.org/wiki/Q772781) P625 = 45.349449, 36.604550 (precision 1e-06)<br>[enwiki](https://en.wikipedia.org/wiki/Yeni-Kale) enwiki 'Yeni-Kale' coordinates = 45.34916667, 36.60472222 (given to whole arcseconds) | wikidata and enwiki agree within 34 m (independent), the stored point is 840.10 km away |
| Guyaju Caves (`27330a46-8900-4b3b-9094-1910364284bf`) | 39.88084, 116.32724 | 40.46241, 115.76850 | 80.22 km | [wikidata](https://www.wikidata.org/wiki/Q10913277) P625 = 40.462413, 115.768498 (precision 1e-06)<br>[enwiki](https://en.wikipedia.org/wiki/Guyaju_Caves) enwiki 'Guyaju Caves' coordinates = 40.46555556, 115.76888889 (given to whole arcseconds) | wikidata and enwiki agree within 351 m (independent), the stored point is 80.22 km away |
| Zempoala (`f947a367-a17a-4cb3-9d43-93965c88d3bf`) | 19.26368, -96.24215 | 19.44708, -96.40411 | 26.54 km | [wikidata](https://www.wikidata.org/wiki/Q1053364) P625 = 19.447083, -96.404111 (precision 2.777777777777778e-05)<br>[enwiki](https://en.wikipedia.org/wiki/Cempoala) enwiki 'Cempoala' coordinates = 19.445, -96.40888889 (given to whole arcseconds) | wikidata and enwiki agree within 552 m (independent), the stored point is 26.54 km away |
| Melgunov Kurgan (`b8abad34-a66f-4e08-85e9-9b069301128b`) | 48.54030, 32.41995 | 48.72456, 32.37936 | 20.70 km | [wikidata](https://www.wikidata.org/wiki/Q12122408) P625 = 48.724560, 32.379360 (precision 1e-05)<br>[enwiki](https://en.wikipedia.org/wiki/Melgunov_Kurgan) enwiki 'Melgunov Kurgan' coordinates = 48.72469444, 32.38055556 (given to 8 decimals) | wikidata and enwiki agree within 89 m (independent), the stored point is 20.70 km away |
| Halamata Cave (`84894867-d7b1-49b7-a1e7-398e73a725f2`) | 36.92739, 42.96822 | 36.83818, 42.94082 | 10.21 km | [wikidata](https://www.wikidata.org/wiki/Q106371911) P625 = 36.838181, 42.940816 (precision 1e-05)<br>[enwiki](https://en.wikipedia.org/wiki/Halamata_Cave) enwiki 'Halamata Cave' coordinates = 36.8404006, 42.9450336 (given to 7 decimals) | wikidata and enwiki agree within 449 m (independent), the stored point is 10.21 km away |
| Iskanwaya (`7d1856ba-e68a-4b0a-b3d9-1da34299a6d0`) | -15.47066, -68.67410 | -15.49472, -68.67306 | 2.68 km | [wikidata](https://www.wikidata.org/wiki/Q1674009) P625 = -15.494722, -68.673056 (precision 0.00027777777777778)<br>[enwiki](https://en.wikipedia.org/wiki/Iskanwaya) enwiki 'Iskanwaya' coordinates = -15.486558, -68.674285 (given to 6 decimals) | wikidata and enwiki agree within 917 m (independent), the stored point is 2.68 km away |
| Las Médulas (`c81634b0-969c-484b-aa1f-5b5926e05fd3`) | 42.46955, -6.77073 | 42.45870, -6.75900 | 1.54 km | [wikidata](https://www.wikidata.org/wiki/Q696803) P625 = 42.458699, -6.759002 (precision 1e-06)<br>[enwiki](https://en.wikipedia.org/wiki/Las_Médulas) enwiki 'Las Médulas' coordinates = 42.45888889, -6.76 (given to whole arcseconds) | wikidata and enwiki agree within 85 m (independent), the stored point is 1.54 km away |
| Pamukkale (`c365e1f8-e4bb-43f0-9c46-58497b709fae`) | 37.91394, 29.11860 | 37.92360, 29.12230 | 1.12 km | [wikidata](https://www.wikidata.org/wiki/Q105893254) P625 = 37.923600, 29.122300 (precision 0.0001)<br>[enwiki](https://en.wikipedia.org/wiki/Pamukkale) enwiki 'Pamukkale' coordinates = 37.92388889, 29.12333333 (given to whole arcseconds) | wikidata and enwiki agree within 96 m (independent), the stored point is 1.12 km away |

## How to run it (the orchestrator's job, in this order, after the owner's go)

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/bcases/run.py plan     # REHEARSAL.sql is not versioned
$PY scripts/remediation/bcases/run.py check    # read-only: every old value still holds
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/bcases/coords_plan/REHEARSAL.sql
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" < output/remediation/bcases/coords_plan/APPLY.sql
$PY scripts/remediation/bcases/run.py verify   # read-only: new values and the journal
```
