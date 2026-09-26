"""Lane WC, the research side: the sentence check of the March descriptions that stay.

Owner decision O5 of 2026-09-26 ("Satzweise pruefen und kuerzen"). The deterministic core - the
sentences, the trim, the composed text, the check record, the invariants - is
`scripts/remediation/phase4/wc4.py`; the write is the writer's group WC (`phase4/write4.py`,
`output/remediation/tools/write_gate4.py --group WC`). This package asks the questions through the
Opus handoff (`scripts/remediation/opus_handoff.py`), checks the answers' quotes against the fetched
pages (`scripts/remediation/opus_audit/quotes.py`) and builds the gate plan. The runbook is
`docs/procedures/SENTENCE_CHECK.md`.
"""
