# Journal reversal - plan (journal-reversal-2)

Built 2026-09-23T17:16:39+00:00 by `scripts/remediation/mechanical/reversal.py`. Lane `journal-reversal-2`: run stamp `2026-09-23_mechanical-journal-reversal-2`, journal test id `P6/journal-reversal-2`, change keys `journal-reversal-2:<site_id>:<column>`.

**53 cell(s) will be written, 0 refused.** Each restores the value a journal row replaced, conditioned on the live value being the value that row wrote, and on that row being the last write of its cell (guard 6).

## Appolonia Temple Ruins - `site_type` Settlement -> Temple complex

Site `3f170e16-175a-4e4c-9717-1f0e32d05e8e`, journal row 27752.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read, identity: the record is named for the temple ruins; the linked item is the city of Apollonia - a Settlement type changes what the record is (B1).

* remediation_change_log:27752: phase3:batch-0002:chunk-0002 (P3/site_type): site_type 'Temple complex' -> 'Settlement' - the write this row undoes
* rereview:phase3:f8cfd1fc0eb1b3d00004bba3841f217ee495a790e385a1b933e630b5fa185da1: hand-read, identity: the record is named for the temple ruins; the linked item is the city of Apollonia - a Settlement type changes what the record is (B1)
* rereview:phase3:f8cfd1fc0eb1b3d00004bba3841f217ee495a790e385a1b933e630b5fa185da1: The Wikidata entity (Q15183441) is described as an "ancient city of Lycia" with P31 = archaeological site and human settlement, so the stored "Temple complex" is not supported and "Settlement" is consistent with the evidence — both halves hold.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Banwolseong - `period_start` -57 -> 1

Site `8cead41d-19f8-45cf-9dc0-144583641e4f`, journal row 27924.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read: the evidence's 57 BCE-938 CE is the Silla kingdom's span, not the palace's start; the stored 1-500 AD bucket is not shown wrong.

* remediation_change_log:27924: phase3:batch-0031:chunk-0001 (P3/period_start): period_start '1' -> '-57' - the write this row undoes
* rereview:phase3:2b9daf737a30bf69496c92616bdc2110ab8549ce6bbd6f556f694e5520e9e07e: hand-read: the evidence's 57 BCE-938 CE is the Silla kingdom's span, not the palace's start; the stored 1-500 AD bucket is not shown wrong
* rereview:phase3:2b9daf737a30bf69496c92616bdc2110ab8549ce6bbd6f556f694e5520e9e07e: Both halves hold — the 57 BCE–938 CE span is the period of use of a Silla royal palace whose founding is placed in the mid-1st century (King Pasa, 4–24) or later 4th century, i.e. far outside the stored `1`–500 CE bucket, and the proposed `-57` base date is supported by that same span.
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD', categorize_period(-57) = '500 BC - 1 AD' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Presa-Tusiu - `site_type` Archaeological site -> Settlement

Site `cb688193-2ff5-4535-b1a7-af488587a451`, journal row 28004.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: WHY names a failing half: 'neither half holds'.

* remediation_change_log:28004: phase3:batch-0049:chunk-0003 (P3/site_type): site_type 'Settlement' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:43b91d4e7809abf0d60c67502eaabcb9e1390e797d68abee8c3eaeab36f89e81: WHY names a failing half: 'neither half holds'
* rereview:phase3:43b91d4e7809abf0d60c67502eaabcb9e1390e797d68abee8c3eaeab36f89e81: Neither half holds - the enwiki extract calls it an archaeological site, and Wikidata P31 (Q839954) is exactly "archaeological site", which does not describe a Settlement.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Annaghmare Court Tomb - `site_type` Megalithic structures -> Cairn

Site `3e7d6ad9-37c8-4899-9956-99088ff63c78`, journal row 28092.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28092: phase3:batch-0070:chunk-0001 (P3/site_type): site_type 'Cairn' -> 'Megalithic structures' - the write this row undoes
* rereview:phase3:a04fac3f8b8cb4984118d7c878e87b8fe251a816dc8ea2f4fbb66b5eedbb21a0: refuted
* rereview:phase3:a04fac3f8b8cb4984118d7c878e87b8fe251a816dc8ea2f4fbb66b5eedbb21a0: The proposed value "Megalithic structures" is merely the name of a Wikipedia category, not an instance type, so the proposal is contradicted by the evidence; Q1081138 denotes "cairn" as the Wikidata instance-of, which supports the stored value.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Ashley, Northamptonshire - `site_type` City/town/settlement -> Residence/villa/farmhouse

Site `c8370b05-1d32-491a-a735-344f6534b4d8`, journal row 28325.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read, identity: the record is the Roman villa; the linked item is the modern village (B1).

* remediation_change_log:28325: phase3:batch-0111:chunk-0001 (P3/site_type): site_type 'Residence/villa/farmhouse' -> 'City/town/settlement' - the write this row undoes
* rereview:phase3:ba461acf4097757eeafeeeb2c04d7fd43886163ee942dfc41324eced7346fe4e: hand-read, identity: the record is the Roman villa; the linked item is the modern village (B1)
* rereview:phase3:ba461acf4097757eeafeeeb2c04d7fd43886163ee942dfc41324eced7346fe4e: The evidence's enwiki extract describes Ashley as a village and civil parish, and Wikidata P31 gives Q532 (village) and Q1115575 (civil parish), so the stored "Residence/villa/farmhouse" is not a settlement type; the Roman villa mentioned is a nearby separate site.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Tavole Palatine - `site_type` Temple -> Temple complex

Site `6af23268-e00e-481b-ac50-8fc3901be8be`, journal row 28597.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28597: phase3:batch-0167:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Temple' - the write this row undoes
* rereview:phase3:839dcbf9e99c87f3691b0ba6ab7808c020306557ddcde134c423eb9b43f03d12: refuted
* rereview:phase3:839dcbf9e99c87f3691b0ba6ab7808c020306557ddcde134c423eb9b43f03d12: The finder's evidence supports `Temple` as the type, but it does not contradict the stored `Temple complex` — the same source describes a sanctuary with temenos wall and altar, and Wikidata lists multiple instance-of values (temple, archaeological site, park), so the finer/compound stored value is not shown wrong.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Treasury of Cyrene - `site_type` Temple -> Megalithic structures

