# Wrong-both corrections - plan (wrong-both)

Built 2026-09-25T06:45:12+00:00 by `scripts/remediation/mechanical/wrong_both.py` from `output/remediation/opus_audit/DECISIONS.jsonl` (sha256 a1f5cb87f2f6d5622a1762be96f2b62d9eecc9f6ac37b19f5d732175b845ae04). Lane `wrong-both`: run stamp `2026-09-25_mechanical-wrong-both`, journal test id `P6/wrong-both`, change keys `wrong-both:<site_id>:<column>`.

**17 cell(s) will be written** - 13 correction(s) and 4 period label(s) - **29 of 42 candidate(s) are listed, not written.** A candidate is a row the audit decided whose route carries a wrong-both verdict. Each write is conditioned on the live value being the old value journal-reversal-3 restored (guard 3).

The rules, the first failure listing the row, are in the module's docstring: (a) the old
value is live, restored by journal-reversal-3; (b) every counted judge that names a value
names this one; (c) the value is valid for its field; (d) a quote of a counted verdict,
found by the audit's machine check, states the value in text about the site.

## Written

### Labna - `period_start` 500 -> -200

Site `042c8c7f-1ec1-485a-ba0b-3ab847320ee7`. the Opus re-verification's judges name '-200' for period_start (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35637: 2026-09-25_mechanical-journal-reversal-3: period_start '200' -> '500' - the reversal of the judged write, which this correction follows
* opus:phase3:b35482d038b3a26e27b415fcd25d6e37e7a689162a03a4acc26b0a6838216fbc: decision 'revert'; p1 wrong-both names '-200' (VERDICTS_RAW.json p1); p2 wrong-both names '-200' (VERDICTS_RAW.json p2)
* https://lugares.inah.gob.mx/es/node/4427: El sitio estuvo poblado desde el año 200 a.C. y alcanzó su apogeo entre el año 800 y el 1000.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states '200 a.C.'; it is about the site: 'labna' stands within 1,500 characters of it on the page

### Labna - `period_name` 500 - 1000 AD -> 500 BC - 1 AD

Site `042c8c7f-1ec1-485a-ba0b-3ab847320ee7`. period_name follows period_start -200 (the period-name lane's rule).

* pipeline/utils/text.py:categorize_period: categorize_period(-200) = '500 BC - 1 AD' - the period_start this correction writes; the frontend's categorizePeriod agrees

### Cissbury Ring - `period_start` -1500 -> -3700

Site `06a73089-340c-40ac-9979-4a5c08f93da5`. the Opus re-verification's judges name '-3700' for period_start (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35641: 2026-09-25_mechanical-journal-reversal-3: period_start '-250' -> '-1500' - the reversal of the judged write, which this correction follows
* opus:phase3:517c19523ffb7ebfe45b4789fa336e81201ace197e6ec744a76a4b1f80b777c7: decision 'revert'; p1 wrong-both names '-3700' (VERDICTS_RAW.json p1); p2 wrong-both names '-3700' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0025/evidence/06a73089-340c-40ac-9979-4a5c08f93da5%2Fenwiki.txt: This individual was recently radiocarbon dated to c. 3700 BC.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states '3700 BC'; it is about the site: an evidence file of the row (fetched for this site)

### Cissbury Ring - `period_name` 1500 - 500 BC -> 4500 - 3000 BC

Site `06a73089-340c-40ac-9979-4a5c08f93da5`. period_name follows period_start -3700 (the period-name lane's rule).

* pipeline/utils/text.py:categorize_period: categorize_period(-3700) = '4500 - 3000 BC' - the period_start this correction writes; the frontend's categorizePeriod agrees

### Castleshaw Roman Fort - `site_type` Fortress/citadel -> Fort

Site `16edc297-75f0-471e-a82a-fc3dc46d6c8f`. the Opus re-verification's judges name 'Fort' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35667: 2026-09-25_mechanical-journal-reversal-3: site_type 'Fortification' -> 'Fortress/citadel' - the reversal of the judged write, which this correction follows
* opus:phase3:db882adf65dde0bc5c3e42cea8d7223d6d361f3152d9818f0eddeb287a832d18: decision 'revert'; p1 revert (VERDICTS_RAW.json p1); p2 wrong-both names 'Fort' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0106/evidence/16edc297-75f0-471e-a82a-fc3dc46d6c8f%2Fenwiki.txt: Castleshaw Roman fort was a castellum in the Roman province of Britannia.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'fort'; it is about the site: an evidence file of the row (fetched for this site)

### Bull of the Corcyreans - `site_type` Megalithic structures -> Monument

Site `563693f3-5fa9-485d-940f-66f26210a9f4`. the Opus re-verification's judges name 'Monument' for site_type (RULES.md rule 5), and a verbatim quote of p2 states it.

* remediation_change_log:35777: 2026-09-25_mechanical-journal-reversal-3: site_type 'Sculptured stone' -> 'Megalithic structures' - the reversal of the judged write, which this correction follows
* opus:phase3:c7311febe701cebe6ff7e297839bc18e66f012d6461f4e666408f50a5f183ab2: decision 'revert'; p1 wrong-both names 'Monument' (VERDICTS_RAW.json p1); p2 wrong-both names 'Monument' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0144/evidence/563693f3-5fa9-485d-940f-66f26210a9f4%2Fenwiki.txt: The statue was made by the sculptor Theopropus from Aegina.
* mechanical/wrong_both.py:states: the quote of p2 (VERDICTS_RAW.json p2), found by the audit's machine check, states 'statue'; it is about the site: an evidence file of the row (fetched for this site)

### Amphitheatre Alba Fucens - `site_type` Megalithic structures -> Amphitheatre

Site `5fc47cd7-e750-44fe-bb29-da865affed4d`. the Opus re-verification's judges name 'Amphitheatre' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35787: 2026-09-25_mechanical-journal-reversal-3: site_type 'City/town/settlement' -> 'Megalithic structures' - the reversal of the judged write, which this correction follows
* opus:phase3:8f11bb9ef2df1a8bbf0864b25e13686ff2669b9bc054a6ebd990ca8f404446ff: decision 'revert'; p1 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p1); p2 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p2)
* https://en.wikipedia.org/wiki/Alba_Fucens: The well-preserved amphitheatre (96 x 79 m) from the reign of Tiberius was built by the Prefect of the Praetorium Nevius Sutorius Macro, born in Alba.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'amphitheatre'; it is about the site: 'alba' stands within 1,500 characters of it on the page

