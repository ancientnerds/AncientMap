# SPDX-License-Identifier: AGPL-3.0-only
"""Conftest for Lyra tests."""

import os

# Set test environment before anything
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# discord.py is not stubbed here. Until 2026-09-26 this file put a MagicMock under
# sys.modules["discord"] whenever discord was not imported yet - and pytest collects this
# package before the test modules beside it, so every test in the suite ran the Discord
# bot and the card game's views against a mock, whatever they asserted. discord.py is a
# declared dependency (requirements-api.txt, which CI's test job installs).