Site `ff136c0c-2d3a-4621-b27b-294758b9cc4d`, journal row 28607.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28607: phase3:batch-0168:chunk-0001 (P3/site_type): site_type 'Megalithic structures' -> 'Temple' - the write this row undoes
* rereview:phase3:20a33156cf8d56ca84a84d7b9919a6433a2117b1aba9ed67fb4b756fdd424948: refuted
* rereview:phase3:20a33156cf8d56ca84a84d7b9919a6433a2117b1aba9ed67fb4b756fdd424948: The proposed value is not contradicted, but neither is the stored value shown wrong — "Treasury" (treasury building, Q1239455) is a finer/specific value than "Temple," and the evidence gives no basis for calling the megalithic classification erroneous beyond it not matching the Doric description.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Arqueológico El Puente Park - `site_type` Archaeological site -> City/town/settlement

Site `f4b1324a-06cd-4f3e-a3c7-aeb863180bc0`, journal row 28621.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28621: phase3:batch-0170:chunk-0001 (P3/site_type): site_type 'City/town/settlement' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:cd45cd66e26678eb06fb54698ec7a2b3fc1a8d44dfa3552008b9000ccef05351: refuted
* rereview:phase3:cd45cd66e26678eb06fb54698ec7a2b3fc1a8d44dfa3552008b9000ccef05351: The proposed value is not contradicted — "archaeological Maya site" describes a settlement, and the stored "City/town/settlement" is compatible with it; P31 = Q30504601 (archaeological site) does not make the broader stored category wrong, and the Wikidata description itself says "site", not a different bucket.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Brauroneion - `period_start` -430 -> -1500

Site `44354857-115b-44d3-b155-cae373565602`, journal row 28627.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: problem on the answer.

* remediation_change_log:28627: phase3:batch-0171:chunk-0001 (P3/period_start): period_start '-1500' -> '-430' - the write this row undoes
* rereview:phase3:4f7ba7b56039824773b857adce9603f1fc23a7ef7cb02bea9b0e748caa7d4410: problem on the answer
* rereview:phase3:4f7ba7b56039824773b857adce9603f1fc23a7ef7cb02bea9b0e748caa7d4410: The first half fails — the finder claims -430 falls in `500 BC - 1 AD`, but the evidence (enwiki extract and Wikidata P571 = -0430) supports -430 as the sanctuary's final form, and its own bucket arithmetic contradicts the stored -1500 only by placing -430 in a different bucket, which the evidence does not actually show for `period_start`; the proposed -430 is the value the evidence gives.
* pipeline/utils/text.py:categorize_period: categorize_period(-1500) = '1500 - 500 BC', categorize_period(-430) = '500 BC - 1 AD' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Alampra - `period_start` -1900 -> -3000

Site `0f7c84f4-7364-434d-b003-706c8d7a3275`, journal row 28632.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: unresolved or unreadable.

* remediation_change_log:28632: phase3:batch-0172:chunk-0001 (P3/period_start): period_start '-3000' -> '-1900' - the write this row undoes
* rereview:phase3:b4601925172d94c28865ca9769061545650154badc7b2143f2b132a306791aac: unresolved or unreadable
* rereview:phase3:b4601925172d94c28865ca9769061545650154badc7b2143f2b132a306791aac: The finder's own source says the settlement is Middle Bronze Age ca. 1900–1650 BC, which contradicts the stored -3000 only if -3000 were meant as the site's dating; but the stored value is the project's period_start sort key and the evidence gives no other Cypriot site data to show -3000 is from a different bucket, so the reason does not clearly hold.
* pipeline/utils/text.py:categorize_period: categorize_period(-3000) = '3000 - 1500 BC', categorize_period(-1900) = '3000 - 1500 BC' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Craigs Dolmen - `site_type` Dolmen -> Necropolis/tombs complex

Site `fa245dcb-9b81-40b2-b221-b670d983549c`, journal row 28663.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: WHY names a failing half: 'neither half holds'.

* remediation_change_log:28663: phase3:batch-0176:chunk-0001 (P3/site_type): site_type 'Necropolis/tombs complex' -> 'Dolmen' - the write this row undoes
* rereview:phase3:feb5b64fe8bf23e34f3b9ee04b97d6314dbe786cea4c7f3a339acc0798e4450d: WHY names a failing half: 'neither half holds'
* rereview:phase3:feb5b64fe8bf23e34f3b9ee04b97d6314dbe786cea4c7f3a339acc0798e4450d: Neither half holds — the site is described as a passage tomb (and "wrongly assumed to be a dolmen"), and Wikidata's P31 = dolmen supports a single-tomb classification, not "Necropolis/tombs complex", so the stored value does not match the evidence.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Dosariyah - `period_start` -5500 -> -6000

Site `84d9c1fb-6f17-4a2e-84a5-5cb05ed6adf2`, journal row 28670.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28670: phase3:batch-0177:chunk-0001 (P3/period_start): period_start '-6000' -> '-5500' - the write this row undoes
* rereview:phase3:f1de6cccb94be9f8f070b6e04795af4a0a4c6422d065252ede85dd6b0b69a037: refuted
* rereview:phase3:f1de6cccb94be9f8f070b6e04795af4a0a4c6422d065252ede85dd6b0b69a037: The reason fails: the evidence dates habitation to the late 6th and early 5th millennium BCE, which begins around -5500, not -6000, so the stored -6000 is not shown wrong by a different bucket—but more decisively, the finder's own cited span (~-5500 to -4500) is consistent with the stored start being only a coarse round value, and the Wikipedia text gives no start date of -6000 being in a different bucket; however, the proposed -5500 is contradicted by the source's own wording which places the range as late 6th/early 5th millennium, i.e. the start is later than -6000, and the stored -6000 is a round era value rather than a demonstrated error.
* pipeline/utils/text.py:categorize_period: categorize_period(-6000) = '< 4500 BC', categorize_period(-5500) = '< 4500 BC' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Undavalli Caves - `site_type` Cave Structures -> Temple complex

