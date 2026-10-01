# Two renames of 2026-10-01 (`name-fix`): plan

Built 2026-10-01T09:53:10+00:00 by `scripts/remediation/mechanical/name_fix.py` from the read-only production read of 2026-10-01 09:53:10.200573+00 (`READ.jsonl`). Lane `name-fix`: run stamp `2026-10-01_mechanical-name-fix`, journal test id `B1/name-fix`, change keys `name-fix:<site_id>:<column>`, premise `coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id), '')`. Decision: owner order 2026-10-01: Wikipedia/Wikidata suffice as the one source.

**2 sites, 4 cells.**

| site | cell | old | new |
|---|---|---|---|
| 'Temple of Augustus, Split' (`4a07cc38-1b55-4254-b0ad-fe875310caf7`) | name | `'Temple of Augustus, Split'` | `Temple of Augustus, Pula` |
| 'Temple of Augustus, Split' (`4a07cc38-1b55-4254-b0ad-fe875310caf7`) | name_normalized | `'temple of augustus, split'` | `temple of augustus, pula` |
| 'Gate of All Nations\u200c Persepolis' (`f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c`) | name | `'Gate of All Nations\u200c Persepolis'` | `Gate of All Nations` |
| 'Gate of All Nations\u200c Persepolis' (`f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c`) | name_normalized | `'gate of all nations\u200c persepolis'` | `gate of all nations` |

## What the transaction checks

* guard 1: the row is a curated site
* guard 2: real changes, only in `name` and `name_normalized`, each within 500 characters
* guard 3: the row still holds the planned old name and its key
* guard 5: the site's external ids are still the ones the new name was read from
* invariant 3: the key written is the key Postgres derives from the name written
* one journal row per cell, and exactly the planned cells moved

## Temple of Augustus, Pula (`4a07cc38-1b55-4254-b0ad-fe875310caf7`)

the stored name puts the Pula temple in Split: the row's own Wikipedia title and Wikidata item (Q770030) are the temple of Pula, its description and its point are Pula's, and no Temple of Augustus is known in Split

* en.wikipedia.org, article 'Temple of Augustus, Pula' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): The Temple of Augustus (Croatian: Augustov hram; Italian: Tempio di Augusto) is a well-preserved Roman temple in the city of Pula, Croatia
* wikidata:Q770030 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): label 'Temple of Augustus', description 'Roman temple in Pula, Croatia', coordinate location 44.8702, 13.84185; the site's stored point 44.87026, 13.84220 is 28 m from it
* wikidata search 'Temple of Augustus' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): ten items named for a Temple of Augustus (Pula, Barcelona, Ankara, Vienne, Philae, Antioch in Pisidia, Cartagena, Rome, Nimes, Leptis Magna), none in Split

## Gate of All Nations (`f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c`)

the stored name carries a U+200C between 'Nations' and 'Persepolis'; the monument's own name - its Wikipedia title and Wikidata label - is 'Gate of All Nations', as the curated siblings at Persepolis are named without the place

* en.wikipedia.org, article 'Gate of All Nations' (read 2026-10-01 through the public MediaWiki and Wikidata APIs): also known as the Gate of Xerxes, is located in the ruins of the ancient city of Persepolis, Iran.
* wikidata:Q5527015 (read 2026-10-01 through the public MediaWiki and Wikidata APIs): English label 'Gate of All Nations'; enwiki sitelink 'Gate of All Nations'

## Run

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/apply.py --lane name-fix --check-primitive
$PY scripts/remediation/mechanical/apply.py --lane name-fix --verify
$PY scripts/remediation/mechanical/apply.py --lane name-fix --interests
$PY scripts/remediation/mechanical/apply.py --lane name-fix --emit
$PY scripts/remediation/mechanical/apply.py --lane name-fix --rehearse
$PY scripts/remediation/mechanical/apply.py --lane name-fix --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane name-fix --apply
$PY scripts/remediation/mechanical/apply.py --lane name-fix --verify
$PY scripts/remediation/mechanical/apply.py --lane name-fix --rehearse-rollback
```

Undo, only as a decision: `ROLLBACK.sql` restores both old names and keys. Lyra's next boot adds each new name to `unified_site_names` as a `label` row (the old name stays there, so an exact search finds both).
