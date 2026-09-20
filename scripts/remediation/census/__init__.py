"""The deterministic census of the curated sites (docs/procedures/SITES_DB_REMEDIATION_2026-09.md).

Package layout
--------------
``model``     Finding / Evidence / TestResult — the currency of the audit.
``fetch``     cached, polite HTTP so every test is a pure function of (snapshot, cache).
``snapshot``  read-only production snapshot loader (scripts/remediation/01_export_snapshot.sh).
``tests``     the ten deterministic checks; each exposes ``run(ctx) -> list[Finding]``.
``run``       driver: runs the registered tests, writes census.jsonl / findings.jsonl.

Nothing in this package writes to a database. Findings are proposals; application is a
separate, journalled step.
"""

__all__ = ["model", "fetch", "snapshot"]
