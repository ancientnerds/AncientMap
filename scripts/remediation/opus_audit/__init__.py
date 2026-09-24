"""The Opus re-verification of every DeepSeek-decided production row (2026-09-23 owner order).

The rules were sealed before the first verdict (`output/remediation/opus_audit/RULES.md`). This
package applies them to the verdicts: `quotes.py` is the machine quote check RULES.md demands,
`decide.py` the decision rule, the keep sample and the reversal input, `run.py` the command line.
Nothing here calls a model, and nothing writes to production.
"""
