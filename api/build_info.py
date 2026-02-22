"""Shared build metadata — imported by main.py and public_v1.py."""

import os
import subprocess


def _get_build_hash() -> str:
    """Get build hash from env var or git."""
    env_hash = os.environ.get("BUILD_HASH")
    if env_hash:
        return env_hash
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


BUILD_HASH = _get_build_hash()
