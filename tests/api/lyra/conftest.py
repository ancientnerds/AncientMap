# SPDX-License-Identifier: AGPL-3.0-only
"""Conftest for Lyra tests — mock heavy dependencies to avoid import failures."""

import os
import sys
from unittest.mock import MagicMock

# Set test environment before anything
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Mock heavy dependencies that aren't needed for unit tests
# discord is only used by cardgame discord_commands — not relevant to Lyra tests
for mod_name in [
    "discord",
    "discord.ext",
    "discord.ext.commands",
    "discord.app_commands",
    "discord.ui",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
