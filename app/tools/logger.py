import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings


def setup_logger() -> None:
    logger.remove()

    log_level = settings.log_level.upper() if hasattr(settings, 'log_level') else "INFO"

    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{module}</cyan> | {message}",
        level=log_level,
        colorize=True,
    )

    log_dir = settings.project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "qed_tracker_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {module}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
    )

    logger.info(f"Logger initialized: level={log_level}, dir={log_dir}")
