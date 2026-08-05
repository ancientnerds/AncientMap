# Vulture whitelist — names that look unused but are intentional API surface.
# CI runs: vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
# Every entry needs a reason. Prefer deleting dead code over whitelisting.

# LLMBackend Protocol parameter (api/services/lyra_backends.py): part of the
# backend interface; individual backends may ignore it.
_.enable_thinking

# thinking_for_effort keeps `effort` for signature compatibility at all call
# sites — M3 QUALITY-MAX decision 2026-06-17: every call reasons, effort no
# longer gates thinking (pipeline/lyra/config.py).
_.effort
