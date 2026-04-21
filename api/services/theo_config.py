"""Configuration for Theodore Furcade — async archaeological research agent."""

from __future__ import annotations

import os

THEO_PARALLEL_SLOTS = 1

# Discord role ID that grants access to Theo Research Lab.
# Set THEO_RESEARCHER_ROLE_ID in .env to the role ID.
# If left empty, the researcher gate is disabled (403 for all users).
THEO_RESEARCHER_ROLE_ID = os.getenv("THEO_RESEARCHER_ROLE_ID", "")
RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 1

# Flat credit cost for a V2 convergence research run.
# Reserved up-front on submit, deducted on success, released on failure/cancel.
THEO_RESEARCH_COST = 600
