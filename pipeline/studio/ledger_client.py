"""The local side of the ledger: send a row or a publish to ledger_cli over ssh."""

from __future__ import annotations

import json
from typing import Any

from pipeline.studio import remote
from pipeline.studio.errors import StudioError

MODULE = "pipeline.studio.ledger_cli"
TIMEOUT_S = 120


def _send(flag: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = remote.run_module(
        MODULE, [flag], stdin=json.dumps(payload).encode("utf-8"), timeout=TIMEOUT_S
    )
    try:
        out = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise remote.RemoteError(
            f"ledger_cli {flag} printed no JSON (exit {result.returncode}): {result.stderr[-800:]}"
        ) from exc
    if result.returncode != 0 or not out.get("ok"):
        raise StudioError(f"ledger_cli {flag} refused: {out.get('error', out)}")
    return out


def record_remote(row: dict[str, Any]) -> dict[str, Any]:
    return _send("--record", row)


def publish_remote(video_sha256: str, youtube_id: str, published_at: str) -> dict[str, Any]:
    return _send(
        "--publish",
        {"video_sha256": video_sha256, "youtube_id": youtube_id, "published_at": published_at},
    )
