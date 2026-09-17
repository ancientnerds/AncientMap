# SPDX-License-Identifier: AGPL-3.0-only
"""Outbound notifications for the API — the implementation lives in
pipeline/utils/notify.py so the Lyra container (which has no `api` tree)
can use the same sender. One implementation, two import paths."""

from pipeline.utils.notify import send_discord_webhook

__all__ = ["send_discord_webhook"]