Site `5be3cff9-8b07-4cfc-b667-933e2d0ae302`, journal row 28675.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28675: phase3:batch-0178:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Cave Structures' - the write this row undoes
* rereview:phase3:6c01e246e098c934ced0ced83a5fd9418bfb49d0d2ee1853d95964a62903a725: refuted
* rereview:phase3:6c01e246e098c934ced0ced83a5fd9418bfb49d0d2ee1853d95964a62903a725: The evidence shows the site was a Jain abode, Buddhist monastic complex, and Hindu temple complex with a four-storey rock-cut temple, so it genuinely is a temple complex and the stored value is not wrong; the proposed "Cave Structures" is a generic form, not a contradiction.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Elewijt Vicus - `site_type` Archaeological site -> City/town/settlement

Site `214ae628-b465-4a07-850b-2a491f421081`, journal row 28744.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28744: phase3:batch-0187:chunk-0001 (P3/site_type): site_type 'City/town/settlement' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:0d5a53bca367feb776fd31f8d9993637f7b9fc5e856f934cc977a39139fa42ae: refuted
* rereview:phase3:0d5a53bca367feb776fd31f8d9993637f7b9fc5e856f934cc977a39139fa42ae: The less-specific Wikidata 'archaeological site' does not make the finer stored 'City/town/settlement' wrong — a vicus is a Roman settlement type, and the finder's own evidence (P2348 = Ancient Rome, P276 = vicus) describes a settlement, so the reason fails.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## King Arthur's Hall - `site_type` Megalithic -> Earthwork

Site `66cebfd5-9c0d-4116-bb94-c6f8dcda9b84`, journal row 28757.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: WHY names a failing half: 'the reason does not hold'.

* remediation_change_log:28757: phase3:batch-0188:chunk-0001 (P3/site_type): site_type 'Earthwork' -> 'Megalithic' - the write this row undoes
* rereview:phase3:8b468850eccd942a254b061e55613202803e8584efa5987a7f9a31c58b14b9b2: WHY names a failing half: 'the reason does not hold'
* rereview:phase3:8b468850eccd942a254b061e55613202803e8584efa5987a7f9a31c58b14b9b2: The reason does not hold: the evidence describes a monument consisting of stones with an earth bank, and an `Earthwork` classification is not shown wrong by calling it a megalithic enclosure; both terms describe the same structure.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Sidrón Cave - `site_type` Cave Structures -> Megalithic structures

Site `a4ac2a6f-0159-447e-a6d2-7300fbc986ef`, journal row 28770.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28770: phase3:batch-0191:chunk-0001 (P3/site_type): site_type 'Megalithic structures' -> 'Cave Structures' - the write this row undoes
* rereview:phase3:325a28d916c8470edc8de62f4e1f3541352946a86efb358930445580bb78a09d: refuted
* rereview:phase3:325a28d916c8470edc8de62f4e1f3541352946a86efb358930445580bb78a09d: The evidence describes a karst cave with Paleolithic art and Neanderthal fossils; nothing supports "megalithic structures," but the proposed value "Cave Structures" is also not a recognized/supported term and is contradicted by Wikidata, which types the feature as a cave (Q35509) and geographical object.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Tipón - `period_start` -1000 -> 1000

Site `d2b71745-bf32-4027-8920-18fcd5600c8d`, journal row 28776.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28776: phase3:batch-0192:chunk-0001 (P3/period_start): period_start '1000' -> '-1000' - the write this row undoes
* rereview:phase3:7b63c3a56c8b5d44e484b5199cd8e82b859f73c8701da638286ac5ef6cc5f59c: refuted
* rereview:phase3:7b63c3a56c8b5d44e484b5199cd8e82b859f73c8701da638286ac5ef6cc5f59c: The evidence's "continuously occupied from the Formative stage" is an occupation span/terminus phrase, not a dating of the site's construction, and the article itself opens by calling Tipón a "sprawling early fifteenth-century Inca archaeological site," so the proposed -1000 is contradicted by the evidence.
* pipeline/utils/text.py:categorize_period: categorize_period(1000) = '1000 - 1500 AD', categorize_period(-1000) = '1500 - 500 BC' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Kutlug-Tepe - `site_type` Fortification -> Temple complex

Site `b0db0a0f-c2c3-4119-bf6f-43f2e040119c`, journal row 28785.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: unresolved or unreadable.

* remediation_change_log:28785: phase3:batch-0194:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Fortification' - the write this row undoes
* rereview:phase3:019606bab77c4ac114f3d791969b77359fc0247ede0d860d4170c61d1e5d26f5: unresolved or unreadable
* rereview:phase3:019606bab77c4ac114f3d791969b77359fc0247ede0d860d4170c61d1e5d26f5: The enwiki text does explicitly describe Kutlug-Tepe as "a fortification," so the proposed value is not contradicted, but the altar note means the "Temple complex" inference is not clearly refuted either—the evidence leaves the correct typology unsettled.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Tarawasi - `site_type` Archaeological site -> Temple complex

Site `3223ecb5-4712-44c1-b02b-f9fabe186d09`, journal row 28804.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28804: phase3:batch-0196:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:4a990973e5b8663692d0eec8addd278454e09d45ae53643abec586362048d6ff: refuted
* rereview:phase3:4a990973e5b8663692d0eec8addd278454e09d45ae53643abec586362048d6ff: The evidence does show Tarahuasi is described only as an archaeological site, but per the project's design a less specific Wikidata value does not make a finer stored type wrong, so the reason does not establish the stored value is an error.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Caer Lêb - `site_type` Archaeological site -> City/town/settlement

Site `2a87862a-98dc-4cbd-8d8e-89f7c1368e63`, journal row 28870.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read: a less specific value does not make 'City/town/settlement' wrong - the evidence itself calls it a settlement.

