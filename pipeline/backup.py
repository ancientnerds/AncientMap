"""
Backup utilities for AncientMap database operations.
Automatically creates backups before destructive operations.
"""
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger


@dataclass
class BackupResult:
    success: bool
    backup_id: str
    database_path: Path | None = None
    contributions_path: Path | None = None
    error: str | None = None

# VPS paths
BACKUP_DIR = Path("/var/www/ancientnerds/backups")
DATA_DIR = Path("/var/www/ancientnerds.com/data")

# Fallback for local development
if not BACKUP_DIR.parent.exists():
    BACKUP_DIR = Path("backups/production")
    DATA_DIR = Path("data")


def create_backup(include_db: bool = True, include_contributions: bool = True) -> BackupResult:
    """Create backup of database and/or contributions before destructive ops.

    Args:
        include_db: Whether to backup the PostgreSQL database
        include_contributions: Whether to backup contributions.json

    Returns:
        BackupResult with paths to created backups and success status
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    result = BackupResult(success=True, backup_id=timestamp)

    # Backup contributions.json
    if include_contributions:
        contrib_src = DATA_DIR / "contributions.json"
        if contrib_src.exists():
            contrib_dst = BACKUP_DIR / f"contributions_{timestamp}.json"
            contrib_dst.write_text(contrib_src.read_text(encoding="utf-8"), encoding="utf-8")
            result.contributions_path = contrib_dst
            logger.info(f"Backed up contributions.json -> {contrib_dst}")
        else:
            logger.info("No contributions.json found (OK if new install)")

    # Backup database via pg_dump
    if include_db:
        db_dst = BACKUP_DIR / f"database_{timestamp}.dump"
        try:
            env = os.environ.copy()
            env["PGPASSWORD"] = os.environ.get("POSTGRES_PASSWORD", "")
            with open(db_dst, "wb") as f:
                subprocess.run(
                    ["pg_dump", "-U", "ancient_map", "-h", "localhost", "-p", "5432", "-Fc", "ancient_map"],
                    stdout=f,
                    env=env,
                    check=True
                )
            result.database_path = db_dst
            logger.info(f"Backed up database -> {db_dst}")
        except FileNotFoundError:
            # pg_dump not available (local development without PostgreSQL)
            logger.warning("pg_dump not found - skipping database backup (OK for local dev)")
        except subprocess.CalledProcessError as e:
            result.success = False
            result.error = f"pg_dump failed: {e}"
            logger.error(result.error)

    return result


def list_backups() -> list[tuple[str, dict[str, Path]]]:
    """List available backups.

    Returns:
        List of tuples (timestamp, {type: path}) sorted by timestamp descending
    """
    if not BACKUP_DIR.exists():
        return []

    backups: dict[str, dict[str, Path]] = {}

    # Find database backups
    for f in BACKUP_DIR.glob("database_*.dump"):
        ts = f.stem.replace("database_", "")
        backups.setdefault(ts, {})["database"] = f

    # Find contributions backups
    for f in BACKUP_DIR.glob("contributions_*.json"):
        ts = f.stem.replace("contributions_", "")
        backups.setdefault(ts, {})["contributions"] = f

    return sorted(backups.items(), reverse=True)


def restore_backup(timestamp: str, restore_db: bool = True, restore_contributions: bool = True) -> bool:
    """Restore from a specific backup.

    Args:
        timestamp: Backup timestamp (e.g., "20260126_143022")
        restore_db: Whether to restore database
        restore_contributions: Whether to restore contributions.json

    Returns:
        True if restore succeeded
    """
    success = True

    # Restore contributions.json
    if restore_contributions:
        contrib_src = BACKUP_DIR / f"contributions_{timestamp}.json"
        if contrib_src.exists():
            contrib_dst = DATA_DIR / "contributions.json"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            contrib_dst.write_text(contrib_src.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info(f"Restored contributions.json from {contrib_src}")
        else:
            logger.warning(f"No contributions backup found for {timestamp}")

    # Restore database
    if restore_db:
        db_src = BACKUP_DIR / f"database_{timestamp}.dump"
        if db_src.exists():
            try:
                env = os.environ.copy()
                env["PGPASSWORD"] = os.environ.get("POSTGRES_PASSWORD", "")
                subprocess.run(
                    ["pg_restore", "-U", "ancient_map", "-h", "localhost", "-p", "5432", "-d", "ancient_map", "-c", str(db_src)],
                    env=env,
                    check=True
                )
                logger.info(f"Restored database from {db_src}")
            except FileNotFoundError:
                logger.warning("pg_restore not found - skipping database restore")
            except subprocess.CalledProcessError as e:
                logger.error(f"Database restore failed: {e}")
                success = False
        else:
            logger.warning(f"No database backup found for {timestamp}")

    return success


def cleanup_old_backups(keep_count: int = 10):
    """Remove old backups, keeping the most recent ones.

    Args:
        keep_count: Number of backups to keep
    """
    if not BACKUP_DIR.exists():
        return

    # Cleanup database backups
    db_files = sorted(BACKUP_DIR.glob("database_*.dump"), reverse=True)
    for f in db_files[keep_count:]:
        f.unlink()
        logger.info(f"Removed old backup: {f}")

    # Cleanup contributions backups
    contrib_files = sorted(BACKUP_DIR.glob("contributions_*.json"), reverse=True)
    for f in contrib_files[keep_count:]:
        f.unlink()
        logger.info(f"Removed old backup: {f}")
