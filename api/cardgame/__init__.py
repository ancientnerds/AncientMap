"""Ancient Nerds Card Game — self-contained package.

Phases:
  A: Deck synergies (category, regional, temporal, cross-combo)
  B: Snap / stake-raising mechanic
  C: Daily quiz mode
  D: PvE expedition campaigns
  E: Card evolution (star levels from duplicates)
"""

from api.cardgame.discord_commands import register_commands

__all__ = ["register_commands"]
