"""Phase-3 runner: the two-stage factual audit of the 1,813 Phase-3 sites.

Piece 1 (this package, offline): the finding schema (`model`), the measured cost and
time ledger (`ledger`), and the CLI skeleton (`run`: `plan`, `prepare`, `status`).
No network and no model call happens anywhere in this package yet; piece 2 adds the
fetch and model-call stages, whose every call and fetch writes one ledger line.

The batching and the stage shape come from `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`
(§ Phase 3, § 13) and the ratified decisions in
`output/remediation/phase3_worklist/{FINDER_BRIEF,REVIEWER_BRIEF,BATCH_PLAN}.md`
(15 sites per run, two stages, 242 lifecycles).
"""