### El Jem Amphitheatre - `site_type` Megalithic stones -> Amphitheatre

Site `62e7aef7-f914-4080-ae06-b4c347600d6d`. the Opus re-verification's judges name 'Amphitheatre' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35792: 2026-09-25_mechanical-journal-reversal-3: site_type 'Theatre' -> 'Megalithic stones' - the reversal of the judged write, which this correction follows
* opus:phase3:c5046a20b782074ecefc22644f2004d8bdf6514a567f90046e252bc8d0ef9023: decision 'revert'; p1 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p1); p2 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0079/evidence/62e7aef7-f914-4080-ae06-b4c347600d6d%2Fwikidata_entity.txt: Roman amphitheatre of El Jem
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'amphitheatre'; it is about the site: an evidence file of the row (fetched for this site)

### Amphitheatre of the Three Gauls - `site_type` Megalithic structures -> Amphitheatre

Site `65050d8b-7a91-4121-8384-84e4b7cea557`. the Opus re-verification's judges name 'Amphitheatre' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35802: 2026-09-25_mechanical-journal-reversal-3: site_type 'Theatre' -> 'Megalithic structures' - the reversal of the judged write, which this correction follows
* opus:phase3:c087b2af14ea704ffa22dbd65444727156dc1db00d6979a5371b59eff67625b0: decision 'revert'; p1 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p1); p2 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0155/evidence/65050d8b-7a91-4121-8384-84e4b7cea557%2Fwikidata_entity.txt: Roman amphitheatre in France
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'amphitheatre'; it is about the site: an evidence file of the row (fetched for this site)

### Sturminster Newton Castle - `site_type` Residence/villa/farmhouse -> Fort

Site `761f4227-befb-435c-b967-9ebd61c06f8f`. the Opus re-verification's judges name 'Fort' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35837: 2026-09-25_mechanical-journal-reversal-3: site_type 'Castle/palace' -> 'Residence/villa/farmhouse' - the reversal of the judged write, which this correction follows
* opus:phase3:41b4489240eb9e91c2e3a8285662aa8b945417bbcf4b0c7ba6b6de9b9b71a212: decision 'revert'; p1 wrong-both names 'Fort' (VERDICTS_RAW.json p1); p2 wrong-both names 'Fort' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0086/evidence/761f4227-befb-435c-b967-9ebd61c06f8f%2Fenwiki.txt: The medieval ruins are within the earthwork remains of an Iron Age promontory fort.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'fort'; it is about the site: an evidence file of the row (fetched for this site)

