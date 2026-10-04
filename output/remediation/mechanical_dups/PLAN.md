# Owner decision O9: five duplicates retired (`dup-retire`): plan

Built 2026-10-01T17:48:50+00:00 by `scripts/remediation/mechanical/dups.py` from the read-only production read of 2026-10-01 17:48:37.993399+00 (`READ.jsonl`). Lane `dup-retire`: run stamp `2026-10-01_mechanical-dup-retire`, journal test id `O9/duplicate-retire`, change keys `dup-retire:<site_id>:<column>`, premise `u.name || ' | ' || 'content links ' || CAST((SELECT count(*) FROM site_content_links c WHERE c.site_id = u.id) AS text) || ', images ' || CAST((SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS text) || ' | ' || coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id), '') || ' | survivor ' || coalesce((SELECT s.name || ' | ' || coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = s.id), '') FROM unified_sites s WHERE CAST(s.id AS text) = CASE CAST(u.id AS text) WHEN 'ae2ca7b1-89da-46cb-8924-f9d04dd5da2e' THEN 'ce7db300-8777-425d-917a-2f6d9f325b58' WHEN '3ebb514f-ac4a-4913-b54b-409bcc29eff4' THEN '51daf6c9-25d3-4818-8857-0543f1203c57' WHEN 'dafc7527-c6c8-45c3-8c7d-4813d20a4dcf' THEN 'd41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d' WHEN 'f23a31c3-6833-4df6-8583-3b3930b5a74f' THEN '21ac323f-7214-4891-9499-74e55c3d7d56' WHEN 'f967e3c4-fc5b-4cd0-91d1-06030d51e31c' THEN '0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3' END), '')`. Decision: `output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, B1-D and B6 (O9, 2026-09-26).

**5 sites, 10 cells.** Nothing is deleted and no country is written (B10).

| retired | cell | old | new |
|---|---|---|---|
| Banias (`ae2ca7b1-89da-46cb-8924-f9d04dd5da2e`) | scope_status | NULL | `retired` |
| Banias (`ae2ca7b1-89da-46cb-8924-f9d04dd5da2e`) | scope_reason | NULL | `duplicate_of:ce7db300-8777-425d-917a-2f6d9f325b58` |
| Ancient Amathunta (`3ebb514f-ac4a-4913-b54b-409bcc29eff4`) | scope_status | NULL | `retired` |
| Ancient Amathunta (`3ebb514f-ac4a-4913-b54b-409bcc29eff4`) | scope_reason | NULL | `duplicate_of:51daf6c9-25d3-4818-8857-0543f1203c57` |
| Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`) | scope_status | NULL | `retired` |
| Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`) | scope_reason | NULL | `duplicate_of:d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d` |
| Thirty-nine (39) Bridge Street, Chester (`f23a31c3-6833-4df6-8583-3b3930b5a74f`) | scope_status | NULL | `retired` |
| Thirty-nine (39) Bridge Street, Chester (`f23a31c3-6833-4df6-8583-3b3930b5a74f`) | scope_reason | NULL | `duplicate_of:21ac323f-7214-4891-9499-74e55c3d7d56` |
| Shaduppum (`f967e3c4-fc5b-4cd0-91d1-06030d51e31c`) | scope_status | NULL | `retired` |
| Shaduppum (`f967e3c4-fc5b-4cd0-91d1-06030d51e31c`) | scope_reason | NULL | `duplicate_of:0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3` |

## What the transaction checks

* guard 1: the row is a curated site
* guard 2: two real changes per row, only in `scope_status` and `scope_reason`
* guard 3: the row still holds the planned old values (both NULL)
* guard 4: the status written is `retired` and nothing else
* guard 5: the row's name, content links, images and external ids, and its survivor's name and external ids, are still as read
* after the write, the survivor its reason names is a curated site, not retired (this write included), and within 2000 m (three checks, each probed with a row of its kind)
* one journal row per cell, and exactly the planned cells moved

## Banias -> Caesarea Philippi (B6)

Retired `ae2ca7b1-89da-46cb-8924-f9d04dd5da2e`, survivor `ce7db300-8777-425d-917a-2f6d9f325b58`: Banias and Caesarea Philippi are one site under its modern and its ancient name: both rows carry Q606295 and the Wikipedia title Banias, which names the Caesarea Philippi of Josephus and the Gospels as the city founded at the Banias spring; the retired row's point is 11 m from Wikipedia's (33.24861, 35.69444), the survivor's 279 m.

* en.wikipedia.org, article 'Banias' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): is a site in the Israeli-occupied Golan Heights, Syria near a natural spring, once associated with the Greek god Pan
* en.wikipedia.org, article 'Banias' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): In 3 BCE, Herod's son, Philip (also known as Philip the Tetrarch) founded a city which became his administrative capital, known from Josephus and the Gospels of Matthew and Mark as Caesarea or Caesarea Philippi
* wikidata:Q606295 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): label 'Banias', description 'archaeological site in the Golan Heights', enwiki sitelink 'Banias'; coordinates 33.2472, 35.6939 and 33.2472, 35.6933
* production: 289.5 m apart; both rows carry wikidata_qid=Q606295 and enwiki_title=Banias

## Ancient Amathunta -> Amathus (B1-D)

Retired `3ebb514f-ac4a-4913-b54b-409bcc29eff4`, survivor `51daf6c9-25d3-4818-8857-0543f1203c57`: both rows are the ancient royal city of Amathus near Agios Tychonas: the one item and the one Wikipedia title, 11 m apart, the same Aphrodite-sanctuary description; 'Amathunta' is the Greek form (Amathounta) of the name. Wikipedia's Amathus article does not list 'Amathunta' as an alias, so the reading rests on the shared item, title and place, not on the name.

* en.wikipedia.org, article 'Amathus' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): Amathus or Amathous (Ancient Greek: Ἀμαθοῦς) was an ancient city-kingdom of Cyprus. [...] Remains of Amathus can be seen today on the southern coast near Agios Tychonas, about 6 miles (9.7 km) east of Limassol and 24 miles (39 km) west of Larnaca
* wikidata:Q2343313 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): label 'Amathus', description 'ancient city and one of the ancient royal cities of Cyprus until about 300 BC.', coordinates 34.7125, 33.1419, enwiki sitelink 'Amathus'
* en.wikipedia.org, article 'Amathounta' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): Amathounta Municipality (Greek: Δήμος Αμαθούντας) is a municipality located in the Limassol District of Cyprus. Headquartered in Agios Athanasios, it is composed of eight municipal districts: Agios Athanasios, Germasogeia, Agios Tychonas, Akrounta, Mathikoloni, Mouttagiaka, Foinikaria, and Armenochori.
* production: 11.3 m apart; both rows carry wikidata_qid=Q2343313 and enwiki_title=Amathus

## Ñusta Hispana -> Conjunto Arqueologico de Ñustahispana (B1-D)

Retired `dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`, survivor `d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d`: both rows are the Inca site Ñusta Hispana (Chuquipalta, with Yurac Rumi) at Vilcabamba: the one item and the one Wikipedia title, 470 m apart, the same description; Wikipedia and Wikidata place the single site at -13.11167, -72.92417, 21 m from the retired row's point and 473 m from the survivor's. The two rows tie on created_at, content links (0), citations (0) and images (20), so the lower id keeps, and the survivor keeps its own name.

* en.wikipedia.org, article 'Ñusta Hispana' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): Ñusta Hispana Ñusta Ispanan (also written Ñusta Ispana), previously known as Chuquipalta (possibly from Quechua chuqi precious metal, p'allta plane) is an archaeological site in Peru. It is located at Vilcabamba, La Convención Province, Cusco Region.
* wikidata:Q13191401 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): label "Ñusta Hisp'ana", description 'archaeological site in Peru', coordinates -13.11167, -72.92417, enwiki sitelink 'Ñusta Hispana'
* production: 468.1 m apart; both rows carry wikidata_qid=Q13191401 and enwiki_title=Ñusta Hispana

## Thirty-nine (39) Bridge Street, Chester -> Bridge Street Number 39, Chester (B1-D)

Retired `f23a31c3-6833-4df6-8583-3b3930b5a74f`, survivor `21ac323f-7214-4891-9499-74e55c3d7d56`: both rows are the one Grade I listed building with a Roman hypocaust in its cellar: the one item and the one Wikipedia title, 14 m apart, the same 27 surviving columns (originally 32 in eight rows). The rows tie on created_at, citations (0) and images (3); the survivor holds 3 content links, the retired row 0.

* en.wikipedia.org, article '39 Bridge Street, Chester' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): 39 Bridge Street is a building in Chester, Cheshire, England. It is recorded in the National Heritage List for England as a designated Grade I listed building, its major archaeological feature being the remains of a Roman hypocaust in its cellar.
* en.wikipedia.org, article '39 Bridge Street, Chester' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): They consist of 27 square columns in a rectangular chamber which originally contained 32 columns in eight rows of four.
* wikidata:Q4636108 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): label '39 Bridge Street, Chester', description 'Grade I listed building in Chester, United Kingdom', coordinates 53.1895, -2.8912, enwiki sitelink '39 Bridge Street, Chester'
* production: 14.0 m apart; both rows carry wikidata_qid=Q4636108 and enwiki_title=39 Bridge Street, Chester

## Shaduppum -> Tel Hermal Fort (B1-D)

Retired `f967e3c4-fc5b-4cd0-91d1-06030d51e31c`, survivor `0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3`: Shaduppum is the ancient name and Tell Harmal / Tel Hermal the modern name of one tell in Baghdad: the one item and the one Wikipedia title, 20 m apart (B1-D's '1,7 km' is not what production holds: Wikipedia's point 33.309483, 44.467065 is the survivor's stored point). The survivor holds 5 content links and 1 citation, the retired row 0 and 0; the retired row's longer text (Gilgamesh tablets, the Laws of Eshnunna) is not merged here.

* en.wikipedia.org, article 'Shaduppum' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): Shaduppum (Šaduppȗm), modern Tell Harmal (also Tell Abu Harmal and Tel Harmal), is an archaeological site in Baghdad Governorate (Iraq). Nowadays, it lies within the borders of modern Baghdad about 600 meters from the site of Tell Muhammad
* en.wikipedia.org, article 'Shaduppum' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): The site, 150 meters in diameter and 5 meters high. Tell Harmal consists of a heavily fortified irregular rectangle
* wikidata:Q3481186 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): label 'Shaduppum', description 'Archaeological site in Baghdad', alias 'Tell Harmal', enwiki sitelink 'Shaduppum'; Wikipedia's coordinates are 33.309483, 44.467065
* production: 20.3 m apart; both rows carry wikidata_qid=Q3481186 and enwiki_title=Shaduppum

## Run

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --check-primitive
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --verify
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --interests
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --emit
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --rehearse
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --apply
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --verify
$PY scripts/remediation/mechanical/apply.py --lane dup-retire --rehearse-rollback
```

Undo, only as a decision: `ROLLBACK.sql` sets the ten cells back to NULL.
