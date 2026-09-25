# Dangling citation markers - plan (dangling-markers)

Built 2026-09-25T17:45:15+00:00 by `scripts/remediation/mechanical/dangling_markers.py` from the export read at 2026-09-25 17:44:59.80949+00 (`export/export.jsonl`, sha256 5568ad6d0c55f1208680a7bd03011fe12329926e5c5294cc9ae896a9a88a203a). Lane `dangling-markers`: run stamp `2026-09-25_mechanical-dangling-markers`, journal test id `T08/dangling-markers`, change keys `dangling-markers:<site_id>:<column>`. The premise (guard 5) is `coalesce((u.raw_data -> '_description_provenance') - 'desc_sha256', 'null'::jsonb)::text`.

D1 (`acceptance/checks.py`) over **5004** curated rows: holds on 5001, fails on **3**. **3 site(s), 6 cell(s) will be written**, **0 listed**. The decision is HUMAN_ONLY.md D9 option (b), the owner's order of 2026-09-25: a marker that points to no source leaves the text, the claims stay under lane L's generated marking. D1 and D4 hold on every planned value (`build`).

## Written

### Killa Mach'ay (`867f08af-8934-4ec0-bbcc-2c730bb2a93a`)

* `description` (`dangling-markers-removed`): the description cites [4] with no entry (entries [1, 2, 3]): [4] x1 removed, the space before a marker run only with the run's last marker; every other character stays, and the claims stay under lane L's generated marking (HUMAN_ONLY.md D9 option (b), the owner's order of 2026-09-25)
* `raw_data` (`provenance-hash-and-uncited-entries`): _description_provenance.desc_sha256 7cebb94d2ab717f79655e9f1085381c583b31c3c89df35e337e081c146d11fe8 -> e3af2533ce5ee217158e5d96d5ce2bfbecd519a14f0ed94c261fe97482ca493c, the sha256 of the new description (D4); entry [2] cited by no marker once the dangling markers are gone removed (the orphan-citations rule); every other raw_data key stays as it is

Old: Killa Mach'ay is a rock art site in Peru's Central Highlands, featuring caves with pre-Hispanic paintings and petroglyphs. The artwork includes depictions of llamas, anthropomorphic figures, and abstract linear motifs carved into rock shelters at 3,400 m elevation in Huancavelica Region [1][3][4].

New: Killa Mach'ay is a rock art site in Peru's Central Highlands, featuring caves with pre-Hispanic paintings and petroglyphs. The artwork includes depictions of llamas, anthropomorphic figures, and abstract linear motifs carved into rock shelters at 3,400 m elevation in Huancavelica Region [1][3].

### Afrodit Tapınağı (`c0e10d6e-fb0e-4e9c-a910-631da9e578ea`)

* `description` (`dangling-markers-removed`): the description cites [2] with no entry (entries [1]): [2] x3 removed, the space before a marker run only with the run's last marker; every other character stays, and the claims stay under lane L's generated marking (HUMAN_ONLY.md D9 option (b), the owner's order of 2026-09-25)
* `raw_data` (`provenance-hash`): _description_provenance.desc_sha256 0ce01601be5b3a9eda6e11c881ef6815a06c13a2173e653b88be00afa03e3fc4 -> 889e849441394a473168424add928dec6e687dc4cc27ee74bc4294eba1050389, the sha256 of the new description (D4); description_citations unchanged; every other raw_data key stays as it is

Old: The Temple of Aphrodite at Aphrodisias, an ancient Greek city in southwestern Turkey inscribed as a UNESCO World Heritage Site in 2017 [1]. The temple dates to the 3rd century BC and anchored a cult combining Anatolian fertility goddess traditions with Hellenic Aphrodite worship [2]. The city flourished from the 2nd century BC through the 6th century AD, famed for its marble sculptors whose work was prized across the Roman Empire [2]. Major structures include a stadium, theatre, agora, and baths. Nearby marble quarries supplied the city's renowned sculpture workshops [1]. The temple was converted to a Christian church around 500 AD [2].

New: The Temple of Aphrodite at Aphrodisias, an ancient Greek city in southwestern Turkey inscribed as a UNESCO World Heritage Site in 2017 [1]. The temple dates to the 3rd century BC and anchored a cult combining Anatolian fertility goddess traditions with Hellenic Aphrodite worship. The city flourished from the 2nd century BC through the 6th century AD, famed for its marble sculptors whose work was prized across the Roman Empire. Major structures include a stadium, theatre, agora, and baths. Nearby marble quarries supplied the city's renowned sculpture workshops [1]. The temple was converted to a Christian church around 500 AD.

### A Figa (`fe4edbed-be84-4b80-b5de-62ab3e4c88ef`)

* `description` (`dangling-markers-removed`): the description cites [2], [3], [4] with no entry (entries [1]): [2] x1, [3] x3, [4] x1 removed, the space before a marker run only with the run's last marker; every other character stays, and the claims stay under lane L's generated marking (HUMAN_ONLY.md D9 option (b), the owner's order of 2026-09-25)
* `raw_data` (`provenance-hash`): _description_provenance.desc_sha256 814e294710b8bd01eacc1108cb7c1a3852620137d0de27ea8645a3f2892c4b37 -> c63321ecfa559f6b1c38330ab7848d62702a0fb4a8f454c192c4765f3419e735, the sha256 of the new description (D4); description_citations unchanged; every other raw_data key stays as it is

Old: A Figa (Corsican for "The Fig") is a Middle Neolithic rock shelter near Punta di Murtoli in the commune of Sartene, southern Corsica [1]. Radiocarbon dating places its primary occupation around 4300-4200 BCE [2]. Excavations yielded fine ceramics, flint and obsidian tools, and abundant shellfish and mammal remains, indicating specialized coastal resource exploitation [3]. Evidence of significantly reduced limpet and periwinkle sizes suggests intensive harvesting pressure on the marine environment [3]. The site also contains Iron Age occupation layers [3]. Cataloged in a 1995 survey of 119 prehistoric sites across the canton of Sartene led by Franck Leandri [4].

New: A Figa (Corsican for "The Fig") is a Middle Neolithic rock shelter near Punta di Murtoli in the commune of Sartene, southern Corsica [1]. Radiocarbon dating places its primary occupation around 4300-4200 BCE. Excavations yielded fine ceramics, flint and obsidian tools, and abundant shellfish and mammal remains, indicating specialized coastal resource exploitation. Evidence of significantly reduced limpet and periwinkle sizes suggests intensive harvesting pressure on the marine environment. The site also contains Iron Age occupation layers. Cataloged in a 1995 survey of 119 prehistoric sites across the canton of Sartene led by Franck Leandri.

## Listed, not written

| reason | sites | what it means |
|---|---|---|

None: every site D1 fails on is written.

## After the apply

Lane L's acceptance reads the raw_data rows this lane rewrote as superseded once it is told the stamp (`verify_writes4.py --lane p4l ... --allow-stamp '2026-09-25_mechanical-dangling-markers'`). The SSR page and the API read the database; the static export, the Qdrant resync and IndexNow of the Phase-6 runbook carry the new texts out. The next card_stats wave's premise reads `md5(description)` of these sites.