### Caerau Hillfort - `period_start` -1500 -> -3600

Site `92d26614-c2fb-4b94-9342-99a5bd2407ab`. the Opus re-verification's judges name '-3600' for period_start (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35883: 2026-09-25_mechanical-journal-reversal-3: period_start '-600' -> '-1500' - the reversal of the judged write, which this correction follows
* opus:phase3:4404e5061070dcfbb49a7bb46cb781f60671e9f471ad029116688049032a2c5f: decision 'revert'; p1 wrong-both names '-3600' (VERDICTS_RAW.json p1); p2 wrong-both names '-3600' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0185/evidence/92d26614-c2fb-4b94-9342-99a5bd2407ab%2Fenwiki.txt: revealed evidence of the site's occupation back to the early Neolithic. Finds included flint tools and weapons dating to 3600 BC.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states '3600 BC'; it is about the site: an evidence file of the row (fetched for this site)

### Caerau Hillfort - `period_name` 1500 - 500 BC -> 4500 - 3000 BC

Site `92d26614-c2fb-4b94-9342-99a5bd2407ab`. period_name follows period_start -3600 (the period-name lane's rule).

* pipeline/utils/text.py:categorize_period: categorize_period(-3600) = '4500 - 3000 BC' - the period_start this correction writes; the frontend's categorizePeriod agrees

### Siphnian Treasury - `site_type` Megalithic structures -> Religious

Site `9624278c-1080-4a2a-ae2e-11829bda299a`. the Opus re-verification's judges name 'Religious' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35891: 2026-09-25_mechanical-journal-reversal-3: site_type 'Treasury' -> 'Megalithic structures' - the reversal of the judged write, which this correction follows
* opus:phase3:f8f7dfdef8df9bb308fba2d0210d920a9278a3fa106522c997017a9d34c238cc: decision 'revert'; p1 wrong-both names 'Religious' (VERDICTS_RAW.json p1); p2 wrong-both names 'Religious' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0213/evidence/9624278c-1080-4a2a-ae2e-11829bda299a%2Fenwiki.txt: the first religious structure made entirely out of marble
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'religious'; it is about the site: an evidence file of the row (fetched for this site)

### Sagaholm - `site_type` Cemetery -> Barrow

Site `abe8f81a-dcdb-42b8-9f99-a763c858fd7f`. the Opus re-verification's judges name 'Barrow' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:35941: 2026-09-25_mechanical-journal-reversal-3: site_type 'Cairn' -> 'Cemetery' - the reversal of the judged write, which this correction follows
* opus:phase3:af99288a43e790b5c7ccf87176e69a8c8fb04db1c01926e7253cd81dd4592231: decision 'revert'; p1 wrong-both names 'Barrow' (VERDICTS_RAW.json p1); p2 wrong-both names 'Barrow' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0287/evidence/abe8f81a-dcdb-42b8-9f99-a763c858fd7f%2Fenwiki.txt: had a large barrow with a circle of slabs of sandstone, probably numbering as many as 100.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'barrow'; it is about the site: an evidence file of the row (fetched for this site)

### Piddington Roman Villa - `period_start` -3000 -> -50

Site `c70f123f-bf31-4408-8204-1b8ef717e0dd`. the Opus re-verification's judges name '-50' for period_start (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:36002: 2026-09-25_mechanical-journal-reversal-3: period_start '-3500' -> '-3000' - the reversal of the judged write, which this correction follows
* opus:phase3:4ca3148009d955fcb383d7b158e43c2190ecef86116ca3b77d2d194b2fb91fec: decision 'revert'; p1 wrong-both names '-50' (VERDICTS_RAW.json p1); p2 wrong-both names '-50' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0203/evidence/c70f123f-bf31-4408-8204-1b8ef717e0dd%2Fenwiki.txt: The site was occupied from about 50 BC, with circular buildings followed by a proto-villa of ca.70 AD
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states '50 BC'; it is about the site: an evidence file of the row (fetched for this site)

### Piddington Roman Villa - `period_name` 3000 - 1500 BC -> 500 BC - 1 AD

Site `c70f123f-bf31-4408-8204-1b8ef717e0dd`. period_name follows period_start -50 (the period-name lane's rule).

* pipeline/utils/text.py:categorize_period: categorize_period(-50) = '500 BC - 1 AD' - the period_start this correction writes; the frontend's categorizePeriod agrees

### Arles Amphitheatre - `site_type` Megalithic structures -> Amphitheatre

Site `fbd17b3c-3aed-48d2-8682-df610a98a31c`. the Opus re-verification's judges name 'Amphitheatre' for site_type (RULES.md rule 5), and a verbatim quote of p1 states it.

* remediation_change_log:36105: 2026-09-25_mechanical-journal-reversal-3: site_type 'Theatre' -> 'Megalithic structures' - the reversal of the judged write, which this correction follows
* opus:phase3:e16c2d42247ba83dca7224c52a23e908fe601d52b35406ee75783786db1a5f01: decision 'revert'; p1 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p1); p2 wrong-both names 'Amphitheatre' (VERDICTS_RAW.json p2)
* output/remediation/phase3_runner/runs/mass/batch-0297/evidence/fbd17b3c-3aed-48d2-8682-df610a98a31c%2Fenwiki.txt: is a Roman amphitheatre in Arles, southern France.
* mechanical/wrong_both.py:states: the quote of p1 (VERDICTS_RAW.json p1), found by the audit's machine check, states 'amphitheatre'; it is about the site: an evidence file of the row (fetched for this site)

## Listed, not written

| reason | rows | what it means |
|---|---|---|
| `judges-disagree` | 8 | the counted judges name more than one value |
| `no-verbatim-evidence` | 13 | no found quote of a counted judge states the value in text about the site - for a human |
| `not-restored-by-journal-reversal-3` | 6 | the cell's last write is not journal-reversal-3 restoring the old value (superseded rows: another lane wrote the cell) |
| `not-reverted` | 2 | the audit's final decision kept the written value |

* Sidi Said `site_type` Archaeological site -> proposal None: `not-reverted` - the audit's final decision is 'keep': the written value stands
* Moylehid `country` Northern Ireland -> proposal Northern Ireland: `not-restored-by-journal-reversal-3` - the cell's last write is journal row 30794 (2026-09-22_mechanical-uk-parts), not journal-reversal-3 restoring 'Ireland' over 'United Kingdom'
* Argura `period_start` -1500 -> proposal -6300: `no-verbatim-evidence` - 1 counted quote(s) state '-6300', but none in text about the site (no word of 'Argura' within 1,500 characters on the page): https://en.wikipedia.org/wiki/Sesklo
* Nine Ladies Stone Circle `period_start` -4500 -> proposal -2500: `no-verbatim-evidence` - 2 counted quote(s) state '-2500', but none in text about the site (no word of 'Nine Ladies Stone Circle' within 1,500 characters on the page): https://en.wikipedia.org/wiki/Bronze_Age_Britain
* Aquae Calidae, Bulgaria `period_start` 1 -> proposal -500: `no-verbatim-evidence` - no counted quote states '-500' (the audit's found quotes, read by `states`)
* Palaestra at Delphi `site_type` Megalithic structures -> proposal Archaeological site: `no-verbatim-evidence` - no counted quote states 'Archaeological site' (the audit's found quotes, read by `states`)
* Carteia `period_start` -3000 -> proposal -400: `no-verbatim-evidence` - no counted quote states '-400' (the audit's found quotes, read by `states`)
* Nine Stones, Winterbourne Abbas `period_start` -4500 -> proposal None: `judges-disagree` - the counted judges name '-2000' (p1), '-2500' (p2)
* Alvastra Pile-Dwelling `site_type` City/town/settlement -> proposal None: `judges-disagree` - the counted judges name 'City/town/settlement' (p1), 'Sacred site' (p2)
* Annadorn Dolmen `country` Northern Ireland -> proposal Northern Ireland: `not-restored-by-journal-reversal-3` - the cell's last write is journal row 30798 (2026-09-22_mechanical-uk-parts), not journal-reversal-3 restoring 'Ireland' over 'United Kingdom'
* Chanhudaro `period_start` -4500 -> proposal None: `judges-disagree` - the counted judges name '-2500' (p1), '-3000' (p2)
* Choquequirao `period_start` 1000 -> proposal None: `judges-disagree` - the counted judges name '1000' (p1), '1450' (p2)
* Altar of Athena Polias `site_type` Megalithic structures -> proposal None: `judges-disagree` - the counted judges name 'Sanctuary' (p1), 'Religious' (p2)
* Península de Kola `site_type` City/town/settlement -> proposal None: `judges-disagree` - the counted judges name 'Natural feature' (p1), 'Archaeological site' (p2/tie)
* Gårdstånga `period_start` -4500 -> proposal -1750: `no-verbatim-evidence` - 1 counted quote(s) state '-1750', but none in text about the site (no word of 'Gårdstånga' within 1,500 characters on the page): https://en.wikipedia.org/wiki/Nordic_Bronze_Age
* Boeotian Treasury `site_type` Megalithic structures -> proposal Religious: `no-verbatim-evidence` - 1 counted quote(s) state 'Religious', but none in text about the site (no word of 'Boeotian Treasury' within 1,500 characters on the page): https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1239455&props=labels%7Cdescriptions&languages=en&format=json
* Holyhead Mountain Hut Circles `period_start` -2000 -> proposal -500: `no-verbatim-evidence` - no counted quote states '-500' (the audit's found quotes, read by `states`)
* Lalibela `period_start` -500 -> proposal 900: `no-verbatim-evidence` - no counted quote states '900' (the audit's found quotes, read by `states`)
* South Stoa I, Athens `site_type` Megalithic structures -> proposal None: `judges-disagree` - the counted judges name 'Infrastructure' (p1), 'Ruin' (p2), 'Monument' (tie)
* Cnidian Treasury `site_type` Megalithic structures -> proposal Religious: `no-verbatim-evidence` - no counted quote states 'Religious' (the audit's found quotes, read by `states`)
* Cave of Aurignac `period_start` -500 -> proposal -33000: `no-verbatim-evidence` - no counted quote states '-33000' (the audit's found quotes, read by `states`)
* Pampas Gramalote `period_start` -3000 -> proposal None: `judges-disagree` - the counted judges name '-2000' (p1), '-1500' (p2/tie)
* Wichqana `site_type` Archaeological site -> proposal Temple complex: `not-reverted` - the audit's final decision is 'keep': the written value stands
* Stoa Poikile `site_type` Megalithic stones -> proposal Monument: `no-verbatim-evidence` - no counted quote states 'Monument' (the audit's found quotes, read by `states`)
* Witham Shield `site_type` City/town/settlement -> proposal Archaeological site: `not-restored-by-journal-reversal-3` - the cell's last write is journal row 29739 (2026-09-22_mechanical-site-type-shape), not journal-reversal-3 restoring 'City/town/settlement' over 'suspect_modern'
* Giant's Ring `country` Northern Ireland -> proposal Northern Ireland: `not-restored-by-journal-reversal-3` - the cell's last write is journal row 30807 (2026-09-22_mechanical-uk-parts), not journal-reversal-3 restoring 'Ireland' over 'United Kingdom'
* Maa Palaeokastro `period_start` -3000 -> proposal -3800: `no-verbatim-evidence` - 2 counted quote(s) state '-3800', but none in text about the site (no word of 'Maa Palaeokastro' within 1,500 characters on the page): https://en.wikipedia.org/wiki/Yeronisos
* Dooey's Cairn `country` Northern Ireland -> proposal Northern Ireland: `not-restored-by-journal-reversal-3` - the cell's last write is journal row 30812 (2026-09-22_mechanical-uk-parts), not journal-reversal-3 restoring 'Ireland' over 'United Kingdom'
* Craigs Dolmen `country` Northern Ireland -> proposal Northern Ireland: `not-restored-by-journal-reversal-3` - the cell's last write is journal row 30814 (2026-09-22_mechanical-uk-parts), not journal-reversal-3 restoring 'Ireland' over 'United Kingdom'

## After the apply

The phase-3 acceptance reads these cells as superseded once it is told the stamp: `verify_writes.py --allow-stamp 2026-09-25_mechanical-wrong-both`, with the stamps applied before it. Re-plan the scope lane and the card_stats recompute afterwards: the scope premise and the cards derive from these columns.
