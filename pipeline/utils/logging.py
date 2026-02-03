"""
Logging configuration for the data pipeline.

Uses loguru for beautiful, structured logging.
"""

import sys
from pathlib import Path

from loguru import logger

from pipeline.config import settings


def setup_logging(
    level: str | None = None,
    log_file: Path | None = None,
    rotation: str = "10 MB",
    retention: str = "1 week",
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logging to file
        rotation: Log rotation setting (e.g., "10 MB", "1 day")
        retention: Log retention setting (e.g., "1 week", "10 files")
    """
    level = level or settings.pipeline.log_level

    # Remove default handler
    logger.remove()

    # Add console handler with colored output
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # Add file handler if specified
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=rotation,
            retention=retention,
            compression="gz",
        )

    logger.info(f"Logging configured: level={level}")


# Only configure logging if not explicitly disabled
import os

if os.environ.get("DISABLE_LOGGING") != "1":
    setup_logging()
