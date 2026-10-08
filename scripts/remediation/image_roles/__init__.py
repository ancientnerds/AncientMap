"""The image lanes of the final repair (2026-10-08, workstream map `plans/images.md`).

D15 re-checks the 47 heroes a Claude check called `other_site` (`served_image/`), D17 researches a
picture for the 952 sites that serve none (`candidate_search/`), D18 settles the credit rule
(`licenses.py`, `import_hero/fetch.py`, `gallery_audit/attribution.py`). This package holds what the
Claude roles of those lanes share: their prompts, their batches and their calibration.

* `calibrate.py`       - the sealed calibration of the image roles (map section 4);
* `mutation_sweep.py`  - one case per guard of the three lanes' new code.
"""