* remediation_change_log:28870: phase3:batch-0208:chunk-0001 (P3/site_type): site_type 'City/town/settlement' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:9ab2738ef6ae816889a7002f7c24795fe4736c31f39f5b312882456a01216d71: hand-read: a less specific value does not make 'City/town/settlement' wrong - the evidence itself calls it a settlement
* rereview:phase3:9ab2738ef6ae816889a7002f7c24795fe4736c31f39f5b312882456a01216d71: Both halves hold — the evidence shows enclosure banks, ditches, excavated structures, Roman/post-Roman pottery and coins (a settlement rather than a city/town), and Wikidata's own P31 lists archaeological site (Q839954), so "Archaeological site" is not contradicted.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Fortifications of Chania - `period_start` -300 -> -500

Site `77127fe3-8116-4567-9b04-aebbe719e5a7`, journal row 28872.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: problem on the answer.

* remediation_change_log:28872: phase3:batch-0208:chunk-0001 (P3/period_start): period_start '-500' -> '-300' - the write this row undoes
* rereview:phase3:e568c8bbaf0e06270de11f20b579e39180974e851a5810c6c8b87bae995b4a8b: problem on the answer
* rereview:phase3:e568c8bbaf0e06270de11f20b579e39180974e851a5810c6c8b87bae995b4a8b: Neither half fails - the evidence supports an earlier start than the stored -500 (Hellenistic walls "around the 3rd century BC"), so the stored value is not shown wrong, but the proposed -300 is contradicted by Wikidata's inception of +1336, leaving no basis to prefer -300 over -500.
* pipeline/utils/text.py:categorize_period: categorize_period(-500) = '500 BC - 1 AD', categorize_period(-300) = '500 BC - 1 AD' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Temple of Jupiter, Pompeii - `site_type` Temple -> Temple complex

Site `5adaee62-3e90-4550-930c-6cd9039c223d`, journal row 28970.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28970: phase3:batch-0219:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Temple' - the write this row undoes
* rereview:phase3:084eff4003e9f16baa64d005ead3c2f6f7ae67aea7eff4acaf2faac537a60323: refuted
* rereview:phase3:084eff4003e9f16baa64d005ead3c2f6f7ae67aea7eff4acaf2faac537a60323: The Wikidata instance-of claims include both Q44539 (temple) and finer subclasses, and the site is the Capitolium temple complex of Pompeii; calling it a "Temple complex" is not contradicted by evidence showing it is a temple, since the proposed "Temple" is merely less specific.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Bow Hill, Sussex - `site_type` Natural feature -> Mound/tumulus

