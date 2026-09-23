# Journal reversal - plan (journal-reversal-1)

Built 2026-09-23T17:15:08+00:00 by `scripts/remediation/mechanical/reversal.py`. Lane `journal-reversal-1`: run stamp `2026-09-23_mechanical-journal-reversal-1`, journal test id `P6/journal-reversal`, change keys `journal-reversal-1:<site_id>:<column>`.

**3 cell(s) will be written, 0 refused.** Each restores the value a journal row replaced, conditioned on the live value being the value that row wrote, and on that row being the last write of its cell (guard 6).

## Stanydale Temple - `period_start` -2500 -> -3000

Site `60722e7e-587a-46fb-b09c-e6e82f1b74f7`, journal row 28018.

**Reason.** phase 3 replaced period_start -3000, which the gold standard judged CORRECT as a bucket-correct sort key (plan 4.3 item 1), with -2500 in the same bucket; under the project's rule only a value from another bucket is an error, so the write was not a correction.

* remediation_change_log:28018: phase3:batch-0052:chunk-0001 (P3/period_start): period_start '-3000' -> '-2500' - the write this row undoes
* gold_standard:60722e7e-587a-46fb-b09c-e6e82f1b74f7: -3000 is the floor of the bucket 3000 - 1500 BC, which contains -2500. Bucket correct (plan 4.3.1).
* pipeline/utils/text.py:categorize_period: categorize_period(-3000) = '3000 - 1500 BC', categorize_period(-2500) = '3000 - 1500 BC' - the same bucket
* residual: The gold standard's own note gives the settlement's dating as 2500-2000 BC: -2500 was the more precise year. The reversal restores the bucket floor the gold standard judged; the remaining map puts the 170 same-bucket writes to the owner as 'precision upgrade or roll back'.

## Ahin Posh Tape - `country` Pakistan -> Afghanistan

Site `786cada5-1feb-4c5c-9e79-b8ffdf8aacc6`, journal row 28384.

**Reason.** phase 3 wrote country Pakistan from Wikidata Q4695118, an item whose statements describe a village in Pakistan while its sitelinks are the Afghan stupa's articles; the site's own description and its English Wikipedia article place the stupa near Jalalabad, Afghanistan.

* remediation_change_log:28384: phase3:batch-0121:chunk-0006 (P3/country): country 'Afghanistan' -> 'Pakistan' - the write this row undoes
* description: A Kushan-era Buddhist stupa and monastery near Jalalabad, Afghanistan
* enwiki:Ahin Posh: is an ancient Buddhist stupa and monastery complex in the vicinity of Jalalabad, Afghanistan
* wikidata:Q4695118: human settlement in Pakistan
* residual: The stored point (33.668, 70.955) is the Pakistani village's, about 80 km from the article's coordinates (34.412, 70.452): after the reversal the country contradicts the point, which T02 will flag again. Coordinates are never written automatically (FIELD_CONTRACT section 4.6); the remaining map records this as a named residual.

## Agri Bavnehøj - `period_start` -1800 -> -3000

Site `94776f9f-ea10-4b05-87bd-fd30c2cbdf6f`, journal row 28638.

**Reason.** phase 3 replaced period_start -3000, which the gold standard judged CORRECT as a bucket-correct sort key (plan 4.3 item 1), with -1800 in the same bucket; under the project's rule only a value from another bucket is an error, so the write was not a correction.

* remediation_change_log:28638: phase3:batch-0173:chunk-0001 (P3/period_start): period_start '-3000' -> '-1800' - the write this row undoes
* gold_standard:94776f9f-ea10-4b05-87bd-fd30c2cbdf6f: -3000 is the floor of the bucket 3000 - 1500 BC, which contains the true start (-1800). Per plan 4.3.1 the round value is not an error as long as the bucket is right - it is.
* pipeline/utils/text.py:categorize_period: categorize_period(-3000) = '3000 - 1500 BC', categorize_period(-1800) = '3000 - 1500 BC' - the same bucket
* residual: The gold standard's own note and the site's description date the mound to c. 1800-1000 BC: -1800 was the more precise year. The reversal restores the bucket floor the gold standard judged.


## After the apply

The phase-3 acceptance reads these cells as superseded once it is told the stamp: `verify_writes.py --allow-stamp 2026-09-23_mechanical-journal-reversal-1`, with the stamps of the lanes applied before it. Re-plan the scope lane and the card_stats recompute afterwards: the scope premise and the cards derive from these columns.
