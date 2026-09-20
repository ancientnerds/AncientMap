"""Mechanical country repairs: the `unified_sites.country` values a script can settle.

`plan.py` decides and emits the plan (plus the rollback); `apply.py` renders the one
transaction, rehearses it against production and runs the read-back. See `plan.py`'s
docstring for what makes a row settlable and what makes it a refusal.
"""
