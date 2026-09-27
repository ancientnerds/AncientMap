"""The studio_episodes ledger (migration 0026): rows, validation and the two writes.

Standard library + SQLAlchemy at module level (plus pipeline.studio.config, itself standard
library only): this module runs inside the API container (through ledger_cli) and must not pull
in anything the image lacks. The id patterns are the studio's one definitions (config's
REQUEST_ID_RE and SHA256_RE; stream A's theo_publishing.YOUTUBE_ID_RE, imported inside
publish_params, where the API image has it). The vocabulary and the published/withdrawn
invariants are CHECK constraints of the migration; a violation raises from the database.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.studio.config import REQUEST_ID_RE, SHA256_RE

STATUSES = ("rendered", "published", "withdrawn")
TOPIC_TYPES = ("A", "B", "C", "D")
ROW_KEYS = frozenset(
    {
        "slug",
        "paper_request_id",
        "topic_type",
        "casefile_sha256",
        "script_sha256",
        "voice_id",
        "pipeline_commit",
        "video_sha256",
        "duration_s",
        "rendered_at",
        "renderer",
    }
)


class LedgerError(ValueError):
    """A ledger payload or write that cannot be accepted."""


@dataclass(frozen=True)
class LedgerRow:
    slug: str
    paper_request_id: str | None
    topic_type: str
    casefile_sha256: str
    script_sha256: str
    voice_id: str
    pipeline_commit: str
    video_sha256: str
    duration_s: float
    rendered_at: datetime
    renderer: str


def _aware(value: Any, what: str) -> datetime:
    if not isinstance(value, str):
        raise LedgerError(f"{what} must be an ISO 8601 string")
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise LedgerError(f"{what} must carry a timezone")
    return stamp


def row_from_json(data: Any) -> LedgerRow:
    if not isinstance(data, dict) or set(data) != ROW_KEYS:
        raise LedgerError(f"row keys must be exactly {sorted(ROW_KEYS)}")
    for key in ("casefile_sha256", "script_sha256", "video_sha256"):
        if not isinstance(data[key], str) or not SHA256_RE.fullmatch(data[key]):
            raise LedgerError(f"{key} is not a sha256")
    pid = data["paper_request_id"]
    if pid is not None and (not isinstance(pid, str) or not REQUEST_ID_RE.fullmatch(pid)):
        raise LedgerError("paper_request_id must be a request uuid or null")
    if data["topic_type"] not in TOPIC_TYPES:
        raise LedgerError(f"topic_type must be one of {list(TOPIC_TYPES)}")
    for key in ("slug", "voice_id", "pipeline_commit"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise LedgerError(f"{key} must be a non-empty string")
    duration = data["duration_s"]
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        raise LedgerError("duration_s must be a positive number")
    if not isinstance(data["renderer"], str) or "NVIDIA" not in data["renderer"]:
        raise LedgerError("renderer must name the NVIDIA GPU")
    return LedgerRow(**{**data, "rendered_at": _aware(data["rendered_at"], "rendered_at")})


_INSERT = text("""
    INSERT INTO studio_episodes (
        slug, paper_request_id, topic_type, casefile_sha256, script_sha256, voice_id,
        pipeline_commit, video_sha256, duration_s, rendered_at, renderer
    ) VALUES (
        :slug, CAST(:paper_request_id AS uuid), :topic_type, :casefile_sha256, :script_sha256,
        :voice_id, :pipeline_commit, :video_sha256, :duration_s, :rendered_at, :renderer
    )
    ON CONFLICT (video_sha256) DO NOTHING
""")

_PUBLISH = text("""
    UPDATE studio_episodes
       SET status = 'published', youtube_id = :youtube_id, published_at = :published_at
     WHERE video_sha256 = :video_sha256 AND status = 'rendered'
""")

_COUNT = text("SELECT COUNT(*) FROM studio_episodes WHERE video_sha256 = :video_sha256")
_PUBLISHED = text(
    "SELECT COUNT(*) FROM studio_episodes WHERE video_sha256 = :video_sha256 "
    "AND status = 'published' AND youtube_id = :youtube_id"
)


def record(session: Session, row: LedgerRow) -> bool:
    """Insert the row; False when this exact file is already in the ledger."""
    return session.execute(_INSERT, asdict(row)).rowcount == 1


def publish_params(data: Any) -> dict[str, Any]:
    from pipeline.lyra.theo_publishing import YOUTUBE_ID_RE

    if not isinstance(data, dict) or set(data) != {"video_sha256", "youtube_id", "published_at"}:
        raise LedgerError("publish payload must be {video_sha256, youtube_id, published_at}")
    if not isinstance(data["video_sha256"], str) or not SHA256_RE.fullmatch(data["video_sha256"]):
        raise LedgerError("video_sha256 is not a sha256")
    if not isinstance(data["youtube_id"], str) or not YOUTUBE_ID_RE.fullmatch(data["youtube_id"]):
        raise LedgerError("youtube_id is not a YouTube video id")
    return {**data, "published_at": _aware(data["published_at"], "published_at")}


def publish(session: Session, params: dict[str, Any]) -> None:
    """Mark a rendered row published; exactly one row must change."""
    changed = session.execute(_PUBLISH, params).rowcount
    if changed != 1:
        raise LedgerError(
            f"{changed} rows changed: no 'rendered' row with video_sha256 {params['video_sha256']}"
        )


def visible_after_commit(session: Session, *, video_sha256: str, youtube_id: str | None) -> bool:
    """Re-read in a fresh session: the write is only done when it can be read back."""
    if youtube_id is None:
        return session.execute(_COUNT, {"video_sha256": video_sha256}).scalar() == 1
    params = {"video_sha256": video_sha256, "youtube_id": youtube_id}
    return session.execute(_PUBLISHED, params).scalar() == 1
