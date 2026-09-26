"""The structured-field lanes of the 2026-09 remediation (FINISH_PLAN workstream WD).

`harvest.py` is the shared, read-only Wikidata/Wikipedia harvest (WD1 and WD2 read its files);
`seeds.py` lists the fields earlier readings found wrong; `classify.py` decides each field of each
site deterministically; `handoff.py` asks Opus about every site with a field in CONFLICT or MISSING
(or flagged by a seed) and imports the machine-checked answers; `plan.py` turns the decisions into
journalled write steps for `mechanical/apply.py`. The runbook is `docs/procedures/FIELDS_WD1.md`.
"""