Site `7748176f-48aa-4377-8b17-f9f64dc5c525`, journal row 28978.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read, identity: the record is the Bronze Age barrows (Devil's Humps); the linked item is the hill (B1).

* remediation_change_log:28978: phase3:batch-0220:chunk-0001 (P3/site_type): site_type 'Mound/tumulus' -> 'Natural feature' - the write this row undoes
* rereview:phase3:bdcf06650bd518fbcdf05bad66f621a113a9d6cc2b82834104578bf7a123ad53: hand-read, identity: the record is the Bronze Age barrows (Devil's Humps); the linked item is the hill (B1)
* rereview:phase3:bdcf06650bd518fbcdf05bad66f621a113a9d6cc2b82834104578bf7a123ad53: Both halves hold — the evidence (and Wikidata's own description "hill in West Sussex, England, UK", P31 = hill) shows Bow Hill is a natural hill, not a mound/tumulus, and the proposed "Natural feature" is not contradicted; the tumuli mentioned (Devil's Humps) are separate features on the ridge, not the site itself.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Ostrusha Mound - `site_type` Tomb -> Mound/tumulus

Site `cbca1610-17fd-49f8-9c3e-536db4f7c9ce`, journal row 28998.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:28998: phase3:batch-0223:chunk-0001 (P3/site_type): site_type 'Mound/tumulus' -> 'Tomb' - the write this row undoes
* rereview:phase3:3efa108fc82b2a75ff9122df29d99868d6c16bced8489a3cd17520c99176a23e: refuted
* rereview:phase3:3efa108fc82b2a75ff9122df29d99868d6c16bced8489a3cd17520c99176a23e: The stored value "Mound/tumulus" is not contradicted by the label/description — Ostrusha is a mound (tumulus) containing a tomb, and Wikidata's P31 includes a tumulus item; the label "tomb" names the structure inside, not a different bucket for the site.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Ashdown Forest - `site_type` Natural feature -> Barrow

Site `b4a99c23-00b3-4eb5-80c0-c1569cb9a351`, journal row 29025.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29025: phase3:batch-0227:chunk-0001 (P3/site_type): site_type 'Barrow' -> 'Natural feature' - the write this row undoes
* rereview:phase3:9b01175707593be7a60331ab9c7f5b00fc2170458ca5bd7a6e6806bf349c7dff: refuted
* rereview:phase3:9b01175707593be7a60331ab9c7f5b00fc2170458ca5bd7a6e6806bf349c7dff: The reason fails — the evidence is about Ashdown Forest as a whole landscape (heathland/forest with barrows among its archaeology), not a claim that the stored `site_type` of any particular barrow site is wrong, and the finder's own source describes a forest/landscape rather than contradicting a `Barrow` classification.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Qohaito - `period_start` -5000 -> 1

Site `941ec7f7-645f-4c87-9cc5-f156e7504054`, journal row 29073.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29073: phase3:batch-0235:chunk-0001 (P3/period_start): period_start '1' -> '-5000' - the write this row undoes
* rereview:phase3:f1b7cedc1e79dd3329a186d850dd70e36e122401cdc4d54432a09d25dfb9f14c: refuted
* rereview:phase3:f1b7cedc1e79dd3329a186d850dd70e36e122401cdc4d54432a09d25dfb9f14c: The fifth-millennium BC rock art only evidences habitation *near* Qohaito, not a founding date for the settlement, and the proposed -5000 is not supported by the evidence, which explicitly denies any founding year.
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD', categorize_period(-5000) = '< 4500 BC' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Roman Temple of Alcántara - `site_type` Temple -> Temple complex

Site `b54580b3-4201-4cc6-9588-785d365974d6`, journal row 29082.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29082: phase3:batch-0236:chunk-0003 (P3/site_type): site_type 'Temple complex' -> 'Temple' - the write this row undoes
* rereview:phase3:dbed8a11468ea1f5b1fdfe60ebfb968776872b48231595c948dd4e7a4c1f2e31: refuted
* rereview:phase3:dbed8a11468ea1f5b1fdfe60ebfb968776872b48231595c948dd4e7a4c1f2e31: The reason does not hold — Wikidata's P31 values (temple Q867143 and Q14752696) show 'temple', which is not a different bucket from the stored 'Temple complex', and a less specific/finer distinction here does not make the stored value wrong.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Combe Hill, East Sussex - `period_start` -3001 -> -4500

Site `9ae31b41-d78d-44da-824d-43487ec611f0`, journal row 29136.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29136: phase3:batch-0244:chunk-0001 (P3/period_start): period_start '-4500' -> '-3001' - the write this row undoes
* rereview:phase3:7b11d7913f95b926b77cbc75a25a7916331a1526bc14c2cc9f950a7dce579214: refuted
* rereview:phase3:7b11d7913f95b926b77cbc75a25a7916331a1526bc14c2cc9f950a7dce579214: The reason does not hold: the site's construction date is not established by Wikidata's coarse P571 (precision 6, millennium-level, stated as -3001), and the enwiki evidence explicitly says the enclosure "was constructed no later than the second half of the fourth millennium BC" and that construction was "probably constructed before this range" of 3500–3300 BC — a fine, radiocarbon-based date incompatible with the rounded millennium value -3001, so neither the "stored value is wrong" claim nor the proposed value is supported.
* pipeline/utils/text.py:categorize_period: categorize_period(-4500) = '4500 - 3000 BC', categorize_period(-3001) = '4500 - 3000 BC' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Jadranovo - `period_start` -6500 -> -500

Site `77935222-436a-4bf7-9337-e7a3d86f74ba`, journal row 29176.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29176: phase3:batch-0249:chunk-0001 (P3/period_start): period_start '-500' -> '-6500' - the write this row undoes
* rereview:phase3:c2faf53e4894ce84639f940b325889a5f1fa8cb6ae697be6630c37985ccd3527: refuted
* rereview:phase3:c2faf53e4894ce84639f940b325889a5f1fa8cb6ae697be6630c37985ccd3527: The proposed value -6500 is contradicted by the evidence, which states the earliest traces date to "6500 BC - 4000 BC" — a range whose upper bound (4000 BC) and nature as settlement traces do not establish a period_start of -6500; moreover, the stored -500 is consistent with the documented 3rd–1st century BC amphorae phase, so the proposed replacement fails.
* pipeline/utils/text.py:categorize_period: categorize_period(-500) = '500 BC - 1 AD', categorize_period(-6500) = '< 4500 BC' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## The Trundle - `period_start` -500 -> -1000

Site `05ee235c-2ded-4af5-9e94-980c7750bc52`, journal row 29246.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read: both values miss the Neolithic causewayed enclosure (c. 3500 BC); the field stays open with that note.

* remediation_change_log:29246: phase3:batch-0260:chunk-0001 (P3/period_start): period_start '-1000' -> '-500' - the write this row undoes
* rereview:phase3:29bb368c0cbc13db96c26fdb01547ecabdbbb960e81ba8d629c147c838b97f62: hand-read: both values miss the Neolithic causewayed enclosure (c. 3500 BC); the field stays open with that note
* rereview:phase3:29bb368c0cbc13db96c26fdb01547ecabdbbb960e81ba8d629c147c838b97f62: Both halves hold — the site's Iron Age hillfort construction is dated by Curwen's excavations to about 500–100 BC, which is the article's own statement, supporting -500 over the stored -1000; the finder's own span reasoning concedes -1000 is only the general earliest hillfort horizon, not this site's construction date.
* pipeline/utils/text.py:categorize_period: categorize_period(-1000) = '1500 - 500 BC', categorize_period(-500) = '500 BC - 1 AD' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md). Both values miss the Neolithic causewayed enclosure (c. 3500 BC): the field stays open with that note (the re-review's hand read).

## Copán Ruins - `site_type` Archaeological site -> Temple complex

Site `63c756cd-955c-4270-8474-916ed14fc2a4`, journal row 29272.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29272: phase3:batch-0263:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:4ea4644a2dc7a79bf34f42d7b36245a279a44fb761995a753a420d29a324c5b9: refuted
* rereview:phase3:4ea4644a2dc7a79bf34f42d7b36245a279a44fb761995a753a420d29a324c5b9: The reason fails - Wikidata's P31 value "archaeological site" is a less specific parent type and does not contradict the finer stored "Temple complex" (the UNESCO name itself is "Maya Site of Copan"), so the evidence does not show the stored value wrong.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Jajce Mithraeum - `period_start` 300 -> 1

Site `8325d125-ed63-4a02-8c93-1e2a6683f5e1`, journal row 29275.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29275: phase3:batch-0264:chunk-0001 (P3/period_start): period_start '1' -> '300' - the write this row undoes
* rereview:phase3:3eb25759e9cff97649c042b6c5ee47de9195a093f2a63e410d8fb69950870862: refuted
* rereview:phase3:3eb25759e9cff97649c042b6c5ee47de9195a093f2a63e410d8fb69950870862: The first half fails: `period_start` is a round era sort key, and stored `1` (start of the 1–500 AD bucket) is not made wrong by a source describing the temple's 4th-century (or 2nd-century) date, so the evidence does not show the stored value erroneous.
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD', categorize_period(300) = '1 - 500 AD' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Butrint - `site_type` City/town/settlement -> Temple complex

Site `17c94d52-2df2-44ba-83f1-41c26ee6eea3`, journal row 29285.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29285: phase3:batch-0266:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'City/town/settlement' - the write this row undoes
* rereview:phase3:d2ed709e36f28b9916022a1d1995a602f136377eabb4a956c03b9fda783cae96: refuted
* rereview:phase3:d2ed709e36f28b9916022a1d1995a602f136377eabb4a956c03b9fda783cae96: The stored site_type "Temple complex" may be plausible because evidence shows a sanctuary dedicated to Asclepius and a temple of Asklepeios at the site, and the finder's claim that nothing matches "Temple complex" is not established; the proposed "City/town/settlement" does not contradict the stored value either, making the refutation fail on the first half.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Nimrod Fortress - `period_start` -332 -> 1

Site `564bde41-2281-41fb-979e-9d75e413a845`, journal row 29326.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29326: phase3:batch-0271:chunk-0001 (P3/period_start): period_start '1' -> '-332' - the write this row undoes
* rereview:phase3:86a20d5e2075cbc5e6125136b2a2cac1a98782561318d81e8fe6d1e72fea1529: refuted
* rereview:phase3:86a20d5e2075cbc5e6125136b2a2cac1a98782561318d81e8fe6d1e72fea1529: The reason fails - the English Wikipedia text says a first castle was "probably" built in the Hellenistic period, which is a tentative hypothesis and does not establish the stored Ayyubid-period value (1 AD, i.e. the Ayyubid/Mamluk fortress the infobox treats as the structure) as wrong; the article itself opens by describing the fortress as "a castle built by the Ayyubids and greatly enlarged by the Mamluks."
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD', categorize_period(-332) = '500 BC - 1 AD' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## San Jose de Moro - `site_type` Necropolis/tombs complex -> Temple complex

Site `37d54e47-00e9-4647-82c8-3ee56814692d`, journal row 29410.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29410: phase3:batch-0284:chunk-0001 (P3/site_type): site_type 'Temple complex' -> 'Necropolis/tombs complex' - the write this row undoes
* rereview:phase3:53f3d18ce943c5b23067198310222200f685be48119d1f0fa488714fbe4c0509: refuted
* rereview:phase3:53f3d18ce943c5b23067198310222200f685be48119d1f0fa488714fbe4c0509: The reason does not hold — the site has ceremonial and ritual functions, not merely burials; the evidence describes feasting, shamans, sacrifice ceremonies, and priestesses, so "Temple complex" is not shown wrong, and a funerary complex is not contradicted either but the refutation half fails.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Nether Heyford - `site_type` City/town/settlement -> Residence/villa/farmhouse

Site `bb0df218-2b05-41e7-b496-73c458bae35f`, journal row 29436.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: unresolved or unreadable.

* remediation_change_log:29436: phase3:batch-0288:chunk-0001 (P3/site_type): site_type 'Residence/villa/farmhouse' -> 'City/town/settlement' - the write this row undoes
* rereview:phase3:5ceef6867f3aafbb556d0100934c99e513c2c75579a0035d962de4ea746e298e: unresolved or unreadable
* rereview:phase3:5ceef6867f3aafbb556d0100934c99e513c2c75579a0035d962de4ea746e298e: Neither half can be settled from this evidence - Q584511 is indeed the village/civil parish, but nothing here identifies whether the catalogued site with stored type `Residence/villa/farmhouse` is that parish or one of the two Roman villas the same article describes ("The parish is the site of two Roman villas"), so the ground truth for the stored value is undetermined.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Billingsgate Roman House and Baths - `site_type` Bath -> Residence/villa/farmhouse

Site `b60c114a-7ee2-4f67-b3ff-a3d3d3e55d15`, journal row 29497.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29497: phase3:batch-0297:chunk-0001 (P3/site_type): site_type 'Residence/villa/farmhouse' -> 'Bath' - the write this row undoes
* rereview:phase3:b8805e82e5b313dbb27ecdda738f46095e71314a1298b2c5e8d031ca717a4b03: refuted
* rereview:phase3:b8805e82e5b313dbb27ecdda738f46095e71314a1298b2c5e8d031ca717a4b03: The proposal is contradicted: Wikidata's P31 instance-of lists a Roman house/building complex (Q6581615) and its bath component (Q14752696), and the enwiki text describes a Roman house with a bath added in the 3rd century, so classifying the whole site solely as "Bath" fails while the stored residence/villa reading remains supported by the house itself.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Audleystown Court Tomb - `site_type` Tomb -> Necropolis/tombs complex

Site `c0d78581-207b-4223-bcdf-680bd82bce83`, journal row 29552.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: WHY names a failing half: 'the reason fails'.

* remediation_change_log:29552: phase3:batch-0306:chunk-0001 (P3/site_type): site_type 'Necropolis/tombs complex' -> 'Tomb' - the write this row undoes
* rereview:phase3:b25108f8e8b9fb1181674f03e2434b65768d6559625e55ecdac948b127be606d: WHY names a failing half: 'the reason fails'
* rereview:phase3:b25108f8e8b9fb1181674f03e2434b65768d6559625e55ecdac948b127be606d: The evidence classifies the site as a court tomb/cairn, not a "Necropolis/tombs complex," and no evidence supports the finer claim that "Tomb" contradicts the stored value; moreover, the proposed "Tomb" is itself not contradicted, so the reason fails only in that the stored value is a broader category rather than demonstrably wrong.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Belas Knap - `period_start` -3000 -> -4500

Site `f0365431-b2a9-42a7-9cff-877433b51551`, journal row 29563.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29563: phase3:batch-0307:chunk-0001 (P3/period_start): period_start '-4500' -> '-3000' - the write this row undoes
* rereview:phase3:f41dd6e50b777e97eb6f395f334cc1d87144329c360e5295ae4f0c65b26d8d54: refuted
* rereview:phase3:f41dd6e50b777e97eb6f395f334cc1d87144329c360e5295ae4f0c65b26d8d54: The enwiki evidence ("around 3000 BC") is a construction estimate for the barrow, but the stored value -4500 falls in the same broad Neolithic bucket (4500–3000 BC) and "around 3000 BC" is itself an imprecise approximation, so the evidence does not establish the stored value as wrong.
* pipeline/utils/text.py:categorize_period: categorize_period(-4500) = '4500 - 3000 BC', categorize_period(-3000) = '3000 - 1500 BC' - another bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Jarlshof - `period_start` -2500 -> -3000

Site `38d80f05-0d81-48f5-9b96-dfcf85493532`, journal row 29578.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29578: phase3:batch-0309:chunk-0001 (P3/period_start): period_start '-3000' -> '-2500' - the write this row undoes
* rereview:phase3:8d8ec2c2b5c4ab86c328cf95d0e54393a5f8a3669fe73ed579f4cf55210370d2: refuted
* rereview:phase3:8d8ec2c2b5c4ab86c328cf95d0e54393a5f8a3669fe73ed579f4cf55210370d2: The finder's reason fails - the article states the oldest known remains date from the Bronze Age (approx. 2000 BC), with evidence of inhabitation as far back as 2500 BC, so "remains dating from 2500 BC" does not show -3000 wrong; the proposed -2500 also contradicts the finer evidence.
* pipeline/utils/text.py:categorize_period: categorize_period(-3000) = '3000 - 1500 BC', categorize_period(-2500) = '3000 - 1500 BC' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Huandacareo - `site_type` Archaeological site -> City/town/settlement

Site `62ea668a-68e5-41fe-93ed-3429127d6b4c`, journal row 29617.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read: the reviewer's WHY opens 'The stored value is not wrong' - a refutation in words the phrase set does not list.

* remediation_change_log:29617: phase3:batch-0315:chunk-0001 (P3/site_type): site_type 'City/town/settlement' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:cdf825f8f38c044e5ce3e68d197f1045c0c2acde03f32473244a2e0a9de7b820: hand-read: the reviewer's WHY opens 'The stored value is not wrong' - a refutation in words the phrase set does not list
* rereview:phase3:cdf825f8f38c044e5ce3e68d197f1045c0c2acde03f32473244a2e0a9de7b820: The stored value is not wrong — the finder's reasons conflict with the evidence, which describes Huandacareo as a site "about two kilometers from the center of the Huandacareo town and municipality" with "Remains of ancient housing units ... underneath present day houses," and Wikidata's P31 is the generic "archaeological site" (Q839954), so neither the reason nor the proposal establishes the stored "City/town/settlement" as an error.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## High Street, Lake District - `site_type` Natural feature -> Road/avenue/trackway

Site `7b8f41e0-5e48-4247-8fc4-33863cb2af59`, journal row 29618.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: hand-read, identity: the record is the Roman road the fell is named after; the linked item is the fell (B1).

* remediation_change_log:29618: phase3:batch-0315:chunk-0001 (P3/site_type): site_type 'Road/avenue/trackway' -> 'Natural feature' - the write this row undoes
* rereview:phase3:e6956263777f5a78efc9d59fef51cba6a943a4ffd8a8a9282556b1f02d74ee36: hand-read, identity: the record is the Roman road the fell is named after; the linked item is the fell (B1)
* rereview:phase3:e6956263777f5a78efc9d59fef51cba6a943a4ffd8a8a9282556b1f02d74ee36: The evidence — P31 = Q8502 (mountain), P2044 elevation 828 m, P2660 prominence 373 m, P4552 mountain range, and the description "fell in the English Lake District" — does show the stored `Road/avenue/trackway` wrong, and the proposed `Natural feature` is not contradicted by it.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Housesteads Roman Fort - `period_start` 124 -> 1

Site `2726f1bb-9af6-4f23-af79-fc0f789a5ddc`, journal row 29628.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29628: phase3:batch-0316:chunk-0001 (P3/period_start): period_start '1' -> '124' - the write this row undoes
* rereview:phase3:4d65a616b8c1832e4aba7a5d8b781bde3eee7228131c0a967dc6c11b7578ffcc: refuted
* rereview:phase3:4d65a616b8c1832e4aba7a5d8b781bde3eee7228131c0a967dc6c11b7578ffcc: Both halves fail — the stored `period_start` is 1, and the finder's own evidence gives AD 124 for the fort's construction, which is in the same `1 - 500 AD` bucket as the stored 1, so the round-value/bucket rule for `period_start` (a sort key) is not violated.
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD', categorize_period(124) = '1 - 500 AD' - the same bucket
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## La Almoloya - `site_type` Archaeological site -> City/town/settlement

Site `78c3716d-79fb-46aa-82df-3a26d8ffd414`, journal row 29633.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29633: phase3:batch-0317:chunk-0001 (P3/site_type): site_type 'City/town/settlement' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:bf873c75cf43b39530ac05672705ec0b47a1235b7504dc6115f20c04977df2f6: refuted
* rereview:phase3:bf873c75cf43b39530ac05672705ec0b47a1235b7504dc6115f20c04977df2f6: The stored "City/town/settlement" is a finer/alternative classification of an Argaric settlement site, and the finding's own evidence — an enwiki extract calling it an archaeological site and Wikidata P31 = archaeological site — shows only a less specific class, not that the stored value is factually wrong; no evidence contradicts settlement status, so half 1 fails.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## Makra Stoa - `site_type` Archaeological site -> Megalithic structures

Site `d85b55ee-afa3-423c-99d5-84149e5f8ee9`, journal row 29642.

**Reason.** the first re-review of the written rows whose reviewer contradicted itself decided to reverse this write: refuted.

* remediation_change_log:29642: phase3:batch-0318:chunk-0001 (P3/site_type): site_type 'Megalithic structures' -> 'Archaeological site' - the write this row undoes
* rereview:phase3:1a4fe3d339845802131fdf6f986cf17302b3728a66aa6affccf01b058a34ba7c: refuted
* rereview:phase3:1a4fe3d339845802131fdf6f986cf17302b3728a66aa6affccf01b058a34ba7c: The reason holds - the enwiki extract calls it "an archaeological site" with no megalithic structure - but the proposed value "Archaeological site" is contradicted by Wikidata's P31 (Q327328), which is "building", matching the described long commercial stoa rather than an archaeological site as its type.
* residual: The field is open again, not corrected: the reversal withdraws a correction whose support did not hold, and does not claim the restored value is right (phase3_runner/REREVIEW_1.md).

## The Trundle - `period_name` 500 BC - 1 AD -> 1500 - 500 BC

Site `05ee235c-2ded-4af5-9e94-980c7750bc52`, journal row 30335.

**Reason.** the period-name lane derived '500 BC - 1 AD' from the period_start -500 that journal row 29246 wrote; this list restores period_start -1000, whose bucket is '1500 - 500 BC' again.

* remediation_change_log:30335: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '1500 - 500 BC' -> '500 BC - 1 AD' - the write this row undoes
* journal: phase3:batch-0260:chunk-0001 (P3/period_start): period_start '-1000' -> '-500' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(-1000) = '1500 - 500 BC' - the period_start the site is left with

## Brauroneion - `period_name` 500 BC - 1 AD -> 1500 - 500 BC

Site `44354857-115b-44d3-b155-cae373565602`, journal row 30386.

**Reason.** the period-name lane derived '500 BC - 1 AD' from the period_start -430 that journal row 28627 wrote; this list restores period_start -1500, whose bucket is '1500 - 500 BC' again.

* remediation_change_log:30386: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '1500 - 500 BC' -> '500 BC - 1 AD' - the write this row undoes
* journal: phase3:batch-0171:chunk-0001 (P3/period_start): period_start '-1500' -> '-430' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(-1500) = '1500 - 500 BC' - the period_start the site is left with

## Nimrod Fortress - `period_name` 500 BC - 1 AD -> 1 - 500 AD

Site `564bde41-2281-41fb-979e-9d75e413a845`, journal row 30405.

**Reason.** the period-name lane derived '500 BC - 1 AD' from the period_start -332 that journal row 29326 wrote; this list restores period_start 1, whose bucket is '1 - 500 AD' again.

* remediation_change_log:30405: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '1 - 500 AD' -> '500 BC - 1 AD' - the write this row undoes
* journal: phase3:batch-0271:chunk-0001 (P3/period_start): period_start '1' -> '-332' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD' - the period_start the site is left with

## Jadranovo - `period_name` < 4500 BC -> 500 BC - 1 AD

Site `77935222-436a-4bf7-9337-e7a3d86f74ba`, journal row 30441.

**Reason.** the period-name lane derived '< 4500 BC' from the period_start -6500 that journal row 29176 wrote; this list restores period_start -500, whose bucket is '500 BC - 1 AD' again.

* remediation_change_log:30441: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '500 BC - 1 AD' -> '< 4500 BC' - the write this row undoes
* journal: phase3:batch-0249:chunk-0001 (P3/period_start): period_start '-500' -> '-6500' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(-500) = '500 BC - 1 AD' - the period_start the site is left with

## Banwolseong - `period_name` 500 BC - 1 AD -> 1 - 500 AD

Site `8cead41d-19f8-45cf-9dc0-144583641e4f`, journal row 30451.

**Reason.** the period-name lane derived '500 BC - 1 AD' from the period_start -57 that journal row 27924 wrote; this list restores period_start 1, whose bucket is '1 - 500 AD' again.

* remediation_change_log:30451: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '1 - 500 AD' -> '500 BC - 1 AD' - the write this row undoes
* journal: phase3:batch-0031:chunk-0001 (P3/period_start): period_start '1' -> '-57' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD' - the period_start the site is left with

## Qohaito - `period_name` < 4500 BC -> 1 - 500 AD

Site `941ec7f7-645f-4c87-9cc5-f156e7504054`, journal row 30454.

**Reason.** the period-name lane derived '< 4500 BC' from the period_start -5000 that journal row 29073 wrote; this list restores period_start 1, whose bucket is '1 - 500 AD' again.

* remediation_change_log:30454: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '1 - 500 AD' -> '< 4500 BC' - the write this row undoes
* journal: phase3:batch-0235:chunk-0001 (P3/period_start): period_start '1' -> '-5000' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(1) = '1 - 500 AD' - the period_start the site is left with

## Tipón - `period_name` 1500 - 500 BC -> 1000 - 1500 AD

Site `d2b71745-bf32-4027-8920-18fcd5600c8d`, journal row 30512.

**Reason.** the period-name lane derived '1500 - 500 BC' from the period_start -1000 that journal row 28776 wrote; this list restores period_start 1000, whose bucket is '1000 - 1500 AD' again.

* remediation_change_log:30512: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '1000 - 1500 AD' -> '1500 - 500 BC' - the write this row undoes
* journal: phase3:batch-0192:chunk-0001 (P3/period_start): period_start '1000' -> '-1000' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(1000) = '1000 - 1500 AD' - the period_start the site is left with

## Belas Knap - `period_name` 3000 - 1500 BC -> 4500 - 3000 BC

Site `f0365431-b2a9-42a7-9cff-877433b51551`, journal row 30536.

**Reason.** the period-name lane derived '3000 - 1500 BC' from the period_start -3000 that journal row 29563 wrote; this list restores period_start -4500, whose bucket is '4500 - 3000 BC' again.

* remediation_change_log:30536: 2026-09-22_mechanical-period-name (P6/period-name-bucket): period_name '4500 - 3000 BC' -> '3000 - 1500 BC' - the write this row undoes
* journal: phase3:batch-0307:chunk-0001 (P3/period_start): period_start '-4500' -> '-3000' - the write that left the label behind
* pipeline/utils/text.py:categorize_period: categorize_period(-4500) = '4500 - 3000 BC' - the period_start the site is left with


## After the apply

The phase-3 acceptance reads these cells as superseded once it is told the stamp: `verify_writes.py --allow-stamp 2026-09-23_mechanical-journal-reversal-2`, with the stamps of the lanes applied before it. Re-plan the scope lane and the card_stats recompute afterwards: the scope premise and the cards derive from these columns.
